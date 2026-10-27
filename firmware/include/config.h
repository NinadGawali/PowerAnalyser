#pragma once

// ---------------------------------------------------------------------------
// Sensor hardware
// ---------------------------------------------------------------------------

// ACS712 sensitivity in mV per amp:
//   ACS712-05B = 185, ACS712-20A = 100, ACS712-30A = 66
#define ACS712_SENSITIVITY_MV_PER_A 100.0f

// The ACS712 runs on 5V and idles at ~2.5V, swinging up to ~4.5V, which is
// above the ESP32's 3.3V ADC limit. Each output goes through a divider:
//
//   ACS712 OUT --[ R_TOP 10k ]--+--[ R_BOTTOM 20k ]-- GND
//                               |
//                           ESP32 ADC pin
//
// V_adc = V_out * R_BOTTOM / (R_TOP + R_BOTTOM) = V_out * 2/3
// So 2.5V idle -> 1.67V, full scale 0.5..4.5V -> 0.33..3.0V.
#define DIVIDER_R_TOP_OHMS    10000.0f
#define DIVIDER_R_BOTTOM_OHMS 20000.0f
// Multiply the ADC pin voltage by this to get the ACS712 output voltage.
#define DIVIDER_RATIO ((DIVIDER_R_TOP_OHMS + DIVIDER_R_BOTTOM_OHMS) / DIVIDER_R_BOTTOM_OHMS)

// ADC1 pins only: ADC2 cannot be read while WiFi is active.
#define NUM_SWITCHES 4
static const int SENSOR_PINS[NUM_SWITCHES] = {34, 35, 32, 33};

// ---------------------------------------------------------------------------
// Measurement
// ---------------------------------------------------------------------------

#define CALIBRATION_SAMPLES 1000
// 200 ms = 10 full cycles at 50 Hz
#define RMS_WINDOW_MS 200
// Readings below this are treated as 0 A (ADC noise when nothing is connected).
// Raise it if an idle channel shows small non-zero current.
#define NOISE_FLOOR_A 0.15f

// ---------------------------------------------------------------------------
// Power
// ---------------------------------------------------------------------------

#define MAINS_VOLTAGE 230.0f
#define POWER_FACTOR  0.9f

// ---------------------------------------------------------------------------
// Network / cloud
// ---------------------------------------------------------------------------

#define DEVICE_ID "esp32_01"
#define UPLOAD_INTERVAL_MS 5000
#define WIFI_RETRY_INTERVAL_MS 10000

// India Standard Time, UTC+5:30 (POSIX TZ sign is inverted)
#define TZ_INFO "IST-5:30"
#define NTP_SERVER_1 "pool.ntp.org"
#define NTP_SERVER_2 "time.google.com"
