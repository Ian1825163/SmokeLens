#!/usr/bin/env python3
"""Clean labeled SmokeLens readings and merge new samples into datapool.csv."""

from __future__ import annotations

import argparse
import csv
import math
import os
import tempfile
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

POOL_COLUMNS = [
    "id",
    "node_id",
    "timestamp",
    "mode",
    "collection_label",
    "trial_state",
    "inference_class",
    "cigarette_detected",
    "inference_score",
    "model_version",
    "voc_raw",
    "co_raw",
    "voc_mv",
    "co_mv",
    "pm1_0",
    "pm2_5",
    "pm10",
    "temperature",
    "humidity",
    "pms_valid",
    "classification",
    "raw_payload",
    "received_at",
    "created_at",
]

# Newer backend rows contain event_marker even when an older CSV header does not.
EVENT_MARKER_COLUMNS = POOL_COLUMNS[:7] + ["event_marker"] + POOL_COLUMNS[7:]

CLASS_LABELS = {
    "normal_air",
    "cooking_fume",
    "vehicle_exhaust",
    "cigarette_smoke",
}
FEATURE_COLUMNS = [
    "voc_mv",
    "co_mv",
    "pm1_0",
    "pm2_5",
    "pm10",
    "temperature",
    "humidity",
]
IDENTITY_NUMBER_COLUMNS = ["timestamp", "voc_raw", "co_raw", *FEATURE_COLUMNS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge new, valid data_collection readings from smokelens.csv "
            "into datapool.csv without adding the same sample twice."
        )
    )
    parser.add_argument(
        "--source",
        default=REPO_ROOT / "data" / "smokelens.csv",
        type=Path,
        help="CSV receiving new backend readings.",
    )
    parser.add_argument(
        "--pool",
        default=REPO_ROOT / "data" / "datapool.csv",
        type=Path,
        help="CSV data pool to update.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be added without changing the data pool.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[dict[str, str]], Counter[str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    rows = []
    stats: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"CSV file is empty: {path}")
        if header != POOL_COLUMNS and header != EVENT_MARKER_COLUMNS:
            raise ValueError(f"Unsupported CSV header in {path}")

        for values in reader:
            if not values or not any(values):
                stats["blank"] += 1
                continue
            if len(values) == len(POOL_COLUMNS):
                columns = POOL_COLUMNS
            elif len(values) == len(EVENT_MARKER_COLUMNS):
                columns = EVENT_MARKER_COLUMNS
                stats["event_marker_schema"] += 1
            else:
                stats["malformed"] += 1
                continue
            rows.append(dict(zip(columns, values)))
    return rows, stats


def normalized_number(value: object) -> str | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return format(number, ".15g")


def is_true(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def rejection_reason(row: dict[str, str]) -> str | None:
    if row.get("mode") != "data_collection":
        return "not_data_collection"
    if row.get("collection_label") not in CLASS_LABELS:
        return "invalid_label"
    if not is_true(row.get("pms_valid")):
        return "invalid_pms"
    if any(normalized_number(row.get(column)) is None for column in FEATURE_COLUMNS):
        return "missing_feature"
    if normalized_number(row.get("timestamp")) is None:
        return "invalid_timestamp"
    return None


def sample_key(row: dict[str, str]) -> tuple[str, ...]:
    numbers = tuple(normalized_number(row.get(column)) or "" for column in IDENTITY_NUMBER_COLUMNS)
    return (
        (row.get("node_id") or "").strip(),
        (row.get("mode") or "").strip(),
        (row.get("collection_label") or "").strip(),
        (row.get("trial_state") or "").strip().lower(),
        *numbers,
    )


def canonical_row(row: dict[str, str], row_id: int) -> dict[str, str]:
    output = {column: row.get(column, "") for column in POOL_COLUMNS}
    output["id"] = str(row_id)
    return output


def next_row_id(rows: list[dict[str, str]]) -> int:
    ids = []
    for row in rows:
        try:
            ids.append(int(float(row.get("id") or 0)))
        except ValueError:
            continue
    return max(ids, default=0) + 1


def write_pool(path: Path, existing: list[dict[str, str]], additions: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=POOL_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(
                {column: row.get(column, "") for column in POOL_COLUMNS}
                for row in existing
            )
            writer.writerows(additions)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    args = parse_args()
    pool_rows, pool_read_stats = read_rows(args.pool)
    source_rows, source_read_stats = read_rows(args.source)

    pool_keys = {
        sample_key(row)
        for row in pool_rows
        if rejection_reason(row) is None
    }
    seen_keys = set(pool_keys)
    rejected: Counter[str] = Counter()
    duplicate_existing = 0
    duplicate_source = 0
    additions = []
    added_by_class: Counter[str] = Counter()
    row_id = next_row_id(pool_rows)

    for row in source_rows:
        reason = rejection_reason(row)
        if reason is not None:
            rejected[reason] += 1
            continue

        key = sample_key(row)
        if key in pool_keys:
            duplicate_existing += 1
            continue
        if key in seen_keys:
            duplicate_source += 1
            continue

        seen_keys.add(key)
        additions.append(canonical_row(row, row_id))
        added_by_class[row["collection_label"]] += 1
        row_id += 1

    action = "Would add" if args.dry_run else "Added"
    print(f"source: {args.source}")
    print(f"pool: {args.pool}")
    print(f"source rows: {len(source_rows)}")
    print(f"already in pool: {duplicate_existing}")
    print(f"duplicate within source: {duplicate_source}")
    for label in sorted(CLASS_LABELS):
        print(f"{label}: {added_by_class[label]}")
    print(f"{action}: {len(additions)}")

    combined_stats = pool_read_stats + source_read_stats
    if combined_stats:
        details = ", ".join(
            f"{name}={count}" for name, count in sorted(combined_stats.items())
        )
        print(f"CSV cleanup: {details}")
    if rejected:
        details = ", ".join(
            f"{name}={count}" for name, count in sorted(rejected.items())
        )
        print(f"Skipped source rows: {details}")

    if not args.dry_run and additions:
        write_pool(args.pool, pool_rows, additions)


if __name__ == "__main__":
    main()
