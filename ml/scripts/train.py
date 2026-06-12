#!/usr/bin/env python3
"""Train a 7-input, 4-output PyTorch MLP for SmokeLens readings."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from copy import deepcopy
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

LABELS = ["normal_air", "cooking_fume", "vehicle_exhaust", "cigarette_smoke"]

# Tune the model here. CLI options can override HIDDEN_LAYERS, MAX_EPOCHS,
# and RANDOM_SEED without editing the file.
HYPERPARAMETERS = {
    "HIDDEN_LAYERS": (16,),
    "ACTIVATION": "relu",
    "LEARNING_RATE": 0.001,
    "L2_REGULARIZATION": 0.0001,
    "BATCH_SIZE": 200,
    "MAX_EPOCHS": 500,
    "EARLY_STOPPING": True,
    "VALIDATION_RATIO": 0.1,
    "EARLY_STOPPING_PATIENCE": 10,
    "MIN_IMPROVEMENT": 0.0001,
    "RANDOM_SEED": 42,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train SmokeLens PyTorch MLP.")
    parser.add_argument(
        "--train",
        default=REPO_ROOT / "ml" / "datasets" / "train.csv",
        type=Path,
        help="Path to training CSV.",
    )
    parser.add_argument(
        "--test",
        default=REPO_ROOT / "ml" / "datasets" / "test.csv",
        type=Path,
        help="Path to testing CSV.",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--runs-dir",
        default=REPO_ROOT / "ml" / "runs",
        type=Path,
        help="Parent directory for timestamped run directories.",
    )
    output_group.add_argument(
        "--run-dir",
        type=Path,
        help="Exact directory for this run; it must not already exist.",
    )
    parser.add_argument(
        "--hidden-layers",
        default=",".join(str(size) for size in HYPERPARAMETERS["HIDDEN_LAYERS"]),
        help="Comma-separated hidden layer sizes.",
    )
    parser.add_argument(
        "--max-epochs", default=HYPERPARAMETERS["MAX_EPOCHS"], type=int
    )
    parser.add_argument("--seed", default=HYPERPARAMETERS["RANDOM_SEED"], type=int)
    return parser.parse_args()


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


def parse_hidden_layers(value: str) -> tuple[int, ...]:
    layers = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not layers or any(layer <= 0 for layer in layers):
        raise ValueError("--hidden-layers must contain positive integers")
    return layers


def load_dataset(path: Path) -> tuple[list[list[float]], list[int]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    x_rows: list[list[float]] = []
    y_rows: list[int] = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = set(FEATURE_COLUMNS + ["label_index"]) - set(
            reader.fieldnames or []
        )
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        for line_number, row in enumerate(reader, start=2):
            features = [float(row[column]) for column in FEATURE_COLUMNS]
            label = int(row["label_index"])
            if not all(math.isfinite(value) for value in features):
                raise ValueError(f"Non-finite feature at {path}:{line_number}")
            if label not in range(len(LABELS)):
                raise ValueError(f"Invalid label_index at {path}:{line_number}")
            if row.get("label") and row["label"] != LABELS[label]:
                raise ValueError(f"label and label_index disagree at {path}:{line_number}")
            x_rows.append(features)
            y_rows.append(label)

    if not x_rows:
        raise ValueError(f"Dataset is empty: {path}")
    return x_rows, y_rows


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
        raise ValueError(
            f"Unsupported ACTIVATION={name!r}; choose from {', '.join(activations)}"
        ) from error


def build_model(torch_nn, hidden_layers: tuple[int, ...], activation: str):
    layers = []
    input_size = len(FEATURE_COLUMNS)
    for output_size in hidden_layers:
        layers.append(torch_nn.Linear(input_size, output_size))
        layers.append(activation_layer(torch_nn, activation))
        input_size = output_size
    layers.append(torch_nn.Linear(input_size, len(LABELS)))
    return torch_nn.Sequential(*layers)


def standardize(torch, train_features, test_features):
    mean = train_features.mean(dim=0)
    std = train_features.std(dim=0, unbiased=False)
    std = torch.where(std > 0, std, torch.ones_like(std))
    return (train_features - mean) / std, (test_features - mean) / std, mean, std


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


def accuracy_score(labels: list[int], predictions: list[int]) -> float:
    return sum(
        expected == predicted
        for expected, predicted in zip(labels, predictions)
    ) / len(labels)


def write_history(path: Path, history: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "epoch",
        "train_loss",
        "train_accuracy",
        "validation_loss",
        "validation_accuracy",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(history)


def print_report(labels: list[int], predictions: list[int]) -> tuple[float, list[list[int]]]:
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for expected, predicted in zip(labels, predictions):
        matrix[expected][predicted] += 1

    accuracy = sum(matrix[index][index] for index in range(len(LABELS))) / len(labels)
    print(f"Accuracy: {accuracy:.4f}\n")
    print(f"{'class':<20} {'precision':>9} {'recall':>9} {'f1-score':>9} {'support':>9}")
    for index, label in enumerate(LABELS):
        true_positive = matrix[index][index]
        predicted_count = sum(row[index] for row in matrix)
        support = sum(matrix[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(f"{label:<20} {precision:>9.4f} {recall:>9.4f} {f1:>9.4f} {support:>9}")

    print("\nConfusion matrix:")
    for row in matrix:
        print(row)
    return accuracy, matrix


def main() -> None:
    args = parse_args()
    hidden_layers = parse_hidden_layers(args.hidden_layers)
    parameters = {
        **HYPERPARAMETERS,
        "HIDDEN_LAYERS": hidden_layers,
        "MAX_EPOCHS": args.max_epochs,
        "RANDOM_SEED": args.seed,
    }

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset, random_split
    except ModuleNotFoundError as error:
        raise SystemExit(
            "Missing PyTorch. Install with: "
            "python3 -m pip install -r ml/requirements-ml.txt"
        ) from error

    random.seed(parameters["RANDOM_SEED"])
    torch.manual_seed(parameters["RANDOM_SEED"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(parameters["RANDOM_SEED"])

    x_train_rows, y_train_rows = load_dataset(args.train)
    x_test_rows, y_test_rows = load_dataset(args.test)
    if set(y_train_rows) != set(range(len(LABELS))):
        raise SystemExit("Training data must contain all four classes.")

    x_train = torch.tensor(x_train_rows, dtype=torch.float32)
    y_train = torch.tensor(y_train_rows, dtype=torch.long)
    x_test = torch.tensor(x_test_rows, dtype=torch.float32)
    y_test = torch.tensor(y_test_rows, dtype=torch.long)
    x_train, x_test, feature_mean, feature_std = standardize(
        torch, x_train, x_test
    )

    training_dataset = TensorDataset(x_train, y_train)
    validation_dataset = None
    if parameters["EARLY_STOPPING"]:
        validation_size = max(
            1, round(len(training_dataset) * parameters["VALIDATION_RATIO"])
        )
        training_size = len(training_dataset) - validation_size
        generator = torch.Generator().manual_seed(parameters["RANDOM_SEED"])
        training_dataset, validation_dataset = random_split(
            training_dataset, [training_size, validation_size], generator=generator
        )

    loader_generator = torch.Generator().manual_seed(parameters["RANDOM_SEED"])
    train_loader = DataLoader(
        training_dataset,
        batch_size=parameters["BATCH_SIZE"],
        shuffle=True,
        generator=loader_generator,
    )
    train_evaluation_loader = DataLoader(
        training_dataset, batch_size=parameters["BATCH_SIZE"]
    )
    validation_loader = (
        DataLoader(validation_dataset, batch_size=parameters["BATCH_SIZE"])
        if validation_dataset is not None
        else None
    )
    test_loader = DataLoader(
        TensorDataset(x_test, y_test), batch_size=parameters["BATCH_SIZE"]
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(nn, hidden_layers, parameters["ACTIVATION"]).to(device)
    loss_function = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=parameters["LEARNING_RATE"],
        weight_decay=parameters["L2_REGULARIZATION"],
    )

    best_state = deepcopy(model.state_dict())
    best_validation_loss = math.inf
    epochs_without_improvement = 0
    epochs_trained = 0
    history = []

    print(f"Device: {device}")
    for epoch in range(1, parameters["MAX_EPOCHS"] + 1):
        model.train()
        for features, targets in train_loader:
            features = features.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            logits = model(features)
            loss = loss_function(logits, targets)
            loss.backward()
            optimizer.step()

        epochs_trained = epoch
        average_training_loss, training_labels, training_predictions = evaluate(
            torch, model, train_evaluation_loader, loss_function, device
        )
        training_accuracy = accuracy_score(
            training_labels, training_predictions
        )
        if validation_loader is None:
            history.append(
                {
                    "epoch": epoch,
                    "train_loss": average_training_loss,
                    "train_accuracy": training_accuracy,
                    "validation_loss": "",
                    "validation_accuracy": "",
                }
            )
            if epoch == 1 or epoch % 10 == 0 or epoch == parameters["MAX_EPOCHS"]:
                print(
                    f"epoch={epoch} train_loss={average_training_loss:.6f} "
                    f"train_accuracy={training_accuracy:.4f}"
                )
            continue

        validation_loss, validation_labels, validation_predictions = evaluate(
            torch, model, validation_loader, loss_function, device
        )
        validation_accuracy = accuracy_score(
            validation_labels, validation_predictions
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": average_training_loss,
                "train_accuracy": training_accuracy,
                "validation_loss": validation_loss,
                "validation_accuracy": validation_accuracy,
            }
        )
        if epoch == 1 or epoch % 10 == 0:
            print(
                f"epoch={epoch} train_loss={average_training_loss:.6f} "
                f"train_accuracy={training_accuracy:.4f} "
                f"validation_loss={validation_loss:.6f} "
                f"validation_accuracy={validation_accuracy:.4f}"
            )

        if validation_loss < best_validation_loss - parameters["MIN_IMPROVEMENT"]:
            best_validation_loss = validation_loss
            best_state = deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= parameters["EARLY_STOPPING_PATIENCE"]:
                print(f"Early stopping at epoch {epoch}")
                model.load_state_dict(best_state)
                break

    run_dir = create_run_dir(args.runs_dir, args.run_dir)
    model_path = run_dir / "model.pt"
    metadata_path = run_dir / "metadata.json"
    history_path = run_dir / "training_history.csv"
    write_history(history_path, history)

    test_loss, test_labels, test_predictions = evaluate(
        torch, model, test_loader, loss_function, device
    )
    print(f"\nTest loss: {test_loss:.6f}")
    accuracy, confusion_matrix = print_report(test_labels, test_predictions)

    checkpoint = {
        "model_state_dict": model.cpu().state_dict(),
        "feature_columns": FEATURE_COLUMNS,
        "feature_mean": feature_mean,
        "feature_std": feature_std,
        "labels": LABELS,
        "hyperparameters": parameters,
    }
    torch.save(checkpoint, model_path)

    metadata = {
        "features": FEATURE_COLUMNS,
        "labels": LABELS,
        "label_encoding": {label: index for index, label in enumerate(LABELS)},
        "hyperparameters": parameters,
        "accuracy": accuracy,
        "test_loss": test_loss,
        "confusion_matrix": confusion_matrix,
        "epochs_trained": epochs_trained,
        "train_rows": len(y_train_rows),
        "test_rows": len(y_test_rows),
        "run_dir": str(run_dir),
        "model_path": str(model_path),
        "history_path": str(history_path),
        "train_path": str(args.train),
        "test_path": str(args.test),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nWrote run directory: {run_dir}")
    print(f"Wrote model: {model_path}")
    print(f"Wrote metadata: {metadata_path}")
    print(f"Wrote training history: {history_path}")


if __name__ == "__main__":
    main()
