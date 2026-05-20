"""Address / weather-city settings."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestAddressSettings:
    """POST /api/ipad/device/setting/address"""

    def test_returns_true(self, api_server):
        device_id = get_device_id(api_server["url"], "addr-uuid-001")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/setting/address",
            json={
                "id": device_id,
                "lat": "55.67611",
                "lon": "12.56889",
                "city_id": "2D701",
                "city_name": "Copenhagen",
            },
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_saves_weather_config(self, api_server):
        """Address update persists the city to weather config."""
        device_id = get_device_id(api_server["url"], "addr-uuid-002")
        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/address",
            json={
                "id": device_id,
                "lat": "55.67611",
                "lon": "12.56889",
                "city_id": "2D701",
                "city_name": "Copenhagen",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/weather",
            params={"id": device_id},
        )
        body = resp.json()
        assert body["data"]["city"] == "Copenhagen"
        assert body["data"]["cityMsg"]["id"] == "2D701"

    def test_mqtt_notification(self, api_server, mqtt_collector):
        """Address update sends MQTT event with city data to the display device."""
        device_uuid = "addr-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/address",
            json={
                "id": device_id,
                "lat": "55.67611",
                "lon": "12.56889",
                "city_id": "2D701",
                "city_name": "Copenhagen",
            },
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/device/setting/Address"
        assert msg["data"]["city_name"] == "Copenhagen"
        assert msg["data"]["city_id"] == "2D701"
        assert msg["data"]["lat"] == "55.67611"
        assert msg["data"]["lon"] == "12.56889"
