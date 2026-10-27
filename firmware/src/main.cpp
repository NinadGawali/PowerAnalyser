#include <Arduino.h>

#include "config.h"
#include "current_sensor.h"

struct SwitchState {
  float current = 0;    // A (RMS)
  float power = 0;      // W
  double energyWh = 0;  // cumulative since boot
};

static CurrentSensor sensors[NUM_SWITCHES] = {
    CurrentSensor(SENSOR_PINS[0]), CurrentSensor(SENSOR_PINS[1]),
    CurrentSensor(SENSOR_PINS[2]), CurrentSensor(SENSOR_PINS[3])};
static SwitchState state[NUM_SWITCHES];

static uint32_t lastMeasureMs = 0;
static uint32_t lastReportMs = 0;

static void calibrateSensors() {
  Serial.println("[CAL] Calibrating zero-current offsets. Make sure ALL loads are OFF.");
  delay(1000);
  for (int i = 0; i < NUM_SWITCHES; i++) {
    sensors[i].calibrate();
    Serial.printf("[CAL] switch_%d (GPIO %d): offset = %.1f mV\n", i + 1,
                  sensors[i].pin(), sensors[i].offsetMv());
    if (sensors[i].offsetMv() < 2000 || sensors[i].offsetMv() > 3000) {
      Serial.printf("[CAL] WARNING: switch_%d offset is far from 2500 mV. "
                    "Check wiring / divider.\n", i + 1);
    }
  }
}

static void measureAll() {
  for (int i = 0; i < NUM_SWITCHES; i++) {
    state[i].current = sensors[i].readRmsAmps();
    state[i].power = MAINS_VOLTAGE * state[i].current * POWER_FACTOR;
  }

  // Integrate energy using the real elapsed time since the last measurement
  uint32_t now = millis();
  double hours = (now - lastMeasureMs) / 3600000.0;
  lastMeasureMs = now;
  for (int i = 0; i < NUM_SWITCHES; i++) {
    state[i].energyWh += state[i].power * hours;
  }
}

static void printReadings() {
  Serial.println("----------------------------------------------");
  Serial.println(" Switch   Current(A)   Power(W)   Energy(Wh)");
  for (int i = 0; i < NUM_SWITCHES; i++) {
    Serial.printf(" %-8d %10.3f %10.1f %12.3f\n", i + 1, state[i].current,
                  state[i].power, state[i].energyWh);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Electronic Power Consumption Analyzer ===");

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);  // ~0..3.1V input range

  calibrateSensors();
  lastMeasureMs = millis();
}

void loop() {
  measureAll();

  if (millis() - lastReportMs >= UPLOAD_INTERVAL_MS) {
    lastReportMs = millis();
    printReadings();
  }
}
