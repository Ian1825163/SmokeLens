# SmokeLens Quickstart

這份文件是給「要測試 / 收資料時快速照做」用的。背景說明與專案狀態請看 `README.md` 和 `PROGRESS.md`。

## 0. 先選你現在要做什麼

| 目的 | 要開的檔案 / 要跑的服務 | 你應該看到 |
| --- | --- | --- |
| 只測 4 個開關與 LED | `tools/GpioButtonTest/GpioButtonTest.ino` | Serial 印出 0/1，GPIO32 接地時 LED 亮 |
| 測完整 ESP32 感測器但不收進 DB | `SmokeLens.ino` + Arduino Serial Monitor | 每 1 秒印一行 JSON |
| 用 USB Serial 收 CSV | `tools/SerialCsvLogger.ps1` | `data/serial/...csv` 自動分段產生 |
| 穩定收資料進 SQLite | Mosquitto + backend + `SmokeLens.ino` | backend log 出現 `[data] ...`，DB 有資料 |
| 匯出資料做分析 | backend export API 或 `npm run export:csv` | 產生 CSV |

## 0.1 目前實測可用啟動流程

這是目前最推薦的 demo / 收資料流程：MQTT 給 dashboard 即時顯示，USB Serial logger 同時把資料穩定存成 CSV。

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
npm.cmd start
```

macOS / Linux:

```bash
cd backend
npm start
```

Terminal 3: USB Serial CSV logger

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\SerialCsvLogger.ps1 -Port COM11
```

macOS:

- 這個 repo 目前提供的是 PowerShell 版 `tools/SerialCsvLogger.ps1`。
- 如果你的 Mac 已安裝 `pwsh`，可以這樣跑：

```bash
pwsh -File ./tools/SerialCsvLogger.ps1 -Port /dev/cu.usbserial-110
```

- 如果還沒裝 PowerShell，先用 `Mosquitto + backend + SmokeLens.ino` 這條主流程收資料即可。

ESP32 插著筆電供電並跑 `SmokeLens.ino` 後：

- MQTT 成功時，資料會進 backend / SQLite / dashboard。
- Serial logger 會同步把每筆 JSON 存到 `data/serial/`。
- 切換 mode 或 label 時，Serial logger 會自動收尾上一段 CSV 並開新檔。

Dashboard:

```text
http://localhost:3000/
http://localhost:3000/admin
```

## 1. 開關與 LED 規則

所有按鈕 GPIO 都用 ESP32 內建 `INPUT_PULLUP`。

意思是：

```text
接到 GND = 1 / active
不接 GND = 0 / inactive
```

不要把按鈕 GPIO 接到 5V。

| 控制 | GPIO | 接到 GND 時 | 不接 GND 時 |
| --- | --- | --- | --- |
| Button 1 | GPIO32 | data collection | inference |
| Button 3 | GPIO33 | label = `cooking_fume` | normal |
| Button 5 | GPIO25 | label = `vehicle_exhaust` | normal |
| Button 8 | GPIO26 | label = `cigarette_smoke` | normal |
| LED 1 | GPIO27 | 保留給未來本機警示 | 目前完整韌體不使用 |

資料收集模式建議一次只開一個 label switch。若多個 label 同時接地，目前優先順序是：

```text
cigarette_smoke > vehicle_exhaust > cooking_fume > normal_air
```

## 2. 測 GPIO 開關

Arduino IDE:

1. 開 `tools/GpioButtonTest/GpioButtonTest.ino`
2. Board 選 ESP32 Dev Module / ESP32 DevKit V1
3. Upload
4. Serial Monitor 設 `115200 baud`

預期：

```text
GPIO32 接 GND -> button_1_mode_gpio32=1, mode=data_collection, LED 亮
GPIO32 放開  -> button_1_mode_gpio32=0, mode=inference, LED 滅
GPIO33 接 GND -> label=cooking_fume
GPIO25 接 GND -> label=vehicle_exhaust
GPIO26 接 GND -> label=cigarette_smoke
```

## 3. 測完整 ESP32 韌體

Arduino IDE:

1. 開 `SmokeLens.ino`
2. 確認同資料夾有 `arduino_secrets.h`
3. Upload
4. Serial Monitor 設 `115200 baud`

如果還沒要連 MQTT，可以讓 `arduino_secrets.h` 的 broker 保持 placeholder：

```cpp
#define SMOKELENS_MQTT_SERVER "YOUR_LAPTOP_WIFI_IP"
```

這樣 ESP32 仍會每 1 秒在 Serial Monitor 印 JSON，只是不會送到 backend。

典型輸出：

```json
{"node_id":"node_01","timestamp":1716000000,"mode":"inference","collection_label":null,"model_version":"backend_pending","inference_class":null,"cigarette_detected":false,"inference_score":null,"voc_raw":600,"co_raw":660,"voc_mv":620,"co_mv":670,"pm1_0":0,"pm2_5":5,"pm10":5,"temperature":21.1,"humidity":70,"pms_valid":true}
```

ESP32 只送 raw sensor values；目前 `backend_rule_v0` 是 backend 端的暫時規則式推論，不是最後訓練好的 SVM model。

## 4. 設定多組 WiFi

ESP32 現在支援多組 WiFi。開機後會照順序嘗試，連不上就換下一組。

在 ignored 的 `arduino_secrets.h` 裡可以這樣填：

```cpp
#pragma once

#define SMOKELENS_WIFI_CREDENTIALS              \
  {                                             \
    SMOKELENS_WIFI_PERSONAL("LabWiFi", "lab_password", "192.168.1.140"), \
    SMOKELENS_WIFI_PERSONAL("PhoneHotspot", "phone_hotspot_password", "172.20.10.3"), \
    SMOKELENS_WIFI_PEAP("ntu_peap", "YOUR_NTU_ACCOUNT", "YOUR_NTU_ACCOUNT", "YOUR_NTU_PASSWORD", "YOUR_LAPTOP_WIFI_IP_ON_NTU_PEAP") \
  }

#define SMOKELENS_MQTT_SERVER "192.168.1.140"
#define SMOKELENS_NODE_ID "node_01"
```

舊的單組 WiFi 寫法也還能用：

```cpp
#define SMOKELENS_WIFI_SSID "PhoneHotspot"
#define SMOKELENS_WIFI_PASSWORD "phone_hotspot_password"
```

Serial Monitor 會印出目前嘗試哪個 SSID：

```text
# WiFi connecting to PhoneHotspot (2/3)
# WiFi connected ssid=PhoneHotspot ip=192.168.43.22
```

`SMOKELENS_WIFI_PERSONAL` 用於一般 WiFi。`SMOKELENS_WIFI_PEAP` 用於 `ntu_peap` 這類 WPA2-Enterprise/PEAP WiFi，參數依序是 SSID、identity、username、password、該 WiFi 下的筆電 MQTT broker IP。

注意：多組 WiFi 只解決「ESP32 要連哪個 WiFi」。如果 MQTT broker 跑在筆電上，每一列最後的 MQTT IP 要填當下筆電在那個 WiFi 裡的 IP。

## 5. 查筆電 IP

ESP32 的 `SMOKELENS_MQTT_SERVER` 要填「跑 Mosquitto 的筆電 WiFi IP」。

Windows PowerShell:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -like "172.*" } |
  Select-Object IPAddress, InterfaceAlias
```

也可以用：

```powershell
ipconfig
```

macOS:

```bash
ifconfig | grep "inet "
```

如果你知道目前是 Wi-Fi 介面，也可以直接查：

```bash
ipconfig getifaddr en0
```

找 Wi-Fi 的 IPv4，例如：

```text
192.168.1.140
```

然後在 `arduino_secrets.h` 裡填：

```cpp
#define SMOKELENS_MQTT_SERVER "192.168.1.140"
```

ESP32 和筆電必須在同一個 WiFi。

## 6. USB Serial 直接收 CSV

如果 WiFi/MQTT 還不穩，建議先用 USB Serial logger 收資料。這個方式不需要 Mosquitto、不需要 backend，也不用從 Arduino Serial Monitor 複製文字。

重要：Arduino Serial Monitor 要關掉，因為同一個 COM port 不能同時被兩個程式打開。

先列出 serial port：

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\SerialCsvLogger.ps1 -ListPorts
```

macOS:

```bash
ls /dev/cu.*
```

假設 ESP32 是 Windows 的 `COM5` 或 macOS 的 `/dev/cu.usbserial-110`，開始記錄：

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\SerialCsvLogger.ps1 -Port COM5
```

macOS:

```bash
pwsh -File ./tools/SerialCsvLogger.ps1 -Port /dev/cu.usbserial-110
```

輸出會放在：

```text
data/serial/
```

logger 會根據 `mode + label` 自動分段：

```text
data_collection + normal_air       -> *_data_collection_normal_air.csv
data_collection + cooking_fume     -> *_data_collection_cooking_fume.csv
data_collection + vehicle_exhaust  -> *_data_collection_vehicle_exhaust.csv
data_collection + cigarette_smoke  -> *_data_collection_cigarette_smoke.csv
inference mode                     -> *_inference_inference.csv
```

切換時會自動關閉上一段 CSV，並開新檔：

```text
# opened segment: ...\20260528_153012_node_01_data_collection_normal_air.csv
# logged node_01 data_collection/normal_air rows=1
# closed segment: ...\20260528_153012_node_01_data_collection_normal_air.csv rows=18
# opened segment: ...\20260528_153142_node_01_data_collection_cooking_fume.csv
```

所以你的操作方式可以是：

1. GPIO32 接 GND，進入 data collection。
2. label switch 都放開，收 normal air。
3. 切 GPIO33，開始收 cooking fume，上一段 normal CSV 會自動完成。
4. 切 GPIO25 或 GPIO26，會再開新的 label CSV。
5. GPIO32 放開回 inference，上一段 data collection CSV 會自動完成。

按 `Ctrl+C` 停止 logger 時，也會收尾目前這段 CSV。

## 7. 啟動 MQTT pipeline

需要三個視窗：Mosquitto、backend、Arduino Serial Monitor。

### Terminal 1: Mosquitto broker

在 repo 根目錄：

Windows PowerShell:

```powershell
mosquitto -c broker/mosquitto.conf -v
```

macOS / Linux:

```bash
mosquitto -c broker/mosquitto.conf -v
```

確認 port：

Windows PowerShell:

```powershell
netstat -ano | Select-String ":1883"
```

macOS / Linux:

```bash
lsof -nP -iTCP:1883 -sTCP:LISTEN
```

好的狀態會看到：

```text
0.0.0.0:1883
```

如果只看到 `127.0.0.1:1883`，ESP32 可能連不到。先關掉原本的 Mosquitto service/process，再用本 repo 的 `broker/mosquitto.conf` 啟動。

### Terminal 2: Node.js backend

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

PowerShell 可能會擋 `npm.ps1`，所以 Windows PowerShell 建議固定用 `npm.cmd`。

預期 log：

```text
[http] listening on http://localhost:3000
[db] ...\data\smokelens.sqlite
[mqtt] connected mqtt://localhost:1883
[mqtt] subscribed smokelens/+/data
```

### 關閉或重啟 Node.js backend

如果改了 backend 程式、`.env`、dashboard 設定，或遇到 `EADDRINUSE: address already in use 0.0.0.0:3000`，需要先停掉舊的 backend 再重開。

如果 backend 是在目前這個 Terminal 前景執行：

```text
Ctrl+C
```

然後重新啟動：

Windows PowerShell:

```powershell
cd backend
npm.cmd start
```

macOS / Linux:

```bash
cd backend
npm start
```

如果找不到是哪個 Terminal 在跑，可以先查 port `3000`。

Windows PowerShell:

```powershell
netstat -ano | Select-String ":3000"
Stop-Process -Id <PID>
```

macOS / Linux:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
kill <PID>
```

其中 `<PID>` 是佔用 `3000` 的 process id。重啟後再重新整理 dashboard：

```text
http://localhost:3000/
```

### Terminal 3: ESP32

1. 確認 `arduino_secrets.h` 的 WiFi 與 MQTT IP 正確
2. Upload `SmokeLens.ino`
3. 打開 Serial Monitor

ESP32 連線成功時應該看到：

```text
# MQTT connected
```

backend 應該開始出現：

```text
[data] node_01 mode=inference label=- infer=normal_air ts=... voc=... co=... pm25=... pms=true
```

Dashboard:

```text
http://localhost:3000/
http://localhost:3000/admin
```

節點地圖位置在 `backend/.env` 設定：

```text
NODE_LOCATIONS_JSON={"node_01":{"name":"Node 01","lat":25.0173,"lng":121.5398,"radius_m":80}}
```

`lat` / `lng` 改成實際放置地點，`radius_m` 是地圖上圈出的影響範圍半徑。

## 8. API 快速檢查

backend 啟動後：

Windows PowerShell:

```powershell
Invoke-RestMethod http://localhost:3000/api/health
Invoke-RestMethod http://localhost:3000/api/latest
Invoke-RestMethod "http://localhost:3000/api/history?node_id=node_01&limit=20"
```

macOS / Linux:

```bash
curl http://localhost:3000/api/health
curl http://localhost:3000/api/latest
curl "http://localhost:3000/api/history?node_id=node_01&limit=20"
```

瀏覽器可以直接開：

```text
http://localhost:3000/api/export.csv
```

## 9. Dashboard

使用者端：

```text
http://localhost:3000/
```

顯示固定節點位置、目前區域狀態，以及偵測到菸煙時的紅色範圍圈。

開發端：

```text
http://localhost:3000/admin
```

顯示節點在線狀態、模式、label、VOC/CO/PM/溫濕度、inference 結果、趨勢圖與即時 feed。

## 10. 收資料流程建議

收資料前先確認：

1. Mosquitto 正在跑
2. backend 正在跑
3. ESP32 Serial 有 JSON
4. backend 有 `[data] ...`
5. `/api/latest` 看得到最新資料

每 1 秒一筆資料，所以：

```text
10 分鐘約 600 筆
20 分鐘約 1200 筆
```

建議每個情境收 10-20 分鐘，先不要一直切換 label。

| 情境 | Button 1 | Label switch |
| --- | --- | --- |
| 正常空氣 | GPIO32 接 GND | GPIO33/25/26 都放開 |
| 油煙 | GPIO32 接 GND | GPIO33 接 GND |
| 汽車廢氣 | GPIO32 接 GND | GPIO25 接 GND |
| 香菸 / 替代煙源 | GPIO32 接 GND | GPIO26 接 GND |
| 推論測試 | GPIO32 放開 | label switches 可放開 |

收資料時建議另外記錄：

- 地點
- 開始 / 結束時間
- 情境 label
- 風向、距離、是否室內、是否有人經過
- 特殊狀況，例如感測器移動、WiFi 斷線、PM 突然歸零

## 11. 匯出 CSV

API 方式：

```text
http://localhost:3000/api/export.csv
```

命令列方式：

Windows PowerShell:

```powershell
cd backend
npm.cmd run export:csv
```

指定輸出檔名：

Windows PowerShell:

```powershell
npm.cmd run export:csv -- ..\data\smokelens_export.csv
```

macOS / Linux:

```bash
cd backend
npm run export:csv
npm run export:csv -- ../data/smokelens_export.csv
```

`data/*.csv` 會被 git ignore，適合放實驗資料。

## 12. 常見問題

### `npm` 被 PowerShell 擋住

Windows PowerShell 改用：

```powershell
npm.cmd install
npm.cmd start
```

macOS / Linux 直接用：

```bash
npm install
npm start
```

### ESP32 顯示 `MQTT failed, state=-2`

通常是 ESP32 連不到 broker。檢查：

1. ESP32 和筆電是否在同一個 WiFi
2. `SMOKELENS_MQTT_SERVER` 是否等於筆電 WiFi IP
3. Mosquitto 是否正在跑
4. `netstat` 是否看到 `0.0.0.0:1883`
5. Windows Firewall 是否允許 TCP 1883

如果你設定了多組 WiFi，要特別看 Serial Monitor 的這行：

```text
# WiFi connected ssid=... ip=... gateway=... subnet=... rssi=...
```

這個 SSID 必須和筆電目前連的 WiFi 是同一個網路。ESP32 連到別的 WiFi 時，NTP timestamp 仍然可能正常，但 MQTT 會連不到筆電 IP。

MQTT 前也會先做一次 raw TCP 測試：

```text
# MQTT TCP diagnostic ok
```

若是：

```text
# MQTT TCP diagnostic failed
```

代表問題在 TCP 連線層，還沒進到 MQTT 協定。常見原因是手機熱點擋 client-to-client、Windows 防火牆擋 inbound，或 `SMOKELENS_MQTT_SERVER` 不是筆電在同一個網路上的 IP。

MQTT 失敗時，韌體會留在目前 WiFi 繼續重試，不會因為 broker 連不上就自動換 WiFi。若要排除多 WiFi 造成的混亂，可以先在 `arduino_secrets.h` 只留筆電目前所在的那一組 WiFi。

### ESP32 一直換 WiFi，連不上

新版韌體每個 WiFi 會等 20 秒，並印出狀態：

```text
# WiFi waiting status=WL_DISCONNECTED elapsed_s=5
# WiFi connect timeout status=WL_NO_SSID_AVAIL
# WiFi trying next saved network
```

常見原因：

- ESP32 只能連 2.4GHz WiFi，不能連 5GHz-only 熱點。
- iPhone 熱點建議開「最大相容性」。
- Windows 熱點建議設定成 2.4GHz。
- 校園 WiFi 如果需要網頁登入、企業帳號驗證，ESP32 通常不能直接連。
- SSID / password 大小寫要完全一樣。
- ESP32 和筆電要連到同一個 WiFi，MQTT server IP 才會對。

如果要外出穩定測試，建議筆電開 Windows hotspot 給 ESP32 連；筆電本身可以用手機 USB 網路或其他方式上網。這樣 ESP32 只要固定連筆電 hotspot。

### PM 一直是 0

乾淨空氣下 PM 可能真的接近 0。若 `pms_valid:true` 且溫濕度有變化，UART 大致是通的。

### 開關一直是 0

檢查 GPIO 是否真的接到 GND，且 ESP32 GND 和開關共地。這些輸入不是接 5V 測試。

### 開關一直是 1

通常代表該 GPIO 被短路到 GND，或 switch 方向接反。
