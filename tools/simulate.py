"""Push realistic fake readings to Firebase so the dashboard and ML can be
tested without hardware.

Writes the same paths as the ESP32:
  /devices/<DEVICE_ID>/live/switch_N
  /devices/<DEVICE_ID>/history/switch_N/<push id>

Usage (from the repo root, with dashboard/.env configured):
  python tools/simulate.py                 # live mode, one sample every 5 s
  python tools/simulate.py --backfill 24   # first write 24 h of history, then go live
"""

import argparse
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, db

IST = timezone(timedelta(hours=5, minutes=30))
VOLTAGE = 230.0
POWER_FACTOR = 0.9
INTERVAL_S = 5

# Typical appliance profiles: (name, watts when on, hours of day it tends to run)
APPLIANCES = {
    "switch_1": ("fan", 75, range(0, 24)),
    "switch_2": ("lights", 40, list(range(18, 24)) + list(range(5, 8))),
    "switch_3": ("fridge", 150, range(0, 24)),       # cycles on/off
    "switch_4": ("iron/heater", 1000, [7, 8, 19]),  # short heavy bursts
}


def is_on(switch, t):
    _, _, hours = APPLIANCES[switch]
    hour = datetime.fromtimestamp(t, IST).hour
    if hour not in hours:
        return False
    if switch == "switch_3":
        # Fridge compressor: ~15 min on, ~20 min off
        return (t // 60) % 35 < 15
    if switch == "switch_4":
        return (t // 60) % 60 < 20
    return True


def reading(switch, t):
    _, watts, _ = APPLIANCES[switch]
    if not is_on(switch, t):
        return 0.0, 0.0
    power = watts * random.uniform(0.95, 1.05)
    # Rare spike so anomaly detection has something to find
    if random.random() < 0.003:
        power *= random.uniform(2.0, 3.0)
    current = power / (VOLTAGE * POWER_FACTOR)
    return round(current, 3), round(power, 1)


def init_firebase():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "dashboard", ".env"))
    load_dotenv()
    firebase_admin.initialize_app(
        credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]),
        {"databaseURL": os.environ["FIREBASE_DB_URL"]},
    )
    return db.reference(f"devices/{os.getenv('DEVICE_ID', 'esp32_01')}")


def backfill(root, hours):
    """Write `hours` of history in batches using multi-path updates."""
    start = int(time.time() - hours * 3600)
    batch = {}
    for t in range(start, int(time.time()), INTERVAL_S):
        for sw in APPLIANCES:
            current, power = reading(sw, t)
            # One sample per switch per second at most, so a timestamped key is unique
            batch[f"history/{sw}/sim_{t}"] = {"current": current, "power": power, "ts": t}
        if len(batch) >= 2000:
            root.update(batch)
            batch = {}
            print(f"  backfilled up to {datetime.fromtimestamp(t, IST):%d %b %H:%M}")
    if batch:
        root.update(batch)
    print(f"Backfill of {hours} h done.")


def run_live(root):
    energy = {sw: 0.0 for sw in APPLIANCES}
    last = time.time()
    print("Simulating live readings, Ctrl+C to stop.")
    while True:
        now = time.time()
        t = int(now)
        update = {}
        for sw in APPLIANCES:
            current, power = reading(sw, t)
            energy[sw] += power * (now - last) / 3600.0
            update[f"live/{sw}"] = {
                "current": current, "power": power,
                "energy_wh": round(energy[sw], 3), "ts": t,
            }
            update[f"history/{sw}/sim_{t}"] = {
                "current": current, "power": power, "ts": t,
            }
        last = now
        root.update(update)
        print(f"{datetime.now(IST):%H:%M:%S}  " + "  ".join(
            f"{sw}={update[f'live/{sw}']['power']:7.1f}W" for sw in APPLIANCES))
        time.sleep(INTERVAL_S)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", type=float, default=0, metavar="HOURS",
                        help="write this many hours of past history before going live")
    args = parser.parse_args()

    root = init_firebase()
    if args.backfill > 0:
        backfill(root, args.backfill)
    run_live(root)


if __name__ == "__main__":
    main()
