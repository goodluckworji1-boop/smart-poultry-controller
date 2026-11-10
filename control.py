"""
Intelligence & control block: turns the DNN prediction into actuator
commands (fan, heater, feeder, lights), alert messages and a status level.
Feed level and lighting are handled by supervisory rules; the trend check
gives the predictive warning described in Section 3.2.3.
"""
from dnn_model import comfort_range

FEED_LOW = 20        # percent
LIGHT_MIN = 20       # lux at bird eye level (Section 3.7)


def decide(pred, r, recent_temps):
    """pred: DNN class; r: reading dict; recent_temps: oldest->newest list."""
    low, high = comfort_range(r["bird_age"])
    act = {"fan": 0, "heater": 0, "feeder": 0, "lights": 0}
    actions, alerts = [], []
    status = "Normal"

    if pred == "Heat Stress":
        act["fan"] = 1
        actions.append("Fans ON at 100%, heater OFF")
        alerts.append(("Critical", f"Heat stress predicted ({r['temperature']} °C, "
                                   f"{r['humidity']}% RH). Cooling activated."))
        status = "Critical"
    elif pred == "Cold Stress":
        act["heater"] = 1
        actions.append("Heater ON, fans at minimum")
        alerts.append(("Warning", f"Cold stress predicted ({r['temperature']} °C, "
                                  f"target {low}-{high} °C for day {r['bird_age']}). "
                                  "Heating activated."))
        status = "Warning"
    elif pred == "Poor Air Quality":
        act["fan"] = 1
        msg = "Ventilation ON to clear ammonia"
        if r["temperature"] < low + 1:
            act["heater"] = 1
            msg += "; heater ON to offset heat loss"
        actions.append(msg)
        alerts.append(("Critical", f"Poor air quality: ammonia at {r['ammonia']} ppm "
                                   "(limit 20 ppm). Ventilation activated."))
        status = "Critical"
    else:
        actions.append("Optimal state: no corrective action")

    # supervisory rule: feed level (ultrasonic sensor)
    if r["feed_level"] < FEED_LOW:
        act["feeder"] = 1
        actions.append("Feeder ON / refill feed")
        alerts.append(("Warning", f"Low feed level ({r['feed_level']}%). Refill the feed silo."))
        if status == "Normal":
            status = "Warning"

    # supervisory rule: lighting (LDR)
    if r["light"] < LIGHT_MIN:
        act["lights"] = 1
        actions.append("Lights ON")

    # predictive warning: temperature trend over recent readings
    if len(recent_temps) >= 5:
        rise = r["temperature"] - recent_temps[0]
        if rise >= 2.0 and pred != "Heat Stress":
            alerts.append(("Warning", f"Temperature rising ({rise:+.1f} °C over the last "
                                      f"{len(recent_temps)} readings). Heat stress likely soon; "
                                      "check ventilation."))
            if status == "Normal":
                status = "Warning"

    return act, "; ".join(actions), status, alerts
