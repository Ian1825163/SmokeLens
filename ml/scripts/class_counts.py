#!/usr/bin/env python3
"""Print per-class row counts from SmokeLens SQLite readings."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASS_LABELS = [
    "normal_air",
    "cooking_fume",
    "vehicle_exhaust",
    "cigarette_smoke",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print SmokeLens data_collection row counts for the 4 labels."
    )
    parser.add_argument(
        "--db",
        default=REPO_ROOT / "data" / "smokelens.sqlite",
        type=Path,
        help="Path to SmokeLens SQLite database.",
    )
    return parser.parse_args()


def load_counts(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    query = """
        SELECT collection_label, COUNT(*) AS row_count
        FROM readings
        WHERE mode = 'data_collection'
          AND collection_label IN (?, ?, ?, ?)
        GROUP BY collection_label
    """

    counts = {label: 0 for label in CLASS_LABELS}
    with sqlite3.connect(db_path) as connection:
        for label, row_count in connection.execute(query, CLASS_LABELS):
            counts[str(label)] = int(row_count)
    return counts


def main() -> None:
    args = parse_args()
    counts = load_counts(args.db)
    total = 0
    for label in CLASS_LABELS:
        row_count = counts[label]
        total += row_count
        print(f"{label}: {row_count}")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
