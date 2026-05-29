# SmokeLens Cloud MQTT Notes

Use cloud MQTT when ESP32 and the laptop cannot reach each other on the same
LAN, for example on phone hotspot networks. The broker runs on the internet, so
both ESP32 and the backend connect outward to the same MQTT service.

## ESP32

Edit ignored `arduino_secrets.h`:

```cpp
#pragma once

#define SMOKELENS_WIFI_CREDENTIALS                                          \
  {                                                                         \
    {"LabWiFi", "lab_password", "your-cluster.s1.eu.hivemq.cloud"},         \
    {"PhoneHotspot", "hotspot_password", "your-cluster.s1.eu.hivemq.cloud"} \
  }

#define SMOKELENS_MQTT_PORT 8883
#define SMOKELENS_MQTT_USE_TLS true
#define SMOKELENS_MQTT_USERNAME "YOUR_CLOUD_MQTT_USERNAME"
#define SMOKELENS_MQTT_PASSWORD "YOUR_CLOUD_MQTT_PASSWORD"
#define SMOKELENS_NODE_ID "node_01"
```

Serial Monitor should show:

```text
# MQTT transport tls=on port=8883 auth=on
# WiFi connecting to PhoneHotspot (2/2) mqtt=your-cluster.s1.eu.hivemq.cloud
# MQTT connecting to your-cluster.s1.eu.hivemq.cloud:8883 tls=on auth=on
# MQTT connected
```

## Backend

Edit ignored `backend/.env`:

```text
MQTT_URL=mqtts://your-cluster.s1.eu.hivemq.cloud:8883
MQTT_USERNAME=YOUR_CLOUD_MQTT_USERNAME
MQTT_PASSWORD=YOUR_CLOUD_MQTT_PASSWORD
MQTT_TOPIC=smokelens/+/data
HTTP_PORT=3000
```

Run:

```powershell
cd "C:\Users\ADMIN\Documents\NTU\Digital electronics\SmokeLens\backend"
npm.cmd start
```

For cloud MQTT you do not need to run local Mosquitto. Keep the USB serial CSV
logger running if you want a local backup copy of all readings.
