"""Cross-cutting persistence: symmetric-clobber regression and schema migration."""
import logging
import sqlite3
import time

import pytest


@pytest.fixture
def db(tmp_path):
    """Initialize an isolated SQLite DB for each test."""
    from src.db import init_db, set_db_path
    path = str(tmp_path / "test.db")
    set_db_path(path)
    init_db(path)
    yield path


def _read_device(uuid):
    from src.api.persistence import load_devices
    return load_devices().get(uuid)


def _seed_device(uuid, **fields):
    from src.db import get_connection
    cols = ["uuid"] + list(fields.keys())
    placeholders = ", ".join(["?"] * len(cols))
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO devices ({', '.join(cols)}) VALUES ({placeholders})",
            [uuid, *fields.values()])
        conn.commit()
    finally:
        conn.close()


class TestSymmetricClobber:
    """The reverse direction: the API's handle_battery path must not wipe
    out a voltage/current update the router just made."""

    def test_api_battery_update_preserves_router_voltage(self, db):
        from src.router.persistence import register_device
        from src.api.persistence import update_device_fields

        _seed_device(
            "dev-sym", mac="DD:DD", voltage=0.0, current_=0.0,
            battery="100", last_seen=time.time(),
        )

        register_device("dev-sym", {
            "uuid": "dev-sym", "voltage": 12.3, "current": 4.5,
        })
        update_device_fields("dev-sym", battery="22")

        d = _read_device("dev-sym")
        assert d["voltage"] == 12.3
        assert d["current"] == 4.5
        assert d["battery"] == "22"


class TestSchemaMigration:
    """Existing databases at schema v2 (pre-split) must transparently gain
    the `charging_switch_reported` column when init_db runs."""

    def test_v2_db_gets_reported_column_added(self, tmp_path):
        import sqlite3
        from src.db import init_db, set_db_path, SCHEMA_VERSION

        path = str(tmp_path / "v2.db")

        # Hand-roll a v2 schema: devices without charging_switch_reported.
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version (version) VALUES (2);
            CREATE TABLE devices (
                uuid TEXT PRIMARY KEY,
                mac TEXT,
                charging_switch INTEGER
            );
            INSERT INTO devices (uuid, mac, charging_switch)
                VALUES ('dev-legacy', '99:99', 1);
        """)
        conn.commit()
        conn.close()

        # Running init_db should migrate the DB in place.
        set_db_path(path)
        init_db(path)

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cols = {r["name"] for r in
                conn.execute("PRAGMA table_info(devices)").fetchall()}
        assert "charging_switch_reported" in cols
        version = conn.execute(
            "SELECT version FROM schema_version").fetchone()["version"]
        assert version == SCHEMA_VERSION
        # Existing row data preserved; new column is NULL by default.
        row = conn.execute(
            "SELECT * FROM devices WHERE uuid = 'dev-legacy'").fetchone()
        assert row["charging_switch"] == 1
        assert row["charging_switch_reported"] is None
        conn.close()

    def test_v6_db_gets_weather_template_id_column_added(self, tmp_path):
        """Schema v7 adds weather_template_id to device_weather_config.

        Existing rows that predate the column must keep their data and
        gain the new column with the default style 1.
        """
        import sqlite3
        from src.db import init_db, set_db_path, SCHEMA_VERSION

        path = str(tmp_path / "v6.db")

        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version (version) VALUES (6);
            CREATE TABLE device_weather_config (
                device_id INTEGER PRIMARY KEY,
                city TEXT NOT NULL,
                city_id TEXT NOT NULL,
                lat TEXT NOT NULL,
                lon TEXT NOT NULL,
                unit INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO device_weather_config
                (device_id, city, city_id, lat, lon, unit)
            VALUES (42, 'Helsinki', 'FI_HEL', '60.1699', '24.9384', 2);
        """)
        conn.commit()
        conn.close()

        set_db_path(path)
        init_db(path)

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(device_weather_config)").fetchall()}
        assert "weather_template_id" in cols
        version = conn.execute(
            "SELECT version FROM schema_version").fetchone()["version"]
        assert version == SCHEMA_VERSION
        row = conn.execute(
            "SELECT * FROM device_weather_config WHERE device_id = 42"
        ).fetchone()
        assert row["city"] == "Helsinki"
        assert row["unit"] == 2
        # New column defaults to style 0 (iFramix 2.2.29 catalog is 0-based)
        assert row["weather_template_id"] == 0
        conn.close()
