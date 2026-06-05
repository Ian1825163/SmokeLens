#pragma once

// Copy this file to arduino_secrets.h and fill in local values.
// arduino_secrets.h is ignored by git so WiFi passwords are not pushed.

// ESP32 tries these WiFi networks in order. Add/remove rows as needed.
// For personal WiFi, the third argument is the MQTT broker IP for that WiFi.
// For PEAP/WPA2-Enterprise WiFi, use identity, username, password, MQTT broker IP.
// Keep this file as a template only; put real passwords in arduino_secrets.h.
#define SMOKELENS_WIFI_CREDENTIALS                                         \
  {                                                                        \
    SMOKELENS_WIFI_PERSONAL("LAB_WIFI", "LAB_WIFI_PASSWORD",              \
                            "192.168.1.140"),                             \
    SMOKELENS_WIFI_PERSONAL("PHONE_HOTSPOT", "PHONE_HOTSPOT_PASSWORD",    \
                            "172.20.10.3"),                               \
    SMOKELENS_WIFI_PEAP("ntu_peap", "YOUR_NTU_ACCOUNT",                   \
                        "YOUR_NTU_ACCOUNT", "YOUR_NTU_PASSWORD",          \
                        "YOUR_LAPTOP_WIFI_IP_ON_NTU_PEAP")                \
  }

// Backward-compatible single-WiFi format also works:
// #define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
// #define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// Fallback MQTT server used by any WiFi row that omits the third column.
#define SMOKELENS_MQTT_SERVER "YOUR_LAPTOP_WIFI_IP"
#define SMOKELENS_NODE_ID "node_01"
