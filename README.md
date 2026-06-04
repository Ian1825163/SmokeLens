# SmokeLens

SmokeLens 是一個分散式煙霧偵測專題。這個 repo 目前包含單一 ESP32 感測節點韌體，以及筆電端的資料接收、儲存與匯出 pipeline。

目前資料流：

```text
ESP32 sensor node -> Mosquitto MQTT broker -> Node.js backend -> SQLite -> CSV / API
```

ESP32 負責讀取 MQ-135、MQ-7、PMS5003T，並每 1 秒輸出一筆 JSON。筆電端 backend 訂閱 MQTT 訊息，將資料存進 SQLite，之後可匯出 CSV 做 baseline、規則式判斷與 SVM-RBF 訓練。

## Quick Links

- 測試與收資料步驟：`QUICKSTART.md`
- 目前進度與下一步：`PROGRESS.md`
- ESP32 主程式：`SmokeLens.ino`
- GPIO 開關測試：`tools/GpioButtonTest/GpioButtonTest.ino`
- USB Serial CSV logger：`tools/SerialCsvLogger.ps1`
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
| LED 1 | 香菸偵測警示 | GPIO27 |

按鈕使用 `INPUT_PULLUP`，所以接到 GND 代表 active / 1，放開代表 inactive / 0。

## Firmware Modes

Default 是 inference mode：

- Button 1 放開：`mode = inference`
- Button 1 接 GND：`mode = data_collection`

data collection mode 會依 Button 3/5/8 輸出 `collection_label`。inference mode 會輸出 `inference_class`、`cigarette_detected`、`inference_score`，並在偵測到香菸時讓 GPIO27 LED 亮。

目前 firmware 內的 inference 是 `rule_fallback_v0` 暫時規則，不是最終訓練好的 SVM model。資料欄位已先準備好，方便之後替換成正式模型。

## Backend

backend 使用：

- `mqtt`：訂閱 `smokelens/+/data`
- `express`：提供 local API
- `ws`：預留 dashboard 即時推送
- `sql.js`：寫入 `data/smokelens.sqlite`
- `Leaflet + OpenStreetMap`：顯示固定節點位置與偵測區域

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

## Local Files

這些檔案是本機設定或產生資料，不會 push 到 GitHub：

```text
arduino_secrets.h
backend/.env
backend/node_modules/
data/*.sqlite
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

下一個重點是穩定收集 labeled data：

1. 確認 ESP32 -> MQTT -> backend -> SQLite 全流程穩定。
2. 分別收 normal air、cooking fume、vehicle exhaust、cigarette smoke / 替代煙源資料。
3. 匯出 CSV 做 baseline、feature engineering。
4. 訓練 SVM-RBF。
5. 將訓練結果接回 inference 流程或 backend 分類流程。

詳細指令請直接看 `QUICKSTART.md`。
