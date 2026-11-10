"""
Data persistence block: MySQL (or SQLite for quick testing).
Tables: users, sensor_logs, alerts.
"""
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

import config


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mysql_conn(with_db=True):
    import pymysql
    args = dict(host=config.MYSQL["host"], port=config.MYSQL["port"],
                user=config.MYSQL["user"], password=config.MYSQL["password"],
                cursorclass=pymysql.cursors.DictCursor, autocommit=True)
    if with_db:
        args["database"] = config.MYSQL["database"]
    return pymysql.connect(**args)


def get_conn():
    if config.DB_ENGINE == "mysql":
        return _mysql_conn()
    conn = sqlite3.connect(config.SQLITE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=(), one=False):
    """Run a SELECT and return list of dicts (or one dict)."""
    if config.DB_ENGINE == "mysql":
        sql = sql.replace("?", "%s")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    """Run INSERT/UPDATE/DELETE and return the new row id."""
    if config.DB_ENGINE == "mysql":
        sql = sql.replace("?", "%s")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT, last_name TEXT, role TEXT, gender TEXT, address TEXT,
        username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS sensor_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperature REAL, humidity REAL, ammonia REAL, light REAL,
        feed_level REAL, bird_age INTEGER,
        prediction TEXT, confidence REAL, status TEXT, action TEXT,
        fan INTEGER, heater INTEGER, feeder INTEGER, lights INTEGER,
        source TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER, level TEXT, message TEXT,
        escalated INTEGER DEFAULT 0, created_at TEXT)""",
]

SCHEMA_MYSQL = [
    """CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        first_name VARCHAR(60), last_name VARCHAR(60), role VARCHAR(60),
        gender VARCHAR(10), address VARCHAR(255),
        username VARCHAR(60) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL,
        is_admin TINYINT DEFAULT 0, created_at DATETIME)""",
    """CREATE TABLE IF NOT EXISTS sensor_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        temperature FLOAT, humidity FLOAT, ammonia FLOAT, light FLOAT,
        feed_level FLOAT, bird_age INT,
        prediction VARCHAR(40), confidence FLOAT, status VARCHAR(20),
        action VARCHAR(255),
        fan TINYINT, heater TINYINT, feeder TINYINT, lights TINYINT,
        source VARCHAR(20), created_at DATETIME)""",
    """CREATE TABLE IF NOT EXISTS alerts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        log_id INT, level VARCHAR(20), message VARCHAR(255),
        escalated TINYINT DEFAULT 0, created_at DATETIME)""",
]


def init_db():
    if config.DB_ENGINE == "mysql":
        conn = _mysql_conn(with_db=False)
        conn.cursor().execute(
            f"CREATE DATABASE IF NOT EXISTS {config.MYSQL['database']}")
        conn.close()
        schema = SCHEMA_MYSQL
    else:
        schema = SCHEMA_SQLITE
    for stmt in schema:
        execute(stmt)

    if not query("SELECT id FROM users WHERE username = ?", ("admin",)):
        execute(
            "INSERT INTO users (first_name, last_name, role, gender, address, "
            "username, password_hash, is_admin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("System", "Administrator", "Farm Manager", "-", "Poultry House",
             "admin", generate_password_hash("admin123"), 1, now()))
