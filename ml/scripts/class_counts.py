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
EXPOSURE_STATES = ["exposure"]


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


def has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column
        for row in connection.execute(f"PRAGMA table_info({table})")
    )


def load_counts(db_path: Path) -> tuple[dict[str, int], bool]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    counts = {label: 0 for label in CLASS_LABELS}
    with sqlite3.connect(db_path) as connection:
        has_trial_state = has_column(connection, "readings", "trial_state")
        exposure_placeholders = ", ".join("?" for _ in EXPOSURE_STATES)
        trial_state_filter = (
            "AND (trial_state IS NULL OR trim(trial_state) = '' "
            f"OR lower(trial_state) IN ({exposure_placeholders}))"
            if has_trial_state
            else ""
        )
        query = f"""
            SELECT collection_label, COUNT(*) AS row_count
            FROM readings
            WHERE mode = 'data_collection'
              AND collection_label IN (?, ?, ?, ?)
              {trial_state_filter}
            GROUP BY collection_label
        """
        params = (
            [*CLASS_LABELS, *EXPOSURE_STATES]
            if has_trial_state
            else CLASS_LABELS
        )
        for label, row_count in connection.execute(query, params):
            counts[str(label)] = int(row_count)
    return counts, has_trial_state


def main() -> None:
    args = parse_args()
    counts, has_trial_state = load_counts(args.db)
    if has_trial_state:
        print("filter: untagged rows plus trial_state=exposure")
    else:
        print("filter: no trial_state column; counting all data_collection rows")
    total = 0
    for label in CLASS_LABELS:
        row_count = counts[label]
        total += row_count
        print(f"{label}: {row_count}")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
