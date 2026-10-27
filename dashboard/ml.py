"""ML insights over the power history stored in Firebase.

Every function accepts whatever data is available and returns a dict with a
"status" of "ok" or "not_enough_data" instead of raising, so the dashboard
works from the very first reading.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression

IST = timezone(timedelta(hours=5, minutes=30))

# Gaps longer than this between samples are treated as "device offline"
# and not integrated into energy.
MAX_SAMPLE_GAP_S = 30

MIN_ANOMALY_SAMPLES = 50
MIN_CLUSTER_HOURS = 6
MIN_FORECAST_HOURS = 6

USAGE_LABELS = ["idle", "normal", "heavy"]


def to_frame(history):
    """Convert {push_id: {current, power, ts}} from Firebase into a DataFrame
    sorted by time with an IST datetime column."""
    if not history:
        return pd.DataFrame(columns=["ts", "power", "current", "time"])
    rows = [v for v in history.values() if isinstance(v, dict) and "ts" in v]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["ts", "power", "current", "time"])
    for col in ("ts", "power", "current"):
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)
    df = df.sort_values("ts").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(IST)
    return df


def energy_wh(df):
    """Integrate power over time (Wh), skipping gaps where the device was offline."""
    if len(df) < 2:
        return 0.0
    dt = df["ts"].diff().fillna(0)
    dt = dt.where(dt <= MAX_SAMPLE_GAP_S, 0)
    return float((df["power"] * dt).sum() / 3600.0)


def hourly_energy(df):
    """Energy in Wh for each IST hour that has data."""
    if len(df) < 2:
        return pd.Series(dtype=float)
    dt = df["ts"].diff().fillna(0)
    dt = dt.where(dt <= MAX_SAMPLE_GAP_S, 0)
    wh = df["power"] * dt / 3600.0
    hours = df["time"].dt.floor("h")
    return wh.groupby(hours).sum()


def detect_anomalies(df):
    """Flag unusual power readings with an IsolationForest."""
    if len(df) < MIN_ANOMALY_SAMPLES:
        return {"status": "not_enough_data", "needed": MIN_ANOMALY_SAMPLES, "have": len(df)}

    # Power level plus how sharply it changed from the previous sample
    features = np.column_stack([df["power"], df["power"].diff().fillna(0)])
    if np.ptp(features[:, 0]) == 0:
        return {"status": "ok", "count": 0, "recent": []}

    model = IsolationForest(contamination=0.01, random_state=0)
    flags = model.fit_predict(features) == -1
    anomalies = df[flags]
    recent = [
        {"time": t.strftime("%d %b %H:%M:%S"), "power": round(float(p), 1)}
        for t, p in zip(anomalies["time"].tail(5), anomalies["power"].tail(5))
    ]
    return {"status": "ok", "count": int(flags.sum()), "recent": recent[::-1]}


def cluster_usage(hourly):
    """Group hourly consumption into idle / normal / heavy with KMeans."""
    if len(hourly) < MIN_CLUSTER_HOURS:
        return {"status": "not_enough_data", "needed": MIN_CLUSTER_HOURS, "have": len(hourly)}

    values = hourly.to_numpy().reshape(-1, 1)
    k = min(3, len(np.unique(values)))
    if k < 2:
        # Every hour identical: nothing to cluster
        name = "idle" if values[0, 0] == 0 else "normal"
        counts = {n: 0 for n in USAGE_LABELS}
        counts[name] = len(values)
        return {"status": "ok", "current": name, "hours": counts}

    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(values)
    # Name clusters by ascending centre: lowest is idle, highest is heavy
    order = np.argsort(km.cluster_centers_.ravel())
    names = ["idle", "heavy"] if k == 2 else USAGE_LABELS
    label_of = {int(cluster): names[rank] for rank, cluster in enumerate(order)}

    labels = [label_of[int(c)] for c in km.labels_]
    counts = {name: labels.count(name) for name in USAGE_LABELS}
    return {"status": "ok", "current": labels[-1], "hours": counts}


def forecast_next_hour(hourly):
    """Estimate next hour's consumption (Wh) with LinearRegression on
    time-of-day and the previous hour's usage."""
    if len(hourly) < MIN_FORECAST_HOURS:
        return {"status": "not_enough_data", "needed": MIN_FORECAST_HOURS, "have": len(hourly)}

    # Fill missing hours with 0 so the lag feature is truly "previous hour"
    full_index = pd.date_range(hourly.index.min(), hourly.index.max(), freq="h")
    series = hourly.reindex(full_index, fill_value=0.0)

    def features(ts, prev):
        angle = 2 * np.pi * ts.hour / 24
        return [np.sin(angle), np.cos(angle), prev]

    X = [features(ts, series.iloc[i - 1]) for i, ts in enumerate(series.index) if i > 0]
    y = series.iloc[1:].to_numpy()

    model = LinearRegression().fit(X, y)
    next_ts = series.index[-1] + pd.Timedelta(hours=1)
    pred = model.predict([features(next_ts, series.iloc[-1])])[0]
    return {
        "status": "ok",
        "hour": next_ts.strftime("%H:00"),
        "estimate_wh": round(max(0.0, float(pred)), 1),
    }


def insights_for(df):
    hourly = hourly_energy(df)
    return {
        "anomalies": detect_anomalies(df),
        "usage": cluster_usage(hourly),
        "forecast": forecast_next_hour(hourly),
    }


def today_start_ts():
    now = datetime.now(IST)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
