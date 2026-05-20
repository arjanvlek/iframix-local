"""Load and save functions for router state, backed by SQLite.

The router uses the same SQLite database as the API server. Functions
return the same data structures as before so callers need minimal changes.
"""

import json
import logging
import time

from src.db import get_connection
from src.router import config

logger = logging.getLogger(__name__)


def load_devices():
    """Load previously known devices from the database into the in-memory registry."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM devices").fetchall()
        for row in rows:
            config.devices[row["uuid"]] = {
                "uuid": row["uuid"],
                "mac": row["mac"],
                "firmware": row["firmware"],
                "wifi_name": row["wifi_name"],
                "voltage": row["voltage"],
                "current": row["current_"],
                "battery": row["battery"],
                "charging_switch": row["charging_switch"],
                "charging_switch_reported":
                    row["charging_switch_reported"],
                "polling": row["polling"],
                "cloud_id": row["cloud_id"],
                "last_seen": row["last_seen"],
            }
        logger.info("Loaded %d known device(s) from database", len(rows))
    finally:
        conn.close()


def load_bindings():
    """Load charger MAC -> device UUID bindings from the database."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM bindings").fetchall()
        return {row["charger_mac"]: row["device_uuid"] for row in rows}
    finally:
        conn.close()


def save_bindings(bindings):
    """Persist charger MAC -> device UUID bindings to the database."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM bindings")
        for mac, device_uuid in bindings.items():
            conn.execute(
                "INSERT INTO bindings (charger_mac, device_uuid) VALUES (?, ?)",
                (mac, device_uuid))
        conn.commit()
    except Exception:
        logger.warning("could not save bindings", exc_info=True)
    finally:
        conn.close()


def load_sessions():
    """Load controller device sessions from the database."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        result = {}
        for row in rows:
            result[row["uuid"]] = {
                "uuid": row["uuid"],
                "id": row["id"],
                "device_name": row["device_name"],
                "device_type": row["device_type"],
                "last_login": row["last_login"],
                "icharger_mac": row["icharger_mac"],
            }
        return result
    finally:
        conn.close()


def save_sessions(sessions):
    """Persist controller device sessions to the database.

    Only updates the fields the router cares about (icharger_mac, last_login).
    Uses INSERT OR REPLACE to avoid conflicts with the API server.
    """
    conn = get_connection()
    try:
        for sess_uuid, sess in sessions.items():
            # Check if session exists (may have been created by API server)
            row = conn.execute(
                "SELECT uuid FROM sessions WHERE uuid = ?",
                (sess_uuid,)).fetchone()
            if row:
                # Only update the fields the router modifies
                conn.execute("""
                    UPDATE sessions SET icharger_mac = ?, last_login = ?
                    WHERE uuid = ?
                """, (
                    sess.get("icharger_mac", ""),
                    sess.get("last_login"),
                    sess_uuid,
                ))
            else:
                # Insert minimal session (router auto-pair creates these)
                conn.execute("""
                    INSERT INTO sessions
                        (uuid, id, device_name, device_type, last_login,
                         icharger_mac)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    sess_uuid,
                    sess.get("id", 0),
                    sess.get("device_name"),
                    sess.get("device_type"),
                    sess.get("last_login"),
                    sess.get("icharger_mac", ""),
                ))
        conn.commit()
    except Exception:
        logger.warning("could not save sessions", exc_info=True)
    finally:
        conn.close()


def save_charger_reading(mac, voltage, current, reading_id, add_time):
    """Persist a single charger voltage/current reading.

    Prunes to the most recent 10,000 rows per MAC after each insert.
    """
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO charger_readings (id, mac, voltage, current_, add_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (reading_id, mac, voltage, current, add_time))
        conn.execute(
            "DELETE FROM charger_readings WHERE mac = ? AND id NOT IN "
            "(SELECT id FROM charger_readings WHERE mac = ? "
            "ORDER BY add_time DESC LIMIT 10000)",
            (mac, mac))
        conn.commit()
    except Exception:
        logger.warning("could not save charger reading", exc_info=True)
    finally:
        conn.close()


_PAYLOAD_TO_COL = {
    "mac": "mac",
    "firmware": "firmware",
    "wifi_name": "wifi_name",
    "voltage": "voltage",
    "current": "current_",
    # The charger's MQTT payloads carry `charging_switch` as the *actual*
    # charging state — the charger telling us what it's doing. The API's
    # refersh-battery path writes the column named `charging_switch`,
    # which carries the *desired* state (the user's command). Keep those
    # two meanings in separate columns so neither overwrites the other.
    "charging_switch": "charging_switch_reported",
}


def register_device(device_uuid, data):
    """Upsert a device row using only the fields present in the MQTT payload.

    Fields the router never owns (battery, charging_switch (desired),
    polling, cloud_id) are left untouched so a concurrent API update (e.g.
    /api/ipad/device/refersh-battery) is not clobbered. No Python-side
    cache is consulted — every call reads and writes the SQLite row
    directly.

    The charger's own `charging_switch` (if present in the payload) is
    persisted to `charging_switch_reported`. When the firmware doesn't
    include that field (observed behaviour — `set_info` only carries
    voltage/current), derive `charging_switch_reported` from the power
    flow instead: nonzero voltage means the charger is actually charging.
    """
    fields = {"last_seen": time.time()}
    for key, col in _PAYLOAD_TO_COL.items():
        if key in data:
            fields[col] = data[key]

    # Fallback: if the charger didn't explicitly report charging_switch,
    # infer it from the measured voltage (> 0.5 V).
    if "charging_switch_reported" not in fields and "voltage" in data:
        try:
            fields["charging_switch_reported"] = (
                1 if float(data["voltage"]) > 0.5 else 0)
        except (TypeError, ValueError):
            pass

    existed = False
    conn = get_connection()
    try:
        existed = conn.execute(
            "SELECT 1 FROM devices WHERE uuid = ?",
            (device_uuid,)).fetchone() is not None

        cols = ["uuid"] + list(fields.keys())
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join(f"{c} = excluded.{c}" for c in fields.keys())
        conn.execute(
            f"INSERT INTO devices ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(uuid) DO UPDATE SET {updates}",
            [device_uuid, *fields.values()])
        conn.commit()
    except Exception:
        logger.warning("could not register device", exc_info=True)
        return
    finally:
        conn.close()

    if not existed:
        logger.info("[NEW] Discovered iCharGuard: %s", device_uuid)
