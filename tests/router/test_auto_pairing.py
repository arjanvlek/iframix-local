"""Router auto-pairing of chargers to controller devices."""
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


class TestAutoPairing:
    """When a charger sends set_config and no binding exists,
    it should auto-pair with the most recently active controller device."""

    def test_auto_pair_notifications(self, router, mosquitto, mqtt_collector):
        """Auto-pairing sends bind + get_config events to the controller device."""
        tmp_path = router["tmp_path"]
        controller_uuid = "test-controller-uuid-001"

        # Pre-populate the database with a controller device session
        seed_session(tmp_path, controller_uuid, {
            "id": 12345,
            "device_name": "Test iPad",
            "device_type": "ios",
            "last_login": int(time.time()),
        })

        mqtt_collector.subscribe(f"/s2c/{controller_uuid}")

        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.12",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        # Expect both bind and get_config notifications
        messages = mqtt_collector.wait_for_messages(count=2, timeout=5)
        controller_messages = [
            m for m in messages
            if m["topic"] == f"/s2c/{controller_uuid}"
        ]
        events = [m["payload"]["event"] for m in controller_messages]
        assert "ipad/icharger/bind" in events, \
            f"Expected bind event, got: {events}"
        assert "ipad/icharger/get_config" in events, \
            f"Expected get_config event, got: {events}"

    def test_bind_event_has_charger_details(self, router, mosquitto, mqtt_collector):
        """The bind notification includes charger MAC, firmware, wifi_name."""
        tmp_path = router["tmp_path"]
        controller_uuid = "test-controller-uuid-002"

        seed_session(tmp_path, controller_uuid, {
            "id": 67890,
            "device_name": "Test Phone",
            "device_type": "ios",
            "last_login": int(time.time()),
        })

        mqtt_collector.subscribe(f"/s2c/{controller_uuid}")

        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.12",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        messages = mqtt_collector.wait_for_messages(count=2, timeout=5)
        bind_msgs = [
            m for m in messages
            if m["payload"].get("event") == "ipad/icharger/bind"
            and m["topic"] == f"/s2c/{controller_uuid}"
        ]
        assert len(bind_msgs) >= 1

        data = bind_msgs[0]["payload"]["data"]
        assert data["icharger_mac"] == CHARGER_MAC
        assert data["firmware"] == "1.1.1.12"
        assert data["wifi_name"] == "IFP_967E"
        assert "charging_switch" in data
        assert "created_at" in data

    def test_binding_persisted(self, router, mosquitto, mqtt_collector):
        """After auto-pairing, the binding is saved to the database."""
        tmp_path = router["tmp_path"]
        controller_uuid = "test-controller-uuid-003"

        seed_session(tmp_path, controller_uuid, {
            "id": 11111,
            "device_name": "Persist Test",
            "device_type": "ios",
            "last_login": int(time.time()),
        })

        # Subscribe so we know when the pairing is complete
        mqtt_collector.subscribe(f"/s2c/{controller_uuid}")

        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.12",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        mqtt_collector.wait_for_messages(count=1, timeout=5)
        time.sleep(0.5)  # Ensure DB write completes

        conn = get_router_db(tmp_path)
        try:
            row = conn.execute(
                "SELECT * FROM bindings WHERE charger_mac = ?",
                (CHARGER_MAC,)).fetchone()
            assert row is not None, "Binding was not saved to database"
            assert row["device_uuid"] == controller_uuid
        finally:
            conn.close()
