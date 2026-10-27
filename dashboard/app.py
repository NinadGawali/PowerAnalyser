"""Flask dashboard for the Electronic Power Consumption Analyzer."""

import os
import time

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, db
from flask import Flask, jsonify, render_template, request

import ml

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "esp32_01")
SWITCHES = [f"switch_{i}" for i in range(1, 5)]
# How much history the ML models look at
ML_WINDOW_HOURS = int(os.getenv("ML_WINDOW_HOURS", "48"))
INSIGHTS_CACHE_S = 60

firebase_admin.initialize_app(
    credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]),
    {"databaseURL": os.environ["FIREBASE_DB_URL"]},
)

app = Flask(__name__)
_insights_cache = {"at": 0, "data": None}


def device_ref(path):
    return db.reference(f"devices/{DEVICE_ID}/{path}")


def fetch_history(switch, since_ts):
    """History entries for one switch newer than since_ts (needs .indexOn ts)."""
    data = device_ref(f"history/{switch}").order_by_child("ts").start_at(since_ts).get()
    return ml.to_frame(data)


@app.route("/")
def index():
    return render_template("index.html", switches=SWITCHES, device_id=DEVICE_ID)


@app.route("/api/live")
def api_live():
    live = device_ref("live").get() or {}
    return jsonify({sw: live.get(sw) for sw in SWITCHES})


@app.route("/api/history")
def api_history():
    switch = request.args.get("switch", "switch_1")
    if switch not in SWITCHES:
        return jsonify({"error": "unknown switch"}), 400
    hours = min(float(request.args.get("hours", 6)), 72)
    df = fetch_history(switch, int(time.time() - hours * 3600))
    return jsonify({
        "ts": df["ts"].astype(int).tolist(),
        "power": df["power"].round(1).tolist(),
    })


@app.route("/api/today")
def api_today():
    start = ml.today_start_ts()
    per_switch = {sw: round(ml.energy_wh(fetch_history(sw, start)), 2) for sw in SWITCHES}
    return jsonify({"switches": per_switch, "total_wh": round(sum(per_switch.values()), 2)})


@app.route("/api/insights")
def api_insights():
    if time.time() - _insights_cache["at"] > INSIGHTS_CACHE_S:
        since = int(time.time() - ML_WINDOW_HOURS * 3600)
        _insights_cache["data"] = {
            sw: ml.insights_for(fetch_history(sw, since)) for sw in SWITCHES
        }
        _insights_cache["at"] = time.time()
    return jsonify(_insights_cache["data"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
