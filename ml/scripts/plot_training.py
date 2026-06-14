#!/usr/bin/env python3
"""Plot median training curves and Q1-Q3 bands across random seeds."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from statistics import median


REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS = ["normal_air", "cooking_fume", "vehicle_exhaust", "cigarette_smoke"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        help=(
            "Run containing seed-* directories. Defaults to the latest valid "
            "directory in ml/runs."
        ),
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
    parser.add_argument(
        "--aggregate-run-dirs",
        nargs="+",
        type=Path,
        help=(
            "Aggregate every seed-* directory from these runs. The median is "
            "drawn as a line and the Q1-Q3 interval as a shaded band."
        ),
    )
    return parser.parse_args()


def latest_run_dir(runs_dir: Path) -> Path:
    run_dirs = sorted(
        path
        for path in runs_dir.iterdir()
        if path.is_dir() and find_seed_dirs([path], required=False)
    )
    if not run_dirs:
        raise FileNotFoundError(f"No training runs with seed-* folders under {runs_dir}")
    return run_dirs[-1]


def resolve_run_dirs(args: argparse.Namespace) -> list[Path]:
    if args.aggregate_run_dirs:
        return args.aggregate_run_dirs
    return [args.run_dir or latest_run_dir(REPO_ROOT / "ml" / "runs")]


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


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def load_seed_history(seed_dir: Path) -> tuple[dict[str, list[float | None]], int]:
    metadata_path = seed_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Seed metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return load_history(seed_dir / "training_history.csv"), int(metadata["best_epoch"])


def aggregate_histories(run_dirs: list[Path]) -> tuple[dict[str, list[float]], int]:
    seed_dirs = find_seed_dirs(run_dirs)
    seed_histories = [load_seed_history(seed_dir) for seed_dir in seed_dirs]
    max_epoch = max(best_epoch for _, best_epoch in seed_histories)
    columns = [
        "train_loss",
        "train_accuracy",
        "validation_loss",
        "validation_accuracy",
    ]
    aggregate = {"epoch": [float(epoch) for epoch in range(1, max_epoch + 1)]}
    for column in columns:
        aggregate[f"{column}_median"] = []
        aggregate[f"{column}_q1"] = []
        aggregate[f"{column}_q3"] = []

    for epoch in range(1, max_epoch + 1):
        for column in columns:
            values = []
            for history, best_epoch in seed_histories:
                selected_epoch = min(epoch, best_epoch)
                value = history[column][selected_epoch - 1]
                if value is None:
                    raise ValueError(
                        f"Missing {column} at epoch {selected_epoch}"
                    )
                values.append(float(value))
            aggregate[f"{column}_median"].append(median(values))
            aggregate[f"{column}_q1"].append(percentile(values, 0.25))
            aggregate[f"{column}_q3"].append(percentile(values, 0.75))
    return aggregate, len(seed_histories)


def find_seed_dirs(run_dirs: list[Path], required: bool = True) -> list[Path]:
    seed_dirs = sorted(
        seed_dir
        for run_dir in run_dirs
        for seed_dir in run_dir.glob("seed-*")
        if seed_dir.is_dir()
        and (seed_dir / "training_history.csv").is_file()
        and (seed_dir / "metadata.json").is_file()
    )
    if required and not seed_dirs:
        raise FileNotFoundError("No seed-* directories found in aggregate runs")
    return seed_dirs


def load_test_metrics(run_dirs: list[Path]) -> list[dict[str, object]]:
    metrics = []
    for seed_dir in find_seed_dirs(run_dirs):
        metadata_path = seed_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metrics.append(metadata["test_metrics"])
    return metrics


def metric_summary(values: list[float]) -> tuple[float, float, float]:
    return median(values), percentile(values, 0.25), percentile(values, 0.75)


def score_axis_lower_bound(summaries: list[tuple[float, float, float]]) -> float:
    minimum = min(item[1] for item in summaries)
    margin = max(0.001, (1.0 - minimum) * 0.25)
    return max(0.0, minimum - margin)


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


def plot_aggregate_metric(axis, aggregate, train_column, validation_column, ylabel):
    epochs = aggregate["epoch"]
    for column, label, color in (
        (train_column, "training median", "tab:blue"),
        (validation_column, "validation median", "tab:orange"),
    ):
        axis.plot(
            epochs,
            aggregate[f"{column}_median"],
            label=label,
            color=color,
            linewidth=2,
        )
        axis.fill_between(
            epochs,
            aggregate[f"{column}_q1"],
            aggregate[f"{column}_q3"],
            color=color,
            alpha=0.2,
            label=f"{label.removesuffix(' median')} middle 50%",
        )
    axis.set_ylabel(ylabel)
    axis.set_title(f"Training and Validation {ylabel}")
    axis.grid(True, alpha=0.3)
    axis.legend()


def save_aggregate_plot(plt, aggregate, seed_count, path, log_loss=False):
    figure, axes = plt.subplots(2, 1, figsize=(10.92, 7), sharex=True)
    plot_aggregate_metric(
        axes[0], aggregate, "train_loss", "validation_loss", "Loss"
    )
    if log_loss:
        axes[0].set_yscale("log")
        axes[0].set_ylabel("Loss (log scale)")
    plot_aggregate_metric(
        axes[1], aggregate, "train_accuracy", "validation_accuracy", "Accuracy"
    )
    axes[1].set_xlabel("Epoch")
    figure.suptitle(f"Median Across {seed_count} Seeds; Shading = Q1-Q3", fontsize=12)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def save_test_metrics_plot(plt, test_metrics, path):
    figure, axes = plt.subplots(2, 1, figsize=(10.92, 7))

    overall_names = ["accuracy", "balanced_accuracy", "macro_f1", "weighted_f1"]
    overall_labels = ["Accuracy", "Balanced\naccuracy", "Macro F1", "Weighted F1"]
    overall = [
        metric_summary([float(metrics[name]) for metrics in test_metrics])
        for name in overall_names
    ]
    x_positions = list(range(len(overall)))
    medians = [item[0] for item in overall]
    axes[0].errorbar(
        x_positions,
        medians,
        yerr=[
            [item[0] - item[1] for item in overall],
            [item[2] - item[0] for item in overall],
        ],
        fmt="o",
        capsize=6,
        linewidth=2,
        markersize=7,
    )
    axes[0].set_xticks(x_positions, overall_labels)
    axes[0].set_ylabel("Score")
    axes[0].set_title("Final Test Metrics: Median with Q1-Q3")
    axes[0].set_ylim(score_axis_lower_bound(overall), 1.0001)
    axes[0].grid(True, axis="y", alpha=0.3)

    class_positions = list(range(len(LABELS)))
    offsets = {"precision": -0.22, "recall": 0.0, "f1": 0.22}
    colors = {"precision": "tab:blue", "recall": "tab:orange", "f1": "tab:green"}
    class_summaries = []
    for metric_name in ("precision", "recall", "f1"):
        summaries = [
            metric_summary(
                [
                    float(metrics["per_class"][label][metric_name])
                    for metrics in test_metrics
                ]
            )
            for label in LABELS
        ]
        class_summaries.extend(summaries)
        positions = [position + offsets[metric_name] for position in class_positions]
        axes[1].errorbar(
            positions,
            [item[0] for item in summaries],
            yerr=[
                [item[0] - item[1] for item in summaries],
                [item[2] - item[0] for item in summaries],
            ],
            fmt="o",
            color=colors[metric_name],
            label=metric_name,
            capsize=5,
            linewidth=2,
            markersize=6,
        )
    axes[1].set_xticks(
        class_positions,
        [label.replace("_", "\n") for label in LABELS],
    )
    axes[1].set_ylabel("Score")
    axes[1].set_title("Per-Class Test Metrics: Median with Q1-Q3")
    axes[1].set_ylim(score_axis_lower_bound(class_summaries), 1.0001)
    axes[1].grid(True, axis="y", alpha=0.3)
    axes[1].legend()

    figure.suptitle(f"Final Test Results Across {len(test_metrics)} Seeds", fontsize=12)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    if args.history is not None:
        history_path = args.history
        out_dir = args.out_dir or history_path.parent
        run_dirs = None
    else:
        run_dirs = resolve_run_dirs(args)
        out_dir = args.out_dir or run_dirs[0]
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

    out_dir.mkdir(parents=True, exist_ok=True)
    if run_dirs is not None:
        aggregate, seed_count = aggregate_histories(run_dirs)
        output_path = out_dir / "training_curves_aggregate.png"
        save_aggregate_plot(plt, aggregate, seed_count, output_path)
        log_output_path = out_dir / "training_curves_aggregate_log_loss.png"
        save_aggregate_plot(
            plt, aggregate, seed_count, log_output_path, log_loss=True
        )
        test_output_path = out_dir / "test_metrics_summary.png"
        save_test_metrics_plot(
            plt, load_test_metrics(run_dirs), test_output_path
        )
        print("Run directories: " + ", ".join(str(path) for path in run_dirs))
        print(f"Aggregated {seed_count} seeds")
        print(f"Wrote {output_path}")
        print(f"Wrote {log_output_path}")
        print(f"Wrote {test_output_path}")
    else:
        history = load_history(history_path)
        output_path = out_dir / "training_curves.png"
        save_plot(plt, history, output_path)
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
