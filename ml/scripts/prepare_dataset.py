#!/usr/bin/env python3
"""Build balanced SmokeLens train/test datasets from data/datapool.csv."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
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

OUTPUT_COLUMNS = FEATURE_COLUMNS + ["label_index", "label"]
EXPOSURE_STATES = {"", "exposure"}
ROWS_TO_RESERVE_PER_CLASS = 21
OVERLAP_REPLACEMENT_LABELS = {
    "normal_air",
    "cooking_fume",
    "vehicle_exhaust",
    "cigarette_smoke",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Balance the four SmokeLens classes with evenly spaced sampling, "
            "then split every five rows into four training rows and one test row."
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
        help="Directory for generated train/test CSV files.",
    )
    return parser.parse_args()


def normalize_label(value: object) -> tuple[str, int] | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    label = LEGACY_LABEL_ALIASES.get(text, text)
    label_index = LABEL_TO_INDEX.get(label)
    if label_index is None:
        return None
    return label, label_index


def row_is_complete(row: dict[str, str]) -> bool:
    return all(str(row.get(column) or "").strip() for column in FEATURE_COLUMNS)


def is_true(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def load_rows(csv_path: Path) -> list[dict[str, object]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        rows = []
        for row in csv.DictReader(file):
            trial_state = (row.get("trial_state") or "").strip().lower()
            if (
                row.get("mode") != "data_collection"
                or trial_state not in EXPOSURE_STATES
                or not is_true(row.get("pms_valid"))
            ):
                continue
            label_source = row.get("collection_label")

            normalized_label = normalize_label(label_source)
            if normalized_label is None or not row_is_complete(row):
                continue

            label, label_index = normalized_label
            output_row = {column: float(row[column]) for column in FEATURE_COLUMNS}
            output_row["label"] = label
            output_row["label_index"] = label_index
            rows.append(output_row)

    return rows


def evenly_spaced_sample(
    rows: list[dict[str, object]], sample_count: int
) -> list[dict[str, object]]:
    if sample_count <= 0 or sample_count > len(rows):
        raise ValueError("sample_count must be between 1 and the row count")
    if sample_count == len(rows):
        return list(rows)
    if sample_count == 1:
        return [rows[0]]

    last_index = len(rows) - 1
    return [
        rows[round(index * last_index / (sample_count - 1))]
        for index in range(sample_count)
    ]


def balance_classes(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(row)

    missing_labels = [label for label in LABEL_TO_INDEX if not grouped[label]]
    if missing_labels:
        raise ValueError(f"Missing classes: {', '.join(missing_labels)}")

    minimum_class_count = min(len(grouped[label]) for label in LABEL_TO_INDEX)
    sample_count = minimum_class_count - ROWS_TO_RESERVE_PER_CLASS
    if sample_count <= 0:
        raise ValueError(
            "Not enough rows to reserve "
            f"{ROWS_TO_RESERVE_PER_CLASS} rows per class"
        )
    balanced_rows = []
    for label in LABEL_TO_INDEX:
        balanced_rows.extend(evenly_spaced_sample(grouped[label], sample_count))
    return balanced_rows, sample_count


def split_four_to_one(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(row)

    train_rows = []
    test_rows = []
    for label in LABEL_TO_INDEX:
        label_rows = grouped[label]
        if label == "vehicle_exhaust":
            feature_counts = Counter(feature_key(row) for row in label_rows)
            singleton_rows = [
                row for row in label_rows if feature_counts[feature_key(row)] == 1
            ]
            test_count = len(label_rows) // 5
            selected_test_rows = evenly_spaced_sample(singleton_rows, test_count)
            selected_test_ids = {id(row) for row in selected_test_rows}
            train_rows.extend(
                row for row in label_rows if id(row) not in selected_test_ids
            )
            test_rows.extend(selected_test_rows)
            continue

        for index, row in enumerate(label_rows):
            if index % 5 == 4:
                test_rows.append(row)
            else:
                train_rows.append(row)
    return train_rows, test_rows


def feature_key(row: dict[str, object]) -> tuple[object, ...]:
    return tuple(row[column] for column in FEATURE_COLUMNS)


def replace_test_overlaps(
    all_rows: list[dict[str, object]],
    train_rows: list[dict[str, object]],
    test_rows: list[dict[str, object]],
) -> dict[str, int]:
    replacements = {}

    for label in LABEL_TO_INDEX:
        if label not in OVERLAP_REPLACEMENT_LABELS:
            continue

        label_train = [row for row in train_rows if row["label"] == label]
        label_test_indexes = [
            index for index, row in enumerate(test_rows) if row["label"] == label
        ]
        train_features = {feature_key(row) for row in label_train}
        overlap_indexes = [
            index
            for index in label_test_indexes
            if feature_key(test_rows[index]) in train_features
        ]
        if not overlap_indexes:
            replacements[label] = 0
            continue

        selected_row_ids = {
            id(row)
            for row in train_rows + test_rows
            if row["label"] == label
        }
        retained_test_features = {
            feature_key(test_rows[index])
            for index in label_test_indexes
            if index not in overlap_indexes
        }

        candidates_by_feature = {}
        for row in all_rows:
            key = feature_key(row)
            if (
                row["label"] == label
                and id(row) not in selected_row_ids
                and key not in train_features
                and key not in retained_test_features
            ):
                candidates_by_feature.setdefault(key, row)

        candidates = list(candidates_by_feature.values())
        if len(candidates) < len(overlap_indexes):
            raise ValueError(
                f"Not enough unique {label} rows to replace "
                f"{len(overlap_indexes)} train/test overlaps; "
                f"only {len(candidates)} candidates are available"
            )

        replacement_rows = evenly_spaced_sample(candidates, len(overlap_indexes))
        for index, replacement in zip(overlap_indexes, replacement_rows):
            test_rows[index] = replacement
        replacements[label] = len(replacement_rows)

    return replacements


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=OUTPUT_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def print_counts(name: str, rows: list[dict[str, object]]) -> None:
    counts = Counter(str(row["label"]) for row in rows)
    summary = ", ".join(f"{label}={counts[label]}" for label in sorted(counts))
    print(f"{name}: {len(rows)} rows ({summary or 'no labels'})")


def main() -> None:
    args = parse_args()
    rows = load_rows(args.csv)
    if not rows:
        raise SystemExit(
            "No usable labeled rows found. Collect rows with "
            "mode=data_collection and collection_label in: normal_air, "
            "cooking_fume, vehicle_exhaust, cigarette_smoke."
        )

    balanced_rows, rows_per_class = balance_classes(rows)
    train_rows, test_rows = split_four_to_one(balanced_rows)
    replacements = replace_test_overlaps(rows, train_rows, test_rows)
    write_csv(args.out_dir / "train.csv", train_rows)
    write_csv(args.out_dir / "test.csv", test_rows)

    print_counts("usable", rows)
    print(f"balanced rows per class: {rows_per_class}")
    print_counts("balanced", balanced_rows)
    print_counts("train", train_rows)
    print_counts("test", test_rows)
    for label in sorted(replacements):
        print(f"replaced {label} test overlaps: {replacements[label]}")
    print(f"Wrote {args.out_dir / 'train.csv'}")
    print(f"Wrote {args.out_dir / 'test.csv'}")


if __name__ == "__main__":
    main()
