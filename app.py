"""
Improved IoT-Based Smart Poultry House Controller
Python (Flask) backend + MySQL + HTML/CSS/JavaScript dashboard.

Run:  python app.py      then open http://127.0.0.1:5000
Login: admin / admin123
"""
import csv
import io
import random
import smtplib
import threading
import time
from email.message import EmailMessage
from functools import wraps

from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import dnn_model
from control import decide
from dnn_model import comfort_range

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# live controller state (kept in memory)
STATE = {
    "bird_age": config.DEFAULT_BIRD_AGE,
    "mode": "auto",                                   # auto | manual
    "manual": {"fan": 0, "heater": 0, "feeder": 0, "lights": 0},
    "actuators": {"fan": 0, "heater": 0, "feeder": 0, "lights": 0},
    "simulating": False,
    "last_probs": {},
}
LOCK = threading.Lock()


# ---------------------------------------------------------------- helpers
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("is_admin"):
            flash("Only the administrator can manage users.")
            return redirect(url_for("dashboard"))
        return f(*a, **k)
    return wrap


def send_email(subject, body):
    if not config.SMTP_HOST:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, config.SMTP_USER, config.ALERT_EMAIL_TO
        msg.set_content(body)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception as e:
        print("Email failed:", e)
        return False


def process_reading(r, source):
    """Core pipeline: acquire -> normalise + DNN inference -> decide -> store."""
    r = {
        "temperature": round(float(r["temperature"]), 1),
        "humidity": round(float(r["humidity"]), 1),
        "ammonia": round(float(r["ammonia"]), 1),
        "light": round(float(r.get("light", 300)), 0),
        "feed_level": round(float(r.get("feed_level", 80)), 0),
        "bird_age": int(r.get("bird_age") or STATE["bird_age"]),
    }
    label, conf, probs = dnn_model.predict(r["temperature"], r["humidity"],
                                           r["ammonia"], r["bird_age"])
    recent = db.query("SELECT temperature FROM sensor_logs ORDER BY id DESC LIMIT 6")
    recent_temps = [x["temperature"] for x in reversed(recent)]
    act, action, status, alerts = decide(label, r, recent_temps)

    with LOCK:
        if STATE["mode"] == "manual":
            act = dict(STATE["manual"])
            action = "MANUAL OVERRIDE: " + ", ".join(
                f"{k} {'ON' if v else 'OFF'}" for k, v in act.items())
        STATE["actuators"] = act
        STATE["last_probs"] = probs

    log_id = db.execute(
        "INSERT INTO sensor_logs (temperature, humidity, ammonia, light, feed_level, "
        "bird_age, prediction, confidence, status, action, fan, heater, feeder, lights, "
        "source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (r["temperature"], r["humidity"], r["ammonia"], r["light"], r["feed_level"],
         r["bird_age"], label, conf, status, action, act["fan"], act["heater"],
         act["feeder"], act["lights"], source, db.now()))
    for level, msg in alerts:
        db.execute("INSERT INTO alerts (log_id, level, message, escalated, created_at) "
                   "VALUES (?,?,?,0,?)", (log_id, level, msg, db.now()))
    return {"log_id": log_id, "prediction": label, "confidence": conf,
            "probabilities": probs, "status": status, "action": action, **act}


# ---------------------------------------------------------------- simulator
class PoultryHouseSimulator:
    """Stands in for the ESP32 + sensors. Conditions drift, scripted events
    happen (heat wave, ammonia build-up, feed running low) and the actuators
    feed back into the environment, so the closed control loop can be seen."""

    def __init__(self):
        self.reset()

    def reset(self):
        lo, hi = comfort_range(STATE["bird_age"])
        self.t, self.h, self.a = (lo + hi) / 2, 62.0, 8.0
        self.light, self.feed = 350.0, 80.0
        self.tick, self.event = 0, None

    def step(self):
        self.tick += 1
        lo, hi = comfort_range(STATE["bird_age"])
        if self.tick % 8 == 0:
            self.event = random.choice(["heat", "ammonia", "cold", "feed", "humid"])
        act = STATE["actuators"]

        if self.event == "heat":
            self.t += random.uniform(0.5, 1.0)
        elif self.event == "cold":
            self.t -= random.uniform(0.5, 1.0)
        elif self.event == "ammonia":
            self.a += random.uniform(2.0, 4.0)
        elif self.event == "humid":
            self.h += random.uniform(2, 4)
        elif self.event == "feed":
            self.feed -= random.uniform(6, 10)

        # actuator feedback
        if act["fan"]:
            self.t -= 0.8
            self.a -= 4.0
            self.h -= 1.5
            if self.event in ("heat", "ammonia", "humid"):
                self.event = None if random.random() < 0.3 else self.event
        if act["heater"]:
            self.t += 0.8
            if self.event == "cold" and random.random() < 0.3:
                self.event = None
        if act["feeder"]:
            self.feed = min(95, self.feed + 15)
            if self.event == "feed":
                self.event = None

        # natural drift back toward normal
        self.t += ((lo + hi) / 2 - self.t) * 0.03 + random.uniform(-0.3, 0.3)
        self.h += (62 - self.h) * 0.05 + random.uniform(-1, 1)
        self.a += (8 - self.a) * 0.02 + random.uniform(-0.4, 0.6)   # natural air exchange
        self.feed -= random.uniform(0.2, 0.8)
        self.light = 350 + random.uniform(-40, 40)

        self.t = max(12, min(42, self.t))
        self.h = max(30, min(98, self.h))
        self.a = max(1, min(60, self.a))
        self.feed = max(0, min(100, self.feed))
        return {"temperature": self.t, "humidity": self.h, "ammonia": self.a,
                "light": self.light, "feed_level": self.feed}


SIM = PoultryHouseSimulator()


def simulation_loop():
    while True:
        if STATE["simulating"]:
            try:
                process_reading(SIM.step(), "simulator")
            except Exception as e:
                print("Simulator error:", e)
        time.sleep(config.SIMULATION_INTERVAL)


# ---------------------------------------------------------------- auth pages
@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db.query("SELECT * FROM users WHERE username = ?",
                     (request.form["username"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.update(user_id=u["id"], is_admin=bool(u["is_admin"]),
                           name=f"{u['first_name']} {u['last_name']}", role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- main pages
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", page="dashboard")


@app.route("/logs")
@login_required
def logs():
    status = request.args.get("status", "")
    if status:
        rows = db.query("SELECT * FROM sensor_logs WHERE status = ? ORDER BY id DESC LIMIT 300",
                        (status,))
    else:
        rows = db.query("SELECT * FROM sensor_logs ORDER BY id DESC LIMIT 300")
    total = db.query("SELECT COUNT(*) AS n FROM sensor_logs", one=True)["n"]
    return render_template("logs.html", page="logs", rows=rows, status=status, total=total)


@app.route("/logs/export")
@login_required
def export_logs():
    rows = db.query("SELECT * FROM sensor_logs ORDER BY id")
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sensor_logs.csv"})


@app.route("/alerts")
@login_required
def alerts():
    rows = db.query("SELECT * FROM alerts ORDER BY id DESC LIMIT 200")
    return render_template("alerts.html", page="alerts", rows=rows)


@app.route("/alerts/<int:aid>/escalate", methods=["POST"])
@login_required
def escalate(aid):
    a = db.query("SELECT * FROM alerts WHERE id = ?", (aid,), one=True)
    if a:
        db.execute("UPDATE alerts SET escalated = 1 WHERE id = ?", (aid,))
        sent = send_email(f"[Poultry House] {a['level']} alert", a["message"])
        flash("Alert escalated" + (" and emailed to the farm manager." if sent
                                   else " (email not configured, escalation logged)."))
    return redirect(url_for("alerts"))


@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    if request.method == "POST":
        f = request.form
        if db.query("SELECT id FROM users WHERE username = ?", (f["username"],)):
            flash("That username already exists.")
        else:
            db.execute(
                "INSERT INTO users (first_name, last_name, role, gender, address, username, "
                "password_hash, is_admin, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (f["first_name"], f["last_name"], f["role"], f["gender"], f["address"],
                 f["username"], generate_password_hash(f["password"]),
                 1 if f.get("is_admin") else 0, db.now()))
            flash("User registered.")
        return redirect(url_for("users"))
    rows = db.query("SELECT * FROM users ORDER BY id")
    return render_template("users.html", page="users", rows=rows)


@app.route("/users/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(uid):
    if uid == session["user_id"]:
        flash("You cannot delete your own account.")
    else:
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        flash("User deleted.")
    return redirect(url_for("users"))


@app.route("/performance")
@login_required
def performance():
    m = dnn_model.load_metrics()
    s = db.query("SELECT COUNT(*) AS n, MIN(created_at) AS first, MAX(created_at) AS last "
                 "FROM sensor_logs", one=True)
    by_status = db.query("SELECT status, COUNT(*) AS n FROM sensor_logs GROUP BY status")
    return render_template("performance.html", page="performance", m=m, s=s,
                           by_status=by_status)


# ---------------------------------------------------------------- APIs
@app.route("/api/sensor", methods=["POST"])
def api_sensor():
    """Endpoint the ESP32 posts JSON to. Returns relay commands."""
    if request.headers.get("X-API-KEY") != config.API_KEY:
        return jsonify({"error": "invalid API key"}), 401
    data = request.get_json(silent=True) or {}
    missing = [k for k in ("temperature", "humidity", "ammonia") if k not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    return jsonify(process_reading(data, "esp32"))


@app.route("/api/manual-reading", methods=["POST"])
@login_required
def api_manual_reading():
    return jsonify(process_reading(request.get_json(), "test input"))


@app.route("/api/latest")
@login_required
def api_latest():
    rows = db.query("SELECT * FROM sensor_logs ORDER BY id DESC LIMIT 40")
    al = db.query("SELECT * FROM alerts ORDER BY id DESC LIMIT 6")
    lo, hi = comfort_range(STATE["bird_age"])
    return jsonify({
        "latest": rows[0] if rows else None,
        "history": list(reversed(rows)),
        "alerts": al,
        "state": {k: STATE[k] for k in ("bird_age", "mode", "actuators", "simulating",
                                        "last_probs")},
        "comfort": [lo, hi],
    })


@app.route("/api/control", methods=["POST"])
@login_required
def api_control():
    d = request.get_json()
    with LOCK:
        if "simulating" in d:
            STATE["simulating"] = bool(d["simulating"])
            if STATE["simulating"]:
                SIM.reset()
        if "mode" in d:
            STATE["mode"] = d["mode"]
            if d["mode"] == "manual":
                STATE["manual"] = dict(STATE["actuators"])
        if "device" in d and STATE["mode"] == "manual":
            STATE["manual"][d["device"]] = int(d["value"])
            STATE["actuators"] = dict(STATE["manual"])
        if "bird_age" in d:
            STATE["bird_age"] = max(1, min(42, int(d["bird_age"])))
    return jsonify({"ok": True})


if __name__ == "__main__":
    db.init_db()
    dnn_model.load_model()
    threading.Thread(target=simulation_loop, daemon=True).start()
    print("\n  Smart Poultry House Controller running at http://127.0.0.1:5000")
    print("  Login: admin / admin123\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
