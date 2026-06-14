/*
  SmokeLens ESP32 sensor node

  Arduino IDE libraries to install:
  - PubSubClient by Nick O'Leary
  - ArduinoJson by Benoit Blanchon

  Board:
  - ESP32 Dev Module / ESP32 DevKit V1
*/

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>
#include <time.h>

#if __has_include("arduino_secrets.h")
#include "arduino_secrets.h"
#endif

#ifndef SMOKELENS_WIFI_SSID
#define SMOKELENS_WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef SMOKELENS_WIFI_PASSWORD
#define SMOKELENS_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

#ifndef SMOKELENS_MQTT_SERVER
#define SMOKELENS_MQTT_SERVER "192.168.x.x"
#endif

#ifndef SMOKELENS_NODE_ID
#define SMOKELENS_NODE_ID "node_01"
#endif

#ifndef SMOKELENS_WIFI_CREDENTIALS
#define SMOKELENS_WIFI_CREDENTIALS \
  { { SMOKELENS_WIFI_SSID, SMOKELENS_WIFI_PASSWORD } }
#endif

// =========================
// User configuration
// =========================
struct WiFiCredential {
  const char *ssid;
  const char *password;
  const char *mqttServer;
};

struct PMS5003TData {
  bool valid;
  uint16_t pm1_0;
  uint16_t pm2_5;
  uint16_t pm10;
  float temperature;
  float humidity;
};

enum class NodeMode {
  Inference,
  DataCollection
};

enum class CollectionLabel {
  NormalAir,
  CookingFume,
  VehicleExhaust,
  CigaretteSmoke
};

struct ButtonSnapshot {
  bool dataCollectionMode;
  bool cookingFume;
  bool vehicleExhaust;
  bool cigaretteSmoke;
};

struct LocalInferenceResult {
  const char *className;
  float score;
  bool cigaretteDetected;
};

const WiFiCredential WIFI_CREDENTIALS[] = SMOKELENS_WIFI_CREDENTIALS;
const size_t WIFI_CREDENTIAL_COUNT =
    sizeof(WIFI_CREDENTIALS) / sizeof(WIFI_CREDENTIALS[0]);

const char *DEFAULT_MQTT_SERVER = SMOKELENS_MQTT_SERVER;
const char *MQTT_SERVER = SMOKELENS_MQTT_SERVER;
const uint16_t MQTT_PORT = 1883;
const char *NODE_ID = SMOKELENS_NODE_ID;

// Set to false for first wiring tests if WiFi/MQTT is not ready yet.
const bool ENABLE_WIFI_MQTT = true;

// For a quick wiring test you can reduce this to 20000UL.
const uint32_t MQ_WARMUP_MS = 20000UL;

// =========================
// Pin configuration
// =========================
const uint8_t MQ135_PIN = 36;  // VOC, ADC1_CH0, VP
const uint8_t MQ7_PIN = 39;    // CO,  ADC1_CH3, VN

const int PMS_RX_PIN = 16;  // ESP32 UART2 RX, connect to PMS5003T TX
const int PMS_TX_PIN = 17;  // Not connected, kept for UART2 init

const uint8_t MODE_BUTTON_PIN = 32;       // GND=data collection, open=inference
const uint8_t COOKING_BUTTON_PIN = 33;    // GND=cooking fume label
const uint8_t EXHAUST_BUTTON_PIN = 25;    // GND=vehicle exhaust label
const uint8_t CIGARETTE_BUTTON_PIN = 26;  // GND=cigarette smoke label

const uint8_t CIGARETTE_LED_PIN = 27;

// =========================
// Runtime constants
// =========================
const uint32_t SERIAL_BAUD = 115200;
const uint32_t PMS_BAUD = 9600;
const uint32_t SAMPLE_INTERVAL_MS = 1000UL;
const uint32_t WIFI_CONNECT_TIMEOUT_MS = 6000UL;
const uint32_t WIFI_STATUS_PRINT_INTERVAL_MS = 2000UL;
const uint32_t MQTT_RETRY_INTERVAL_MS = 5000UL;
const uint32_t PMS_READ_TIMEOUT_MS = 1500UL;

const uint8_t ADC_SAMPLE_COUNT = 10;
const uint16_t PMS_FRAME_SIZE = 32;
const uint16_t PMS_PAYLOAD_LENGTH = 28;

// =========================
// Model Configuration & Helper
// =========================
const char *INFERENCE_MODEL_VERSION = "smokelens_mlp_7x2x4_seed46";
const int MODEL_NUM_FEATURES = 7;
const int MODEL_NUM_HIDDEN = 2;
const int MODEL_NUM_CLASSES = 4;

const char *MODEL_CLASS_LABELS[MODEL_NUM_CLASSES] = {
  "normal_air",
  "cooking_fume",
  "vehicle_exhaust",
  "cigarette_smoke"
};

const float MODEL_FEATURE_MEAN[MODEL_NUM_FEATURES] = {
  2330.2529296875f, 2951.18310546875f, 21.832805633544922f,
  40.26411819458008f, 45.935150146484375f, 25.602771759033203f,
  62.662818908691406f
};

const float MODEL_FEATURE_STD[MODEL_NUM_FEATURES] = {
  138.3492889404297f, 150.11744689941406f, 60.79207229614258f,
  101.38980102539062f, 123.67350769042969f, 1.9774922132492065f,
  5.921822547912598f
};

const float MODEL_HIDDEN_WEIGHTS[MODEL_NUM_HIDDEN][MODEL_NUM_FEATURES] = {
  {-1.0365674495697021f, -1.5532931089401245f, 0.17726042866706848f,
   -0.3885403275489807f, 0.3419538140296936f, -1.126071810722351f,
   -1.215725302696228f},
  {-1.1333826780319214f, -1.2400188446044922f, -0.9836373925209045f,
   -0.4688897430896759f, -1.2161506414413452f, 1.4170540571212769f,
   -0.6437466740608215f}
};

const float MODEL_HIDDEN_BIAS[MODEL_NUM_HIDDEN] = {
  0.041490331292152405f, 0.914577305316925f
};

const float MODEL_OUTPUT_WEIGHTS[MODEL_NUM_CLASSES][MODEL_NUM_HIDDEN] = {
  {0.6457064747810364f, 1.0696167945861816f},
  {-1.034229040145874f, -1.1338354349136353f},
  {-2.2867629528045654f, 1.5423558950424194f},
  {1.6596026420593262f, -1.191158413887024f}
};

const float MODEL_OUTPUT_BIAS[MODEL_NUM_CLASSES] = {
  -1.7766072750091553f, 1.4398103952407837f, -0.48451095819473267f,
  -0.9452698230743408f
};

LocalInferenceResult runLocalInference(float voc_mv, float co_mv, float pm1_0,
                                       float pm2_5, float pm10, float temp,
                                       float humid) {
  float inputs[MODEL_NUM_FEATURES] = { voc_mv, co_mv, pm1_0, pm2_5, pm10, temp, humid };
  float standardized[MODEL_NUM_FEATURES];

  for (int i = 0; i < MODEL_NUM_FEATURES; i++) {
    standardized[i] = (inputs[i] - MODEL_FEATURE_MEAN[i]) / MODEL_FEATURE_STD[i];
  }

  float hidden[MODEL_NUM_HIDDEN];
  for (int h = 0; h < MODEL_NUM_HIDDEN; h++) {
    hidden[h] = MODEL_HIDDEN_BIAS[h];
    for (int f = 0; f < MODEL_NUM_FEATURES; f++) {
      hidden[h] += MODEL_HIDDEN_WEIGHTS[h][f] * standardized[f];
    }
    if (hidden[h] < 0.0f) {
      hidden[h] = 0.0f;
    }
  }

  float logits[MODEL_NUM_CLASSES];
  float maxLogit = -1e9f;
  for (int c = 0; c < MODEL_NUM_CLASSES; c++) {
    logits[c] = MODEL_OUTPUT_BIAS[c];
    for (int h = 0; h < MODEL_NUM_HIDDEN; h++) {
      logits[c] += MODEL_OUTPUT_WEIGHTS[c][h] * hidden[h];
    }
    if (logits[c] > maxLogit) {
      maxLogit = logits[c];
    }
  }

  float exps[MODEL_NUM_CLASSES];
  float sumExp = 0.0f;
  for (int c = 0; c < MODEL_NUM_CLASSES; c++) {
    exps[c] = expf(logits[c] - maxLogit);
    sumExp += exps[c];
  }

  int bestIndex = 0;
  float bestProb = 0.0f;
  for (int c = 0; c < MODEL_NUM_CLASSES; c++) {
    float prob = exps[c] / sumExp;
    if (prob > bestProb) {
      bestProb = prob;
      bestIndex = c;
    }
  }
  
  LocalInferenceResult res;
  res.className = MODEL_CLASS_LABELS[bestIndex];
  res.score = bestProb;
  res.cigaretteDetected = (bestIndex == 3);
  return res;
}


HardwareSerial pmsSerial(2);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

char mqttTopic[96];
uint32_t lastWiFiAttemptMs = 0;
uint32_t lastWiFiStatusPrintMs = 0;
uint32_t lastMQTTAttemptMs = 0;
uint32_t lastSampleMs = 0;
int currentWiFiCredentialIndex = -1;
bool timeConfigured = false;
bool wifiWasConnected = false;
bool mqttTcpDiagnosticPrinted = false;



const char *modeToString(NodeMode mode) {
  return mode == NodeMode::DataCollection ? "data_collection" : "inference";
}

const char *labelToString(CollectionLabel label) {
  switch (label) {
    case CollectionLabel::CookingFume:
      return "cooking_fume";
    case CollectionLabel::VehicleExhaust:
      return "vehicle_exhaust";
    case CollectionLabel::CigaretteSmoke:
      return "cigarette_smoke";
    case CollectionLabel::NormalAir:
    default:
      return "normal_air";
  }
}

CollectionLabel selectedCollectionLabel(const ButtonSnapshot &buttons) {
  if (buttons.cigaretteSmoke) {
    return CollectionLabel::CigaretteSmoke;
  }
  if (buttons.vehicleExhaust) {
    return CollectionLabel::VehicleExhaust;
  }
  if (buttons.cookingFume) {
    return CollectionLabel::CookingFume;
  }
  return CollectionLabel::NormalAir;
}

void setupButtonsAndLED() {
  pinMode(MODE_BUTTON_PIN, INPUT_PULLUP);
  pinMode(COOKING_BUTTON_PIN, INPUT_PULLUP);
  pinMode(EXHAUST_BUTTON_PIN, INPUT_PULLUP);
  pinMode(CIGARETTE_BUTTON_PIN, INPUT_PULLUP);

  pinMode(CIGARETTE_LED_PIN, OUTPUT);
  digitalWrite(CIGARETTE_LED_PIN, LOW);
}

ButtonSnapshot readButtons() {
  ButtonSnapshot buttons;
  buttons.dataCollectionMode = digitalRead(MODE_BUTTON_PIN) == LOW;
  buttons.cookingFume = digitalRead(COOKING_BUTTON_PIN) == LOW;
  buttons.vehicleExhaust = digitalRead(EXHAUST_BUTTON_PIN) == LOW;
  buttons.cigaretteSmoke = digitalRead(CIGARETTE_BUTTON_PIN) == LOW;
  return buttons;
}

bool mqttServerValueLooksValid(const char *server) {
  return server != nullptr && strlen(server) > 0 &&
         strcmp(server, "192.168.x.x") != 0 &&
         strcmp(server, "YOUR_LAPTOP_WIFI_IP") != 0;
}

const char *mqttServerForCredential(const WiFiCredential &credential) {
  if (mqttServerValueLooksValid(credential.mqttServer)) {
    return credential.mqttServer;
  }
  return DEFAULT_MQTT_SERVER;
}

bool wifiCredentialLooksValid(const WiFiCredential &credential) {
  return strlen(credential.ssid) > 0 &&
         strcmp(credential.ssid, "YOUR_SSID") != 0 &&
         strcmp(credential.ssid, "YOUR_WIFI_SSID") != 0 &&
         strcmp(credential.password, "YOUR_PASSWORD") != 0 &&
         strcmp(credential.password, "YOUR_WIFI_PASSWORD") != 0;
}

bool wifiCredentialConfigLooksValid(const WiFiCredential &credential) {
  return wifiCredentialLooksValid(credential) &&
         mqttServerValueLooksValid(mqttServerForCredential(credential));
}

int nextValidWiFiCredentialIndex() {
  if (WIFI_CREDENTIAL_COUNT == 0) {
    return -1;
  }

  const size_t baseIndex = currentWiFiCredentialIndex < 0
                               ? WIFI_CREDENTIAL_COUNT - 1
                               : static_cast<size_t>(currentWiFiCredentialIndex);

  for (size_t offset = 1; offset <= WIFI_CREDENTIAL_COUNT; ++offset) {
    const size_t candidateIndex = (baseIndex + offset) % WIFI_CREDENTIAL_COUNT;
    if (wifiCredentialConfigLooksValid(WIFI_CREDENTIALS[candidateIndex])) {
      return static_cast<int>(candidateIndex);
    }
  }

  return -1;
}

bool wifiConfigLooksValid() {
  return ENABLE_WIFI_MQTT && nextValidWiFiCredentialIndex() >= 0;
}

void printWiFiCredentialSummary(const WiFiCredential &credential) {
  Serial.print(credential.ssid);
  Serial.print(" (");
  Serial.print(currentWiFiCredentialIndex + 1);
  Serial.print("/");
  Serial.print(WIFI_CREDENTIAL_COUNT);
  Serial.print(")");
}

bool scanWiFiForCredential(const WiFiCredential &credential) {
  Serial.print("# WiFi scanning for ");
  printWiFiCredentialSummary(credential);
  Serial.println();

  const int networkCount = WiFi.scanNetworks(false, true);
  if (networkCount < 0) {
    Serial.print("# WiFi scan failed code=");
    Serial.println(networkCount);
    return true;
  }

  int matches = 0;
  int bestRssi = -999;
  int bestChannel = 0;

  for (int i = 0; i < networkCount; ++i) {
    if (WiFi.SSID(i) != credential.ssid) {
      continue;
    }

    matches += 1;
    if (WiFi.RSSI(i) > bestRssi) {
      bestRssi = WiFi.RSSI(i);
      bestChannel = WiFi.channel(i);
    }
  }

  Serial.print("# WiFi scan result for ");
  printWiFiCredentialSummary(credential);
  Serial.print(" visible=");
  Serial.print(matches > 0 ? "yes" : "no");
  Serial.print(" matches=");
  Serial.print(matches);
  Serial.print(" scanned=");
  Serial.print(networkCount);
  if (matches > 0) {
    Serial.print(" best_rssi=");
    Serial.print(bestRssi);
    Serial.print(" channel=");
    Serial.print(bestChannel);
  }
  Serial.println();
  WiFi.scanDelete();

  return matches > 0;
}

void printNetworkDetails() {
  Serial.print("# WiFi connected ssid=");
  Serial.print(WiFi.SSID());
  Serial.print(" ip=");
  Serial.print(WiFi.localIP());
  Serial.print(" gateway=");
  Serial.print(WiFi.gatewayIP());
  Serial.print(" subnet=");
  Serial.print(WiFi.subnetMask());
  Serial.print(" rssi=");
  Serial.print(WiFi.RSSI());
  Serial.print(" mqtt_server=");
  Serial.println(MQTT_SERVER);
}

bool testMQTTTcpConnect() {
  WiFiClient testClient;
  const bool connected = testClient.connect(MQTT_SERVER, MQTT_PORT);
  if (connected) {
    testClient.stop();
  }
  return connected;
}

const char *wifiStatusToString(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:
      return "WL_IDLE_STATUS";
    case WL_NO_SSID_AVAIL:
      return "WL_NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED:
      return "WL_SCAN_COMPLETED";
    case WL_CONNECTED:
      return "WL_CONNECTED";
    case WL_CONNECT_FAILED:
      return "WL_CONNECT_FAILED";
    case WL_CONNECTION_LOST:
      return "WL_CONNECTION_LOST";
    case WL_DISCONNECTED:
      return "WL_DISCONNECTED";
    default:
      return "WL_UNKNOWN";
  }
}

uint16_t readU16BE(const uint8_t *buffer, size_t index) {
  return (static_cast<uint16_t>(buffer[index]) << 8) | buffer[index + 1];
}

bool readByteWithTimeout(Stream &stream, uint8_t &value, uint32_t startMs,
                         uint32_t timeoutMs) {
  while (millis() - startMs < timeoutMs) {
    int incoming = stream.read();
    if (incoming >= 0) {
      value = static_cast<uint8_t>(incoming);
      return true;
    }
    delay(1);
  }
  return false;
}

void setupADC() {
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  analogSetPinAttenuation(MQ135_PIN, ADC_11db);
  analogSetPinAttenuation(MQ7_PIN, ADC_11db);
}

uint16_t readADCAverage(uint8_t pin) {
  uint32_t sum = 0;

  for (uint8_t i = 0; i < ADC_SAMPLE_COUNT; ++i) {
    sum += analogRead(pin);
    delay(5);
  }

  return static_cast<uint16_t>((sum + ADC_SAMPLE_COUNT / 2) / ADC_SAMPLE_COUNT);
}

uint16_t readMilliVoltAverage(uint8_t pin) {
  uint32_t sum = 0;

  for (uint8_t i = 0; i < ADC_SAMPLE_COUNT; ++i) {
    sum += analogReadMilliVolts(pin);
    delay(5);
  }

  return static_cast<uint16_t>((sum + ADC_SAMPLE_COUNT / 2) / ADC_SAMPLE_COUNT);
}

void drainPMSInput() {
  while (pmsSerial.available() > 0) {
    pmsSerial.read();
  }
}

bool readPMSFrame(PMS5003TData &data, uint32_t timeoutMs) {
  uint8_t frame[PMS_FRAME_SIZE] = {0};
  uint32_t startMs = millis();

  while (millis() - startMs < timeoutMs) {
    uint8_t firstByte = 0;
    if (!readByteWithTimeout(pmsSerial, firstByte, startMs, timeoutMs)) {
      return false;
    }

    if (firstByte != 0x42) {
      continue;
    }

    uint8_t secondByte = 0;
    if (!readByteWithTimeout(pmsSerial, secondByte, startMs, timeoutMs)) {
      return false;
    }

    if (secondByte != 0x4D) {
      continue;
    }

    frame[0] = firstByte;
    frame[1] = secondByte;

    for (uint8_t i = 2; i < PMS_FRAME_SIZE; ++i) {
      if (!readByteWithTimeout(pmsSerial, frame[i], startMs, timeoutMs)) {
        return false;
      }
    }

    if (readU16BE(frame, 2) != PMS_PAYLOAD_LENGTH) {
      continue;
    }

    uint16_t checksum = 0;
    for (uint8_t i = 0; i < PMS_FRAME_SIZE - 2; ++i) {
      checksum += frame[i];
    }

    if (checksum != readU16BE(frame, PMS_FRAME_SIZE - 2)) {
      continue;
    }

    data.valid = true;
    data.pm1_0 = readU16BE(frame, 10);  // Atmospheric PM1.0
    data.pm2_5 = readU16BE(frame, 12);  // Atmospheric PM2.5
    data.pm10 = readU16BE(frame, 14);   // Atmospheric PM10

    // PMS5003T keeps temperature and humidity at data 11 / data 12.
    data.temperature = static_cast<int16_t>(readU16BE(frame, 24)) / 10.0f;
    data.humidity = readU16BE(frame, 26) / 10.0f;
    return true;
  }

  return false;
}

PMS5003TData readPMS5003T() {
  PMS5003TData latest = {false, 0, 0, 0, 0.0f, 0.0f};
  uint32_t startMs = millis();

  do {
    uint32_t elapsedMs = millis() - startMs;
    if (elapsedMs >= PMS_READ_TIMEOUT_MS) {
      break;
    }

    PMS5003TData candidate = {false, 0, 0, 0, 0.0f, 0.0f};
    if (!readPMSFrame(candidate, PMS_READ_TIMEOUT_MS - elapsedMs)) {
      break;
    }

    latest = candidate;
  } while (pmsSerial.available() >= PMS_FRAME_SIZE);

  return latest;
}

void startWiFiAttempt() {
  for (size_t attempt = 0; attempt < WIFI_CREDENTIAL_COUNT; ++attempt) {
    const int nextIndex = nextValidWiFiCredentialIndex();
    if (nextIndex < 0) {
      Serial.println("# WiFi skipped: update WiFi credentials and MQTT servers first");
      return;
    }

    currentWiFiCredentialIndex = nextIndex;
    const WiFiCredential &credential =
        WIFI_CREDENTIALS[currentWiFiCredentialIndex];
    MQTT_SERVER = mqttServerForCredential(credential);

    if (mqtt.connected()) {
      mqtt.disconnect();
    }
    mqtt.setServer(MQTT_SERVER, MQTT_PORT);
    WiFi.disconnect(false);

    if (!scanWiFiForCredential(credential)) {
      Serial.println("# WiFi SSID not visible; attempting direct connection anyway");
    }

    WiFi.begin(credential.ssid, credential.password);
    lastWiFiAttemptMs = millis();
    lastWiFiStatusPrintMs = lastWiFiAttemptMs;
    mqttTcpDiagnosticPrinted = false;
    wifiWasConnected = false;

    Serial.print("# WiFi connecting to ");
    printWiFiCredentialSummary(credential);
    Serial.print(" mqtt=");
    Serial.println(MQTT_SERVER);
    return;
  }

  lastWiFiAttemptMs = millis();
  lastWiFiStatusPrintMs = lastWiFiAttemptMs;
  Serial.println("# WiFi skipped: no configured SSID is currently visible");
}

void beginWiFi() {
  if (!ENABLE_WIFI_MQTT) {
    Serial.println("# WiFi/MQTT skipped: disabled in firmware");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  startWiFiAttempt();
}

void maintainWiFi() {
  if (!wifiConfigLooksValid()) {
    return;
  }

  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      mqttTcpDiagnosticPrinted = false;
      printNetworkDetails();
    }
    return;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    timeConfigured = false;
    Serial.println("# WiFi disconnected");
  }

  const uint32_t elapsedMs = millis() - lastWiFiAttemptMs;

  if (millis() - lastWiFiStatusPrintMs >= WIFI_STATUS_PRINT_INTERVAL_MS) {
    lastWiFiStatusPrintMs = millis();
    const WiFiCredential &credential = WIFI_CREDENTIALS[currentWiFiCredentialIndex];
    Serial.print("# WiFi waiting for ");
    printWiFiCredentialSummary(credential);
    Serial.print(" status=");
    Serial.print(wifiStatusToString(WiFi.status()));
    Serial.print(" elapsed_s=");
    Serial.println(elapsedMs / 1000UL);
  }

  if (elapsedMs < WIFI_CONNECT_TIMEOUT_MS) {
    return;
  }

  const WiFiCredential &credential = WIFI_CREDENTIALS[currentWiFiCredentialIndex];
  Serial.print("# WiFi connect timeout for ");
  printWiFiCredentialSummary(credential);
  Serial.print(" status=");
  Serial.println(wifiStatusToString(WiFi.status()));
  Serial.println("# WiFi trying next saved network");
  startWiFiAttempt();
}

void setupTimeIfNeeded() {
  if (!wifiConfigLooksValid() || timeConfigured || WiFi.status() != WL_CONNECTED) {
    return;
  }

  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.nist.gov");

  time_t now = time(nullptr);
  uint32_t startedMs = millis();
  while (now < 1700000000 && millis() - startedMs < 5000UL) {
    delay(100);
    now = time(nullptr);
  }

  timeConfigured = now >= 1700000000;
  Serial.println(timeConfigured ? "# NTP time synced" : "# NTP time not ready");
}

uint32_t currentTimestampSeconds() {
  time_t now = time(nullptr);
  if (timeConfigured && now >= 1700000000) {
    return static_cast<uint32_t>(now);
  }
  return millis() / 1000UL;
}

void maintainMQTT() {
  if (!wifiConfigLooksValid() || WiFi.status() != WL_CONNECTED) {
    return;
  }

  setupTimeIfNeeded();

  if (mqtt.connected()) {
    mqtt.loop();
    return;
  }

  if (millis() - lastMQTTAttemptMs < MQTT_RETRY_INTERVAL_MS) {
    return;
  }

  lastMQTTAttemptMs = millis();
  Serial.print("# MQTT connecting to ");
  Serial.print(MQTT_SERVER);
  Serial.print(':');
  Serial.println(MQTT_PORT);

  if (!mqttTcpDiagnosticPrinted) {
    mqttTcpDiagnosticPrinted = true;
    Serial.print("# MQTT TCP diagnostic ");
    Serial.println(testMQTTTcpConnect() ? "ok" : "failed");
  }

  if (mqtt.connect(NODE_ID)) {
    Serial.println("# MQTT connected");
  } else {
    Serial.print("# MQTT failed, state=");
    Serial.println(mqtt.state());
  }
}

void warmupSensors() {
  Serial.print("# MQ warmup seconds=");
  Serial.println(MQ_WARMUP_MS / 1000UL);

  uint32_t startedMs = millis();
  uint32_t lastPrintMs = startedMs;

  while (millis() - startedMs < MQ_WARMUP_MS) {
    maintainWiFi();
    maintainMQTT();

    if (millis() - lastPrintMs >= 5000UL) {
      lastPrintMs = millis();
      uint32_t remainingMs = MQ_WARMUP_MS - (millis() - startedMs);
      Serial.print("# warmup remaining seconds=");
      Serial.println((remainingMs + 999UL) / 1000UL);
    }

    delay(20);
  }

  drainPMSInput();
  Serial.println("# warmup done");
}

void addPMSJsonFields(JsonObject doc, const PMS5003TData &pms) {
  if (pms.valid) {
    doc["pm1_0"] = pms.pm1_0;
    doc["pm2_5"] = pms.pm2_5;
    doc["pm10"] = pms.pm10;
    doc["temperature"] = pms.temperature;
    doc["humidity"] = pms.humidity;
  } else {
    doc["pm1_0"] = nullptr;
    doc["pm2_5"] = nullptr;
    doc["pm10"] = nullptr;
    doc["temperature"] = nullptr;
    doc["humidity"] = nullptr;
  }
  doc["pms_valid"] = pms.valid;
}

void sampleAndPublish() {
  ButtonSnapshot buttons = readButtons();
  const NodeMode mode =
      buttons.dataCollectionMode ? NodeMode::DataCollection : NodeMode::Inference;
  const CollectionLabel collectionLabel = selectedCollectionLabel(buttons);

  uint16_t vocRaw = readADCAverage(MQ135_PIN);
  uint16_t coRaw = readADCAverage(MQ7_PIN);
  uint16_t vocMilliVolt = readMilliVoltAverage(MQ135_PIN);
  uint16_t coMilliVolt = readMilliVoltAverage(MQ7_PIN);
  PMS5003TData pms = readPMS5003T();

  digitalWrite(CIGARETTE_LED_PIN, LOW);

  // Local inference variables
  const char *infClass = nullptr;
  float infScore = 0.0f;
  bool cigDetected = false;
  const char *modelVer = "backend_pending";

  if (mode == NodeMode::Inference && pms.valid) {
    LocalInferenceResult localRes = runLocalInference(
      static_cast<float>(vocMilliVolt),
      static_cast<float>(coMilliVolt),
      static_cast<float>(pms.pm1_0),
      static_cast<float>(pms.pm2_5),
      static_cast<float>(pms.pm10),
      pms.temperature,
      pms.humidity
    );
    infClass = localRes.className;
    infScore = localRes.score;
    cigDetected = localRes.cigaretteDetected;
    modelVer = INFERENCE_MODEL_VERSION;

    if (cigDetected) {
      digitalWrite(CIGARETTE_LED_PIN, HIGH);
    }
  }

  StaticJsonDocument<768> doc;
  JsonObject root = doc.to<JsonObject>();
  root["node_id"] = NODE_ID;
  root["timestamp"] = currentTimestampSeconds();
  root["mode"] = modeToString(mode);
  root["collection_label"] =
      mode == NodeMode::DataCollection ? labelToString(collectionLabel) : nullptr;
  
  root["model_version"] = modelVer;
  if (infClass != nullptr) {
    root["inference_class"] = infClass;
    root["inference_score"] = infScore;
  } else {
    root["inference_class"] = nullptr;
    root["inference_score"] = nullptr;
  }
  root["cigarette_detected"] = cigDetected;

  root["voc_raw"] = vocRaw;
  root["co_raw"] = coRaw;
  root["voc_mv"] = vocMilliVolt;
  root["co_mv"] = coMilliVolt;
  addPMSJsonFields(root, pms);

  JsonObject buttonJson = root.createNestedObject("buttons");
  buttonJson["mode_data_collection"] = buttons.dataCollectionMode;
  buttonJson["cooking_fume"] = buttons.cookingFume;
  buttonJson["vehicle_exhaust"] = buttons.vehicleExhaust;
  buttonJson["cigarette_smoke"] = buttons.cigaretteSmoke;
  buttonJson["led_cigarette"] = cigDetected;

  char payload[768];
  size_t payloadLength = serializeJson(root, payload, sizeof(payload));
  Serial.println(payload);

  if (mqtt.connected()) {
    bool published = mqtt.publish(mqttTopic, reinterpret_cast<const uint8_t *>(payload),
                                  payloadLength);
    if (!published) {
      Serial.printf(
          "# MQTT publish failed: connected=%s state=%d payload_bytes=%u buffer_bytes=%u wifi_rssi=%d heap=%u\n",
          mqtt.connected() ? "true" : "false",
          mqtt.state(),
          static_cast<unsigned int>(payloadLength),
          static_cast<unsigned int>(mqtt.getBufferSize()),
          WiFi.RSSI(),
          static_cast<unsigned int>(ESP.getFreeHeap())
      );
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);

  snprintf(mqttTopic, sizeof(mqttTopic), "smokelens/%s/data", NODE_ID);

  setupADC();
  setupButtonsAndLED();
  pmsSerial.setRxBufferSize(512);
  pmsSerial.begin(PMS_BAUD, SERIAL_8N1, PMS_RX_PIN, PMS_TX_PIN);

  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(5);

  Serial.println("# SmokeLens node boot");
  Serial.print("# MQTT topic=");
  Serial.println(mqttTopic);

  beginWiFi();
  warmupSensors();

  lastSampleMs = millis() - SAMPLE_INTERVAL_MS;
}

void loop() {
  mqtt.loop();
  maintainWiFi();
  maintainMQTT();

  if (millis() - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = millis();
    sampleAndPublish();
  }

  delay(10);
}
