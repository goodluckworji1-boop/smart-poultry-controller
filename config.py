"""
Configuration for the Improved IoT-Based Smart Poultry House Controller.

DB_ENGINE:
  "sqlite" - runs immediately with no setup (good for a quick test)
  "mysql"  - uses MySQL (as described in the dissertation). Start MySQL from
             XAMPP/WAMP first, then set DB_ENGINE = "mysql".
"""

DB_ENGINE = "sqlite"          # change to "mysql" for the defense

MYSQL = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",           # XAMPP default is empty
    "database": "smart_poultry_db",
}

SQLITE_PATH = "smart_poultry.db"

SECRET_KEY = "change-this-secret-key"

# The ESP32 must send this key in the X-API-KEY header
API_KEY = "esp32-poultry-key"

# Default flock age (days) shown when the app starts
DEFAULT_BIRD_AGE = 21

# Seconds between readings in the built-in simulator
SIMULATION_INTERVAL = 3

# Optional email alerts (leave SMTP_HOST empty to only log alerts)
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASSWORD = ""
ALERT_EMAIL_TO = ""
