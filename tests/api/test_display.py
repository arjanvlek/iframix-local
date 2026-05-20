"""Display position/scale settings."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestDisplaySettings:
    """GET and POST /api/ipad/device/setting/display"""

    def test_set_returns_true(self, api_server):
        device_id = get_device_id(api_server["url"], "disp-uuid-001")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/setting/display",
            json={"id": device_id, "values": {"top": 0.0, "left": 0.0, "scale": 0.904}},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_mqtt_notification(self, api_server, mqtt_collector):
        """Display update sends MQTT event with correct data."""
        device_uuid = "disp-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/display",
            json={"id": device_id, "values": {"top": 0.0, "left": 0.0, "scale": 0.904}},
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/device/setting/Display"
        assert msg["data"]["scale"] == 0.904
        assert msg["data"]["top"] == 0.0
        assert msg["data"]["left"] == 0.0

    def test_mqtt_envelope_fields(self, api_server, mqtt_collector):
        """MQTT message has the standard envelope: uuid, msg_id, event, data."""
        device_uuid = "disp-mqtt-uuid-002"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/display",
            json={"id": device_id, "values": {"top": 0, "left": 0, "scale": 1.0}},
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        msg = messages[0]["payload"]
        assert "uuid" in msg
        assert "msg_id" in msg
        assert "event" in msg
        assert "data" in msg
        assert isinstance(msg["msg_id"], int)
        assert msg["uuid"] == device_uuid
