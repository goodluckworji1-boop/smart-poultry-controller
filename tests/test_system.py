"""
Software test cases for the Smart Poultry House Controller.
Run from the project folder:   python -m unittest -v tests/test_system.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.SQLITE_PATH = "test_poultry.db"
config.DB_ENGINE = "sqlite"

import db
import dnn_model
from control import decide
from app import app


class TestSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(config.SQLITE_PATH):
            os.remove(config.SQLITE_PATH)
        db.init_db()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.remove(config.SQLITE_PATH)

    def login(self):
        return self.client.post("/login", data={"username": "admin", "password": "admin123"})

    # TC01
    def test_01_valid_login(self):
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/dashboard", r.headers["Location"])

    # TC02
    def test_02_invalid_login(self):
        r = self.client.post("/login", data={"username": "admin", "password": "wrong"})
        self.assertIn(b"Invalid username or password", r.data)

    # TC03
    def test_03_dashboard_requires_login(self):
        c = app.test_client()
        r = c.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    # TC04
    def test_04_optimal_prediction(self):
        label, conf, _ = dnn_model.predict(26.5, 60, 6, 21)
        self.assertEqual(label, "Optimal")

    # TC05
    def test_05_humidity_heat_stress(self):
        label, _, _ = dnn_model.predict(27.5, 90, 10, 21)
        self.assertEqual(label, "Heat Stress")

    # TC06
    def test_06_cold_stress_brooding_chicks(self):
        label, _, _ = dnn_model.predict(28.0, 60, 6, 3)
        self.assertEqual(label, "Cold Stress")

    # TC07
    def test_07_ammonia_priority(self):
        label, _, _ = dnn_model.predict(22.0, 55, 35, 21)
        self.assertEqual(label, "Poor Air Quality")

    # TC08
    def test_08_ammonia_with_cold_turns_on_fan_and_heater(self):
        r = {"temperature": 22.0, "humidity": 55, "ammonia": 35, "light": 300,
             "feed_level": 70, "bird_age": 21}
        act, action, status, alerts = decide("Poor Air Quality", r, [])
        self.assertEqual((act["fan"], act["heater"], status), (1, 1, "Critical"))

    # TC09
    def test_09_low_feed_alert(self):
        r = {"temperature": 26.5, "humidity": 60, "ammonia": 6, "light": 300,
             "feed_level": 12, "bird_age": 21}
        act, action, status, alerts = decide("Optimal", r, [])
        self.assertEqual(act["feeder"], 1)
        self.assertTrue(any("Low feed" in m for _, m in alerts))

    # TC10
    def test_10_rising_temperature_warning(self):
        r = {"temperature": 27.8, "humidity": 60, "ammonia": 6, "light": 300,
             "feed_level": 70, "bird_age": 21}
        _, _, status, alerts = decide("Optimal", r, [25.0, 25.6, 26.3, 26.9, 27.3])
        self.assertEqual(status, "Warning")
        self.assertTrue(any("rising" in m for _, m in alerts))

    # TC11
    def test_11_sensor_api_rejects_bad_key(self):
        r = self.client.post("/api/sensor", json={"temperature": 25, "humidity": 60, "ammonia": 5},
                             headers={"X-API-KEY": "wrong"})
        self.assertEqual(r.status_code, 401)

    # TC12
    def test_12_sensor_api_rejects_incomplete_packet(self):
        r = self.client.post("/api/sensor", json={"temperature": 25},
                             headers={"X-API-KEY": config.API_KEY})
        self.assertEqual(r.status_code, 400)

    # TC13
    def test_13_sensor_api_stores_reading_and_returns_commands(self):
        before = db.query("SELECT COUNT(*) AS n FROM sensor_logs", one=True)["n"]
        r = self.client.post("/api/sensor",
                             json={"temperature": 31, "humidity": 85, "ammonia": 12,
                                   "light": 500, "feed_level": 70},
                             headers={"X-API-KEY": config.API_KEY})
        d = r.get_json()
        after = db.query("SELECT COUNT(*) AS n FROM sensor_logs", one=True)["n"]
        self.assertEqual(r.status_code, 200)
        self.assertEqual(d["prediction"], "Heat Stress")
        self.assertEqual(d["fan"], 1)
        self.assertEqual(after, before + 1)

    # TC14
    def test_14_alert_saved_for_critical_reading(self):
        a = db.query("SELECT * FROM alerts ORDER BY id DESC LIMIT 1", one=True)
        self.assertIsNotNone(a)

    # TC15
    def test_15_register_user(self):
        self.login()
        self.client.post("/users", data={"first_name": "Test", "last_name": "Attendant",
                                         "role": "Poultry Attendant", "gender": "Female",
                                         "address": "Farm", "username": "attendant1",
                                         "password": "secret123"})
        u = db.query("SELECT * FROM users WHERE username = ?", ("attendant1",), one=True)
        self.assertIsNotNone(u)
        self.assertNotEqual(u["password_hash"], "secret123")   # stored as hash

    # TC16
    def test_16_manual_override(self):
        self.login()
        self.client.post("/api/control", json={"mode": "manual"})
        self.client.post("/api/control", json={"device": "fan", "value": 1})
        d = self.client.get("/api/latest").get_json()
        self.assertEqual(d["state"]["mode"], "manual")
        self.assertEqual(d["state"]["actuators"]["fan"], 1)
        self.client.post("/api/control", json={"mode": "auto"})

    # TC17
    def test_17_csv_export(self):
        self.login()
        r = self.client.get("/logs/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"temperature", r.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
