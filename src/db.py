"""SQLite database module for iCharGuard persistent state.

Replaces the per-file JSON persistence with a single SQLite database
using WAL mode for safe concurrent access from the API server and
the MQTT router.

Usage:
    from src.db import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO devices ...")
"""

import json
import os
import sqlite3
import threading

# Default database path (overridden by config or tests)
_db_path = None
_db_path_lock = threading.Lock()

SCHEMA_VERSION = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    uuid TEXT PRIMARY KEY,
    mac TEXT,
    firmware TEXT,
    wifi_name TEXT,
    voltage REAL,
    current_ REAL,
    battery TEXT,
    -- `charging_switch` = desired state: the last charge command the
    -- controller app sent via /api/ipad/device/refersh-battery.
    -- `charging_switch_reported` = actual state: the last charging_switch
    -- value the charger itself echoed back in an MQTT message. May stay
    -- NULL if the firmware never includes it in set_info/set_config.
    charging_switch INTEGER,
    charging_switch_reported INTEGER,
    polling INTEGER,
    cloud_id INTEGER,
    last_seen REAL,
    -- `mode` controls what happens on /api/ipad/device/refersh-battery.
    -- In 'manual' (default), the handler only records the desired
    -- charging_switch and the admin Enable/Disable buttons drive MQTT.
    -- In 'auto', every refersh-battery call also publishes the MQTT
    -- charging_switch command to the charger.
    mode TEXT NOT NULL DEFAULT 'manual'
);

CREATE INDEX IF NOT EXISTS idx_devices_mac ON devices(mac);

CREATE TABLE IF NOT EXISTS sessions (
    uuid TEXT PRIMARY KEY,
    id INTEGER NOT NULL,
    device_name TEXT,
    device_type TEXT,
    ios_version TEXT,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    user_id INTEGER DEFAULT 1,
    user TEXT DEFAULT 'local',
    is_ipad INTEGER DEFAULT 0,
    is_h5 INTEGER DEFAULT 0,
    bind_at INTEGER,
    created_at TEXT,
    last_login INTEGER,
    last_disconnected_at INTEGER DEFAULT 0,
    icharger_mac TEXT DEFAULT '',
    screensaver_json TEXT DEFAULT '[]',
    display_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS bindings (
    charger_mac TEXT PRIMARY KEY,
    device_uuid TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_weather_config (
    device_id INTEGER PRIMARY KEY,
    city TEXT NOT NULL,
    city_id TEXT NOT NULL,
    lat TEXT NOT NULL,
    lon TEXT NOT NULL,
    unit INTEGER NOT NULL DEFAULT 1,
    weather_template_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS calendars (
    id TEXT PRIMARY KEY,
    device_id INTEGER,
    driver TEXT NOT NULL DEFAULT '',
    name TEXT DEFAULT '',
    url TEXT DEFAULT '',
    update_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    summary TEXT DEFAULT '',
    driver TEXT DEFAULT 'manual',
    uuid TEXT DEFAULT '',
    start_date_time TEXT DEFAULT '',
    end_date_time TEXT DEFAULT '',
    description TEXT DEFAULT '',
    update_at TEXT DEFAULT '',
    schedule_ids_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS media_settings (
    media_id TEXT PRIMARY KEY,
    device_id INTEGER,
    display TEXT DEFAULT '',
    template_id INTEGER DEFAULT 0,
    template_type INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS charger_readings (
    id INTEGER PRIMARY KEY,
    mac TEXT NOT NULL,
    voltage REAL NOT NULL,
    current_ REAL NOT NULL,
    add_time INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_readings_mac_time
    ON charger_readings(mac, add_time DESC);

CREATE TABLE IF NOT EXISTS ai_albums (
    device_id INTEGER PRIMARY KEY,
    albums_json TEXT NOT NULL DEFAULT '[]'
);
"""


def set_db_path(path):
    """Set the database file path. Must be called before any get_connection()."""
    global _db_path
    with _db_path_lock:
        _db_path = path


def get_db_path():
    """Return the current database path."""
    with _db_path_lock:
        return _db_path


def get_connection():
    """Return a new SQLite connection with WAL mode and foreign keys enabled.

    Each call returns a fresh connection. The caller is responsible for
    closing it (use as context manager: ``with get_connection() as conn:``).

    The connection uses autocommit=False by default (Python sqlite3 behavior),
    so changes are committed when using ``with conn:`` blocks or by calling
    ``conn.commit()`` explicitly.
    """
    path = get_db_path()
    if path is None:
        raise RuntimeError("Database path not set. Call set_db_path() first.")

    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _run_migrations(conn, from_version):
    """Apply incremental migrations to reach SCHEMA_VERSION."""
    if from_version < 3:
        if not _column_exists(conn, "devices", "charging_switch_reported"):
            conn.execute(
                "ALTER TABLE devices ADD COLUMN "
                "charging_switch_reported INTEGER")
    if from_version < 4:
        if not _column_exists(conn, "devices", "mode"):
            conn.execute(
                "ALTER TABLE devices ADD COLUMN "
                "mode TEXT NOT NULL DEFAULT 'manual'")
    if from_version < 5:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_weather_config (
                device_id INTEGER PRIMARY KEY,
                city TEXT NOT NULL,
                city_id TEXT NOT NULL,
                lat TEXT NOT NULL,
                lon TEXT NOT NULL,
                unit INTEGER NOT NULL DEFAULT 1
            )
        """)
    if from_version < 6:
        # Drop the singleton global default — weather settings are now
        # required to be configured per device. Unconfigured devices get
        # an empty response so the display can prompt the user.
        conn.execute("DROP TABLE IF EXISTS weather_config")
    if from_version < 7:
        # iFramix Pro 2.2.29 introduced 4 selectable weather station
        # templates (0..3, matching the webapp's 0-based catalog);
        # persist the per-device choice alongside city/unit.
        if not _column_exists(
                conn, "device_weather_config", "weather_template_id"):
            conn.execute(
                "ALTER TABLE device_weather_config ADD COLUMN "
                "weather_template_id INTEGER NOT NULL DEFAULT 0")


def init_db(path=None):
    """Create the database and tables if they don't exist.

    Args:
        path: Optional path override. If provided, also calls set_db_path().
    """
    if path is not None:
        set_db_path(path)

    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)

        # Set or migrate schema version
        row = conn.execute(
            "SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,))
        elif row["version"] < SCHEMA_VERSION:
            _run_migrations(conn, row["version"])
            conn.execute(
                "UPDATE schema_version SET version = ?",
                (SCHEMA_VERSION,))

        conn.commit()
    finally:
        conn.close()


def dict_from_row(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)
