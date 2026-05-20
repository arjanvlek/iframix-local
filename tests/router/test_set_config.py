"""Router response to charger `set_config`."""
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


class TestSetConfigResponse:
    """When a charger sends set_config, the router responds with get_config."""

    def test_get_config_response(self, router, mosquitto, mqtt_collector):
        """Router publishes get_config to the charger's response topic."""
        mqtt_collector.subscribe(f"/mqtt/s2c/{CHARGER_UUID}")

        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.11",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        assert len(messages) >= 1

        # Find the get_config message (there may also be bind/config
        # messages to controller devices)
        get_config_msgs = [
            m for m in messages
            if m["topic"] == f"/mqtt/s2c/{CHARGER_UUID}"
            and m["payload"].get("event") == "ipad/icharger/get_config"
        ]
        assert len(get_config_msgs) >= 1
        msg = get_config_msgs[0]["payload"]

        assert "msg_id" in msg
        assert isinstance(msg["msg_id"], int)

        data = msg["data"]
        assert data["bind_status"] == 1
        assert data["polling"] == 15
        assert "battery" in data
        assert "charging_switch" in data

    def test_get_config_charging_defaults(self, router, mosquitto, mqtt_collector):
        """Default get_config has charging_switch=1 (on) and battery=0 (no limit)."""
        mqtt_collector.subscribe(f"/mqtt/s2c/{CHARGER_UUID}")

        publish_charger_event(mosquitto, "ipad/icharger/set_config", {
            "uuid": CHARGER_UUID,
            "firmware": "1.1.1.11",
            "mac": CHARGER_MAC,
            "random_str": "",
            "ip": "0.0.0.0",
            "wifi_name": "IFP_967E",
        })

        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        get_config_msgs = [
            m for m in messages
            if m["topic"] == f"/mqtt/s2c/{CHARGER_UUID}"
            and m["payload"].get("event") == "ipad/icharger/get_config"
        ]
        data = get_config_msgs[0]["payload"]["data"]
        assert data["charging_switch"] == 1  # charging ON by default
        assert data["battery"] == 0  # no battery limit
