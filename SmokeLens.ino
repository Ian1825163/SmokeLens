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

#if __has_include(<esp_eap_client.h>)
#include <esp_eap_client.h>
#define SMOKELENS_HAS_ENTERPRISE_WIFI 1
#define SMOKELENS_USE_EAP_CLIENT 1
#elif __has_include(<esp_wpa2.h>)
#include <esp_wpa2.h>
#define SMOKELENS_HAS_ENTERPRISE_WIFI 1
#define SMOKELENS_USE_WPA2_ENT 1
#else
#define SMOKELENS_HAS_ENTERPRISE_WIFI 0
#endif

#define SMOKELENS_WIFI_PERSONAL(ssid, password, mqttServer) \
  { ssid, password, mqttServer, nullptr, nullptr, false }

#define SMOKELENS_WIFI_PEAP(ssid, identity, username, password, mqttServer) \
  { ssid, password, mqttServer, identity, username, true }

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
  const char *enterpriseIdentity;
  const char *enterpriseUsername;
  bool enterprise;
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
const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000UL;
const uint32_t WIFI_STATUS_PRINT_INTERVAL_MS = 5000UL;
const uint32_t MQTT_RETRY_INTERVAL_MS = 5000UL;
const uint32_t PMS_READ_TIMEOUT_MS = 1500UL;

const uint8_t ADC_SAMPLE_COUNT = 10;
const uint16_t PMS_FRAME_SIZE = 32;
const uint16_t PMS_PAYLOAD_LENGTH = 28;

const char *INFERENCE_MODEL_VERSION = "backend_pending";

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

bool credentialValueLooksValid(const char *value, const char *placeholder) {
  return value != nullptr && strlen(value) > 0 && strcmp(value, placeholder) != 0;
}

const char *mqttServerForCredential(const WiFiCredential &credential) {
  if (mqttServerValueLooksValid(credential.mqttServer)) {
    return credential.mqttServer;
  }
  return DEFAULT_MQTT_SERVER;
}

const char *enterpriseIdentityForCredential(const WiFiCredential &credential) {
  if (credential.enterpriseIdentity != nullptr &&
      strlen(credential.enterpriseIdentity) > 0) {
    return credential.enterpriseIdentity;
  }
  return credential.enterpriseUsername;
}

bool wifiCredentialLooksValid(const WiFiCredential &credential) {
  if (!credentialValueLooksValid(credential.ssid, "YOUR_SSID") ||
      strcmp(credential.ssid, "YOUR_WIFI_SSID") == 0) {
    return false;
  }

  if (credential.enterprise) {
    return SMOKELENS_HAS_ENTERPRISE_WIFI &&
           credentialValueLooksValid(credential.enterpriseUsername,
                                     "YOUR_NTU_ACCOUNT") &&
           credentialValueLooksValid(credential.password,
                                     "YOUR_NTU_PASSWORD");
  }

  return credentialValueLooksValid(credential.password, "YOUR_PASSWORD") &&
         strcmp(credential.password, "YOUR_WIFI_PASSWORD") != 0;
}

bool wifiCredentialConfigLooksValid(const WiFiCredential &credential) {
  return wifiCredentialLooksValid(credential) &&
         mqttServerValueLooksValid(mqttServerForCredential(credential));
}

const char *wifiCredentialAuthMode(const WiFiCredential &credential) {
  return credential.enterprise ? "peap" : "personal";
}

void disableEnterpriseWiFi() {
#if SMOKELENS_HAS_ENTERPRISE_WIFI
#if defined(SMOKELENS_USE_EAP_CLIENT)
  esp_wifi_sta_enterprise_disable();
#elif defined(SMOKELENS_USE_WPA2_ENT)
  esp_wifi_sta_wpa2_ent_disable();
#endif
#endif
}

uint8_t *credentialBytes(const char *value) {
  return reinterpret_cast<uint8_t *>(const_cast<char *>(value));
}

bool configureEnterpriseWiFi(const WiFiCredential &credential) {
#if !SMOKELENS_HAS_ENTERPRISE_WIFI
  (void)credential;
  Serial.println("# PEAP skipped: this ESP32 Arduino core has no enterprise WiFi API");
  return false;
#else
  const char *identity = enterpriseIdentityForCredential(credential);
  const char *username = credential.enterpriseUsername;
  const char *password = credential.password;

  if (identity == nullptr || username == nullptr || password == nullptr) {
    Serial.println("# PEAP skipped: identity, username, or password is missing");
    return false;
  }

#if defined(SMOKELENS_USE_EAP_CLIENT)
  esp_eap_client_set_identity(credentialBytes(identity), strlen(identity));
  esp_eap_client_set_username(credentialBytes(username), strlen(username));
  esp_eap_client_set_password(credentialBytes(password), strlen(password));
  esp_wifi_sta_enterprise_enable();
#elif defined(SMOKELENS_USE_WPA2_ENT)
  esp_wifi_sta_wpa2_ent_set_identity(credentialBytes(identity), strlen(identity));
  esp_wifi_sta_wpa2_ent_set_username(credentialBytes(username), strlen(username));
  esp_wifi_sta_wpa2_ent_set_password(credentialBytes(password), strlen(password));
  esp_wifi_sta_wpa2_ent_enable();
#endif

  return true;
#endif
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
  const int nextIndex = nextValidWiFiCredentialIndex();
  if (nextIndex < 0) {
    Serial.println("# WiFi skipped: update WiFi credentials and MQTT servers first");
    return;
  }

  currentWiFiCredentialIndex = nextIndex;
  const WiFiCredential &credential = WIFI_CREDENTIALS[currentWiFiCredentialIndex];
  MQTT_SERVER = mqttServerForCredential(credential);

  if (mqtt.connected()) {
    mqtt.disconnect();
  }
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  WiFi.disconnect(true);
  disableEnterpriseWiFi();
  delay(100);

  if (credential.enterprise) {
    if (!configureEnterpriseWiFi(credential)) {
      Serial.println("# WiFi skipped: PEAP configuration failed");
      return;
    }
    WiFi.begin(credential.ssid);
  } else {
    WiFi.begin(credential.ssid, credential.password);
  }

  lastWiFiAttemptMs = millis();
  lastWiFiStatusPrintMs = lastWiFiAttemptMs;
  mqttTcpDiagnosticPrinted = false;
  wifiWasConnected = false;

  Serial.print("# WiFi connecting to ");
  Serial.print(credential.ssid);
  Serial.print(" (");
  Serial.print(currentWiFiCredentialIndex + 1);
  Serial.print("/");
  Serial.print(WIFI_CREDENTIAL_COUNT);
  Serial.print(") auth=");
  Serial.print(wifiCredentialAuthMode(credential));
  Serial.print(" mqtt=");
  Serial.println(MQTT_SERVER);
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
    Serial.print("# WiFi waiting status=");
    Serial.print(wifiStatusToString(WiFi.status()));
    Serial.print(" elapsed_s=");
    Serial.println(elapsedMs / 1000UL);
  }

  if (elapsedMs < WIFI_CONNECT_TIMEOUT_MS) {
    return;
  }

  Serial.print("# WiFi connect timeout status=");
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

  StaticJsonDocument<768> doc;
  JsonObject root = doc.to<JsonObject>();
  root["node_id"] = NODE_ID;
  root["timestamp"] = currentTimestampSeconds();
  root["mode"] = modeToString(mode);
  root["collection_label"] =
      mode == NodeMode::DataCollection ? labelToString(collectionLabel) : nullptr;
  root["model_version"] = INFERENCE_MODEL_VERSION;
  root["inference_class"] = nullptr;
  root["cigarette_detected"] = false;
  root["inference_score"] = nullptr;
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
  buttonJson["led_cigarette"] = false;

  char payload[768];
  size_t payloadLength = serializeJson(root, payload, sizeof(payload));
  Serial.println(payload);

  if (mqtt.connected()) {
    bool published = mqtt.publish(mqttTopic, reinterpret_cast<const uint8_t *>(payload),
                                  payloadLength);
    if (!published) {
      Serial.println("# MQTT publish failed");
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
  mqtt.setBufferSize(512);

  Serial.println("# SmokeLens node boot");
  Serial.print("# MQTT topic=");
  Serial.println(mqttTopic);

  beginWiFi();
  warmupSensors();

  lastSampleMs = millis() - SAMPLE_INTERVAL_MS;
}

void loop() {
  maintainWiFi();
  maintainMQTT();

  if (millis() - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = millis();
    sampleAndPublish();
  }

  mqtt.loop();
  delay(10);
}
