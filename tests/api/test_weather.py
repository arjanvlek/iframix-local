"""Weather forecast endpoint."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestWeatherSettings:
    """GET /api/ipad/device/setting/weather

    Note: The weather forecast endpoint (GET /api/ipad/weather/weather) is
    intentionally not tested here because it calls Open-Meteo and requires
    live network access. The city search endpoint
    (GET /api/ipad/address/city) is similarly skipped.
    """

    def test_unconfigured_device_returns_empty(self, api_server):
        """A device with no saved weather row gets an empty data object.

        The display device renders this as
        "no relevant city information, please setup in the controller
        device first" — there is no longer a global default.
        """
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/weather",
            params={"id": 1},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == {}

    def test_configured_response_format(self, api_server):
        """After saving, the response carries city, cityMsg, and unit."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-fmt-001")
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Amsterdam",
                    "cityMsg": {
                        "id": "NL_AMS",
                        "name": "Amsterdam",
                        "lat": "52.37403",
                        "lon": "4.88969",
                    },
                    "unit": 1,
                },
            },
        )
        resp = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        )
        data = resp.json()["data"]
        assert data["city"] == "Amsterdam"
        assert "cityMsg" in data
        assert "unit" in data
        city_msg = data["cityMsg"]
        assert city_msg["id"] == "NL_AMS"
        assert city_msg["name"] == "Amsterdam"
        assert city_msg["lat"] == "52.37403"
        assert city_msg["lon"] == "4.88969"


class TestPerDeviceWeather:
    """Weather settings (city + unit) must be stored per display device."""

    def test_weather_update_isolated_per_device(self, api_server):
        """Two devices saving different cities don't overwrite each other."""
        url = api_server["url"]
        device_a = get_device_id(url, "weather-uuid-A")
        device_b = get_device_id(url, "weather-uuid-B")

        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_a,
                "values": {
                    "city": "Paris",
                    "cityMsg": {
                        "id": "FR_PAR",
                        "name": "Paris",
                        "lat": "48.85661",
                        "lon": "2.35222",
                    },
                    "unit": 1,
                },
            },
        )
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_b,
                "values": {
                    "city": "Tokyo",
                    "cityMsg": {
                        "id": "JP_TKY",
                        "name": "Tokyo",
                        "lat": "35.68950",
                        "lon": "139.69171",
                    },
                    "unit": 2,
                },
            },
        )

        a = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_a},
        ).json()["data"]
        b = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_b},
        ).json()["data"]

        assert a["city"] == "Paris"
        assert a["cityMsg"]["id"] == "FR_PAR"
        assert a["unit"] == 1
        assert b["city"] == "Tokyo"
        assert b["cityMsg"]["id"] == "JP_TKY"
        assert b["unit"] == 2

    def test_address_update_isolated_per_device(self, api_server):
        """Address (city) updates are also kept per-device."""
        url = api_server["url"]
        device_a = get_device_id(url, "weather-addr-A")
        device_b = get_device_id(url, "weather-addr-B")

        requests.post(
            f"{url}/api/ipad/device/setting/address",
            json={
                "id": device_a,
                "lat": "51.50735",
                "lon": "-0.12776",
                "city_id": "GB_LON",
                "city_name": "London",
            },
        )
        requests.post(
            f"{url}/api/ipad/device/setting/address",
            json={
                "id": device_b,
                "lat": "40.71278",
                "lon": "-74.00594",
                "city_id": "US_NYC",
                "city_name": "New York",
            },
        )

        a = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_a},
        ).json()["data"]
        b = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_b},
        ).json()["data"]

        assert a["city"] == "London"
        assert a["cityMsg"]["id"] == "GB_LON"
        assert b["city"] == "New York"
        assert b["cityMsg"]["id"] == "US_NYC"

    def test_unconfigured_device_returns_empty(self, api_server):
        """A device with no per-device row gets an empty data object."""
        url = api_server["url"]
        # 999 is not associated with any session/per-device row
        resp = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": 999},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == {}

    def test_address_update_preserves_unit(self, api_server):
        """An address-only update keeps the device's previously chosen unit."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-unit-keep-001")

        # First save imperial unit
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Houston",
                    "cityMsg": {
                        "id": "US_HOU",
                        "name": "Houston",
                        "lat": "29.76043",
                        "lon": "-95.36980",
                    },
                    "unit": 2,
                },
            },
        )

        # Then change only the city via the address endpoint
        requests.post(
            f"{url}/api/ipad/device/setting/address",
            json={
                "id": device_id,
                "lat": "39.95233",
                "lon": "-75.16379",
                "city_id": "US_PHL",
                "city_name": "Philadelphia",
            },
        )

        data = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert data["city"] == "Philadelphia"
        assert data["cityMsg"]["id"] == "US_PHL"
        # Unit must survive the city-only update
        assert data["unit"] == 2

    def test_unbind_removes_weather_row(self, api_server):
        """unbindUser deletes the per-device weather row."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-unbind-001")

        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Berlin",
                    "cityMsg": {
                        "id": "DE_BER",
                        "name": "Berlin",
                        "lat": "52.52000",
                        "lon": "13.40500",
                    },
                    "unit": 1,
                },
            },
        )

        # Sanity check: per-device row is in place
        before = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert before["city"] == "Berlin"

        # Unbind the display device
        resp = requests.post(
            f"{url}/api/ipad/device/unbindUser",
            json={"id": device_id},
        )
        assert resp.json()["code"] == 1

        # After unbind the per-device row is gone, so the endpoint
        # responds with an empty data object — there is no global
        # default to fall back on any more.
        after = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()
        assert after["data"] == {}

        # And the underlying table no longer has a row for this device
        from src.db import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM device_weather_config WHERE device_id = ?",
                (device_id,)).fetchall()
        finally:
            conn.close()
        assert rows == []

    def test_weather_template_id_round_trip(self, api_server):
        """POST + GET preserve the iFramix 2.2.29 weather_template_id (0..3)."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-tpl-roundtrip")

        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Madrid",
                    "cityMsg": {
                        "id": "ES_MAD",
                        "name": "Madrid",
                        "lat": "40.41670",
                        "lon": "-3.70330",
                    },
                    "unit": 1,
                    "weather_template_id": 2,
                },
            },
        )
        data = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert data["weather_template_id"] == 2

    def test_weather_template_id_defaults_to_zero(self, api_server):
        """A POST without weather_template_id leaves the device at style 0."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-tpl-default")
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Rome",
                    "cityMsg": {
                        "id": "IT_ROM",
                        "name": "Rome",
                        "lat": "41.89030",
                        "lon": "12.49250",
                    },
                    "unit": 1,
                },
            },
        )
        data = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert data["weather_template_id"] == 0

    def test_weather_template_id_preserved_on_city_only_post(self, api_server):
        """Updating just the city/unit keeps the previously-saved style."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-tpl-preserve")

        # Initial save picks style 3 (the last of the 0..3 catalog)
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Lisbon",
                    "cityMsg": {
                        "id": "PT_LIS",
                        "name": "Lisbon",
                        "lat": "38.72260",
                        "lon": "-9.13930",
                    },
                    "unit": 1,
                    "weather_template_id": 3,
                },
            },
        )
        # Subsequent POST omits weather_template_id (older app version)
        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Porto",
                    "cityMsg": {
                        "id": "PT_OPO",
                        "name": "Porto",
                        "lat": "41.14960",
                        "lon": "-8.61090",
                    },
                    "unit": 2,
                },
            },
        )
        data = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert data["city"] == "Porto"
        assert data["unit"] == 2
        assert data["weather_template_id"] == 3

    def test_address_update_preserves_weather_template_id(self, api_server):
        """An address-only update keeps the previously chosen style."""
        url = api_server["url"]
        device_id = get_device_id(url, "weather-tpl-addr")

        requests.post(
            f"{url}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Vienna",
                    "cityMsg": {
                        "id": "AT_VIE",
                        "name": "Vienna",
                        "lat": "48.20820",
                        "lon": "16.37380",
                    },
                    "unit": 1,
                    "weather_template_id": 1,
                },
            },
        )
        requests.post(
            f"{url}/api/ipad/device/setting/address",
            json={
                "id": device_id,
                "lat": "47.49790",
                "lon": "19.04020",
                "city_id": "HU_BUD",
                "city_name": "Budapest",
            },
        )
        data = requests.get(
            f"{url}/api/ipad/device/setting/weather",
            params={"id": device_id},
        ).json()["data"]
        assert data["city"] == "Budapest"
        assert data["weather_template_id"] == 1

    def test_weather_template_id_in_mqtt_payload(self, api_server, mqtt_collector):
        """The MQTT Weather event echoes the saved weather_template_id."""
        device_uuid = "weather-tpl-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/weather",
            json={
                "id": device_id,
                "values": {
                    "city": "Oslo",
                    "cityMsg": {
                        "id": "NO_OSL",
                        "name": "Oslo",
                        "lat": "59.91390",
                        "lon": "10.75220",
                    },
                    "unit": 1,
                    "weather_template_id": 2,
                },
            },
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        weather_msgs = [m for m in messages
                        if m["payload"].get("event") == "ipad/device/setting/Weather"]
        assert weather_msgs, "Expected ipad/device/setting/Weather MQTT event"
        # The POST handler forwards the controller's exact values; the
        # admin sends weather_template_id inside values.
        assert weather_msgs[0]["payload"]["data"]["weather_template_id"] == 2

    def test_weather_template_id_column_exists(self, api_server):
        """Schema v7 added weather_template_id to device_weather_config."""
        from src.db import get_connection
        conn = get_connection()
        try:
            cols = [r["name"] for r in conn.execute(
                "PRAGMA table_info(device_weather_config)").fetchall()]
        finally:
            conn.close()
        assert "weather_template_id" in cols

    def test_global_weather_config_table_is_gone(self, api_server):
        """The legacy weather_config singleton table must not exist any more."""
        from src.db import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='weather_config'"
            ).fetchone()
        finally:
            conn.close()
        assert row is None
