#!/usr/bin/env python3
"""Build chronological train/validation/test datasets from datapool.csv."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FEATURE_COLUMNS = [
    "voc_mv",
    "co_mv",
    "pm1_0",
    "pm2_5",
    "pm10",
    "temperature",
    "humidity",
]

LABEL_TO_INDEX = {
    "normal_air": 0,
    "cooking_fume": 1,
    "vehicle_exhaust": 2,
    "cigarette_smoke": 3,
}

LEGACY_LABEL_ALIASES = {
    "normal": "normal_air",
    "cooking_oil": "cooking_fume",
    "car_exhaust": "vehicle_exhaust",
    "smoke_smell": "cigarette_smoke",
    "0": "normal_air",
    "1": "cooking_fume",
    "2": "vehicle_exhaust",
    "3": "cigarette_smoke",
}

OUTPUT_COLUMNS = ["node_id", "timestamp"] + FEATURE_COLUMNS + ["label_index", "label"]
EXPOSURE_STATES = {"", "exposure"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Use every valid row and split each class into chronological "
            "train, validation, and test intervals."
        )
    )
    parser.add_argument(
        "--csv",
        default=REPO_ROOT / "data" / "datapool.csv",
        type=Path,
        help="Path to the data pool CSV file.",
    )
    parser.add_argument(
        "--out-dir",
        default=REPO_ROOT / "ml" / "datasets",
        type=Path,
        help=(
            "Root directory for timestamped dataset folders. Each run writes "
            "to YYMMDD_HHMMSS under this directory."
        ),
    )
    parser.add_argument("--train-ratio", default=0.80, type=float)
    parser.add_argument("--validation-ratio", default=0.10, type=float)
    return parser.parse_args()


def normalize_label(value: object) -> tuple[str, int] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    label = LEGACY_LABEL_ALIASES.get(text, text)
    label_index = LABEL_TO_INDEX.get(label)
    return (label, label_index) if label_index is not None else None


def is_true(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def load_rows(csv_path: Path) -> list[dict[str, object]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        for source_index, row in enumerate(csv.DictReader(file)):
            trial_state = (row.get("trial_state") or "").strip().lower()
            if (
                row.get("mode") != "data_collection"
                or trial_state not in EXPOSURE_STATES
                or not is_true(row.get("pms_valid"))
            ):
                continue

            normalized_label = normalize_label(row.get("collection_label"))
            if normalized_label is None:
                continue
            try:
                features = {
                    column: float(row[column]) for column in FEATURE_COLUMNS
                }
                timestamp = int(float(row["timestamp"]))
                received_at = int(float(row.get("received_at") or 0))
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in features.values()):
                continue

            label, label_index = normalized_label
            rows.append(
                {
                    "node_id": (row.get("node_id") or "").strip(),
                    "timestamp": timestamp,
                    "_sort_timestamp": (
                        timestamp
                        if timestamp >= 1_000_000_000
                        else received_at // 1000
                    ),
                    **features,
                    "label_index": label_index,
                    "label": label,
                    "_source_index": source_index,
                }
            )
    return rows


def validate_ratios(train_ratio: float, validation_ratio: float) -> None:
    if train_ratio <= 0 or validation_ratio <= 0:
        raise ValueError("train and validation ratios must be positive")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio + validation_ratio must be less than 1")


def feature_key(row: dict[str, object]) -> tuple[float, ...]:
    return tuple(float(row[column]) for column in FEATURE_COLUMNS)


def remove_conflicting_rows(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    labels_by_features: dict[tuple[float, ...], set[str]] = defaultdict(set)
    for row in rows:
        labels_by_features[feature_key(row)].add(str(row["label"]))
    conflicting_features = {
        key for key, labels in labels_by_features.items() if len(labels) > 1
    }

    filtered = [row for row in rows if feature_key(row) not in conflicting_features]
    return filtered, len(rows) - len(filtered)


def group_duplicate_features(
    rows: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    grouped: dict[tuple[str, tuple[float, ...]], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["label"]), feature_key(row))].append(row)

    groups = []
    for group in grouped.values():
        group.sort(
            key=lambda row: (
                int(row["_sort_timestamp"]),
                str(row["node_id"]),
                int(row["_source_index"]),
            )
        )
        groups.append(group)
    groups.sort(
        key=lambda group: (
            int(group[0]["_sort_timestamp"]),
            str(group[0]["node_id"]),
            int(group[0]["_source_index"]),
        )
    )
    return groups


def closest_group_boundary(
    groups: list[list[dict[str, object]]], target_rows: float, minimum: int, maximum: int
) -> int:
    cumulative = 0
    best_index = minimum
    best_distance = float("inf")
    for index, group in enumerate(groups, start=1):
        cumulative += len(group)
        if index < minimum or index > maximum:
            continue
        distance = abs(cumulative - target_rows)
        if distance < best_distance:
            best_index = index
            best_distance = distance
    return best_index


def split_class_interval(
    rows: list[dict[str, object]], train_ratio: float, validation_ratio: float
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    groups = group_duplicate_features(rows)
    if len(groups) < 3:
        raise ValueError("Each class needs at least three distinct feature groups")

    train_end = closest_group_boundary(
        groups,
        len(rows) * train_ratio,
        minimum=1,
        maximum=len(groups) - 2,
    )
    validation_end = closest_group_boundary(
        groups,
        len(rows) * (train_ratio + validation_ratio),
        minimum=train_end + 1,
        maximum=len(groups) - 1,
    )

    return tuple(
        sorted(
            (row for group in group_slice for row in group),
            key=lambda row: (
                int(row["_sort_timestamp"]),
                str(row["node_id"]),
                int(row["_source_index"]),
            ),
        )
        for group_slice in (
            groups[:train_end],
            groups[train_end:validation_end],
            groups[validation_end:],
        )
    )


def split_by_chronological_intervals(
    rows: list[dict[str, object]], train_ratio: float, validation_ratio: float
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(row)

    missing_labels = [label for label in LABEL_TO_INDEX if not grouped[label]]
    if missing_labels:
        raise ValueError(f"Missing classes: {', '.join(missing_labels)}")

    splits = ([], [], [])
    for label in LABEL_TO_INDEX:
        label_splits = split_class_interval(
            grouped[label], train_ratio, validation_ratio
        )
        for destination, source in zip(splits, label_splits):
            destination.extend(source)
    return splits


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {column: row[column] for column in OUTPUT_COLUMNS} for row in rows
        )


def print_counts(name: str, rows: list[dict[str, object]]) -> None:
    counts = Counter(str(row["label"]) for row in rows)
    summary = ", ".join(f"{label}={counts[label]}" for label in LABEL_TO_INDEX)
    print(f"{name}: {len(rows)} rows ({summary})")


def timestamped_output_dir(root: Path) -> Path:
    return root / datetime.now().strftime("%y%m%d_%H%M%S")


def main() -> None:
    args = parse_args()
    output_dir = timestamped_output_dir(args.out_dir)
    validate_ratios(args.train_ratio, args.validation_ratio)
    loaded_rows = load_rows(args.csv)
    if not loaded_rows:
        raise SystemExit("No usable labeled rows found")
    rows, conflict_count = remove_conflicting_rows(loaded_rows)
    feature_group_count = len(group_duplicate_features(rows))
    duplicate_row_count = len(rows) - feature_group_count

    train_rows, validation_rows, test_rows = split_by_chronological_intervals(
        rows, args.train_ratio, args.validation_ratio
    )
    write_csv(output_dir / "train.csv", train_rows)
    write_csv(output_dir / "validation.csv", validation_rows)
    write_csv(output_dir / "test.csv", test_rows)

    print_counts("usable", loaded_rows)
    print(f"removed conflicting-label rows: {conflict_count}")
    print(f"retained same-label duplicate rows: {duplicate_row_count}")
    print(f"distinct label/feature groups: {feature_group_count}")
    print_counts("retained", rows)
    print_counts("train", train_rows)
    print_counts("validation", validation_rows)
    print_counts("test", test_rows)
    print(f"dataset directory: {output_dir}")
    print(f"Wrote {output_dir / 'train.csv'}")
    print(f"Wrote {output_dir / 'validation.csv'}")
    print(f"Wrote {output_dir / 'test.csv'}")


if __name__ == "__main__":
    main()
