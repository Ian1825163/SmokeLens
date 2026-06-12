# SmokeLens ML Scripts

This folder contains the first MLP training pipeline for air-quality state
classification.

Classes:

```text
0 = normal_air
1 = cooking_fume
2 = vehicle_exhaust
3 = cigarette_smoke
```

Input features:

```text
voc_mv
co_mv
pm1_0
pm2_5
pm10
temperature
humidity
```

`voc_raw` and `co_raw` are still stored in CSV for debugging, but they are
not used for MLP training because they are redundant with the calibrated
millivolt features.

`pms_valid` is not used as a model input. Rows with invalid PMS data are
filtered out before training.

## Install Python Dependencies

```bash
python3 -m pip install -r ml/requirements-ml.txt
```

## Prepare Train/Test Data

The script reads `data/datapool.csv`, filters usable labeled rows, removes
exact duplicate feature vectors within each class, and writes chronological
train/validation/test CSV files under `ml/datasets/`.

```bash
python3 ml/scripts/prepare_dataset.py
```

Useful options:

```bash
python3 ml/scripts/prepare_dataset.py --csv data/datapool.csv --out-dir ml/datasets
```

Rows are usable only when:

- `mode` is `data_collection`
- `collection_label` is one of `normal_air`, `cooking_fume`, `vehicle_exhaust`, `cigarette_smoke`
- `pms_valid` is true
- all 7 input features are present

Within each class, rows are ordered by timestamp and split into contiguous
intervals: the earliest 80% is training data, the next 10% is validation data,
and the latest 10% is test data. No undersampling or interleaved row sampling
is performed.

This is a chronological holdout, not a fully independent experiment-session
holdout. Several classes currently have too few independent collection
sessions for a reliable session-level split. Once more sessions are available,
keep each complete session in exactly one split to measure cross-session
generalization.

## Train MLP

```bash
python3 ml/scripts/train.py
```

This trains a PyTorch MLP with feature standardization. The default model
shape is:

```text
7 -> 4 -> 4
```

Training uses all unique rows. Inverse-frequency class weights are calculated
from the training set and passed to cross-entropy loss. By default, five random
seeds are trained and compared using validation macro F1:

```bash
python3 ml/scripts/train.py --seeds 42,43,44,45,46
```

Use a linear `7 -> 4` baseline with no hidden layer:

```bash
python3 ml/scripts/train.py --hidden-layers none
```

Select a smaller input feature set, for example a linear `2 -> 4` model using
only VOC and PM2.5:

```bash
python3 ml/scripts/train.py --hidden-layers none --features voc_mv,pm2_5
```

Each invocation creates its own timestamped run directory:

```text
ml/runs/20260613-143025/
├── model.pt
├── metadata.json
├── training_history.csv
├── metrics.csv
├── summary.json
├── seed-42/
│   ├── model.pt
│   ├── metadata.json
│   └── training_history.csv
└── seed-43/...
```

`model.pt`, `metadata.json`, and `training_history.csv` at the run root belong
to the seed with the best validation macro F1. `metrics.csv` contains
per-class precision, recall, F1, and support for every seed. `summary.json`
contains aggregate test means and standard deviations.

Use `--run-dir ml/runs/my-experiment` to choose a specific directory name.
The script refuses to overwrite an existing run directory.

Plot loss and accuracy against epoch after training:

```bash
python3 ml/scripts/plot_training.py
```

Without arguments, this plots the latest run and writes `training_curves.png`
into that run directory. The image contains loss and accuracy charts stacked
vertically with an overall width-to-height ratio of 1.56. Use `--run-dir` to
select a different run.
