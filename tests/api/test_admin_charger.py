"""Admin panel charger control: manual toggle, mode flag, set-mode."""
import time

import pytest
import requests

from tests.helpers import login, get_device_id, seed_auto_charger


class TestAdminToggle:
    """POST /admin/toggle publishes a charging_switch MQTT command AND
    records the admin's click in the admin_switch column so the admin
    page's Power button / pending badge update immediately. The app's
    Charge command column (charging_switch) is left untouched."""

    def _seed_charger(self, api_server, uuid="dev-admin", mac="BE:EF:00:00"):
        from src.api.persistence import insert_device_if_missing
        insert_device_if_missing(uuid, mac=mac, last_seen=time.time())
        return uuid

    def test_toggle_updates_admin_switch_on(self, api_server):
        from src.api.persistence import load_devices
        uuid = self._seed_charger(api_server)

        resp = requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": True},
        )
        assert resp.status_code == 200
        assert load_devices()[uuid]["admin_switch"] == 1

    def test_toggle_updates_admin_switch_off(self, api_server):
        from src.api.persistence import load_devices
        uuid = self._seed_charger(api_server, uuid="dev-admin-off")

        requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": False},
        )
        assert load_devices()[uuid]["admin_switch"] == 0

    def test_toggle_publishes_charging_switch_mqtt_event(
            self, api_server, mqtt_collector):
        uuid = self._seed_charger(api_server, uuid="dev-admin-mqtt")
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": True},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        assert len(messages) >= 1
        payload = messages[0]["payload"]
        assert payload["event"] == "ipad/icharger/charging_switch"
        assert payload["data"]["charging_switch"] == 1

    def test_toggle_does_not_touch_reported_column(self, api_server):
        """The admin command is the user's intent, not a charger report."""
        from src.api.persistence import load_devices
        uuid = self._seed_charger(api_server, uuid="dev-admin-rep")

        requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": True},
        )
        # Reported column stays NULL until the charger actually reports
        # (via set_info → router's current-based inference).
        assert load_devices()[uuid]["charging_switch_reported"] is None

    def test_toggle_rejected_in_auto_mode(self, api_server, mqtt_collector):
        """In auto mode the charger is driven by the app's refersh-battery
        calls, not by the admin buttons. The toggle endpoint must refuse
        so a stale browser tab can't push a conflicting command."""
        from src.api.persistence import (
            insert_device_if_missing, update_device_fields,
        )
        uuid = "dev-admin-auto-reject"
        insert_device_if_missing(uuid, mac="BE:EF:00:99", last_seen=time.time())
        update_device_fields(uuid, mode="auto")

        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        resp = requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": True},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 0

        messages = mqtt_collector.wait_for_messages(count=1, timeout=1)
        assert messages == []


class TestAdminPendingSemantics:
    """The chargers fragment (GET /admin/chargers) shows a "pending-note"
    only when the *driving* command disagrees with the charger's reported
    state. In manual mode the driving command is the admin's Power click
    (admin_switch), NOT the controller app's wish (charging_switch)."""

    def test_app_wish_mismatch_alone_is_not_pending(self, api_server):
        """Manual charger ON (reported=1) while the app once wished OFF
        (charging_switch=0) and the admin never clicked (admin_switch
        NULL) must NOT show a pending badge."""
        from src.api.persistence import (
            insert_device_if_missing, update_device_fields,
        )
        uuid = "dev-pending-appwish"
        insert_device_if_missing(
            uuid, mac="BE:EF:0A:01", last_seen=time.time())
        update_device_fields(
            uuid, charging_switch=0, charging_switch_reported=1)

        resp = requests.get(f"{api_server['url']}/admin/chargers")
        assert resp.status_code == 200
        assert "pending-note" not in resp.text

    def test_admin_click_mismatch_is_pending(self, api_server):
        """After the admin clicks Power off on a charger reporting ON,
        the fragment shows pending and the button offers Power on."""
        from src.api.persistence import (
            insert_device_if_missing, update_device_fields,
        )
        uuid = "dev-pending-adminclick"
        insert_device_if_missing(
            uuid, mac="BE:EF:0A:02", last_seen=time.time())
        update_device_fields(
            uuid, charging_switch=0, charging_switch_reported=1)

        resp = requests.post(
            f"{api_server['url']}/admin/toggle",
            json={"uuid": uuid, "charging_on": False},
        )
        assert resp.status_code == 200

        resp = requests.get(f"{api_server['url']}/admin/chargers")
        assert resp.status_code == 200
        # Only inspect this charger's row.
        marker = f'data-uuid="{uuid}"'
        start = resp.text.index(marker)
        end = resp.text.index("</tr>", start)
        row = resp.text[start:end]
        assert "pending-note" in row
        assert "Power on" in row

    def test_set_mode_resets_admin_switch(self, api_server):
        """Flipping mode clears any stale admin click so it can't drive
        the button label / pending after the switch."""
        from src.api.persistence import (
            insert_device_if_missing, update_device_fields, load_devices,
        )
        uuid = "dev-pending-modereset"
        insert_device_if_missing(
            uuid, mac="BE:EF:0A:03", last_seen=time.time())
        update_device_fields(uuid, admin_switch=1)

        resp = requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "auto"},
        )
        assert resp.status_code == 200
        assert load_devices()[uuid]["admin_switch"] is None


class TestChargerMode:
    """Per-charger mode column + /admin/set-mode endpoint.

    manual (default): refersh-battery only records the desired state.
    auto: refersh-battery also publishes charging_switch to the charger
    every call, even if the requested state equals the stored state.
    """

    def test_new_charger_defaults_to_manual_mode(self, api_server):
        from src.api.persistence import (
            insert_device_if_missing, load_devices,
        )
        insert_device_if_missing(
            "dev-new-mode", mac="BE:EF:11:11", last_seen=time.time())
        assert load_devices()["dev-new-mode"]["mode"] == "manual"

    def test_manual_mode_does_not_publish_mqtt(
            self, api_server, mqtt_collector):
        uuid = seed_auto_charger(
            "dev-manual-silent", mac="BE:EF:22:22",
            cloud_id=501001, mode="manual")
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 501001, "battery": 50, "charging_switch": 1},
        )
        assert resp.status_code == 200

        messages = mqtt_collector.wait_for_messages(count=1, timeout=1)
        assert messages == []

    def test_auto_mode_publishes_charging_switch_on(
            self, api_server, mqtt_collector):
        uuid = seed_auto_charger(
            "dev-auto-on", mac="BE:EF:33:33",
            cloud_id=501002, mode="auto")
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 501002, "battery": 40, "charging_switch": 1},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        assert len(messages) >= 1
        payload = messages[0]["payload"]
        assert payload["event"] == "ipad/icharger/charging_switch"
        assert payload["data"]["charging_switch"] == 1

    def test_auto_mode_publishes_charging_switch_off(
            self, api_server, mqtt_collector):
        uuid = seed_auto_charger(
            "dev-auto-off", mac="BE:EF:44:44",
            cloud_id=501003, mode="auto")
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 501003, "battery": 80, "charging_switch": 0},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        assert len(messages) >= 1
        assert messages[0]["payload"]["data"]["charging_switch"] == 0

    def test_auto_mode_publishes_even_when_state_unchanged(
            self, api_server, mqtt_collector):
        """Auto mode must fire MQTT every call — no dedupe against the
        stored desired state. The physical charger may have lost the
        earlier command, so every refresh is a resync opportunity."""
        uuid = seed_auto_charger(
            "dev-auto-resync", mac="BE:EF:55:55",
            cloud_id=501004, mode="auto", charging_switch=1)
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 501004, "battery": 40, "charging_switch": 1},
        )
        requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 501004, "battery": 40, "charging_switch": 1},
        )
        messages = mqtt_collector.wait_for_messages(count=2, timeout=5)
        assert len(messages) >= 2

    def test_auto_mode_unmatched_id_does_not_publish(
            self, api_server, mqtt_collector):
        """If no real charger is paired to the posted id, do nothing on
        MQTT even when refersh-battery still records an _unmatched_id_*
        placeholder for debugging."""
        from src.api.persistence import load_devices

        # Subscribe to a wildcard so any unexpected publish is caught.
        mqtt_collector.subscribe("/mqtt/s2c/#")

        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/refersh-battery",
            json={"id": 888888, "battery": 20, "charging_switch": 1},
        )
        assert resp.status_code == 200
        assert load_devices().get("_unmatched_id_888888") is not None

        messages = mqtt_collector.wait_for_messages(count=1, timeout=1)
        assert messages == []


class TestAdminSetMode:
    """POST /admin/set-mode flips a charger between manual and auto.

    When switching INTO auto, the currently stored desired
    charging_switch (if any) is pushed over MQTT so the physical
    charger's state matches immediately.
    """

    def _seed(self, uuid="dev-mode", mac="BE:EF:66:66",
              charging_switch=None, mode="manual"):
        from src.api.persistence import (
            insert_device_if_missing, update_device_fields,
        )
        insert_device_if_missing(uuid, mac=mac, last_seen=time.time())
        fields = {"mode": mode}
        if charging_switch is not None:
            fields["charging_switch"] = charging_switch
        update_device_fields(uuid, **fields)
        return uuid

    def test_set_mode_to_auto_persists(self, api_server, mqtt_collector):
        from src.api.persistence import load_devices
        uuid = self._seed(uuid="dev-mode-auto")

        resp = requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "auto"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 1
        assert load_devices()[uuid]["mode"] == "auto"

    def test_set_mode_to_manual_persists(self, api_server, mqtt_collector):
        from src.api.persistence import load_devices
        uuid = self._seed(uuid="dev-mode-manual", mode="auto")

        requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "manual"},
        )
        assert load_devices()[uuid]["mode"] == "manual"

    def test_set_mode_rejects_invalid_value(self, api_server):
        uuid = self._seed(uuid="dev-mode-bad")
        resp = requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "chaos"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 0

    def test_set_mode_to_auto_publishes_current_desired_state(
            self, api_server, mqtt_collector):
        uuid = self._seed(
            uuid="dev-mode-sync", mac="BE:EF:77:77", charging_switch=1)
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "auto"},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=5)
        assert len(messages) >= 1
        assert messages[0]["payload"]["data"]["charging_switch"] == 1

    def test_set_mode_to_auto_without_desired_state_does_not_publish(
            self, api_server, mqtt_collector):
        uuid = self._seed(
            uuid="dev-mode-nosync", mac="BE:EF:88:88",
            charging_switch=None)
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "auto"},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=1)
        assert messages == []

    def test_set_mode_to_manual_does_not_publish_mqtt(
            self, api_server, mqtt_collector):
        uuid = self._seed(
            uuid="dev-mode-back", mac="BE:EF:99:99",
            charging_switch=1, mode="auto")
        mqtt_collector.subscribe(f"/mqtt/s2c/{uuid}")

        requests.post(
            f"{api_server['url']}/admin/set-mode",
            json={"uuid": uuid, "mode": "manual"},
        )
        messages = mqtt_collector.wait_for_messages(count=1, timeout=1)
        assert messages == []
