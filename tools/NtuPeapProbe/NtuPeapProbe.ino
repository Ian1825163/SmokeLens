/*
  Minimal ntu_peap probe for ESP32.

  This sketch isolates WPA2-Enterprise/PEAP from SmokeLens sensor, MQTT, and
  fallback logic. It reuses arduino_secrets.h from the repo root.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <esp_err.h>
#include <esp_log.h>

#if __has_include(<esp_eap_client.h>)
#include <esp_eap_client.h>
#define PROBE_HAS_EAP_CLIENT 1
#elif __has_include(<esp_wpa2.h>)
#include <esp_wpa2.h>
#define PROBE_HAS_WPA2_ENT 1
#else
#define PROBE_HAS_NO_ENTERPRISE_WIFI 1
#endif

struct ProbeWiFiCredential {
  const char *ssid;
  const char *password;
  const char *mqttServer;
  const char *enterpriseIdentity;
  const char *enterpriseUsername;
  bool enterprise;
};

#define SMOKELENS_WIFI_PERSONAL(ssid, password, mqttServer) \
  { ssid, password, mqttServer, nullptr, nullptr, false }

#define SMOKELENS_WIFI_PEAP(ssid, identity, username, password, mqttServer) \
  { ssid, password, mqttServer, identity, username, true }

#include "../../arduino_secrets.h"

const ProbeWiFiCredential WIFI_CREDENTIALS[] = SMOKELENS_WIFI_CREDENTIALS;
const size_t WIFI_CREDENTIAL_COUNT =
    sizeof(WIFI_CREDENTIALS) / sizeof(WIFI_CREDENTIALS[0]);

const uint32_t SERIAL_BAUD = 115200;
const uint32_t CONNECT_TIMEOUT_MS = 20000UL;
const uint32_t STATUS_INTERVAL_MS = 1000UL;

bool connected = false;
bool gotIp = false;
bool authFailed = false;
uint8_t lastDisconnectReason = 0;

uint8_t *credentialBytes(const char *value) {
  return reinterpret_cast<uint8_t *>(const_cast<char *>(value));
}

const char *statusToString(wl_status_t status) {
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

const char *identityMode(const char *identity, const char *username) {
  if (identity == nullptr || strlen(identity) == 0) {
    return "blank";
  }
  if (strcmp(identity, "anonymous") == 0 ||
      strstr(identity, "anonymous@") == identity) {
    return "anonymous";
  }
  if (username != nullptr && strcmp(identity, username) == 0) {
    return "same_as_username";
  }
  return "custom";
}

const char *disconnectReasonToString(uint8_t reason) {
  switch (reason) {
    case 2:
      return "AUTH_EXPIRE";
    case 3:
      return "AUTH_LEAVE";
    case 8:
      return "ASSOC_LEAVE";
    case 23:
      return "802_1X_AUTH_FAILED";
    case 36:
      return "AUTH_FAIL_OR_EAP_FAILURE";
    default:
      return "UNKNOWN";
  }
}

void disableEnterpriseWiFi() {
#if defined(PROBE_HAS_EAP_CLIENT)
  esp_wifi_sta_enterprise_disable();
  esp_eap_client_clear_identity();
  esp_eap_client_clear_username();
  esp_eap_client_clear_password();
  esp_eap_client_clear_new_password();
#elif defined(PROBE_HAS_WPA2_ENT)
  esp_wifi_sta_wpa2_ent_disable();
  esp_wifi_sta_wpa2_ent_clear_identity();
  esp_wifi_sta_wpa2_ent_clear_username();
  esp_wifi_sta_wpa2_ent_clear_password();
  esp_wifi_sta_wpa2_ent_clear_new_password();
#endif
}

bool logEspResult(const char *step, esp_err_t err) {
  Serial.print("# probe ");
  Serial.print(step);
  Serial.print("=");
  Serial.print(esp_err_to_name(err));
  Serial.print(" (");
  Serial.print(static_cast<int>(err));
  Serial.println(")");
  return err == ESP_OK;
}

void handleWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
#if defined(PROBE_HAS_EAP_CLIENT)
  if (event == ARDUINO_EVENT_WIFI_STA_CONNECTED) {
    connected = true;
    Serial.println("# probe event connected_to_ap");
  } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    gotIp = true;
    Serial.print("# probe event got_ip ");
    Serial.println(WiFi.localIP());
  } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    lastDisconnectReason = info.wifi_sta_disconnected.reason;
    if (lastDisconnectReason == 23) {
      authFailed = true;
    }
    Serial.print("# probe event disconnected reason=");
    Serial.print(lastDisconnectReason);
    Serial.print(" (");
    Serial.print(disconnectReasonToString(lastDisconnectReason));
    Serial.println(")");
  }
#elif defined(PROBE_HAS_WPA2_ENT)
  if (event == SYSTEM_EVENT_STA_CONNECTED) {
    connected = true;
    Serial.println("# probe event connected_to_ap");
  } else if (event == SYSTEM_EVENT_STA_GOT_IP) {
    gotIp = true;
    Serial.print("# probe event got_ip ");
    Serial.println(WiFi.localIP());
  } else if (event == SYSTEM_EVENT_STA_DISCONNECTED) {
    lastDisconnectReason = info.disconnected.reason;
    if (lastDisconnectReason == 23) {
      authFailed = true;
    }
    Serial.print("# probe event disconnected reason=");
    Serial.print(lastDisconnectReason);
    Serial.print(" (");
    Serial.print(disconnectReasonToString(lastDisconnectReason));
    Serial.println(")");
  }
#else
  (void)event;
  (void)info;
#endif
}

bool configureEnterprise(const ProbeWiFiCredential &credential, bool peapOnly) {
#if defined(PROBE_HAS_NO_ENTERPRISE_WIFI)
  (void)credential;
  (void)peapOnly;
  Serial.println("# probe no enterprise WiFi API available");
  return false;
#else
  const char *identity =
      credential.enterpriseIdentity == nullptr ? credential.enterpriseUsername
                                               : credential.enterpriseIdentity;
  const char *username = credential.enterpriseUsername;
  const char *password = credential.password;

  if (identity == nullptr || username == nullptr || password == nullptr) {
    Serial.println("# probe missing identity/username/password");
    return false;
  }

  Serial.print("# probe configure ssid=");
  Serial.print(credential.ssid);
  Serial.print(" mode=");
  Serial.print(peapOnly ? "peap_only" : "all_eap_methods");
  Serial.print(" identity_mode=");
  Serial.print(identityMode(identity, username));
  Serial.print(" identity_len=");
  Serial.print(strlen(identity));
  Serial.print(" username_len=");
  Serial.print(strlen(username));
  Serial.print(" password_len=");
  Serial.println(strlen(password));

  WiFi.disconnect(true);
  disableEnterpriseWiFi();
  delay(200);
  WiFi.mode(WIFI_STA);

#if defined(PROBE_HAS_EAP_CLIENT)
  esp_eap_client_clear_identity();
  esp_eap_client_clear_username();
  esp_eap_client_clear_password();
  esp_eap_client_clear_new_password();
  if (peapOnly &&
      !logEspResult("set_eap_methods",
                    esp_eap_client_set_eap_methods(ESP_EAP_TYPE_PEAP))) {
    return false;
  }
  logEspResult("disable_time_check", esp_eap_client_set_disable_time_check(true));
  if (strlen(identity) == 0) {
    esp_eap_client_clear_identity();
    Serial.println("# probe cleared outer identity");
  } else if (!logEspResult("set_identity",
                           esp_eap_client_set_identity(credentialBytes(identity),
                                                       strlen(identity)))) {
    return false;
  }
  if (!logEspResult("set_username",
                    esp_eap_client_set_username(credentialBytes(username),
                                                strlen(username))) ||
      !logEspResult("set_password",
                    esp_eap_client_set_password(credentialBytes(password),
                                                strlen(password))) ||
      !logEspResult("enable_enterprise", esp_wifi_sta_enterprise_enable())) {
    return false;
  }
#elif defined(PROBE_HAS_WPA2_ENT)
  esp_wifi_sta_wpa2_ent_clear_identity();
  esp_wifi_sta_wpa2_ent_clear_username();
  esp_wifi_sta_wpa2_ent_clear_password();
  esp_wifi_sta_wpa2_ent_clear_new_password();
  logEspResult("disable_time_check",
               esp_wifi_sta_wpa2_ent_set_disable_time_check(true));
  if (strlen(identity) == 0) {
    esp_wifi_sta_wpa2_ent_clear_identity();
    Serial.println("# probe cleared outer identity");
  } else if (!logEspResult("set_identity",
                           esp_wifi_sta_wpa2_ent_set_identity(
                               credentialBytes(identity), strlen(identity)))) {
    return false;
  }
  if (!logEspResult("set_username",
                    esp_wifi_sta_wpa2_ent_set_username(
                        credentialBytes(username), strlen(username))) ||
      !logEspResult("set_password",
                    esp_wifi_sta_wpa2_ent_set_password(
                        credentialBytes(password), strlen(password))) ||
      !logEspResult("enable_enterprise", esp_wifi_sta_wpa2_ent_enable())) {
    return false;
  }
#endif

  wl_status_t status = WiFi.begin(credential.ssid);
  Serial.print("# probe WiFi.begin=");
  Serial.println(statusToString(status));
  return true;
#endif
}

void runProbe(const ProbeWiFiCredential &credential, bool peapOnly) {
  connected = false;
  gotIp = false;
  authFailed = false;
  lastDisconnectReason = 0;

  if (!configureEnterprise(credential, peapOnly)) {
    Serial.println("# probe configure failed");
    return;
  }

  uint32_t startedMs = millis();
  uint32_t lastStatusMs = 0;
  while (millis() - startedMs < CONNECT_TIMEOUT_MS) {
    if (gotIp || WiFi.status() == WL_CONNECTED) {
      Serial.print("# probe connected ip=");
      Serial.println(WiFi.localIP());
      WiFi.disconnect(true);
      disableEnterpriseWiFi();
      return;
    }
    if (authFailed) {
      Serial.println("# probe auth failed; ending this test");
      WiFi.disconnect(true);
      disableEnterpriseWiFi();
      return;
    }
    if (millis() - lastStatusMs >= STATUS_INTERVAL_MS) {
      lastStatusMs = millis();
      Serial.print("# probe waiting status=");
      Serial.print(statusToString(WiFi.status()));
      Serial.print(" elapsed_s=");
      Serial.println((millis() - startedMs) / 1000UL);
    }
    delay(20);
  }

  Serial.print("# probe timeout status=");
  Serial.print(statusToString(WiFi.status()));
  Serial.print(" last_reason=");
  Serial.print(lastDisconnectReason);
  Serial.print(" (");
  Serial.print(disconnectReasonToString(lastDisconnectReason));
  Serial.println(")");
  WiFi.disconnect(true);
  disableEnterpriseWiFi();
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(500);
  Serial.setDebugOutput(true);
  esp_log_level_set("*", ESP_LOG_VERBOSE);
  WiFi.onEvent(handleWiFiEvent);

  Serial.println("# ntu_peap probe boot");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  for (size_t i = 0; i < WIFI_CREDENTIAL_COUNT; ++i) {
    const ProbeWiFiCredential &credential = WIFI_CREDENTIALS[i];
    if (!credential.enterprise || credential.ssid == nullptr ||
        strcmp(credential.ssid, "ntu_peap") != 0) {
      continue;
    }

    Serial.print("# probe credential ");
    Serial.print(i + 1);
    Serial.print("/");
    Serial.println(WIFI_CREDENTIAL_COUNT);
    runProbe(credential, true);
    delay(1000);
    runProbe(credential, false);
    delay(1000);
  }

  Serial.println("# ntu_peap probe done");
}

void loop() {
  delay(1000);
}
