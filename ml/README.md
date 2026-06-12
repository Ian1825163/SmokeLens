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

The script reads `data/datapool.csv`, filters usable labeled rows, and writes
train/test CSV files under `ml/datasets/`.

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

## Train MLP

```bash
python3 ml/scripts/train.py
```

This trains a PyTorch MLP with feature standardization. The default model
shape is:

```text
7 -> 16 -> 4
```

If train accuracy is high but test accuracy is low, reduce model size or add
more diverse data. If train accuracy is low, increase model size, for example
with `--hidden-layers 32,16`.

Each invocation creates its own timestamped run directory:

```text
ml/runs/20260613-143025/
├── model.pt
├── metadata.json
└── training_history.csv
```

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
