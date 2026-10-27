#pragma once

#include <Arduino.h>

class CurrentSensor {
 public:
  explicit CurrentSensor(int pin) : pin_(pin) {}

  // Measures the zero-current output voltage. Loads must be OFF.
  void calibrate();

  // Returns RMS current in amps over one RMS_WINDOW_MS window,
  // or 0 if below the noise floor.
  float readRmsAmps();

  float offsetMv() const { return offsetMv_; }
  int pin() const { return pin_; }

 private:
  // ACS712 output voltage (before the divider) in millivolts.
  float readSensorMv();

  int pin_;
  float offsetMv_ = 2500.0f;
};
