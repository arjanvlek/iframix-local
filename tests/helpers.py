"""Shared helpers for the split tests/ tree.

Originally inlined in tests/test_api.py and tests/test_router.py. Lifted
here so per-feature split files can import them without duplication.
"""
import json
import os
import sqlite3
import struct as _s
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import requests


CHARGER_UUID = "IFP_94_51_DC_66_96_7E_36_BC"
CHARGER_MAC = "94:51:DC:66:96:7E"


# --- API: login & device-id lookup ------------------------------------------

def login(base_url, device_uuid, origin="view"):
    """Login and return the full response JSON."""
    resp = requests.post(
        f"{base_url}/api/user/public/login",
        json={"username": "test@example.com", "password": "test"},
        headers={
            "XX-Device-Uuid": device_uuid,
            "XX-Device-Origin": origin,
            "XX-Device-Name": "TestDevice",
            "XX-Device-Type": "ios",
            "XX-Device-Version": "16.0",
            "XX-Device-Is-Ipad": "false",
        },
    )
    assert resp.status_code == 200
    return resp.json()


def get_device_id(base_url, device_uuid):
    """Login as a display device and return the numeric device ID."""
    data = login(base_url, device_uuid, origin="view")
    return data["data"]["device"]["id"]


# --- API: charger seed for refersh-battery routing -------------------------

def seed_auto_charger(uuid, mac, cloud_id, mode="manual",
                      charging_switch=None):
    """Seed a real charger row resolvable by a refersh-battery cloud_id."""
    from src.api.persistence import (
        insert_device_if_missing, update_device_fields,
    )
    insert_device_if_missing(
        uuid, mac=mac, cloud_id=cloud_id, last_seen=time.time())
    fields = {"mode": mode}
    if charging_switch is not None:
        fields["charging_switch"] = charging_switch
    update_device_fields(uuid, **fields)
    return uuid


# --- Router: db + MQTT helpers ---------------------------------------------

def get_router_db(tmp_path):
    """Return a sqlite3 connection to the router's test database."""
    db_path = os.path.join(str(tmp_path), "icharguard.db")
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def publish_charger_event(mosquitto, event, data):
    """Publish a charger event to /mqtt/cts/message as if from the hardware."""
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"test_charger_{uuid.uuid4().hex[:6]}",
    )
    connected = threading.Event()
    client.on_connect = lambda *_: connected.set()
    client.connect(mosquitto["host"], mosquitto["mqtt_port"])
    client.loop_start()
    connected.wait(timeout=5)

    payload = json.dumps({"event": event, "data": data})
    client.publish("/mqtt/cts/message", payload, qos=1)
    time.sleep(0.5)  # Allow message to be delivered

    client.loop_stop()
    client.disconnect()


def seed_session(tmp_path, controller_uuid, session_data):
    """Insert a session into the router's test database."""
    db_path = os.path.join(str(tmp_path), "icharguard.db")
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("""
        INSERT OR REPLACE INTO sessions
            (uuid, id, device_name, device_type, last_login, icharger_mac)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        controller_uuid,
        session_data.get("id", 0),
        session_data.get("device_name"),
        session_data.get("device_type"),
        session_data.get("last_login"),
        session_data.get("icharger_mac", ""),
    ))
    conn.commit()
    conn.close()


# --- EXIF JPEG fixtures (for AI-photo / EXIF tests) ------------------------

def build_jpeg_with_exif(ifd0_entries=None, exif_entries=None):
    """Build a minimal JPEG with arbitrary IFD0 and ExifIFD entries.

    Each entry is a ``(tag, type, values)`` tuple:
    - type 2 (ASCII): values is a ``str``; a trailing NUL is added.
    - type 3 (SHORT)/4 (LONG): values is an ``int`` (count=1).
    - type 5 (RATIONAL): values is ``(num, den)`` (count=1, 8 bytes at offset).

    When exif_entries is provided, an ExifIFD pointer (tag 0x8769) is
    appended to IFD0 automatically. All offsets are measured from the
    start of the TIFF header. Little-endian byte order.
    """
    def _encode_entry(entry, next_offset):
        tag, type_, values = entry
        if type_ == 2:
            data = values.encode("ascii") + b"\x00"
            n = len(data)
            if n <= 4:
                entry_b = _s.pack("<HHI", tag, type_, n) + data.ljust(4, b"\x00")
                return entry_b, b"", next_offset
            entry_b = _s.pack("<HHII", tag, type_, n, next_offset)
            return entry_b, data, next_offset + n
        if type_ == 3:
            entry_b = (_s.pack("<HHI", tag, type_, 1) +
                       _s.pack("<H", values) + b"\x00\x00")
            return entry_b, b"", next_offset
        if type_ == 4:
            entry_b = _s.pack("<HHII", tag, type_, 1, values)
            return entry_b, b"", next_offset
        if type_ == 5:
            num, den = values
            entry_b = _s.pack("<HHII", tag, type_, 1, next_offset)
            return entry_b, _s.pack("<II", num, den), next_offset + 8
        raise ValueError(f"unsupported EXIF type {type_}")

    ifd0_entries = list(ifd0_entries or [])
    exif_entries = list(exif_entries or [])

    ifd0_end = 8 + 2 + len(ifd0_entries) * 12 + 4
    has_exif = bool(exif_entries)
    if has_exif:
        ifd0_end += 12

    next_off = ifd0_end
    ifd0_blob = b""
    extras = b""
    for e in ifd0_entries:
        entry_b, extra, next_off = _encode_entry(e, next_off)
        ifd0_blob += entry_b
        extras += extra

    if has_exif:
        exif_ifd_off = next_off
        ifd0_blob += _s.pack("<HHII", 0x8769, 4, 1, exif_ifd_off)

        exif_end = exif_ifd_off + 2 + len(exif_entries) * 12 + 4
        next_off2 = exif_end
        exif_blob = b""
        exif_extras = b""
        for e in exif_entries:
            entry_b, extra, next_off2 = _encode_entry(e, next_off2)
            exif_blob += entry_b
            exif_extras += extra

        tiff = (b"II" + _s.pack("<H", 0x002A) + _s.pack("<I", 8) +
                _s.pack("<H", len(ifd0_entries) + 1) + ifd0_blob +
                _s.pack("<I", 0) + extras +
                _s.pack("<H", len(exif_entries)) + exif_blob +
                _s.pack("<I", 0) + exif_extras)
    else:
        tiff = (b"II" + _s.pack("<H", 0x002A) + _s.pack("<I", 8) +
                _s.pack("<H", len(ifd0_entries)) + ifd0_blob +
                _s.pack("<I", 0) + extras)

    app1_payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + _s.pack(">H", len(app1_payload) + 2) + app1_payload
    return b"\xff\xd8" + app1 + b"\xff\xd9"


def jpeg_with_datetime(dt_str, tag=0x9003, in_ifd0=False):
    """Convenience wrapper: build a JPEG with one datetime tag."""
    if in_ifd0:
        return build_jpeg_with_exif(ifd0_entries=[(tag, 2, dt_str)])
    return build_jpeg_with_exif(exif_entries=[(tag, 2, dt_str)])
