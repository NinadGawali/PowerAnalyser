# PowerAnalyser – Electronic Power Consumption Analyzer

An ESP32 reads four ACS712 current sensors (one per switch/appliance), computes
RMS current, power and energy, and pushes the readings to Firebase Realtime
Database every 5 seconds. A self-hosted Flask dashboard shows live power,
history charts, today's energy and ML insights (anomalies, usage patterns and a
next-hour estimate).

```
ACS712 x4 ──> ESP32 ──HTTPS──> Firebase RTDB <──firebase-admin── Flask dashboard + ML
                                     ^
                                     └── tools/simulate.py (fake data, no hardware needed)
```

| Folder | Contents |
|---|---|
| `firmware/` | PlatformIO project for the ESP32 (Arduino framework) |
| `dashboard/` | Flask app (`app.py`), ML insights (`ml.py`), HTML template |
| `tools/` | `simulate.py`, pushes realistic fake readings to Firebase |

---

## ⚠️ Mains safety warning

**230 V AC mains can kill.** The ACS712 sits in series with the live wire of
each load, so its high-current screw terminals are at mains potential.

- Do all wiring with the mains supply **switched off and unplugged**.
- Keep the mains side (ACS712 screw terminals, appliance wiring) physically
  separated from the low-voltage side (ESP32, dividers, USB).
- Put the whole build in a closed, insulated enclosure. Never touch it while
  it's powered.
- Use wire rated for the load current, and a fuse/MCB on each load line.
- Don't exceed the sensor rating (20 A for the ACS712-20A; stay well below it
  in practice).
- If you're not confident working with mains, get a qualified electrician to
  do the mains side.

---

## Hardware

- ESP32 DevKit V1 (38-pin)
- 4 × ACS712 current sensor modules (20A version assumed; 5A and 30A supported)
- 4 × 10 kΩ and 4 × 20 kΩ resistors (one divider per sensor)
- 5 V supply for the ACS712 modules (the ESP32's `VIN`/`5V` pin works when
  powered from USB)

### Why a voltage divider?

The ACS712 runs on 5 V and outputs ~2.5 V at 0 A, swinging to ~0.5–4.5 V at
full scale. The ESP32 ADC only accepts up to ~3.1 V, so each output goes
through a divider:

```
ACS712 OUT ──[ 10k ]──┬──[ 20k ]── GND
                      │
                 ESP32 GPIO
```

`V_adc = V_out × 20k / (10k + 20k) = V_out × 2/3`, so 2.5 V becomes 1.67 V and
the full 0.5–4.5 V range becomes 0.33–3.0 V. The firmware multiplies the ADC
reading by 1.5 (`DIVIDER_RATIO` in `firmware/include/config.h`) to recover the
real sensor voltage. If you use other resistor values, update
`DIVIDER_R_TOP_OHMS` / `DIVIDER_R_BOTTOM_OHMS`.

### Wiring

Only ADC1 pins are used, because ADC2 can't be read while WiFi is active.

| Sensor | ACS712 VCC | ACS712 GND | ACS712 OUT → divider | Divider midpoint → ESP32 | Divider bottom |
|---|---|---|---|---|---|
| Switch 1 | ESP32 `5V`/`VIN` | ESP32 `GND` | OUT → 10k | **GPIO 34** | 20k → `GND` |
| Switch 2 | ESP32 `5V`/`VIN` | ESP32 `GND` | OUT → 10k | **GPIO 35** | 20k → `GND` |
| Switch 3 | ESP32 `5V`/`VIN` | ESP32 `GND` | OUT → 10k | **GPIO 32** | 20k → `GND` |
| Switch 4 | ESP32 `5V`/`VIN` | ESP32 `GND` | OUT → 10k | **GPIO 33** | 20k → `GND` |

Mains side, for each switch:

| From | To |
|---|---|
| Mains **Live** | ACS712 screw terminal IP+ |
| ACS712 screw terminal IP− | Switch → appliance live |
| Mains **Neutral** | Appliance neutral (does **not** go through the sensor) |

All grounds (ESP32 GND, ACS712 GND, divider bottoms) must be common. Mains
neutral is **never** connected to the ESP32 ground.

---

## Firmware

### Configuration

`firmware/include/config.h` holds every tunable value:

| Constant | Default | Meaning |
|---|---|---|
| `ACS712_SENSITIVITY_MV_PER_A` | `100` | 185 for 5A, 100 for 20A, 66 for 30A |
| `DIVIDER_R_TOP_OHMS` / `DIVIDER_R_BOTTOM_OHMS` | 10k / 20k | Divider resistors |
| `RMS_WINDOW_MS` | `200` | RMS window (10 cycles at 50 Hz) |
| `NOISE_FLOOR_A` | `0.15` | Readings below this show 0 A |
| `MAINS_VOLTAGE` | `230` | Assumed RMS mains voltage |
| `POWER_FACTOR` | `0.9` | Used for `P = V × Irms × PF` |
| `UPLOAD_INTERVAL_MS` | `5000` | Firebase upload period |
| `DEVICE_ID` | `esp32_01` | Firebase device node |

### Secrets

```bash
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

Fill in WiFi credentials, the Firebase Web API key, database URL, and the
email/password of the device user (see Firebase setup). `secrets.h` is
gitignored.

### Build and flash

Install [PlatformIO](https://platformio.org/install/cli) (CLI or the VS Code
extension), connect the ESP32 over USB, then:

```bash
cd firmware
pio run                    # build
pio run -t upload          # flash
pio device monitor         # serial output at 115200 baud
```

If the upload doesn't start, hold the **BOOT** button on the DevKit while
"Connecting…" is printed.

### Calibration note

On every boot the firmware measures each sensor's zero-current output
(average of 1000 samples) and uses it as the offset. **All loads must be OFF
for the first few seconds after power-up / reset.** The serial log prints each
offset; it should be near 2500 mV. If a channel is far off, check its divider
and wiring.

If an idle channel shows a small non-zero current, raise `NOISE_FLOOR_A`. For
better accuracy, compare against a known load (e.g. a 1000 W heater) or a
clamp meter, and adjust `ACS712_SENSITIVITY_MV_PER_A` or `POWER_FACTOR`.
Since voltage isn't measured, power is an estimate based on 230 V and the
configured power factor.

---

## Firebase setup

1. Go to the [Firebase console](https://console.firebase.google.com/) and
   create a project.
2. **Build → Realtime Database → Create database.** Pick a location (e.g.
   `asia-southeast1`) and start in **locked mode**. Copy the database URL
   shown at the top of the Data tab.
3. **Rules tab:** paste the following and publish:

   ```json
   {
     "rules": {
       "devices": {
         "$device": {
           ".read": "auth != null",
           ".write": "auth != null",
           "history": {
             "$switch": { ".indexOn": ["ts"] }
           }
         }
       }
     }
   }
   ```

   The `.indexOn` lets the dashboard query history by time.
4. **Build → Authentication → Get started → Sign-in method:** enable
   **Email/Password**. Under **Users**, add a user for the device (e.g.
   `device@yourdomain.com`). Put that email/password in `secrets.h`.
5. **Project settings → General:** copy the **Web API Key** into `secrets.h`
   (add a web app if no key is shown).
6. **Project settings → Service accounts → Generate new private key.** Save
   the JSON as `dashboard/serviceAccount.json`. This file is gitignored;
   never commit it. The Admin SDK bypasses the database rules.

### Data layout

```
/devices/esp32_01/live/switch_N            -> { current, power, energy_wh, ts }
/devices/esp32_01/history/switch_N/<id>    -> { current, power, ts }
```

`current` is in A (RMS), `power` in W, `energy_wh` is cumulative since the
ESP32 booted, and `ts` is Unix time in seconds (from NTP; the dashboard
displays it in IST).

---

## Dashboard

```bash
cd dashboard
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
cp .env.example .env            # then edit .env
python app.py
```

Open <http://localhost:5000>. The page shows:

- **Live power** per switch (refreshes every 5 s, marks a switch offline if
  no data for 30 s)
- **Energy today**, integrated from history since IST midnight
- **History** chart per switch (1 h / 6 h / 24 h)
- **Insights** (from `ml.py`, last 48 h of history, refreshed each minute):
  - *Anomalies:* IsolationForest on power and its rate of change
  - *Usage pattern:* KMeans on hourly energy, labelled idle / normal / heavy
  - *Next-hour estimate:* LinearRegression on hour-of-day and the previous
    hour's energy

Each model needs a minimum amount of data (50 samples, or 6 hours of
history). Until then the dashboard shows "Collecting data" instead of a
result.

## Simulator

Test the dashboard and ML without any hardware. It uses the same `.env` and
service account as the dashboard:

```bash
pip install -r dashboard/requirements.txt
python tools/simulate.py                 # live readings every 5 s
python tools/simulate.py --backfill 24   # write 24 h of history first, then go live
```

It simulates a fan, lights, a cycling fridge and a heavy iron/heater, with
occasional spikes for the anomaly detector to find. Use `--backfill` so the
clustering and forecast have enough hourly data straight away.
