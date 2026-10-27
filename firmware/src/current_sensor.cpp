#include "current_sensor.h"

#include <math.h>

#include "config.h"

float CurrentSensor::readSensorMv() {
  // analogReadMilliVolts() applies the chip's factory ADC calibration,
  // which is far more linear than raw analogRead() counts.
  return analogReadMilliVolts(pin_) * DIVIDER_RATIO;
}

void CurrentSensor::calibrate() {
  double sum = 0;
  for (int i = 0; i < CALIBRATION_SAMPLES; i++) {
    sum += readSensorMv();
    // Spread the samples over ~10 mains cycles
    delayMicroseconds(200);
  }
  offsetMv_ = sum / CALIBRATION_SAMPLES;
}

float CurrentSensor::readRmsAmps() {
  double sumSq = 0;
  uint32_t n = 0;
  uint32_t start = millis();
  while (millis() - start < RMS_WINDOW_MS) {
    float mv = readSensorMv() - offsetMv_;
    sumSq += (double)mv * mv;
    n++;
  }
  if (n == 0) return 0;

  float rmsMv = sqrt(sumSq / n);
  float amps = rmsMv / ACS712_SENSITIVITY_MV_PER_A;
  return amps < NOISE_FLOOR_A ? 0.0f : amps;
}
