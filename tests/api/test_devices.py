"""Device index/info, bind/unbind."""
import base64
import json
import os
import time

import pytest
import requests

from tests.helpers import login, get_device_id


class TestDeviceIndex:

    def test_empty_initially(self, api_server):
        """No sessions -> empty list."""
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"]["list"] == []
        assert body["data"]["pagination"]["totalCount"] == 0

    def test_pagination_structure(self, api_server):
        """Pagination object has page, limit, totalCount."""
        login(api_server["url"], "idx-uuid-001", origin="view")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        pagination = resp.json()["data"]["pagination"]
        assert "page" in pagination
        assert "limit" in pagination
        assert "totalCount" in pagination

    def test_limit_returned_as_string(self, api_server):
        """The original server returns limit as a string — verify we match."""
        login(api_server["url"], "idx-uuid-002", origin="view")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        assert isinstance(resp.json()["data"]["pagination"]["limit"], str)

    def test_device_record_fields(self, api_server):
        """Each record has all fields from the spec (including online, icharger)."""
        login(api_server["url"], "idx-uuid-003", origin="view")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        record = resp.json()["data"]["list"][0]
        for field in ("id", "uuid", "device_name", "device_type", "is_ipad",
                      "is_h5", "ios_version", "width", "height", "user_id",
                      "bind_at", "created_at", "deleted_at", "is_online",
                      "online", "icharger"):
            assert field in record, f"Missing field: {field}"

    def test_online_subfields(self, api_server):
        """The online object has start_connected_at and last_disconnected_at."""
        login(api_server["url"], "idx-uuid-004", origin="view")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        online = resp.json()["data"]["list"][0]["online"]
        assert "start_connected_at" in online
        assert "last_disconnected_at" in online

    def test_icharger_null_when_no_charger(self, api_server):
        """icharger is null when no charger is bound to the device."""
        login(api_server["url"], "idx-uuid-005", origin="view")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            params={"limit": "-1"},
        )
        assert resp.json()["data"]["list"][0]["icharger"] is None


class TestDeviceInfo:

    def test_has_user_field(self, api_server):
        """Device info includes a 'user' field (email string), unlike device index."""
        device_id = get_device_id(api_server["url"], "info-uuid-001")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": device_id},
        )
        record = resp.json()["data"]
        assert "user" in record
        assert isinstance(record["user"], str)

    def test_has_icharger_field(self, api_server):
        """Device info includes an icharger field."""
        device_id = get_device_id(api_server["url"], "info-uuid-002")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": device_id},
        )
        assert "icharger" in resp.json()["data"]

    def test_has_is_online(self, api_server):
        """Device info includes is_online."""
        device_id = get_device_id(api_server["url"], "info-uuid-003")
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": device_id},
        )
        assert "is_online" in resp.json()["data"]

    def test_not_found(self, api_server):
        """Returns error for unknown device ID."""
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": 99999},
        )
        assert resp.json()["code"] != 1


class TestBindUser:

    def test_returns_true(self, api_server):
        login(api_server["url"], "bind-uuid-001", origin="view")
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/bindUser",
            json={
                "uuid": "bind-uuid-001",
                "device_name": "Test iPad",
                "device_type": "ios",
                "ios_version": "16.0",
                "width": 1024,
                "height": 768,
            },
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] is True

    def test_updates_device_dimensions(self, api_server):
        """bindUser updates screen dimensions, visible via device info."""
        device_id = get_device_id(api_server["url"], "bind-uuid-002")
        requests.post(
            f"{api_server['url']}/api/ipad/device/bindUser",
            json={
                "uuid": "bind-uuid-002",
                "device_name": "Updated iPad",
                "device_type": "ios",
                "ios_version": "17.0",
                "width": 2048,
                "height": 1536,
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": device_id},
        )
        record = resp.json()["data"]
        assert record["device_name"] == "Updated iPad"
        assert record["width"] == 2048
        assert record["height"] == 1536


class TestUnbindUser:
    """unbindUser must delete the session and *all* per-device data."""

    def test_no_session_still_returns_true(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/unbindUser",
            json={"id": 99999999},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_invalid_id_returns_400(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/ipad/device/unbindUser",
            json={"id": "not-a-number"},
        )
        assert resp.status_code == 400

    def test_removes_session(self, api_server):
        url = api_server["url"]
        device_uuid = "unbind-cleanup-uuid-001"
        device_id = get_device_id(url, device_uuid)

        resp = requests.post(
            f"{url}/api/ipad/device/unbindUser",
            json={"id": device_id},
        )
        assert resp.json()["code"] == 1

        # Session is gone from device index
        resp = requests.get(f"{url}/api/ipad/device/index")
        ids = [d["id"] for d in resp.json()["data"]["list"]]
        assert device_id not in ids

    def test_removes_charger_binding(self, api_server):
        url = api_server["url"]
        device_uuid = "unbind-cleanup-uuid-002"
        device_id = get_device_id(url, device_uuid)

        from src.db import get_connection
        charger_mac = "AA:BB:CC:DD:EE:01"
        conn = get_connection()
        conn.execute(
            "UPDATE sessions SET icharger_mac = ? WHERE uuid = ?",
            (charger_mac, device_uuid))
        conn.execute(
            "INSERT INTO bindings (charger_mac, device_uuid) VALUES (?, ?)",
            (charger_mac, device_uuid))
        conn.commit()
        conn.close()

        requests.post(
            f"{url}/api/ipad/device/unbindUser",
            json={"id": device_id},
        )

        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM bindings WHERE device_uuid = ?",
            (device_uuid,)).fetchall()
        conn.close()
        assert rows == []

    def test_removes_photos_logs_and_db_rows(self, api_server):
        url = api_server["url"]
        tmp_path = api_server["tmp_path"]
        mod = api_server["module"]
        cfg = mod.config

        device_uuid = "unbind-cleanup-uuid-003"
        device_id = get_device_id(url, device_uuid)

        # Photos: drop a file in each per-device dir
        photo_dir = os.path.join(cfg.PHOTOS_DIR, str(device_id))
        ai_dir = os.path.join(cfg.PHOTOS_AI_DIR, str(device_id))
        log_dir = os.path.join(cfg.LOGS_DIR, device_uuid)
        os.makedirs(photo_dir, exist_ok=True)
        os.makedirs(ai_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(photo_dir, "x.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")
        with open(os.path.join(ai_dir, "y.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")
        with open(os.path.join(log_dir, "client.log"), "w") as f:
            f.write("hello\n")

        # DB rows: link a calendar, an event, an ai_album, a media_setting
        from src.db import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO calendars (id, device_id, driver, name, url) "
            "VALUES (?, ?, ?, ?, ?)",
            ("CAL-DEL-1", device_id, "google", "Work", "ical://x"))
        conn.execute(
            "INSERT INTO calendar_events "
            "(id, summary, schedule_ids_json) VALUES (?, ?, ?)",
            ("EVT-DEL-1", "Standup", json.dumps(["CAL-DEL-1"])))
        conn.execute(
            "INSERT INTO ai_albums (device_id, albums_json) VALUES (?, ?)",
            (device_id, json.dumps([{"name": "Holiday"}])))
        conn.execute(
            "INSERT INTO media_settings "
            "(media_id, device_id, display, template_id, template_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("MID-DEL-1", device_id, "", 3, 1))
        # And a second device's data that must be left alone
        conn.execute(
            "INSERT INTO calendars (id, device_id, driver, name, url) "
            "VALUES (?, ?, ?, ?, ?)",
            ("CAL-KEEP", 12345, "google", "Other", "ical://y"))
        conn.execute(
            "INSERT INTO ai_albums (device_id, albums_json) VALUES (?, ?)",
            (12345, json.dumps([{"name": "Other"}])))
        conn.execute(
            "INSERT INTO media_settings "
            "(media_id, device_id, display, template_id, template_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("MID-KEEP", 12345, "", 1, 1))
        conn.commit()
        conn.close()

        resp = requests.post(
            f"{url}/api/ipad/device/unbindUser",
            json={"id": device_id},
        )
        assert resp.json()["code"] == 1

        # On-disk
        assert not os.path.isdir(photo_dir)
        assert not os.path.isdir(ai_dir)
        assert not os.path.isdir(log_dir)

        # DB
        conn = get_connection()
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE uuid = ?", (device_uuid,)).fetchall()
        cals = conn.execute(
            "SELECT id FROM calendars WHERE device_id = ?",
            (device_id,)).fetchall()
        events = conn.execute(
            "SELECT id FROM calendar_events WHERE id = ?",
            ("EVT-DEL-1",)).fetchall()
        albums = conn.execute(
            "SELECT * FROM ai_albums WHERE device_id = ?",
            (device_id,)).fetchall()
        media = conn.execute(
            "SELECT * FROM media_settings WHERE device_id = ?",
            (device_id,)).fetchall()
        # Untouched
        keep_cals = conn.execute(
            "SELECT * FROM calendars WHERE id = ?",
            ("CAL-KEEP",)).fetchall()
        keep_albums = conn.execute(
            "SELECT * FROM ai_albums WHERE device_id = ?",
            (12345,)).fetchall()
        keep_media = conn.execute(
            "SELECT * FROM media_settings WHERE media_id = ?",
            ("MID-KEEP",)).fetchall()
        conn.close()

        assert sessions == []
        assert cals == []
        assert events == []
        assert albums == []
        assert media == []
        assert len(keep_cals) == 1
        assert len(keep_albums) == 1
        assert len(keep_media) == 1
