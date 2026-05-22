# SmokeLens Next Session Plan

Updated: 2026-05-22

This file is the handoff plan for the next work session. Follow the steps from
top to bottom to continue without reconstructing today's context.

## 0. Today Summary

Completed today:

- ESP32 Arduino firmware was created in `SmokeLens.ino`.
- Hardware serial output was verified.
- MQ-135 and MQ-7 ADC readings became non-zero after wiring/debug.
- PMS5003T UART parsing was verified:
  - `pms_valid:true`
  - temperature and humidity readable
  - PM values can be `0` in clean air and will be tested later with a particle source
- MQTT publishing was enabled in firmware.
- Mosquitto local broker config was added at `broker/mosquitto.conf`.
- Node.js backend was added under `backend/`.
- Backend receives MQTT, stores readings in SQLite, exposes API, and exports CSV.
- `better-sqlite3` was replaced by `sql.js` to avoid Visual Studio C++ build issues on Windows/Node v24.
- `npm.cmd install` completed successfully.
- `data/smokelens.sqlite` was created successfully.
- WiFi/MQTT secrets were moved out of `SmokeLens.ino` into ignored `arduino_secrets.h`.
- `arduino_secrets.example.h` was added as the committed template.
- ML work is now on the `ml` branch.
- Python ML scripts were added under `ml/`:
  - `ml/scripts/prepare_dataset.py`
  - `ml/scripts/train_mlp.py`
  - `ml/requirements-ml.txt`
  - `ml/README.md`
- A local Python virtual environment was created at `.env/` and is ignored by git.
- ML dependencies were installed in `.env/`:
  - `scikit-learn`
  - `joblib`
  - `numpy`
  - `scipy`
- MLP input was changed from 9 to 7 dimensions. `voc_raw` and `co_raw` are
  still stored in SQLite for debugging, but ML training keeps the millivolt
  versions to avoid redundant raw/mV pairs.
  Current MLP input features:
  - `voc_mv`
  - `co_mv`
  - `pm1_0`
  - `pm2_5`
  - `pm10`
  - `temperature`
  - `humidity`
- `pms_valid` is kept in the database but is not an MLP input. Rows with
  `pms_valid != 1` should be excluded from training.
- Classification labels were changed to integer classes:
  - `0` = normal air
  - `1` = cooking oil fume
  - `2` = car exhaust
  - `3` = smoke smell
  - `NULL` = unlabeled
- Backend classification storage was changed from text labels such as
  `unclassified` to integer classes `0`-`3` or `NULL`.
- The planned MLP architecture is currently:
  - input: 7
  - hidden layers: `16`
  - output classes: 4
  - normalization: `StandardScaler` in the Python training pipeline
- Dataset CSV column order is:
  - 7 input features
  - `label_index`
  - `label`
- `label_index` is the model target. `label` is kept as the final column for
  human-readable inspection.
- A local fake database was created for pipeline testing:
  - `data/smokelens_fake.sqlite`
  - 80 usable rows
  - 20 rows per class
  - ignored by git
- Fake generated `ml/datasets/train.csv` and `ml/datasets/test.csv` are also
  ignored by git. The real default input for `prepare_dataset.py` remains
  `data/smokelens.sqlite`; use `--db data/smokelens_fake.sqlite` only for local
  testing.

Important local-only files:

- `arduino_secrets.h` contains local WiFi/MQTT values and is ignored by git.
- `backend/.env` contains local backend settings and is ignored by git.
- `data/smokelens.sqlite` is generated data and is ignored by git.
- `.env/` contains the local Python virtual environment and is ignored by git.
- `ml/datasets/*.csv` contains generated train/test CSV files and is ignored by git.
- `ml/models/*.joblib` and `ml/models/*.json` contain trained model artifacts
  and are ignored by git for now.

## 1. Current Architecture

```text
ESP32 sensor node
  -> WiFi
  -> Mosquitto MQTT broker on laptop
  -> Node.js backend
  -> SQLite database
  -> API / CSV export
```

Topic:

```text
smokelens/node_01/data
```

Backend subscribes to:

```text
smokelens/+/data
```

## 2. Files To Know

Firmware:

- `SmokeLens.ino`
- `arduino_secrets.example.h`
- local ignored file: `arduino_secrets.h`

Broker:

- `broker/mosquitto.conf`

Backend:

- `backend/package.json`
- `backend/package-lock.json`
- `backend/src/server.js`
- `backend/src/db.js`
- `backend/src/config.js`
- `backend/src/classifier.js`
- `backend/src/csv.js`
- `backend/scripts/export-csv.js`
- `backend/.env.example`
- local ignored file: `backend/.env`

Data:

- generated DB: `data/smokelens.sqlite`

ML:

- `ml/README.md`
- `ml/requirements-ml.txt`
- `ml/scripts/prepare_dataset.py`
- `ml/scripts/train_mlp.py`
- generated train/test CSV: `ml/datasets/train.csv`, `ml/datasets/test.csv`
- generated model artifacts:
  - `ml/models/smokelens_mlp.joblib`
  - `ml/models/smokelens_mlp_metadata.json`

Current ML branch:

```text
ml
```

## 3. Start-Of-Session Checklist

Open PowerShell.

Check Node:

```powershell
node --version
npm.cmd --version
```

Check Mosquitto:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

Check laptop WiFi IP:

```powershell
ipconfig
```

Look for:

```text
Wireless LAN adapter Wi-Fi
IPv4 Address . . . : 192.168.x.x
```

Make sure `arduino_secrets.h` has that IP:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.x.x"
```

## 4. Start Mosquitto

Terminal 1:

```powershell
cd "C:\Users\ADMIN\Documents\NTU\Digital electronics\SmokeLens"
& "C:\Program Files\mosquitto\mosquitto.exe" -c broker\mosquitto.conf -v
```

Expected:

```text
Opening ipv4 listen socket on port 1883
```

Confirm it is listening on WiFi/all interfaces:

```powershell
netstat -ano | Select-String ":1883"
```

Good:

```text
0.0.0.0:1883
```

Problem:

```text
127.0.0.1:1883
```

If it only listens on `127.0.0.1`, stop the existing Mosquitto service/process
and restart with `broker/mosquitto.conf`.

## 5. Start Backend

Terminal 2:

```powershell
cd "C:\Users\ADMIN\Documents\NTU\Digital electronics\SmokeLens\backend"
npm.cmd install
Copy-Item .env.example .env -Force
npm.cmd start
```

Expected:

```text
[http] listening on http://localhost:3000
[db] ...\data\smokelens.sqlite
[mqtt] connected mqtt://localhost:1883
[mqtt] subscribed smokelens/+/data
```

If install fails because of an old partial install:

```powershell
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
npm.cmd install
```

## 6. Start ESP32

Arduino IDE:

1. Open `SmokeLens.ino`.
2. Confirm `arduino_secrets.h` exists in the sketch folder.
3. Upload to ESP32.
4. Open Serial Monitor at `115200`.

Expected Serial:

```text
# SmokeLens node boot
# MQTT topic=smokelens/node_01/data
# WiFi connecting to ...
# MQTT connected
```

Expected JSON:

```json
{"node_id":"node_01","timestamp":1716000000,"voc_raw":600,"co_raw":660,"voc_mv":620,"co_mv":670,"pm1_0":0,"pm2_5":5,"pm10":5,"temperature":21.1,"humidity":70,"pms_valid":true}
```

Expected backend log:

```text
[data] node_01 ts=... voc=... co=... pm25=... pms=true
```

## 7. Verify API And Database

Health:

```powershell
Invoke-WebRequest http://localhost:3000/api/health
```

Latest:

```powershell
Invoke-WebRequest http://localhost:3000/api/latest
```

History:

```powershell
Invoke-WebRequest "http://localhost:3000/api/history?node_id=node_01&limit=20"
```

CSV export:

```text
http://localhost:3000/api/export.csv
```

Command line CSV export:

```powershell
cd "C:\Users\ADMIN\Documents\NTU\Digital electronics\SmokeLens\backend"
npm.cmd run export:csv
```

## 8. If MQTT Fails

ESP32 message:

```text
# MQTT failed, state=-2
```

Checklist:

1. ESP32 and laptop are on the same WiFi.
2. `SMOKELENS_MQTT_SERVER` equals laptop WiFi IP.
3. Mosquitto is running.
4. Mosquitto listens on `0.0.0.0:1883` or laptop WiFi IP, not only `127.0.0.1`.
5. Windows Firewall allows TCP `1883`.

Firewall rule if needed:

```powershell
New-NetFirewallRule -DisplayName "SmokeLens MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```

## 9. Next Development Tasks

Do these after the full pipeline is confirmed:

1. Add a labeling workflow for SQLite rows.
   - Need a script or API to mark time ranges with `classification = 0..3`.
   - Suggested classes:
     - `0` = normal air
     - `1` = cooking oil fume
     - `2` = car exhaust
     - `3` = smoke smell
2. Collect labeled data for each class.
   - Keep each experiment sequence clear, for example:
     - normal air
     - exposure state
     - recovery back to normal air
3. Export/prepare train and test data:

```bash
.env/bin/python ml/scripts/prepare_dataset.py
```

This reads `data/smokelens.sqlite`, filters rows where:

- `pms_valid = 1`
- `classification` is one of `0`, `1`, `2`, `3`
- all 7 MLP input features are non-null

Then it writes:

```text
ml/datasets/train.csv
ml/datasets/test.csv
```

CSV format:

```text
voc_mv,co_mv,pm1_0,pm2_5,pm10,temperature,humidity,label_index,label
```

`label_index` is used by training. `label` is for human inspection and should
stay as the final column.

4. Train the MLP:

```bash
.env/bin/python ml/scripts/train_mlp.py
```

This writes:

```text
ml/models/smokelens_mlp.joblib
ml/models/smokelens_mlp_metadata.json
```

5. Inspect ranges and class balance for:
   - `voc_mv`
   - `co_mv`
   - `pm1_0`
   - `pm2_5`
   - `pm10`
   - `temperature`
   - `humidity`
6. Build a minimal dashboard page:
   - latest values
   - node online/offline
   - simple trend chart
7. After a stable demo model exists, optionally commit one named model artifact,
   for example `smokelens_mlp_demo_v1.joblib`.
8. Later add an export script to convert the trained MLP into an Arduino header:
   - scaler mean/std arrays
   - dense layer weight arrays
   - dense layer bias arrays
   - ESP32 inference helper

## 10. Commit/Push Notes

Files that should be committed:

- source code
- README
- PROGRESS
- package files
- broker config
- example secrets file

Files that should not be committed:

- `arduino_secrets.h`
- `backend/.env`
- `backend/node_modules/`
- `data/*.sqlite`
- `.env/`
- `ml/datasets/*.csv`
- `ml/models/*.joblib`
- `ml/models/*.json`
- `.pio/`

Before push:

```powershell
git status --short
```

No WiFi password should appear in tracked files.
