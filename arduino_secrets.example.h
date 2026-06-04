#pragma once

// Copy this file to arduino_secrets.h and fill in local values.
// arduino_secrets.h is ignored by git so WiFi passwords are not pushed.

// ESP32 tries these WiFi networks in order. Add/remove rows as needed.
// Third column is the MQTT broker IP for that WiFi.
// Keep this file as a template only; put real passwords in arduino_secrets.h.
#define SMOKELENS_WIFI_CREDENTIALS                                         \
  {                                                                        \
    {"LAB_WIFI", "LAB_WIFI_PASSWORD", "192.168.1.140"},                   \
    {"PHONE_HOTSPOT", "PHONE_HOTSPOT_PASSWORD", "172.20.10.3"},          \
    {"HOME_WIFI", "HOME_WIFI_PASSWORD", "192.168.31.129"}                \
  }

// Backward-compatible single-WiFi format also works:
// #define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
// #define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// Fallback MQTT server used by any WiFi row that omits the third column.
#define SMOKELENS_MQTT_SERVER "YOUR_LAPTOP_WIFI_IP"
#define SMOKELENS_NODE_ID "node_01"
