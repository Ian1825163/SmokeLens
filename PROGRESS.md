# SmokeLens Progress And Next Plan

Updated: 2026-05-28

Current branch:

```text
main
```

This file is the handoff plan for the next work session. For test commands and
data collection checklists, start from `QUICKSTART.md`.

Current working run flow:

```text
Terminal 1: Mosquitto with broker/mosquitto.conf
Terminal 2: backend npm.cmd start
Terminal 3: tools/SerialCsvLogger.ps1 -Port COM11
ESP32: plugged into laptop, running SmokeLens.ino
```

This records data through both MQTT/dashboard and USB Serial CSV when MQTT is available.

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

Button/mode feature work completed and merged:

- Added ESP32 button-controlled mode switching.
- Added firmware JSON fields for data collection labels and inference output.
- Added LED 1 alert output for cigarette detection in inference mode.
- Added backend database/CSV columns for mode, labels, inference class, score, and model version.
- Added `QUICKSTART.md` so GPIO tests, data collection, backend startup, and CSV export commands are easier to find.
- Added multi-WiFi firmware configuration through `SMOKELENS_WIFI_CREDENTIALS`, while keeping the old single-WiFi macros compatible.
- Added `tools/SerialCsvLogger.ps1` for USB Serial data collection without MQTT, with automatic CSV splitting by mode/label segment.
- Added web dashboards:
  - `/` for user-facing smoke area status on a Leaflet/OpenStreetMap view.
  - `/admin` for developer telemetry, node status, trend, and live feed.

Important local-only files:

- `arduino_secrets.h` contains local WiFi/MQTT values and is ignored by git.
- `backend/.env` contains local backend settings and is ignored by git.
- `data/smokelens.sqlite` is generated data and is ignored by git.

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
- `QUICKSTART.md`
- `tools/SerialCsvLogger.ps1`
- `tools/GpioButtonTest/GpioButtonTest.ino`
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
- `backend/public/`
- local ignored file: `backend/.env`

Data:

- generated DB: `data/smokelens.sqlite`

## 2.1 Button/LED Mapping

| Control | ESP32 Pin | Open / pullup | Connected to GND |
| --- | --- | --- | --- |
| Button 1 | GPIO 32 | Inference | Data collection |
| Button 3 | GPIO 33 | Normal air | Oil/cooking fume label |
| Button 5 | GPIO 25 | Normal air | Vehicle exhaust label |
| Button 8 | GPIO 26 | Normal air | Cigarette label |
| LED 1 | GPIO 27 | Cigarette detected in inference mode | Off |

If multiple label buttons are HIGH, current priority is:

```text
cigarette_smoke > vehicle_exhaust > cooking_fume > normal_air
```

Current inference model:

```text
rule_fallback_v0
```

This is a placeholder until trained model parameters are exported to firmware.

## 2.2 GPIO Button Test Sketch

Before testing full firmware, use:

```text
tools/GpioButtonTest/GpioButtonTest.ino
```

Arduino IDE setup:

1. Open the test sketch directly.
2. Upload to ESP32.
3. Open Serial Monitor at `115200`.

Expected:

- GPIO32 connected to GND prints `mode=data_collection` and turns LED 1 on.
- GPIO32 open prints `mode=inference` and turns LED 1 off.
- GPIO33 connected to GND prints `label=cooking_fume`.
- GPIO25 connected to GND prints `label=vehicle_exhaust`.
- GPIO26 connected to GND prints `label=cigarette_smoke`.
- All label inputs open prints `label=normal_air`.

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
{"node_id":"node_01","timestamp":1716000000,"mode":"inference","collection_label":null,"model_version":"rule_fallback_v0","inference_class":"normal_air","cigarette_detected":false,"inference_score":0,"voc_raw":600,"co_raw":660,"voc_mv":620,"co_mv":670,"pm1_0":0,"pm2_5":5,"pm10":5,"temperature":21.1,"humidity":70,"pms_valid":true}
```

Expected backend log:

```text
[data] node_01 mode=inference label=- infer=normal_air ts=... voc=... co=... pm25=... pms=true
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

1. Test button GPIO states in Serial JSON.
2. Confirm Button 1 switches `mode` between `inference` and `data_collection`.
3. Confirm Button 3/5/8 produce `collection_label` values in data collection mode.
4. Confirm LED 1 turns on only in inference mode when `cigarette_detected:true`.
5. Collect 10-20 minutes of normal-air baseline data.
6. Export CSV and inspect ranges for:
   - `voc_raw`
   - `co_raw`
   - `pm2_5`
   - temperature/humidity
7. Replace `rule_fallback_v0` with trained model parameters once available.
8. Add a simple baseline summary endpoint or script.
9. Build a minimal dashboard page:
   - latest values
   - node online/offline
   - simple trend chart
10. Expand dashboard metrics from the current 4 fields to all 7 sensor values:
   - VOC raw
   - CO raw
   - VOC mV
   - CO mV
   - PM2.5
   - temperature
   - humidity
11. Add `ml/scripts/class_counts.py` to print row counts for the 4 training classes:
   - `normal_air`
   - `cooking_fume`
   - `vehicle_exhaust`
   - `cigarette_smoke`
12. Add a `prepare_dataset.py` option to rebalance classes down to the smallest class size.
   - Use the smallest class row count as the target count for every class.
   - For larger classes such as `normal_air`, downsample by evenly spaced interval selection.
13. Later collect labeled scenarios:
   - normal air
   - cigarette smoke or incense substitute
   - cooking fume
   - vehicle exhaust
14. Then train SVM-RBF from exported CSV.

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
- `.pio/`

Before push:

```powershell
git status --short
```

No WiFi password should appear in tracked files.
