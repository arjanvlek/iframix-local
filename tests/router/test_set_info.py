"""Router handling of charger `set_info` (registration + reading history)."""
import json
import os
import sqlite3
import time

import paho.mqtt.client as mqtt
import pytest

from tests.helpers import (
    CHARGER_UUID, CHARGER_MAC, get_router_db, publish_charger_event,
    seed_session,
)


class TestSetInfoRegistration:
    """set_info events should register/update the device in the database."""

    def test_device_registered(self, router, mosquitto):
        """After set_info, the charger appears in the database with correct data."""
        publish_charger_event(mosquitto, "ipad/icharger/set_info", {
            "uuid": CHARGER_UUID,
            "mac": CHARGER_MAC,
            "voltage": 5.241,
            "current": 2.454,
        })

        time.sleep(1)  # Wait for router to process and save

        conn = get_router_db(router["tmp_path"])
        try:
            row = conn.execute(
                "SELECT * FROM devices WHERE uuid = ?",
                (CHARGER_UUID,)).fetchone()
            assert row is not None, "Device was not registered in database"
            assert row["mac"] == CHARGER_MAC
            assert row["voltage"] == 5.241
            assert row["current_"] == 2.454
        finally:
            conn.close()

    def test_set_config_also_registers(self, router, mosquitto):
        """set_config events also register the device (firmware, wifi_name)."""
        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.11",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        time.sleep(1)

        conn = get_router_db(router["tmp_path"])
        try:
            row = conn.execute(
                "SELECT * FROM devices WHERE uuid = ?",
                (CHARGER_UUID,)).fetchone()
            assert row is not None
            assert row["firmware"] == "1.1.1.11"
            assert row["wifi_name"] == "IFP_967E"
        finally:
            conn.close()


class TestSetInfoReadingHistory:
    """set_info events should create charger reading history records."""

    def test_reading_persisted(self, router, mosquitto):
        """After set_info, a reading is saved to charger_readings."""
        publish_charger_event(mosquitto, "ipad/icharger/set_info", {
            "uuid": CHARGER_UUID,
            "mac": CHARGER_MAC,
            "voltage": 5.14,
            "current": 0.31,
        })
        time.sleep(1)

        conn = get_router_db(router["tmp_path"])
        try:
            rows = conn.execute(
                "SELECT * FROM charger_readings WHERE mac = ?",
                (CHARGER_MAC,)).fetchall()
            assert len(rows) >= 1
            row = rows[0]
            assert abs(row["voltage"] - 5.14) < 0.001
            assert abs(row["current_"] - 0.31) < 0.001
            assert row["id"] > 0
            assert row["add_time"] > 0
        finally:
            conn.close()

    def test_multiple_readings(self, router, mosquitto):
        """Multiple set_info events create multiple readings."""
        for voltage in (5.14, 5.12, 5.10):
            publish_charger_event(mosquitto, "ipad/icharger/set_info", {
                "uuid": CHARGER_UUID,
                "mac": CHARGER_MAC,
                "voltage": voltage,
                "current": 0.31,
            })
        time.sleep(2)

        conn = get_router_db(router["tmp_path"])
        try:
            rows = conn.execute(
                "SELECT * FROM charger_readings WHERE mac = ? "
                "ORDER BY add_time DESC",
                (CHARGER_MAC,)).fetchall()
            assert len(rows) >= 3
        finally:
            conn.close()
