"""POST /refersh-battery (battery + charging_switch desired state)."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestBatteryReport:
    """Note: 'refersh' (not 'refresh') is the original API's typo, preserved here."""

    def test_returns_true(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 99999, "battery": 85, "charging_switch": 1},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] is True

    def test_typo_endpoint_exists(self, api_server):
        """The misspelled endpoint is reachable (not 404)."""
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 1, "battery": 50, "charging_switch": 0},
        )
        assert resp.status_code == 200

    def test_persists_battery_and_charging_switch_for_unmatched_id(
            self, api_server):
        """An unknown device id with no existing mapping creates an
        `_unmatched_id_<id>` placeholder row holding both the battery
        reading and the desired charging switch from the controller app."""
        from src.api.persistence import load_devices

        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 424242, "battery": 73, "charging_switch": 1},
        )
        assert resp.status_code == 200

        row = load_devices().get("_unmatched_id_424242")
        assert row is not None
        assert row["battery"] == "73"
        assert row["charging_switch"] == 1
        assert row["cloud_id"] == 424242

    def test_charging_switch_off_is_persisted(self, api_server):
        """charging_switch=0 (the controller app asking the charger to stop)
        must be stored, not dropped — it is a desired-state command, not a
        live reading."""
        from src.api.persistence import load_devices

        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 717171, "battery": 10, "charging_switch": 0},
        )
        row = load_devices().get("_unmatched_id_717171")
        assert row is not None
        assert row["charging_switch"] == 0

    def test_charging_switch_update_overwrites_previous_value(
            self, api_server):
        """Subsequent refersh-battery calls must update the stored
        charging_switch, not just insert once."""
        from src.api.persistence import load_devices

        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 909090, "battery": 60, "charging_switch": 1},
        )
        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 909090, "battery": 65, "charging_switch": 0},
        )
        row = load_devices().get("_unmatched_id_909090")
        assert row is not None
        assert row["battery"] == "65"
        assert row["charging_switch"] == 0
