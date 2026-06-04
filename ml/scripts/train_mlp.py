#!/usr/bin/env python3
"""Train a 7-input, 4-output MLP classifier for SmokeLens readings."""

from __future__ import annotations

import argparse
import csv
import json
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train SmokeLens MLP model.")
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
    parser.add_argument(
        "--model",
        default=REPO_ROOT / "ml" / "models" / "smokelens_mlp.joblib",
        type=Path,
        help="Output model path.",
    )
    parser.add_argument(
        "--hidden-layers",
        default="16",
        help="Comma-separated hidden layer sizes.",
    )
    parser.add_argument("--max-iter", default=500, type=int)
    parser.add_argument("--seed", default=42, type=int)
    return parser.parse_args()


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
        for row in reader:
            x_rows.append([float(row[column]) for column in FEATURE_COLUMNS])
            y_rows.append(int(row["label_index"]))

    if not x_rows:
        raise ValueError(f"Dataset is empty: {path}")
    return x_rows, y_rows


def main() -> None:
    args = parse_args()
    hidden_layers = parse_hidden_layers(args.hidden_layers)

    try:
        import joblib
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
        )
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as error:
        raise SystemExit(
            "Missing ML dependency. Install with: "
            "python3 -m pip install -r ml/requirements-ml.txt"
        ) from error

    x_train, y_train = load_dataset(args.train)
    x_test, y_test = load_dataset(args.test)
    if len(set(y_train)) < 2:
        raise SystemExit(
            "Training data must contain at least 2 classes. Collect more "
            "data_collection rows with different collection_label values "
            "before training."
        )

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "mlp",
                MLPClassifier(
                    hidden_layer_sizes=hidden_layers,
                    activation="relu",
                    solver="adam",
                    max_iter=args.max_iter,
                    random_state=args.seed,
                ),
            ),
        ]
    )

    model.fit(x_train, y_train)
    predictions = model.predict(x_test)

    accuracy = accuracy_score(y_test, predictions)
    print(f"Accuracy: {accuracy:.4f}")
    print()
    print(
        classification_report(
            y_test,
            predictions,
            labels=list(range(len(LABELS))),
            target_names=LABELS,
            zero_division=0,
        )
    )
    print("Confusion matrix:")
    print(confusion_matrix(y_test, predictions, labels=list(range(len(LABELS)))))

    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model)

    metadata_path = args.model.with_name(f"{args.model.stem}_metadata.json")
    metadata = {
        "features": FEATURE_COLUMNS,
        "labels": LABELS,
        "label_encoding": {label: index for index, label in enumerate(LABELS)},
        "hidden_layers": hidden_layers,
        "accuracy": accuracy,
        "train_rows": len(y_train),
        "test_rows": len(y_test),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print()
    print(f"Wrote model: {args.model}")
    print(f"Wrote metadata: {metadata_path}")


if __name__ == "__main__":
    main()
