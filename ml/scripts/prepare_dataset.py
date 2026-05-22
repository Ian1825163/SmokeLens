#!/usr/bin/env python3
"""Prepare SmokeLens train/test CSV files from SQLite readings."""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3
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

INDEX_TO_LABEL = {
    0: "normal",
    1: "cooking_oil",
    2: "car_exhaust",
    3: "smoke_smell",
}

OUTPUT_COLUMNS = FEATURE_COLUMNS + ["label_index", "label"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare SmokeLens train/test datasets from SQLite."
    )
    parser.add_argument(
        "--db",
        default=REPO_ROOT / "data" / "smokelens.sqlite",
        type=Path,
        help="Path to SmokeLens SQLite database.",
    )
    parser.add_argument(
        "--out-dir",
        default=REPO_ROOT / "ml" / "datasets",
        type=Path,
        help="Directory for generated train/test CSV files.",
    )
    parser.add_argument(
        "--test-size",
        default=0.2,
        type=float,
        help="Fraction of rows per class to reserve for testing.",
    )
    parser.add_argument("--seed", default=42, type=int, help="Random seed.")
    return parser.parse_args()


def normalize_classification(value: object) -> tuple[str, int] | None:
    if value is None:
        return None
    try:
        label_index = int(value)
    except (TypeError, ValueError):
        return None
    label = INDEX_TO_LABEL.get(label_index)
    if label is None:
        return None
    return label, label_index


def row_is_complete(row: sqlite3.Row) -> bool:
    return all(row[column] is not None for column in FEATURE_COLUMNS)


def load_rows(db_path: Path) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    query = f"""
        SELECT {", ".join(FEATURE_COLUMNS)}, pms_valid, classification
        FROM readings
        WHERE pms_valid = 1
    """

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = []
        for row in connection.execute(query):
            classification = normalize_classification(row["classification"])
            if classification is None or not row_is_complete(row):
                continue

            label, label_index = classification
            output_row = {column: row[column] for column in FEATURE_COLUMNS}
            output_row["label"] = label
            output_row["label_index"] = label_index
            rows.append(output_row)

    return rows


def stratified_split(
    rows: list[dict[str, object]], test_size: float, seed: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not 0.0 < test_size < 1.0:
        raise ValueError("--test-size must be between 0 and 1")

    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(row)

    train_rows = []
    test_rows = []

    for label, label_rows in sorted(grouped.items()):
        rng.shuffle(label_rows)
        test_count = max(1, round(len(label_rows) * test_size))
        if len(label_rows) <= 1:
            test_count = 0

        test_rows.extend(label_rows[:test_count])
        train_rows.extend(label_rows[test_count:])

    rng.shuffle(train_rows)
    rng.shuffle(test_rows)
    return train_rows, test_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def print_counts(name: str, rows: list[dict[str, object]]) -> None:
    counts = Counter(str(row["label"]) for row in rows)
    summary = ", ".join(f"{label}={counts[label]}" for label in sorted(counts))
    print(f"{name}: {len(rows)} rows ({summary or 'no labels'})")


def main() -> None:
    args = parse_args()
    rows = load_rows(args.db)
    if not rows:
        raise SystemExit(
            "No usable labeled rows found. Set readings.classification to an "
            "integer class: 0=normal, 1=cooking_oil, 2=car_exhaust, "
            "3=smoke_smell."
        )

    train_rows, test_rows = stratified_split(rows, args.test_size, args.seed)
    write_csv(args.out_dir / "train.csv", train_rows)
    write_csv(args.out_dir / "test.csv", test_rows)

    print_counts("all", rows)
    print_counts("train", train_rows)
    print_counts("test", test_rows)
    print(f"Wrote {args.out_dir / 'train.csv'}")
    print(f"Wrote {args.out_dir / 'test.csv'}")


if __name__ == "__main__":
    main()
