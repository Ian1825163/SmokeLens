/*
  SmokeLens GPIO button test

  Open this sketch directly in Arduino IDE:
    tools/GpioButtonTest/GpioButtonTest.ino

  Purpose:
  - Verify GPIO32 / GPIO33 / GPIO25 / GPIO26 can read HIGH/LOW correctly.
  - Verify LED 1 output can be driven.

  Wiring expectation:
  - Each button/switch connects the ESP32 GPIO pin to GND when ON.
  - The sketch uses INPUT_PULLUP.
  - Connected to GND = active = prints 1.
  - Open/not connected to GND = inactive = prints 0.
*/

#include <Arduino.h>

const uint32_t SERIAL_BAUD = 115200;
const uint32_t PRINT_INTERVAL_MS = 1000;
const uint32_t DEBOUNCE_MS = 30;

const uint8_t MODE_BUTTON_PIN = 32;       // GND=data collection, open=inference
const uint8_t COOKING_BUTTON_PIN = 33;    // GND=cooking fume, open=normal
const uint8_t EXHAUST_BUTTON_PIN = 25;    // GND=vehicle exhaust, open=normal
const uint8_t CIGARETTE_BUTTON_PIN = 26;  // GND=cigarette smoke, open=normal
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

bool readActive(uint8_t pin) {
  return digitalRead(pin) == LOW;
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
    Serial.print(input.stableState ? "1" : "0");
  }

  Serial.print(" led=");
  Serial.println(digitalRead(LED_PIN) == HIGH ? "HIGH" : "LOW");
}

void setupInputs() {
  for (InputState &input : inputs) {
    pinMode(input.pin, INPUT_PULLUP);
    input.stableState = readActive(input.pin);
    input.lastRawState = input.stableState;
    input.lastChangeMs = millis();
  }
}

void updateInputs() {
  const uint32_t now = millis();
  bool anyStableChange = false;

  for (InputState &input : inputs) {
    const bool rawState = readActive(input.pin);

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
      Serial.println(input.stableState ? "1" : "0");
    }
  }

  // In this test sketch, LED mirrors button 1 / GPIO32.
  digitalWrite(LED_PIN, inputs[0].stableState ? HIGH : LOW);

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
  Serial.println("# pins use INPUT_PULLUP; connect each input to GND for 1");
  Serial.println("# LED mirrors button 1 / GPIO32 in this test sketch");
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
