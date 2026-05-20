"""Charger-side unbind MQTT event."""
import json
import time

import pytest
import requests

from tests.helpers import login, get_device_id


class TestChargerUnbind:
    """POST /api/ipad/icharger/unbind"""

    def test_returns_true_for_unknown(self, api_server):
        """Unbind returns true even when no matching device exists."""
        resp = requests.post(
            f"{api_server['url']}/api/ipad/icharger/unbind",
            json={"device_id": 99999},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_mqtt_unbind_event(self, api_server, mqtt_collector):
        """Unbinding a charger sends MQTT unbind event to the bound device."""
        url = api_server["url"]
        tmp_path = api_server["tmp_path"]
        mod = api_server["module"]

        device_uuid = "unbind-ctrl-uuid-001"
        charger_mac = "94:51:DC:66:96:7E"
        charger_uuid = "IFP_94_51_DC_66_96_7E_36_BC"

        # Create a session
        login(url, device_uuid, origin="view")

        # Create a charger device entry in the database
        from src.db import get_connection
        conn = get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO devices
                (uuid, mac, firmware, wifi_name, last_seen)
            VALUES (?, ?, ?, ?, ?)
        """, (charger_uuid, charger_mac, "1.1.1.11", "IFP_967E", time.time()))

        # Set up the charger-to-device binding
        conn.execute(
            "UPDATE sessions SET icharger_mac = ? WHERE uuid = ?",
            (charger_mac, device_uuid))
        conn.execute(
            "INSERT OR REPLACE INTO bindings (charger_mac, device_uuid) VALUES (?, ?)",
            (charger_mac, device_uuid))
        conn.commit()
        conn.close()

        # Find the numeric device ID for the charger
        id_map = mod.build_id_map(mod.load_devices())
        charger_device_id = next(
            (did for did, duuid in id_map.items() if duuid == charger_uuid),
            None,
        )
        assert charger_device_id is not None

        # Subscribe and unbind
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")
        resp = requests.post(
            f"{url}/api/ipad/icharger/unbind",
            json={"device_id": charger_device_id},
        )
        assert resp.json()["code"] == 1

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/icharger/unbind"
        assert msg["data"] == {}
        assert msg["uuid"] == device_uuid
