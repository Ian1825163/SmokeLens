/*
  SmokeLens GPIO button test

  Open this sketch directly in Arduino IDE:
    tools/GpioButtonTest/GpioButtonTest.ino

  Purpose:
  - Verify GPIO32 / GPIO33 / GPIO25 / GPIO26 can read HIGH/LOW correctly.
  - Verify LED 1 output can be driven.

  Wiring expectation:
  - Each button/switch output goes to the ESP32 GPIO pin.
  - LOW means connected to GND or left low by the internal pulldown.
  - HIGH means connected to 3.3V.
  - Do not connect any GPIO input to 5V.
*/

#include <Arduino.h>

const uint32_t SERIAL_BAUD = 115200;
const uint32_t PRINT_INTERVAL_MS = 1000;
const uint32_t DEBOUNCE_MS = 30;

const uint8_t MODE_BUTTON_PIN = 32;       // HIGH=data collection, LOW=inference
const uint8_t COOKING_BUTTON_PIN = 33;    // HIGH=cooking fume, LOW=normal
const uint8_t EXHAUST_BUTTON_PIN = 25;    // HIGH=vehicle exhaust, LOW=normal
const uint8_t CIGARETTE_BUTTON_PIN = 26;  // HIGH=cigarette smoke, LOW=normal
const uint8_t LED_PIN = 27;

struct InputState {
  const char *name;
  uint8_t pin;
  bool stableState;
  bool lastRawState;
  uint32_t lastChangeMs;
};

InputState inputs[] = {
    {"button_1_mode_gpio32", MODE_BUTTON_PIN, false, false, 0},
    {"button_3_cooking_gpio33", COOKING_BUTTON_PIN, false, false, 0},
    {"button_5_exhaust_gpio25", EXHAUST_BUTTON_PIN, false, false, 0},
    {"button_8_cigarette_gpio26", CIGARETTE_BUTTON_PIN, false, false, 0},
};

uint32_t lastPrintMs = 0;

bool readHigh(uint8_t pin) {
  return digitalRead(pin) == HIGH;
}

const char *modeName() {
  return inputs[0].stableState ? "data_collection" : "inference";
}

const char *labelName() {
  if (inputs[3].stableState) {
    return "cigarette_smoke";
  }
  if (inputs[2].stableState) {
    return "vehicle_exhaust";
  }
  if (inputs[1].stableState) {
    return "cooking_fume";
  }
  return "normal_air";
}

void printStateLine(const char *prefix) {
  Serial.print(prefix);
  Serial.print(" mode=");
  Serial.print(modeName());
  Serial.print(" label=");
  Serial.print(labelName());

  for (InputState &input : inputs) {
    Serial.print(' ');
    Serial.print(input.name);
    Serial.print('=');
    Serial.print(input.stableState ? "HIGH" : "LOW");
  }

  Serial.print(" led=");
  Serial.println(digitalRead(LED_PIN) == HIGH ? "HIGH" : "LOW");
}

void setupInputs() {
  for (InputState &input : inputs) {
    pinMode(input.pin, INPUT_PULLDOWN);
    input.stableState = readHigh(input.pin);
    input.lastRawState = input.stableState;
    input.lastChangeMs = millis();
  }
}

void updateInputs() {
  const uint32_t now = millis();
  bool anyStableChange = false;

  for (InputState &input : inputs) {
    const bool rawState = readHigh(input.pin);

    if (rawState != input.lastRawState) {
      input.lastRawState = rawState;
      input.lastChangeMs = now;
    }

    if (rawState != input.stableState &&
        now - input.lastChangeMs >= DEBOUNCE_MS) {
      input.stableState = rawState;
      anyStableChange = true;

      Serial.print("# changed ");
      Serial.print(input.name);
      Serial.print(" -> ");
      Serial.println(input.stableState ? "HIGH" : "LOW");
    }
  }

  // In this test sketch, LED mirrors the cigarette label input so the output can
  // be tested without needing smoke/inference.
  digitalWrite(LED_PIN, inputs[3].stableState ? HIGH : LOW);

  if (anyStableChange) {
    printStateLine("# state");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  setupInputs();

  Serial.println("# SmokeLens GPIO button test");
  Serial.println("# pins use INPUT_PULLDOWN; drive each input to 3.3V for HIGH");
  Serial.println("# LED mirrors button 8 / GPIO26 in this test sketch");
  printStateLine("# initial");
}

void loop() {
  updateInputs();

  if (millis() - lastPrintMs >= PRINT_INTERVAL_MS) {
    lastPrintMs = millis();
    printStateLine("# heartbeat");
  }

  delay(5);
}
