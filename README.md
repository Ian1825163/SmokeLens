# SmokeLens

SmokeLens 是一個分散式煙霧偵測專題。這個 repo 目前包含單一 ESP32 感測節點韌體，以及筆電端的資料接收、儲存與匯出 pipeline。

目前資料流：

```text
ESP32 sensor node -> Mosquitto MQTT broker -> Node.js backend -> CSV / API
```

ESP32 負責讀取 MQ-135、MQ-7、PMS5003T，並每 1 秒輸出一筆 raw JSON。筆電端 backend 訂閱 MQTT 訊息，將資料追加到 CSV，並使用訓練完成的 MLP 模型進行 inference。

主要資料檔是 `data/smokelens.csv`，可用 `CSV_PATH` 指定其他位置。

## Quick Links

- 測試與收資料步驟：`QUICKSTART.md`
- 目前進度與下一步：`PROGRESS.md`
- ESP32 主程式：`SmokeLens.ino`
- GPIO 開關測試：`tools/GpioButtonTest/GpioButtonTest.ino`
- USB Serial CSV logger：Windows 使用 `tools/SerialCsvLogger.ps1`，macOS 使用 `tools/serial_csv_logger.py`
- 本地 MQTT 設定：`broker/mosquitto.conf`
- Node.js backend：`backend/`
- 使用者 Dashboard：`http://localhost:3000/`
- 開發端 Dashboard：`http://localhost:3000/admin`

## Hardware

| 元件 | 型號 / 用途 | ESP32 |
| --- | --- | --- |
| MQ-135 | VOC 類比感測 | GPIO36 / ADC1_CH0 |
| MQ-7 | CO 類比感測 | GPIO39 / ADC1_CH3 |
| PMS5003T | PM1.0/2.5/10、溫濕度 | TX -> GPIO16 / UART2 RX |
| Button 1 | 模式切換 | GPIO32 |
| Button 3 | 油煙 label | GPIO33 |
| Button 5 | 汽車廢氣 label | GPIO25 |
| Button 8 | 香菸 label | GPIO26 |
| LED 1 | 保留給未來本機警示 | GPIO27 |

按鈕使用 `INPUT_PULLUP`，所以接到 GND 代表 active / 1，放開代表 inactive / 0。

## Firmware Modes

Default 是 inference mode：

- Button 1 放開：`mode = inference`
- Button 1 接 GND：`mode = data_collection`

data collection mode 會依 Button 3/5/8 輸出 `collection_label`。inference mode
由 ESP32 使用本機模型產生 `inference_class`、`cigarette_detected` 與
`inference_score`，並連同 raw sensor values 上傳。backend 收到任何模式的有效感測
資料後都會使用同一份模型重新計算推論，確保 CSV、API 與 dashboard 採用正式模型
結果，而不依賴裝置 payload 中既有的推論欄位。data collection mode 會同時保留
人工 `collection_label` 與模型的 `inference_class` / `inference_score`，方便比較標籤
和預測結果。

目前正式採用 seed 46、epoch 13 的 `7 -> 2 -> 4` ReLU MLP，版本為
`smokelens_mlp_7x2x4_seed46`：

- 對外模型名稱：`EmberLens 1`
- 內部模型識別：`emberlens_1_seed46`
- 推論版本識別：`smokelens_mlp_7x2x4_seed46`

- Input：`voc_mv`、`co_mv`、`pm1_0`、`pm2_5`、`pm10`、`temperature`、`humidity`
- Hidden layer：2 neurons + ReLU
- Output：4 classes + softmax

目前產品輸出採二分類模式，只顯示 `normal_air` 或 `cigarette_smoke`。底層模型仍計算
四類 softmax，但正式判斷只使用 `cigarette_smoke` 機率；機率達 0.5 時輸出
`cigarette_smoke`，否則輸出 `normal_air`。`cooking_fume` 與 `vehicle_exhaust`
暫時不作為 inference 結果顯示。

另外設有 PM safety guard：`PM1.0 >= 10`、`PM2.5 >= 15`、`PM10 >= 15`
三項中任兩項達標時，會直接判定為 `cigarette_smoke`，避免模型將明顯升高的
粒狀物誤判為 normal air。

模型輸入會先使用 checkpoint 中的 mean/std 標準化。ESP32 與 backend 使用相同的
mean/std、hidden/output weights 與 bias。`inference_score` 是預測類別的 softmax
probability，`cigarette_detected` 只在預測為 `cigarette_smoke` 時成立。

此模型以 validation macro F1 選出，評估結果如下：

- Validation macro F1：`0.9833`
- Test macro F1：`0.9933`
- Test accuracy：`99.35%`

來源 checkpoint：

```text
ml/runs/20260615-060651/seed-46/model.pt
```

模型檔案位於：

```text
ml/models/smokelens_linear.pt
ml/models/smokelens_linear.json
ml/models/smokelens_linear_metadata.json
```

Node.js backend 使用 JSON 版本做原生 inference，不需要在執行環境安裝
Python 或 PyTorch。可透過 `MODEL_PATH` 指向其他相容模型 JSON。

## Backend

backend 使用：

- `mqtt`：訂閱 `smokelens/+/data`
- `express`：提供 local API
- `ws`：預留 dashboard 即時推送
- Node.js `fs`：追加寫入 `data/smokelens.csv`
- `Leaflet + OpenStreetMap`：顯示固定節點位置與偵測區域
- `ml/models/smokelens_linear.json`：四類 `7 -> 2 -> 4` ReLU MLP inference 模型

常用 API：

```text
GET http://localhost:3000/api/health
GET http://localhost:3000/api/latest
GET http://localhost:3000/api/status
GET http://localhost:3000/api/history?node_id=node_01&limit=100
GET http://localhost:3000/api/export.csv
```

Dashboard:

```text
GET http://localhost:3000/
GET http://localhost:3000/admin
```

## Quick Start

先開 terminal，切到 repo 根目錄：

```bash
cd /path/to/SmokeLens
```

Terminal 1: Mosquitto broker

Windows PowerShell:

```powershell
mosquitto -c broker/mosquitto.conf -v
```

如果 `mosquitto` 不在 PATH，再改用安裝路徑：

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c broker\mosquitto.conf -v
```

macOS / Linux:

```bash
mosquitto -c broker/mosquitto.conf -v
```

Terminal 2: backend + dashboard

Windows PowerShell:

```powershell
cd backend
npm.cmd install
Copy-Item .env.example .env -Force
npm.cmd start
```

macOS / Linux:

```bash
cd backend
cp -n .env.example .env
npm install
npm start
```

Terminal 3: ESP32

1. 確認 `arduino_secrets.h` 的 WiFi 與 MQTT IP 正確
2. Upload `SmokeLens.ino`
3. 打開 Serial Monitor，設 `115200 baud`

常用檢查：

Windows PowerShell:

```powershell
Invoke-RestMethod http://localhost:3000/api/health
Invoke-RestMethod http://localhost:3000/api/latest
```

macOS / Linux:

```bash
curl http://localhost:3000/api/health
curl http://localhost:3000/api/latest
```

更完整的跨平台收資料步驟請看 `QUICKSTART.md`。

## Local Files

這些檔案是本機設定或產生資料，不會 push 到 GitHub：

```text
arduino_secrets.h
backend/.env
backend/node_modules/
data/*.csv
data/serial/
.pio/
```


第一次設定 ESP32 WiFi/MQTT 時，複製：

```text
arduino_secrets.example.h -> arduino_secrets.h
```

Multi-WiFi MQTT mapping is supported. Each WiFi row can include a third value
for the Mosquitto broker IP used on that network:

```cpp
#define SMOKELENS_WIFI_CREDENTIALS                                \
  {                                                               \
    {"LabWiFi", "lab_password", "192.168.1.140"},                 \
    {"PhoneHotspot", "phone_hotspot_password", "172.20.10.3"}    \
  }
```

Rows with only SSID/password still work and fall back to
`SMOKELENS_MQTT_SERVER`.

然後填入 WiFi SSID、password、筆電 MQTT broker IP 和 node ID。韌體支援多組 WiFi，會依序嘗試 `SMOKELENS_WIFI_CREDENTIALS` 裡的 SSID；舊的單組 `SMOKELENS_WIFI_SSID` / `SMOKELENS_WIFI_PASSWORD` 寫法也仍可用。

## Current Focus

下一個重點是收集更多獨立 session，驗證模型跨時間與場景的泛化：

1. 確認 ESP32 -> MQTT -> backend -> CSV 全流程穩定。
2. 分別收 normal air、cooking fume、vehicle exhaust、cigarette smoke / 替代煙源資料。
3. 以完整 session 作 train/validation/test 切分。
4. 監測 production inference 的 false positive 與 false negative。
5. 新模型通過跨 session 評估後再替換 `MODEL_PATH`。

詳細指令請直接看 `QUICKSTART.md`。
