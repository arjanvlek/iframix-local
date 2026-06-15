"""Playback-mode settings (iFramix Pro app 2.3.1+).

Covers GET/POST /api/ipad/device/setting/playback (per-device playback
settings document, full replace on every POST), the value normalization
(interval clamp, module whitelist, HH:MM rule validation), the
``ipad/device/setting/Playback`` MQTT notification, the new
POST /api/ipad/device/update session-metadata refresh, and the admin
panel's Playback tab markup.

Endpoint shapes were captured from the real cloud server with app 2.3.1
(captures/20260610-app-2.3.1/).
"""
import requests

from tests.helpers import get_device_id, login


# The full settings document exactly as app 2.3.1 posts it.
def make_playback_values(**overrides):
    values = {
        "mode": "fixed",
        "random": {"intervalMinutes": 14, "excludedModules": ["calendar"]},
        "fixed": {
            "defaultModule": "album",
            "rules": [
                {"startTime": "21:04", "endTime": "22:04",
                 "module": "album"},
                {"startTime": "22:05", "endTime": "22:20",
                 "module": "screensaver"},
            ],
        },
        "isPlaying": False,
        "currentModule": "",
    }
    values.update(overrides)
    return values


class TestPlaybackSettings:
    """GET and POST /api/ipad/device/setting/playback"""

    def test_get_unconfigured_returns_empty_array(self, api_server):
        """The cloud returns ``data: []`` (not ``{}``) for a device
        that has never saved playback settings."""
        device_id = get_device_id(api_server["url"], "pb-uuid-001")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            params={"id": device_id},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == []

    def test_get_unknown_id_returns_empty_array(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            params={"id": 999999},
        )
        assert resp.json()["data"] == []

    def test_get_invalid_id_returns_empty_array(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            params={"id": "not-a-number"},
        )
        assert resp.json()["data"] == []

    def test_set_returns_true(self, api_server):
        device_id = get_device_id(api_server["url"], "pb-uuid-002")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": make_playback_values()},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] is True

    def test_set_invalid_id_rejected(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            json={"id": "bogus", "values": make_playback_values()},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 0

    def test_round_trip_full_document(self, api_server):
        """POST then GET returns the identical settings document."""
        device_id = get_device_id(api_server["url"], "pb-roundtrip")
        url = api_server["url"]
        values = make_playback_values()
        requests.post(
            f"{url}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": values},
        )
        got = requests.get(
            f"{url}/api/ipad/device/setting/playback",
            params={"id": device_id},
        ).json()["data"]
        assert got == values

    def test_full_replace_on_every_post(self, api_server):
        """The app posts the whole document on every change (rule
        delete included) — storage must not merge with prior state."""
        device_id = get_device_id(api_server["url"], "pb-replace")
        url = api_server["url"]
        requests.post(
            f"{url}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": make_playback_values()},
        )
        # Same document with the first rule deleted.
        slimmer = make_playback_values()
        slimmer["fixed"]["rules"] = [
            {"startTime": "22:05", "endTime": "22:20",
             "module": "screensaver"}]
        requests.post(
            f"{url}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": slimmer},
        )
        got = requests.get(
            f"{url}/api/ipad/device/setting/playback",
            params={"id": device_id},
        ).json()["data"]
        assert got["fixed"]["rules"] == slimmer["fixed"]["rules"]

    def test_settings_survive_relogin(self, api_server):
        """Re-login must not clear the stored playback settings."""
        device_uuid = "pb-relogin"
        device_id = get_device_id(api_server["url"], device_uuid)
        url = api_server["url"]
        values = make_playback_values()
        requests.post(
            f"{url}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": values},
        )
        login(url, device_uuid, origin="view")
        got = requests.get(
            f"{url}/api/ipad/device/setting/playback",
            params={"id": device_id},
        ).json()["data"]
        assert got == values


class TestPlaybackNormalization:
    """Posted values are normalised into the canonical 2.3.1 shape."""

    def _round_trip(self, api_server, uuid, values):
        device_id = get_device_id(api_server["url"], uuid)
        url = api_server["url"]
        requests.post(
            f"{url}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": values},
        )
        return requests.get(
            f"{url}/api/ipad/device/setting/playback",
            params={"id": device_id},
        ).json()["data"]

    def test_interval_clamped_to_app_range(self, api_server):
        """The app's picker offers 1..240 minutes."""
        got = self._round_trip(
            api_server, "pb-norm-interval", make_playback_values(
                random={"intervalMinutes": 9999, "excludedModules": []}))
        assert got["random"]["intervalMinutes"] == 240
        got = self._round_trip(
            api_server, "pb-norm-interval2", make_playback_values(
                random={"intervalMinutes": 0, "excludedModules": []}))
        assert got["random"]["intervalMinutes"] == 1

    def test_unknown_modules_dropped(self, api_server):
        got = self._round_trip(
            api_server, "pb-norm-modules", make_playback_values(
                random={"intervalMinutes": 15,
                        "excludedModules": ["calendar", "bogus"]}))
        assert got["random"]["excludedModules"] == ["calendar"]

    def test_malformed_rules_dropped(self, api_server):
        values = make_playback_values()
        values["fixed"]["rules"] = [
            # valid
            {"startTime": "07:00", "endTime": "09:00", "module": "album"},
            # invalid time format
            {"startTime": "25:00", "endTime": "09:00", "module": "album"},
            # unknown module
            {"startTime": "10:00", "endTime": "11:00", "module": "nope"},
            # missing times
            {"module": "weather"},
        ]
        got = self._round_trip(api_server, "pb-norm-rules", values)
        assert got["fixed"]["rules"] == [
            {"startTime": "07:00", "endTime": "09:00", "module": "album"}]

    def test_invalid_mode_falls_back_to_random(self, api_server):
        got = self._round_trip(
            api_server, "pb-norm-mode",
            make_playback_values(mode="surprise"))
        assert got["mode"] == "random"

    def test_invalid_default_module_cleared(self, api_server):
        values = make_playback_values()
        values["fixed"]["defaultModule"] = "bogus"
        got = self._round_trip(api_server, "pb-norm-default", values)
        assert got["fixed"]["defaultModule"] == ""


class TestPlaybackMqtt:
    """POST publishes ipad/device/setting/Playback to the display."""

    def test_mqtt_notification_carries_full_document(
            self, api_server, mqtt_collector):
        device_uuid = "pb-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        values = make_playback_values()
        requests.post(
            f"{api_server['url']}/api/ipad/device/setting/playback",
            json={"id": device_id, "values": values},
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1, \
            "Expected MQTT notification for playback update"
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/device/setting/Playback"
        assert msg["uuid"] == device_uuid
        assert msg["data"] == values
        assert "msg_id" in msg


class TestDeviceUpdate:
    """POST /api/ipad/device/update (app 2.3.1+ session metadata refresh)"""

    def test_returns_true(self, api_server):
        device_id = get_device_id(api_server["url"], "du-uuid-001")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/update",
            json={
                "id": device_id,
                "uuid": "du-uuid-001",
                "device_name": "iPad 26.4.1",
                "device_type": "ios",
                "ios_version": "26.4.1",
                "width": 1112,
                "height": 834,
            },
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] is True

    def test_updates_session_metadata(self, api_server):
        device_uuid = "du-uuid-002"
        device_id = get_device_id(api_server["url"], device_uuid)
        url = api_server["url"]
        requests.post(
            f"{url}/api/ipad/device/update",
            json={
                "id": device_id,
                "uuid": device_uuid,
                "device_name": "Renamed iPad",
                "ios_version": "26.5",
                "width": 2048,
                "height": 1536,
            },
        )
        info = requests.get(
            f"{url}/api/ipad/device/info",
            params={"id": device_id},
        ).json()["data"]
        assert info["device_name"] == "Renamed iPad"
        assert info["ios_version"] == "26.5"
        assert info["width"] == 2048
        assert info["height"] == 1536

    def test_partial_update_keeps_other_fields(self, api_server):
        device_uuid = "du-uuid-003"
        device_id = get_device_id(api_server["url"], device_uuid)
        url = api_server["url"]
        requests.post(
            f"{url}/api/ipad/device/update",
            json={"id": device_id, "device_name": "Only The Name"},
        )
        info = requests.get(
            f"{url}/api/ipad/device/info",
            params={"id": device_id},
        ).json()["data"]
        assert info["device_name"] == "Only The Name"
        # Set at login by tests.helpers.login and must survive.
        assert info["device_type"] == "ios"

    def test_invalid_id_rejected(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/update",
            json={"id": "bogus", "device_name": "X"},
        )
        assert resp.status_code == 400

    def test_unknown_id_still_succeeds(self, api_server):
        """An unknown device id is a no-op success, like the cloud."""
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/update",
            json={"id": 987654, "device_name": "Ghost"},
        )
        assert resp.json()["code"] == 1


class TestAdminPlaybackTab:
    """The admin device detail view exposes the Playback tab."""

    def test_playback_tab_and_panel_rendered(self, api_server):
        get_device_id(api_server["url"], "pb-admin-uuid")
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        assert 'data-tab="playback"' in resp.text
        assert 'data-panel="playback"' in resp.text
        assert 'data-seg="playback-mode"' in resp.text
        # Random-mode controls
        assert "playback-interval" in resp.text
        # One toggle per module, app 2.3.1 catalog
        for module in ("album", "album_ai", "screensaver", "weather",
                       "calendar"):
            assert f'data-module="{module}"' in resp.text
        # Fixed-mode controls
        assert "playback-default" in resp.text
        assert "rule-add-btn" in resp.text
        assert "playback-save" in resp.text
