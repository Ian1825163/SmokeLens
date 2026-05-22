# SmokeLens Sensor Node And Data Pipeline

SmokeLens is a distributed smoke-sensing project. This repository currently
contains the firmware for one ESP32 sensing node and a laptop-side data pipeline
for receiving and storing sensor readings.

Current goal:

```text
ESP32 sensor node -> MQTT broker -> Node.js backend -> SQLite database
```

In simple terms:

- The ESP32 reads sensors.
- The MQTT broker receives messages from the ESP32.
- The Node.js backend subscribes to those messages and organizes them.
- SQLite stores every reading so we can analyze it later.

## Big Picture

```text
+-------------------+
| ESP32 sensor node |
| MQ-135 / MQ-7 /   |
| PMS5003T          |
+---------+---------+
          |
          | publishes JSON by MQTT
          v
+-------------------+
| Mosquitto broker  |
| message relay     |
+---------+---------+
          |
          | backend subscribes
          v
+-------------------+
| Node.js backend   |
| parse / save / API|
+---------+---------+
          |
          | writes rows
          v
+-------------------+
| SQLite database   |
| data/smokelens... |
+-------------------+
```

The ESP32 should stay simple. It should collect raw sensor data and send it out.
More complex work, such as storage, baseline calculation, classification, CSV
export, and dashboard updates, belongs on the laptop/backend side.

## What Each Part Means

### ESP32 Sensor Node

The ESP32 is the physical sensing device. It reads:

- MQ-135 for VOC-like gas response
- MQ-7 for CO-like gas response
- PMS5003T for PM1.0 / PM2.5 / PM10 / temperature / humidity

It produces one JSON reading every 5 seconds.

Example:

```json
{
  "node_id": "node_01",
  "timestamp": 1716000000,
  "mode": "inference",
  "collection_label": null,
  "model_version": "rule_fallback_v0",
  "inference_class": "normal_air",
  "cigarette_detected": false,
  "inference_score": 0.0,
  "voc_raw": 620,
  "co_raw": 681,
  "voc_mv": 502,
  "co_mv": 550,
  "pm1_0": 0,
  "pm2_5": 0,
  "pm10": 1,
  "temperature": 21.2,
  "humidity": 68.2,
  "pms_valid": true,
  "buttons": {
    "mode_data_collection": false,
    "cooking_fume": false,
    "vehicle_exhaust": false,
    "cigarette_smoke": false,
    "led_cigarette": false
  }
}
```

The ESP32 always prints this JSON to Serial Monitor. If WiFi/MQTT is configured,
it also sends the same JSON to the MQTT broker.

### MQTT

MQTT is a lightweight messaging protocol often used in IoT systems.

It has two common actions:

- publish: send a message to a named channel
- subscribe: listen to messages from a named channel

The named channel is called a topic.

SmokeLens topic format:

```text
smokelens/{node_id}/data
```

For `node_01`, the topic is:

```text
smokelens/node_01/data
```

### Mosquitto Broker

Mosquitto is the MQTT broker.

The broker is like a message relay station:

```text
ESP32 publishes message -> Mosquitto receives it -> backend receives a copy
```

The ESP32 does not write directly to a database. It only sends messages to
Mosquitto. This keeps the ESP32 firmware simpler and more reliable.

In this project, Mosquitto runs on the laptop during development/demo.

### Node.js Backend

The Node.js backend is our own program that runs on the laptop.

It does four jobs:

1. Connects to Mosquitto.
2. Subscribes to `smokelens/+/data`.
3. Receives and parses ESP32 JSON.
4. Saves each reading into SQLite.

It also provides HTTP API endpoints for later dashboard and analysis use.

### SQLite Database

SQLite is a lightweight database stored as a normal file.

For this project, the database file is:

```text
data/smokelens.sqlite
```

Unlike MySQL or PostgreSQL, SQLite does not require a separate database server.
The Node.js backend writes directly into this file.

SQLite is useful here because:

- easy to set up
- good enough for demo and data collection
- easy to export later
- Python can read it for analysis

## Repository Layout

```text
SmokeLens/
├─ SmokeLens.ino              ESP32 Arduino firmware
├─ broker/
│  └─ mosquitto.conf          local MQTT broker config
├─ backend/
│  ├─ package.json            Node.js dependencies and scripts
│  ├─ .env.example            backend configuration template
│  ├─ src/
│  │  ├─ server.js            API server + MQTT subscriber
│  │  ├─ db.js                SQLite schema and queries
│  │  ├─ config.js            config loader
│  │  ├─ classifier.js        placeholder classifier
│  │  └─ csv.js               CSV formatting helper
│  └─ scripts/
│     └─ export-csv.js        CSV export command
├─ data/
│  └─ .gitkeep                database folder placeholder
├─ README.md
└─ PROGRESS.md
```

## ESP32 Firmware Setup

Open `SmokeLens.ino` in Arduino IDE.

Install these Arduino libraries:

- `PubSubClient` by Nick O'Leary
- `ArduinoJson` by Benoit Blanchon

Board:

```text
ESP32 Dev Module / ESP32 DevKit V1
```

Serial Monitor:

```text
115200 baud
```

Local WiFi/MQTT settings are kept in `arduino_secrets.h`.

First-time setup:

1. Copy `arduino_secrets.example.h` to `arduino_secrets.h`.
2. Edit `arduino_secrets.h`.
3. Fill in your WiFi SSID, WiFi password, laptop MQTT broker IP, and node ID.

Example:

```cpp
#define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
#define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define SMOKELENS_MQTT_SERVER "192.168.1.23"
#define SMOKELENS_NODE_ID "node_01"
```

`arduino_secrets.h` is ignored by git so passwords are not pushed to GitHub.

Current wiring:

| Signal | ESP32 Pin |
| --- | --- |
| MQ-135 AO via divider | GPIO 36 / VP / ADC1_CH0 |
| MQ-7 AO via divider | GPIO 39 / VN / ADC1_CH3 |
| PMS5003T TXD | GPIO 16 / RXD2 |
| PMS5003T RXD | Not connected |
| PMS5003T SET/RST | 3.3V |

Button/LED wiring for mode control:

| Control | ESP32 Pin | HIGH / Pull Up | LOW / Pull Down |
| --- | --- | --- | --- |
| Button 1 | GPIO 32 | Open / inactive | GND = Data collection mode |
| Button 3 | GPIO 33 | Open / inactive | GND = Label: `cooking_fume` |
| Button 5 | GPIO 25 | Open / inactive | GND = Label: `vehicle_exhaust` |
| Button 8 | GPIO 26 | Open / inactive | GND = Label: `cigarette_smoke` |
| LED 1 | GPIO 27 | On when cigarette detected in inference mode | Off |

The button pins use ESP32 internal pullup mode. A connected-to-GND state means
active and is reported as `1`; open/not connected to GND means inactive and is
reported as `0`.

Mode behavior:

- Default after power-on is inference mode because GPIO32 is pulled up/open.
- In inference mode, ESP32 sends raw sensor data plus inference output.
- In data collection mode, ESP32 sends raw sensor data plus the selected label.
- Label priority, if multiple label buttons are HIGH, is cigarette > vehicle exhaust > cooking fume > normal.

Current firmware inference uses `rule_fallback_v0` thresholds until trained
model parameters are exported into firmware. The JSON field layout is already
prepared for the final trained model output.

## GPIO Button Test Sketch

Before testing the full sensing firmware, you can verify the physical button
inputs with:

```text
tools/GpioButtonTest/GpioButtonTest.ino
```

Open that sketch directly in Arduino IDE and upload it to the ESP32. Serial
Monitor should be set to `115200 baud`.

The test sketch:

- Reads GPIO32 / GPIO33 / GPIO25 / GPIO26 with `INPUT_PULLUP`.
- Prints a heartbeat every second.
- Prints a change line whenever a button/switch changes state.
- Prints `1` when an input is connected to GND, otherwise `0`.
- Mirrors Button 1 / GPIO32 to LED 1 on `GPIO27`, so mode switch and LED wiring can be checked.

Expected behavior:

```text
GPIO32 connected to GND -> mode=data_collection and LED on
GPIO32 open             -> mode=inference and LED off
GPIO33 connected to GND -> label=cooking_fume
GPIO25 connected to GND -> label=vehicle_exhaust
GPIO26 connected to GND -> label=cigarette_smoke
all label buttons open  -> label=normal_air
```

Important: this wiring style connects GPIO to `GND` only. Do not feed ESP32
GPIO pins with `5V`.

Before MQTT is ready, it is okay to leave this in `arduino_secrets.h`:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.x.x"
```

In that state, the ESP32 skips WiFi/MQTT and only prints JSON to Serial Monitor.

## `MQTT_SERVER` Explained

`MQTT_SERVER` should be the IP address of the laptop running Mosquitto.

It is not:

- the WiFi name
- the Node.js backend URL
- the SQLite database path

It is the broker IP.

Example:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.1.23"
```

The ESP32 and laptop must be on the same WiFi network.

To find the laptop IP on Windows PowerShell:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -like "172.*" } |
  Select-Object IPAddress, InterfaceAlias
```

Choose the IP from the WiFi adapter connected to the same network as ESP32.

## Step-By-Step Laptop Setup

This section is for the laptop that will receive and store ESP32 data.

You need to install:

- Node.js LTS: runs the SmokeLens backend.
- Mosquitto: runs the MQTT broker.

### Step 1: Open PowerShell

Open Windows PowerShell or Windows Terminal.

Administrator mode is recommended for installation:

```text
Start menu -> type "PowerShell" -> Run as administrator
```

### Step 2: Install Node.js LTS

Recommended command:

```powershell
winget install -e --id OpenJS.NodeJS.LTS
```

If `winget` does not work, install manually:

1. Go to `https://nodejs.org/en/download`
2. Download the Windows Installer for the LTS version.
3. Run the installer.
4. Keep the default options.
5. Make sure the installer adds Node.js to PATH.

After installing, close PowerShell and open a new one. Then check:

```powershell
node --version
npm.cmd --version
```

Expected result:

```text
v...
...
```

On Windows PowerShell, use `npm.cmd` instead of `npm`. PowerShell may block
`npm.ps1` because of execution policy, while `npm.cmd` works without changing
security settings.

If `node` or `npm.cmd` is still not found, Node.js is probably not in PATH. It
is usually installed here:

```text
C:\Program Files\nodejs
```

You can add it to your user PATH with:

```powershell
$nodePath = "C:\Program Files\nodejs"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $nodePath) {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$nodePath", "User")
}
```

Close and reopen PowerShell after changing PATH.

### Step 3: Install Mosquitto

Recommended command:

```powershell
winget install -e --id EclipseFoundation.Mosquitto
```

If `winget` does not work, install manually:

1. Go to `https://mosquitto.org/download/`
2. Download the Windows installer.
3. Run the installer.
4. Keep the default install location.

After installing, close PowerShell and open a new one. Then check:

```powershell
mosquitto -h
```

If `mosquitto` is not found, it may still be installed correctly but not added
to PATH. It is usually here:

```text
C:\Program Files\mosquitto
```

You can either run it with the full path:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

Or add Mosquitto to your user PATH:

```powershell
$mosquittoPath = "C:\Program Files\mosquitto"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $mosquittoPath) {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$mosquittoPath", "User")
}
```

Close and reopen PowerShell after changing PATH.

### Step 4: Check Your Laptop IP

ESP32 needs the laptop's WiFi IP because Mosquitto will run on the laptop.

Use:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -like "172.*" } |
  Select-Object IPAddress, InterfaceAlias
```

Look for the WiFi interface. Example:

```text
IPAddress      InterfaceAlias
---------      --------------
192.168.1.23   Wi-Fi
```

In this example, the ESP32 firmware should use:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.1.23"
```

If the command above is confusing, this simpler command also works:

```powershell
ipconfig
```

Look for:

```text
Wireless LAN adapter Wi-Fi
IPv4 Address . . . . . . . . . . : 192.168.x.x
```

### Step 5: Start The Data Pipeline

Use three terminals.

### Terminal 1: Start Mosquitto

From the repository root:

```powershell
mosquitto -c broker\mosquitto.conf -v
```

If Mosquitto is not on PATH:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c broker\mosquitto.conf -v
```

This starts the local MQTT broker on port `1883`.

### Terminal 2: Start Node.js Backend

From the repository root:

```powershell
cd backend
npm.cmd install
Copy-Item .env.example .env
npm.cmd start
```

If `npm.cmd install` previously failed, clean the partial install first:

```powershell
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
npm.cmd install
```

The backend defaults are:

```text
MQTT broker: mqtt://localhost:1883
MQTT topic:  smokelens/+/data
HTTP API:    http://localhost:3000
SQLite DB:   data/smokelens.sqlite
```

Expected backend startup messages:

```text
[http] listening on http://localhost:3000
[db] ...\data\smokelens.sqlite
[mqtt] connected mqtt://localhost:1883
[mqtt] subscribed smokelens/+/data
```

### Terminal 3: Optional API Checks

Health check:

```powershell
Invoke-WebRequest http://localhost:3000/api/health
```

Latest readings:

```powershell
Invoke-WebRequest http://localhost:3000/api/latest
```

## Configure ESP32 For MQTT

Once Mosquitto and the backend are running:

1. Find the laptop WiFi IP.
2. Edit `arduino_secrets.h`.
3. Change:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.x.x"
```

to something like:

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.1.23"
```

4. Confirm WiFi settings:

```cpp
#define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
#define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
```

5. Upload the firmware again.
6. Open Serial Monitor.

Expected Serial Monitor messages:

```text
# WiFi connecting to YOUR_WIFI_SSID
# MQTT connecting to 192.168.1.23:1883
# MQTT connected
```

Expected backend message:

```text
[data] node_01 ts=1716000000 voc=620 co=681 pm25=0 pms=true
```

## MQTT Troubleshooting

### ESP32 shows `MQTT failed, state=-2`

In `PubSubClient`, state `-2` means the ESP32 failed to connect to the MQTT
broker. If WiFi is already connected and timestamp uses real NTP time, this is
usually a broker/port/firewall problem, not a sensor problem.

First check whether Mosquitto is listening on the laptop WiFi IP:

```powershell
netstat -ano | Select-String ":1883"
```

Good result:

```text
TCP    0.0.0.0:1883      0.0.0.0:0      LISTENING
```

or:

```text
TCP    192.168.1.140:1883      0.0.0.0:0      LISTENING
```

Problem result:

```text
TCP    127.0.0.1:1883    0.0.0.0:0      LISTENING
```

`127.0.0.1` means Mosquitto only accepts connections from the laptop itself.
ESP32 cannot connect to that from WiFi.

Fix:

1. Stop the currently running Mosquitto window or service.
2. Start Mosquitto using this repository config:

```powershell
mosquitto -c broker\mosquitto.conf -v
```

If Mosquitto is not on PATH:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c broker\mosquitto.conf -v
```

Then check again:

```powershell
netstat -ano | Select-String ":1883"
```

If it still only shows `127.0.0.1:1883`, another Mosquitto process may already
be using the port. Close it first, or stop the Windows service from Services.

Also make sure Windows Firewall allows inbound TCP port `1883` on the current
WiFi network.

### `npm install` fails on `better-sqlite3` or Visual Studio C++

Older backend versions used `better-sqlite3`, which needs a native compiled
binary. On some Windows/Node versions, npm tries to build it locally and then
fails if the Visual Studio C++ toolset is missing.

The current backend uses `sql.js` instead, so it should not need Visual Studio
C++ Build Tools.

Fix the partial install:

```powershell
cd "C:\Users\ADMIN\Documents\NTU\Digital electronics\SmokeLens\backend"
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
npm.cmd install
npm.cmd start
```

Do not worry if the old error mentioned `better-sqlite3`. It was removed from
`backend/package.json`.

## Backend API

When `npm.cmd start` is running:

```text
GET http://localhost:3000/api/health
GET http://localhost:3000/api/latest
GET http://localhost:3000/api/status
GET http://localhost:3000/api/history?node_id=node_01&limit=100
GET http://localhost:3000/api/export.csv
```

Endpoint meaning:

| Endpoint | Purpose |
| --- | --- |
| `/api/health` | Check backend, broker setting, DB path |
| `/api/latest` | Latest reading from each node |
| `/api/status` | Online/offline status for each node |
| `/api/history` | Historical readings |
| `/api/export.csv` | Export readings as CSV |

## Export Data For Analysis

Browser/API export:

```text
http://localhost:3000/api/export.csv
```

Command-line export:

```powershell
cd backend
npm.cmd run export:csv
```

The exported CSV can be used later in Python for:

- baseline analysis
- threshold tuning
- feature engineering
- SVM-RBF training

## Stored Database Fields

SQLite table:

```text
readings
```

Important fields:

| Field | Meaning |
| --- | --- |
| `node_id` | Sensor node name, for example `node_01` |
| `timestamp` | ESP32 timestamp |
| `mode` | `inference` or `data_collection` |
| `collection_label` | Data collection label, for example `normal_air` or `cigarette_smoke` |
| `inference_class` | Firmware inference result in inference mode |
| `cigarette_detected` | Boolean alert result from firmware inference |
| `inference_score` | Firmware inference score |
| `model_version` | Firmware model/version string |
| `voc_raw` | MQ-135 ADC raw value |
| `co_raw` | MQ-7 ADC raw value |
| `voc_mv` | MQ-135 estimated ADC millivolts |
| `co_mv` | MQ-7 estimated ADC millivolts |
| `pm1_0` | PM1.0 concentration |
| `pm2_5` | PM2.5 concentration |
| `pm10` | PM10 concentration |
| `temperature` | PMS5003T temperature |
| `humidity` | PMS5003T relative humidity |
| `pms_valid` | Whether PMS frame passed validation |
| `classification` | Currently `unclassified` |
| `raw_payload` | Original ESP32 JSON |
| `received_at` | Laptop receive time in milliseconds |

## Current Project Status

Confirmed:

- ESP32 firmware uploads successfully.
- Serial Monitor prints JSON.
- MQ-135 and MQ-7 produce non-zero ADC readings.
- PMS5003T UART works because `pms_valid:true` and temperature/humidity are readable.
- PM values can stay `0` in clean air; smoke/dust testing is deferred.

Not yet confirmed:

- Mosquitto installed and running on laptop.
- Node.js installed and running on laptop.
- ESP32 MQTT publish reaches backend.
- SQLite receives real readings.

## Next Milestone

The next milestone is complete when:

```text
Mosquitto running
Node.js backend running
ESP32 MQTT connected
Backend logs incoming data
data/smokelens.sqlite contains readings
/api/export.csv returns useful CSV data
```

After this, the project can move to baseline collection and rule-based
classification.
