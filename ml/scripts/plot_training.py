#!/usr/bin/env python3
"""Plot SmokeLens training loss and accuracy from training_history.csv."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory to plot. Defaults to the latest directory in ml/runs.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        help="Training history CSV; overrides --run-dir.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for the PNG file. Defaults to the selected run directory.",
    )
    return parser.parse_args()


def latest_run_dir(runs_dir: Path) -> Path:
    run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    if not run_dirs:
        raise FileNotFoundError(f"No training runs found under {runs_dir}")
    return run_dirs[-1]


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.history is not None:
        history_path = args.history
    else:
        run_dir = args.run_dir or latest_run_dir(REPO_ROOT / "ml" / "runs")
        history_path = run_dir / "training_history.csv"
    return history_path, args.out_dir or history_path.parent


def optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def load_history(path: Path) -> dict[str, list[float | None]]:
    if not path.exists():
        raise FileNotFoundError(f"Training history not found: {path}")

    columns = {
        "epoch": [],
        "train_loss": [],
        "train_accuracy": [],
        "validation_loss": [],
        "validation_accuracy": [],
    }
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing history columns: {', '.join(sorted(missing))}")
        for row in reader:
            columns["epoch"].append(float(row["epoch"]))
            for name in columns.keys() - {"epoch"}:
                columns[name].append(optional_float(row[name]))

    if not columns["epoch"]:
        raise ValueError(f"Training history is empty: {path}")
    return columns


def valid_series(
    epochs: list[float | None], values: list[float | None]
) -> tuple[list[float], list[float]]:
    pairs = [
        (float(epoch), float(value))
        for epoch, value in zip(epochs, values)
        if epoch is not None and value is not None
    ]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def plot_metric(axis, history, train_column, validation_column, ylabel):
    train_epochs, train_values = valid_series(history["epoch"], history[train_column])
    axis.plot(train_epochs, train_values, label="training", linewidth=2)

    validation_epochs, validation_values = valid_series(
        history["epoch"], history[validation_column]
    )
    if validation_values:
        axis.plot(
            validation_epochs,
            validation_values,
            label="validation",
            linewidth=2,
        )

    axis.set_ylabel(ylabel)
    axis.set_title(f"Training and Validation {ylabel}")
    axis.grid(True, alpha=0.3)
    axis.legend()


def save_plot(plt, history, path):
    figure, axes = plt.subplots(2, 1, figsize=(10.92, 7), sharex=True)
    plot_metric(
        axes[0],
        history,
        "train_loss",
        "validation_loss",
        "Loss",
    )
    plot_metric(
        axes[1],
        history,
        "train_accuracy",
        "validation_accuracy",
        "Accuracy",
    )

    axes[1].set_xlabel("Epoch")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    history_path, out_dir = resolve_paths(args)
    cache_dir = Path(tempfile.gettempdir()) / "smokelens-matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as error:
        raise SystemExit(
            "Missing matplotlib. Install with: "
            "python3 -m pip install -r ml/requirements-ml.txt"
        ) from error

    history = load_history(history_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "training_curves.png"
    save_plot(plt, history, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
