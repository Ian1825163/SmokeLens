#!/usr/bin/env python3
"""Train and evaluate the SmokeLens MLP across multiple random seeds."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_ROOT = REPO_ROOT / "ml" / "datasets"
DATASET_FILENAMES = {
    "train": "train.csv",
    "validation": "validation.csv",
    "test": "test.csv",
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
LABELS = ["normal_air", "cooking_fume", "vehicle_exhaust", "cigarette_smoke"]

HYPERPARAMETERS = {
    "HIDDEN_LAYERS": (2,),
    "ACTIVATION": "relu",
    "LEARNING_RATE": 0.001,
    "L2_REGULARIZATION": 0.0001,
    "BATCH_SIZE": 200,
    "MAX_EPOCHS": 500,
    "EARLY_STOPPING_PATIENCE": 10,
    "MIN_IMPROVEMENT": 0.0001,
}
DEFAULT_SEEDS = (42, 43, 44, 45, 46)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        help=(
            "Directory containing train.csv, validation.csv, and test.csv. "
            "Defaults to the latest valid folder under ml/datasets."
        ),
    )
    parser.add_argument(
        "--train",
        type=Path,
        help="Optional train.csv override.",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        help="Optional validation.csv override.",
    )
    parser.add_argument(
        "--test",
        type=Path,
        help="Optional test.csv override.",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--runs-dir", default=REPO_ROOT / "ml" / "runs", type=Path
    )
    output_group.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--hidden-layers",
        default=",".join(str(size) for size in HYPERPARAMETERS["HIDDEN_LAYERS"]),
        help="Comma-separated hidden layer sizes, or 'none' for a linear model.",
    )
    parser.add_argument(
        "--features",
        default=",".join(FEATURE_COLUMNS),
        help="Comma-separated input feature columns.",
    )
    parser.add_argument(
        "--max-epochs", default=HYPERPARAMETERS["MAX_EPOCHS"], type=int
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in DEFAULT_SEEDS),
        help="Comma-separated random seeds.",
    )
    return parser.parse_args()


def is_dataset_dir(path: Path) -> bool:
    return path.is_dir() and all(
        (path / filename).is_file() for filename in DATASET_FILENAMES.values()
    )


def latest_dataset_dir(root: Path = DATASETS_ROOT) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"Dataset root not found: {root}")
    candidates = sorted(
        (path for path in root.iterdir() if is_dataset_dir(path)),
        key=lambda path: path.name,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No dataset folder containing train/validation/test CSV files under {root}"
        )
    return candidates[-1]


def resolve_dataset_paths(args: argparse.Namespace) -> tuple[Path, dict[str, Path]]:
    dataset_dir = args.dataset_dir or latest_dataset_dir()
    if not is_dataset_dir(dataset_dir):
        raise FileNotFoundError(
            f"Dataset directory must contain train.csv, validation.csv, and test.csv: "
            f"{dataset_dir}"
        )
    paths = {
        name: getattr(args, name) or dataset_dir / filename
        for name, filename in DATASET_FILENAMES.items()
    }
    return dataset_dir, paths


def parse_positive_integers(value: str, option: str) -> tuple[int, ...]:
    values = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not values or any(item <= 0 for item in values):
        raise ValueError(f"{option} must contain positive integers")
    return values


def parse_hidden_layers(value: str) -> tuple[int, ...]:
    if value.strip().lower() in {"none", "linear"}:
        return ()
    return parse_positive_integers(value, "--hidden-layers")


def parse_feature_columns(value: str) -> tuple[str, ...]:
    columns = tuple(part.strip() for part in value.split(",") if part.strip())
    if not columns:
        raise ValueError("--features must contain at least one feature")
    unknown = [column for column in columns if column not in FEATURE_COLUMNS]
    if unknown:
        raise ValueError(f"Unknown features: {', '.join(unknown)}")
    if len(set(columns)) != len(columns):
        raise ValueError("--features must not contain duplicates")
    return columns


def create_run_dir(runs_dir: Path, requested_run_dir: Path | None) -> Path:
    if requested_run_dir is not None:
        requested_run_dir.mkdir(parents=True, exist_ok=False)
        return requested_run_dir

    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for suffix in range(1000):
        name = timestamp if suffix == 0 else f"{timestamp}-{suffix:02d}"
        run_dir = runs_dir / name
        try:
            run_dir.mkdir()
            return run_dir
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not allocate a unique run directory under {runs_dir}")


def load_dataset(
    path: Path, feature_columns: tuple[str, ...]
) -> tuple[list[list[float]], list[int]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    features = []
    labels = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = set(feature_columns + ("label_index",)) - set(
            reader.fieldnames or []
        )
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        for line_number, row in enumerate(reader, start=2):
            values = [float(row[column]) for column in feature_columns]
            label = int(row["label_index"])
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Non-finite feature at {path}:{line_number}")
            if label not in range(len(LABELS)):
                raise ValueError(f"Invalid label_index at {path}:{line_number}")
            if row.get("label") and row["label"] != LABELS[label]:
                raise ValueError(f"label and label_index disagree at {path}:{line_number}")
            features.append(values)
            labels.append(label)
    if not features:
        raise ValueError(f"Dataset is empty: {path}")
    return features, labels


def activation_layer(torch_nn, name: str):
    activations = {
        "relu": torch_nn.ReLU,
        "tanh": torch_nn.Tanh,
        "sigmoid": torch_nn.Sigmoid,
        "gelu": torch_nn.GELU,
    }
    try:
        return activations[name.lower()]()
    except KeyError as error:
        raise ValueError(f"Unsupported activation: {name}") from error


def build_model(
    torch_nn, input_size: int, hidden_layers: tuple[int, ...], activation: str
):
    layers = []
    for output_size in hidden_layers:
        layers.append(torch_nn.Linear(input_size, output_size))
        layers.append(activation_layer(torch_nn, activation))
        input_size = output_size
    layers.append(torch_nn.Linear(input_size, len(LABELS)))
    return torch_nn.Sequential(*layers)


def standardize(torch, train_features, validation_features, test_features):
    feature_mean = train_features.mean(dim=0)
    feature_std = train_features.std(dim=0, unbiased=False)
    feature_std = torch.where(
        feature_std > 0, feature_std, torch.ones_like(feature_std)
    )

    def transform(features):
        return (features - feature_mean) / feature_std

    return (
        transform(train_features),
        transform(validation_features),
        transform(test_features),
        feature_mean,
        feature_std,
    )


def inverse_frequency_weights(torch, labels: list[int]):
    counts = Counter(labels)
    if set(counts) != set(range(len(LABELS))):
        raise ValueError("Training data must contain all four classes")
    total = len(labels)
    weights = [total / (len(LABELS) * counts[index]) for index in range(len(LABELS))]
    return torch.tensor(weights, dtype=torch.float32), counts


def evaluate(torch, model, loader, loss_function, device):
    model.eval()
    total_loss = 0.0
    labels = []
    predictions = []
    with torch.no_grad():
        for features, targets in loader:
            features = features.to(device)
            targets = targets.to(device)
            logits = model(features)
            total_loss += loss_function(logits, targets).item() * len(targets)
            labels.extend(targets.cpu().tolist())
            predictions.extend(logits.argmax(dim=1).cpu().tolist())
    return total_loss / len(labels), labels, predictions


def classification_metrics(
    labels: list[int], predictions: list[int]
) -> dict[str, object]:
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for expected, predicted in zip(labels, predictions):
        matrix[expected][predicted] += 1

    per_class = {}
    for index, label in enumerate(LABELS):
        true_positive = matrix[index][index]
        predicted_count = sum(row[index] for row in matrix)
        support = sum(matrix[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    total = len(labels)
    accuracy = sum(matrix[index][index] for index in range(len(LABELS))) / total
    macro_precision = mean(item["precision"] for item in per_class.values())
    macro_recall = mean(item["recall"] for item in per_class.values())
    macro_f1 = mean(item["f1"] for item in per_class.values())
    weighted_precision = sum(
        item["precision"] * item["support"] for item in per_class.values()
    ) / total
    weighted_recall = sum(
        item["recall"] * item["support"] for item in per_class.values()
    ) / total
    weighted_f1 = sum(
        item["f1"] * item["support"] for item in per_class.values()
    ) / total
    return {
        "accuracy": accuracy,
        "balanced_accuracy": macro_recall,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def write_history(path: Path, history: list[dict[str, object]]) -> None:
    fieldnames = [
        "epoch",
        "train_loss",
        "train_accuracy",
        "train_macro_f1",
        "validation_loss",
        "validation_accuracy",
        "validation_macro_f1",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(history)


def print_report(metrics: dict[str, object]) -> None:
    print(
        f"Accuracy: {metrics['accuracy']:.4f}  "
        f"Balanced accuracy: {metrics['balanced_accuracy']:.4f}  "
        f"Macro F1: {metrics['macro_f1']:.4f}  "
        f"Weighted F1: {metrics['weighted_f1']:.4f}\n"
    )
    print(f"{'class':<20} {'precision':>9} {'recall':>9} {'f1-score':>9} {'support':>9}")
    for label in LABELS:
        item = metrics["per_class"][label]
        print(
            f"{label:<20} {item['precision']:>9.4f} {item['recall']:>9.4f} "
            f"{item['f1']:>9.4f} {item['support']:>9}"
        )
    print("\nConfusion matrix:")
    for row in metrics["confusion_matrix"]:
        print(row)


def make_loader(torch, TensorDataset, DataLoader, features, labels, batch_size, shuffle, seed):
    generator = torch.Generator().manual_seed(seed) if shuffle else None
    return DataLoader(
        TensorDataset(features, labels),
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
    )


def train_seed(
    torch,
    nn,
    DataLoader,
    TensorDataset,
    seed: int,
    parameters: dict[str, object],
    tensors: dict[str, object],
    class_weights,
    class_counts: Counter,
    feature_mean,
    feature_std,
    feature_columns: tuple[str, ...],
    seed_dir: Path,
    source_paths: dict[str, Path],
    device,
) -> dict[str, object]:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    batch_size = int(parameters["BATCH_SIZE"])
    train_loader = make_loader(
        torch, TensorDataset, DataLoader, tensors["x_train"], tensors["y_train"],
        batch_size, True, seed
    )
    train_eval_loader = make_loader(
        torch, TensorDataset, DataLoader, tensors["x_train"], tensors["y_train"],
        batch_size, False, seed
    )
    validation_loader = make_loader(
        torch, TensorDataset, DataLoader, tensors["x_validation"],
        tensors["y_validation"], batch_size, False, seed
    )
    test_loader = make_loader(
        torch, TensorDataset, DataLoader, tensors["x_test"], tensors["y_test"],
        batch_size, False, seed
    )

    model = build_model(
        nn,
        len(feature_columns),
        tuple(parameters["HIDDEN_LAYERS"]),
        str(parameters["ACTIVATION"]),
    ).to(device)
    loss_function = nn.CrossEntropyLoss(weight=class_weights.to(device))
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(parameters["LEARNING_RATE"]),
        weight_decay=float(parameters["L2_REGULARIZATION"]),
    )

    best_state = deepcopy(model.state_dict())
    best_validation_macro_f1 = -1.0
    best_validation_loss = math.inf
    best_epoch = 0
    epochs_without_improvement = 0
    history = []

    print(f"\nSeed {seed}")
    for epoch in range(1, int(parameters["MAX_EPOCHS"]) + 1):
        model.train()
        for features, targets in train_loader:
            features = features.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            loss = loss_function(model(features), targets)
            loss.backward()
            optimizer.step()

        train_loss, train_labels, train_predictions = evaluate(
            torch, model, train_eval_loader, loss_function, device
        )
        validation_loss, validation_labels, validation_predictions = evaluate(
            torch, model, validation_loader, loss_function, device
        )
        train_metrics = classification_metrics(train_labels, train_predictions)
        validation_metrics = classification_metrics(
            validation_labels, validation_predictions
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "train_accuracy": train_metrics["accuracy"],
                "train_macro_f1": train_metrics["macro_f1"],
                "validation_loss": validation_loss,
                "validation_accuracy": validation_metrics["accuracy"],
                "validation_macro_f1": validation_metrics["macro_f1"],
            }
        )
        if epoch == 1 or epoch % 10 == 0:
            print(
                f"epoch={epoch} train_loss={train_loss:.6f} "
                f"train_macro_f1={train_metrics['macro_f1']:.4f} "
                f"validation_loss={validation_loss:.6f} "
                f"validation_macro_f1={validation_metrics['macro_f1']:.4f}"
            )

        improved = (
            validation_metrics["macro_f1"]
            > best_validation_macro_f1 + float(parameters["MIN_IMPROVEMENT"])
        )
        tied_but_lower_loss = (
            abs(validation_metrics["macro_f1"] - best_validation_macro_f1)
            <= float(parameters["MIN_IMPROVEMENT"])
            and validation_loss < best_validation_loss
        )
        if improved or tied_but_lower_loss:
            best_state = deepcopy(model.state_dict())
            best_validation_macro_f1 = validation_metrics["macro_f1"]
            best_validation_loss = validation_loss
            best_epoch = epoch
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= int(parameters["EARLY_STOPPING_PATIENCE"]):
                print(f"Early stopping at epoch {epoch}")
                break

    model.load_state_dict(best_state)
    validation_loss, validation_labels, validation_predictions = evaluate(
        torch, model, validation_loader, loss_function, device
    )
    test_loss, test_labels, test_predictions = evaluate(
        torch, model, test_loader, loss_function, device
    )
    validation_metrics = classification_metrics(validation_labels, validation_predictions)
    test_metrics = classification_metrics(test_labels, test_predictions)
    print(f"\nSeed {seed} test loss: {test_loss:.6f}")
    print_report(test_metrics)

    seed_dir.mkdir()
    model_path = seed_dir / "model.pt"
    history_path = seed_dir / "training_history.csv"
    metadata_path = seed_dir / "metadata.json"
    write_history(history_path, history)
    torch.save(
        {
            "model_state_dict": model.cpu().state_dict(),
            "feature_columns": list(feature_columns),
            "feature_mean": feature_mean,
            "feature_std": feature_std,
            "labels": LABELS,
            "class_weights": class_weights,
            "hyperparameters": parameters,
        },
        model_path,
    )
    metadata = {
        "seed": seed,
        "features": list(feature_columns),
        "labels": LABELS,
        "hyperparameters": parameters,
        "class_counts": {LABELS[index]: class_counts[index] for index in range(len(LABELS))},
        "class_weights": {LABELS[index]: class_weights[index].item() for index in range(len(LABELS))},
        "best_epoch": best_epoch,
        "epochs_trained": len(history),
        "validation_loss": validation_loss,
        "validation_metrics": validation_metrics,
        "test_loss": test_loss,
        "test_metrics": test_metrics,
        "model_path": str(model_path),
        "history_path": str(history_path),
        **{f"{name}_path": str(path) for name, path in source_paths.items()},
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def aggregate_seed_metrics(seed_results: list[dict[str, object]]) -> dict[str, object]:
    metric_names = [
        "accuracy",
        "balanced_accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
    ]
    aggregate = {}
    for metric_name in metric_names:
        values = [result["test_metrics"][metric_name] for result in seed_results]
        aggregate[metric_name] = {
            "mean": mean(values),
            "std": pstdev(values),
            "values": values,
        }
    aggregate["per_class"] = {}
    for label in LABELS:
        aggregate["per_class"][label] = {}
        for metric_name in ("precision", "recall", "f1"):
            values = [
                result["test_metrics"]["per_class"][label][metric_name]
                for result in seed_results
            ]
            aggregate["per_class"][label][metric_name] = {
                "mean": mean(values),
                "std": pstdev(values),
                "values": values,
            }
    return aggregate


def write_metrics_csv(path: Path, seed_results: list[dict[str, object]]) -> None:
    fieldnames = [
        "seed",
        "split",
        "class",
        "precision",
        "recall",
        "f1",
        "support",
        "accuracy",
        "balanced_accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for result in seed_results:
            for split in ("validation", "test"):
                metrics = result[f"{split}_metrics"]
                for label in LABELS:
                    writer.writerow(
                        {
                            "seed": result["seed"],
                            "split": split,
                            "class": label,
                            **metrics["per_class"][label],
                            **{
                                name: metrics[name]
                                for name in fieldnames[7:]
                            },
                        }
                    )


def main() -> None:
    args = parse_args()
    dataset_dir, source_paths = resolve_dataset_paths(args)
    hidden_layers = parse_hidden_layers(args.hidden_layers)
    feature_columns = parse_feature_columns(args.features)
    seeds = parse_positive_integers(args.seeds, "--seeds")
    parameters = {
        **HYPERPARAMETERS,
        "HIDDEN_LAYERS": hidden_layers,
        "FEATURE_COLUMNS": feature_columns,
        "MAX_EPOCHS": args.max_epochs,
    }

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ModuleNotFoundError as error:
        raise SystemExit(
            "Missing PyTorch. Install with: python3 -m pip install -r ml/requirements-ml.txt"
        ) from error

    x_train_rows, y_train_rows = load_dataset(source_paths["train"], feature_columns)
    x_validation_rows, y_validation_rows = load_dataset(
        source_paths["validation"], feature_columns
    )
    x_test_rows, y_test_rows = load_dataset(source_paths["test"], feature_columns)
    class_weights, class_counts = inverse_frequency_weights(torch, y_train_rows)

    x_train = torch.tensor(x_train_rows, dtype=torch.float32)
    x_validation = torch.tensor(x_validation_rows, dtype=torch.float32)
    x_test = torch.tensor(x_test_rows, dtype=torch.float32)
    x_train, x_validation, x_test, feature_mean, feature_std = standardize(
        torch, x_train, x_validation, x_test
    )
    tensors = {
        "x_train": x_train,
        "y_train": torch.tensor(y_train_rows, dtype=torch.long),
        "x_validation": x_validation,
        "y_validation": torch.tensor(y_validation_rows, dtype=torch.long),
        "x_test": x_test,
        "y_test": torch.tensor(y_test_rows, dtype=torch.long),
    }
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    run_dir = create_run_dir(args.runs_dir, args.run_dir)
    print(f"Device: {device}")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Run directory: {run_dir}")
    print(f"Features: {', '.join(feature_columns)}")
    print("Class weights: " + ", ".join(
        f"{LABELS[index]}={class_weights[index].item():.4f}"
        for index in range(len(LABELS))
    ))

    seed_results = []
    for seed in seeds:
        seed_parameters = {**parameters, "RANDOM_SEED": seed}
        seed_results.append(
            train_seed(
                torch, nn, DataLoader, TensorDataset, seed, seed_parameters,
                tensors, class_weights, class_counts, feature_mean, feature_std,
                feature_columns, run_dir / f"seed-{seed}", source_paths, device
            )
        )

    best_result = max(
        seed_results,
        key=lambda result: (
            result["validation_metrics"]["macro_f1"],
            -result["validation_loss"],
        ),
    )
    best_seed_dir = run_dir / f"seed-{best_result['seed']}"
    for filename in ("model.pt", "training_history.csv"):
        shutil.copyfile(best_seed_dir / filename, run_dir / filename)
    selected_metadata = dict(best_result)
    selected_metadata["selected_seed"] = best_result["seed"]
    selected_metadata["model_path"] = str(run_dir / "model.pt")
    selected_metadata["history_path"] = str(run_dir / "training_history.csv")
    (run_dir / "metadata.json").write_text(
        json.dumps(selected_metadata, indent=2), encoding="utf-8"
    )

    summary = {
        "seeds": list(seeds),
        "selected_seed": best_result["seed"],
        "selection_metric": "validation_macro_f1",
        "aggregate_test_metrics": aggregate_seed_metrics(seed_results),
        "seed_results": seed_results,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metrics_path = run_dir / "metrics.csv"
    write_metrics_csv(metrics_path, seed_results)
    print(f"\nSelected seed: {best_result['seed']}")
    print(f"Wrote summary: {summary_path}")
    print(f"Wrote metrics: {metrics_path}")
    print(f"Wrote representative model: {run_dir / 'model.pt'}")


if __name__ == "__main__":
    main()
