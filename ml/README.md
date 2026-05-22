# SmokeLens ML Scripts

This folder contains the first MLP training pipeline for air-quality state
classification.

Classes:

```text
0 = normal
1 = cooking_oil
2 = car_exhaust
3 = smoke_smell
```

Input features:

```text
voc_raw
co_raw
voc_mv
co_mv
pm1_0
pm2_5
pm10
temperature
humidity
```

`pms_valid` is not used as a model input. Rows with invalid PMS data are
filtered out before training.

## Install Python Dependencies

```bash
python3 -m pip install -r ml/requirements-ml.txt
```

## Prepare Train/Test Data

The script reads `data/smokelens.sqlite`, filters usable labeled rows, and
writes CSV files under `ml/datasets/`.

```bash
python3 ml/scripts/prepare_dataset.py
```

Useful options:

```bash
python3 ml/scripts/prepare_dataset.py --test-size 0.2 --seed 42
python3 ml/scripts/prepare_dataset.py --db data/smokelens.sqlite --out-dir ml/datasets
```

Rows are usable only when:

- `classification` is one of `normal`, `cooking_oil`, `car_exhaust`,
  `smoke_smell`
- `pms_valid` is true
- all 9 input features are present

## Train MLP

```bash
python3 ml/scripts/train_mlp.py
```

This trains a scikit-learn MLP with feature standardization and writes:

```text
ml/models/smokelens_mlp.joblib
ml/models/smokelens_mlp_metadata.json
```

