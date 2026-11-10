"""
ESP32 stand-in: sends sensor readings to the server as JSON over HTTP,
exactly the way the real ESP32 firmware does, and prints the relay
commands the server sends back.

Run in a second window while app.py is running:
    python esp32_simulator.py
"""
import json
import random
import time
import urllib.request

import config

URL = "http://127.0.0.1:5000/api/sensor"


def send(reading):
    req = urllib.request.Request(URL, data=json.dumps(reading).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-API-KEY": config.API_KEY})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    print("Sending sensor packets to", URL, "(Ctrl+C to stop)\n")
    t, h, a, feed = 26.5, 62.0, 8.0, 80.0
    while True:
        t += random.uniform(-0.6, 0.8)
        h += random.uniform(-2, 2)
        a += random.uniform(-1, 1.5)
        feed -= random.uniform(0.5, 2)
        packet = {"temperature": round(t, 1), "humidity": round(h, 1),
                  "ammonia": round(max(a, 1), 1), "light": random.randint(250, 400),
                  "feed_level": round(max(feed, 0), 1)}
        res = send(packet)
        print(f"SENT {packet}")
        print(f"  DNN: {res['prediction']} ({res['confidence']}%)  "
              f"fan={res['fan']} heater={res['heater']} feeder={res['feeder']} "
              f"lights={res['lights']}\n")
        if res["fan"]:
            t -= 1.0; a -= 3; h -= 1.5
        if res["heater"]:
            t += 1.0
        if res["feeder"]:
            feed = 90
        time.sleep(3)
