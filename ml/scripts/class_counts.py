#!/usr/bin/env python3
"""Print per-class row counts from the SmokeLens data pool."""

from __future__ import annotations

import argparse
import csv
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
        description="Print data_collection row counts from data/datapool.csv."
    )
    parser.add_argument(
        "--csv",
        default=REPO_ROOT / "data" / "datapool.csv",
        # default=REPO_ROOT / "data" / "smokelens.csv",
        type=Path,
        help="Path to the data pool CSV file.",
    )
    return parser.parse_args()

def load_counts(csv_path: Path) -> tuple[dict[str, int], bool]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    counts = {label: 0 for label in CLASS_LABELS}
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        has_trial_state = "trial_state" in (reader.fieldnames or [])
        for row in reader:
            label = (row.get("collection_label") or "").strip()
            trial_state = (row.get("trial_state") or "").strip().lower()
            if row.get("mode") != "data_collection" or label not in counts:
                continue
            if has_trial_state and trial_state and trial_state not in EXPOSURE_STATES:
                continue
            counts[label] += 1
    return counts, has_trial_state


def main() -> None:
    args = parse_args()
    counts, has_trial_state = load_counts(args.csv)
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
