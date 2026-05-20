"""Screensaver (flip-clock) settings."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestScreensaverSettings:
    """GET and POST /api/ipad/device/setting/screensaver"""

    def test_get_default(self, api_server):
        """Default screensaver settings are empty."""
        device_id = get_device_id(api_server["url"], "ss-uuid-001")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/screensaver",
            params={"id": device_id},
        )
        assert resp.json()["code"] == 1

    def test_set_returns_true(self, api_server):
        device_id = get_device_id(api_server["url"], "ss-uuid-002")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/setting/screensaver",
            json={"id": device_id, "values": {"no": 1, "time": 2}},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_round_trip_multiple_styles(self, api_server):
        """iFramix Pro 2.2.29 ships 5 flip-clock styles (no=1..5).

        Updates targeting different ``no`` values are stored side-by-side
        so the latest pick for each style sticks. The GET endpoint returns
        the most recently saved style, which is what the display device
        renders.
        """
        device_id = get_device_id(api_server["url"], "ss-style-roundtrip")
        url = api_server["url"]
        for no, time in [(1, 1), (3, 2), (5, 1)]:
            resp = requests.post(
                f"{url}/api/ipad/device/setting/screensaver",
                json={"id": device_id, "values": {"no": no, "time": time}},
            )
            assert resp.json()["code"] == 1
        # Latest save -> no=5, time=1
        latest = requests.get(
            f"{url}/api/ipad/device/setting/screensaver",
            params={"id": device_id},
        ).json()["data"]
        assert latest["no"] == 5
        assert latest["time"] == 1

    def test_mqtt_notification(self, api_server, mqtt_collector):
        """Per the spec, setting screensaver should send an MQTT notification:
        event: 'ipad/device/setting/Screensaver', data: {no, time}"""
        device_uuid = "ss-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/screensaver",
            json={"id": device_id, "values": {"no": 1, "time": 2}},
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1, "Expected MQTT notification for screensaver update"
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/device/setting/Screensaver"
        assert msg["data"]["no"] == 1
        assert msg["data"]["time"] == 2
