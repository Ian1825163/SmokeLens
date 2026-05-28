#pragma once

// Copy this file to arduino_secrets.h and fill in local values.
// arduino_secrets.h is ignored by git so WiFi passwords are not pushed.

// ESP32 tries these WiFi networks in order. Add/remove rows as needed.
// Keep this file as a template only; put real passwords in arduino_secrets.h.
#define SMOKELENS_WIFI_CREDENTIALS            \
  {                                           \
    {"YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD"}, \
    {"YOUR_PHONE_HOTSPOT", "YOUR_PASSWORD"}   \
  }

// Backward-compatible single-WiFi format also works:
// #define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
// #define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

#define SMOKELENS_MQTT_SERVER "YOUR_LAPTOP_WIFI_IP"
#define SMOKELENS_NODE_ID "node_01"
