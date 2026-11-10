"""
System evaluation for Chapter Four (Discussion of Result).
1. Response time: 1,000 sensor packets through the /api/sensor endpoint
2. Data integrity: checks every stored record for missing values
3. Environmental stability: the same simulated poultry house run for
   1,200 readings (one hour at 3-second intervals) with no controller,
   a fixed-threshold controller (existing system logic) and the DNN controller
Run:  python evaluate_system.py    -> results in model/evaluation.json
"""
import json
import os
import random
import statistics
import time

import config
config.DB_ENGINE = "sqlite"
config.SQLITE_PATH = "evaluation.db"

import db
import dnn_model
from control import decide
from dnn_model import comfort_range
import app as webapp

BASE = os.path.dirname(os.path.abspath(__file__))


def latency_test(n=1000):
    client = webapp.app.test_client()
    times, dnn_times = [], []
    for i in range(n):
        pkt = {"temperature": round(random.uniform(18, 34), 1),
               "humidity": round(random.uniform(40, 95), 1),
               "ammonia": round(random.uniform(2, 35), 1),
               "light": random.randint(5, 500), "feed_level": random.randint(5, 100)}
        t0 = time.perf_counter()
        dnn_model.predict(pkt["temperature"], pkt["humidity"], pkt["ammonia"], 21)
        dnn_times.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        r = client.post("/api/sensor", json=pkt, headers={"X-API-KEY": config.API_KEY})
        times.append(time.perf_counter() - t0)
        assert r.status_code == 200
    ms = lambda v: round(v * 1000, 2)
    times.sort()
    return {"requests": n,
            "dnn_inference_mean_ms": ms(statistics.mean(dnn_times)),
            "end_to_end_mean_ms": ms(statistics.mean(times)),
            "end_to_end_p95_ms": ms(times[int(0.95 * n) - 1]),
            "end_to_end_max_ms": ms(times[-1]),
            "successful": n}


def integrity_test():
    rows = db.query("SELECT * FROM sensor_logs")
    nulls = sum(1 for r in rows for v in r.values() if v is None)
    return {"records": len(rows), "records_with_missing_values": nulls}


def run_house(mode, steps=1200, seed=7, age=21):
    random.seed(seed)
    webapp.STATE["bird_age"] = age
    webapp.STATE["actuators"] = {"fan": 0, "heater": 0, "feeder": 0, "lights": 0}
    sim = webapp.PoultryHouseSimulator()
    lo, hi = comfort_range(age)
    temps, ammonia, feed, recent = [], [], [], []
    for _ in range(steps):
        r = sim.step()
        r = {k: round(v, 1) for k, v in r.items()}
        r["bird_age"] = age
        if mode == "threshold":
            # existing-system logic: static temperature thresholds only
            webapp.STATE["actuators"] = {"fan": int(r["temperature"] >= 30),
                                         "heater": int(r["temperature"] <= 24),
                                         "feeder": int(r["feed_level"] < 20), "lights": 0}
        elif mode == "dnn":
            label, _, _ = dnn_model.predict(r["temperature"], r["humidity"], r["ammonia"], age)
            act, _, _, _ = decide(label, r, recent[-6:])
            webapp.STATE["actuators"] = act
        recent.append(r["temperature"])
        temps.append(r["temperature"])
        ammonia.append(r["ammonia"])
        feed.append(r["feed_level"])
    inside = sum(1 for t in temps if lo <= t <= hi)
    return {
        "within_comfort_zone_pct": round(100 * inside / steps, 1),
        "temperature_std_c": round(statistics.pstdev(temps), 2),
        "temperature_range_c": [round(min(temps), 1), round(max(temps), 1)],
        "ammonia_readings_at_or_above_20ppm": sum(1 for a in ammonia if a >= 20),
        "max_ammonia_ppm": round(max(ammonia), 1),
        "low_feed_readings_below_20pct": sum(1 for f in feed if f < 20),
        "temps": temps, "ammonia": ammonia,
    }


def stability_chart(off, thr, on, lo, hi):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = [i * 3 / 60 for i in range(len(off["temps"]))]
    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    ax = axes[0]
    ax.axhspan(lo, hi, color="#3F8A4F", alpha=0.15, label="Comfort zone (day 21)")
    ax.plot(x, off["temps"], color="#B83A2B", lw=1, label="Without controller")
    ax.plot(x, thr["temps"], color="#D4A72C", lw=1, label="Fixed-threshold controller")
    ax.plot(x, on["temps"], color="#2D6A8E", lw=1.2, label="With DNN controller")
    ax.set_ylabel("Temperature (°C)")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("Environmental stability under three control strategies")
    ax = axes[1]
    ax.axhline(20, color="black", ls="--", lw=1, label="20 ppm limit")
    ax.plot(x, off["ammonia"], color="#B83A2B", lw=1, label="Without controller")
    ax.plot(x, thr["ammonia"], color="#D4A72C", lw=1, label="Fixed-threshold controller")
    ax.plot(x, on["ammonia"], color="#2D6A8E", lw=1.2, label="With DNN controller")
    ax.set_ylabel("Ammonia (ppm)")
    ax.set_xlabel("Time (minutes)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(BASE, "static", "img", "stability_comparison.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    if os.path.exists(config.SQLITE_PATH):
        os.remove(config.SQLITE_PATH)
    db.init_db()
    dnn_model.load_model()
    random.seed(1)
    lat = latency_test()
    integ = integrity_test()
    off = run_house("none")
    thr = run_house("threshold")
    on = run_house("dnn")
    lo, hi = comfort_range(21)
    stability_chart(off, thr, on, lo, hi)
    for d in (off, thr, on):
        d.pop("temps"), d.pop("ammonia")
    result = {"latency": lat, "integrity": integ,
              "stability": {"comfort_zone_c": [lo, hi], "without_controller": off,
                            "fixed_threshold_controller": thr,
                            "with_controller": on}}
    with open(os.path.join(BASE, "model", "evaluation.json"), "w") as f:
        json.dump(result, f, indent=2)
    os.remove(config.SQLITE_PATH)
    print(json.dumps(result, indent=2))
