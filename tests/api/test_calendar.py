"""External calendar link + manual event CRUD."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestCalendar:

    def test_link_returns_true(self, api_server):
        """POST /api/calendar/external/link returns true."""
        device_id = get_device_id(api_server["url"], "cal-uuid-001")
        resp = requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/test.ics",
                "device_id": device_id,
                "name": "Test Calendar",
                "driver": "google",
            },
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

    def test_index_format(self, api_server):
        """GET /api/calendar/index returns pagination + list with 'linsence' (sic) field."""
        device_id = get_device_id(api_server["url"], "cal-uuid-002")
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/test2.ics",
                "device_id": device_id,
                "name": "Google Calendar",
                "driver": "google",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        body = resp.json()
        assert body["code"] == 1
        assert "pagination" in body["data"]
        assert "list" in body["data"]
        assert len(body["data"]["list"]) >= 1

        cal = body["data"]["list"][0]
        for field in ("id", "uuid", "driver", "update_at", "name", "icon"):
            assert field in cal, f"Missing calendar field: {field}"
        # The original server uses the misspelling 'linsence' (not 'licence')
        assert "linsence" in cal
        assert cal["linsence"] == "https://calendar.google.com/test2.ics"

    def test_index_pagination_structure(self, api_server):
        """Calendar index pagination has page, limit, totalCount."""
        device_id = get_device_id(api_server["url"], "cal-uuid-003")
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        pagination = resp.json()["data"]["pagination"]
        assert "page" in pagination
        assert "limit" in pagination
        assert "totalCount" in pagination

    def test_sync_mqtt_notification(self, api_server, mqtt_collector):
        """Calendar sync sends MQTT refresh event to display device."""
        device_uuid = "cal-mqtt-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        requests.post(
            f"{api_server['url']}/api/calendar/device-synchronize",
            json={"device_id": device_id},
        )

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/calendar/refresh"
        assert msg["data"]["verb"] == "synchronize"
        assert msg["data"]["device_origin"] == "control"

    def test_update_renames_calendar(self, api_server):
        """POST /api/calendar/update renames a calendar."""
        device_id = get_device_id(api_server["url"], "cal-uuid-upd-001")
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/rename.ics",
                "device_id": device_id,
                "name": "Old Name",
                "driver": "google",
            },
        )
        # Get the calendar ID
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_id = resp.json()["data"]["list"][0]["id"]

        # Rename it
        resp = requests.post(
            f"{api_server['url']}/api/calendar/update",
            json={"id": cal_id, "name": "New Name"},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

        # Verify the name changed
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal = resp.json()["data"]["list"][0]
        assert cal["name"] == "New Name"

    def test_delete_removes_calendar(self, api_server):
        """POST /api/calendar/delete removes a calendar."""
        device_id = get_device_id(api_server["url"], "cal-uuid-del-001")
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/delete.ics",
                "device_id": device_id,
                "name": "Doomed Calendar",
                "driver": "google",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        assert resp.json()["data"]["pagination"]["totalCount"] == 1
        cal_id = resp.json()["data"]["list"][0]["id"]

        # Delete it
        resp = requests.post(
            f"{api_server['url']}/api/calendar/delete",
            json={"id": cal_id},
        )
        assert resp.json()["code"] == 1
        assert resp.json()["data"] is True

        # Verify it's gone
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        assert resp.json()["data"]["pagination"]["totalCount"] == 0

    def test_synchronize_mqtt_notification(self, api_server, mqtt_collector):
        """POST /api/calendar/synchronize sends MQTT refresh by calendar ID."""
        device_uuid = "cal-sync-uuid-001"
        device_id = get_device_id(api_server["url"], device_uuid)
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/sync.ics",
                "device_id": device_id,
                "name": "Sync Calendar",
                "driver": "google",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_id = resp.json()["data"]["list"][0]["id"]

        mqtt_collector.subscribe(f"/s2c/{device_uuid}")

        resp = requests.post(
            f"{api_server['url']}/api/calendar/synchronize",
            json={"id": cal_id},
        )
        assert resp.json()["code"] == 1

        messages = mqtt_collector.wait_for_messages(count=1, timeout=3)
        assert len(messages) >= 1
        msg = messages[0]["payload"]
        assert msg["event"] == "ipad/calendar/refresh"
        assert msg["data"]["verb"] == "synchronize"

    def test_events_multiple_schedule_ids(self, api_server):
        """GET /api/calendar/events with comma-separated schedule_ids returns combined events."""
        device_id = get_device_id(api_server["url"], "cal-uuid-multi-001")
        for name in ("Calendar A", "Calendar B"):
            requests.post(
                f"{api_server['url']}/api/calendar/external/link",
                json={
                    "url": "https://calendar.google.com/fake.ics",
                    "device_id": device_id,
                    "name": name,
                    "driver": "google",
                },
            )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_ids = [c["id"] for c in resp.json()["data"]["list"]]
        assert len(cal_ids) == 2

        # Request events for both calendars (comma-separated)
        # The iCal fetch will fail (fake URL), but the endpoint should not
        # report "not found" and should return a valid response.
        resp = requests.get(
            f"{api_server['url']}/api/calendar/events",
            params={"schedule_id": ",".join(cal_ids), "device_id": device_id},
        )
        body = resp.json()
        assert body["code"] == 1
        assert "list" in body["data"]
        assert "pagination" in body["data"]

    def test_event_create_returns_event_record(self, api_server):
        """POST /api/calendar/event/create returns the created event."""
        device_id = get_device_id(api_server["url"], "cal-uuid-evt-001")
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/evt.ics",
                "device_id": device_id,
                "name": "Events Cal",
                "driver": "google",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_id = resp.json()["data"]["list"][0]["id"]

        resp = requests.post(
            f"{api_server['url']}/api/calendar/event/create",
            json={
                "summary": "Manual Event",
                "schedule_id": cal_id,
                "start_date_time": "2026-04-13 22:00:00.000",
                "end_date_time": "2026-04-13 23:00:00.000",
                "device_id": device_id,
                "description": "A test event",
            },
        )
        assert resp.json()["code"] == 1
        data = resp.json()["data"]
        assert data["summary"] == "Manual Event"
        assert data["id"].startswith("E")
        assert data["schedule_id"] == cal_id
        assert data["device_id"] == device_id
        assert len(data["schedules"]) == 1
        assert data["schedules"][0]["name"] == "Events Cal"

    def test_event_create_merged_into_events(self, api_server):
        """Manually created events appear in GET /api/calendar/events."""
        device_id = get_device_id(api_server["url"], "cal-uuid-evt-002")
        requests.post(
            f"{api_server['url']}/api/calendar/external/link",
            json={
                "url": "https://calendar.google.com/evt2.ics",
                "device_id": device_id,
                "name": "Merge Cal",
                "driver": "google",
            },
        )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_id = resp.json()["data"]["list"][0]["id"]

        # Create a manual event
        requests.post(
            f"{api_server['url']}/api/calendar/event/create",
            json={
                "summary": "Merged Event",
                "schedule_id": cal_id,
                "start_date_time": "2026-05-01 10:00:00.000",
                "end_date_time": "2026-05-01 11:00:00.000",
                "device_id": device_id,
                "description": "",
            },
        )

        # Retrieve events — the manual event should be included
        resp = requests.get(
            f"{api_server['url']}/api/calendar/events",
            params={"schedule_id": cal_id, "device_id": device_id},
        )
        body = resp.json()
        assert body["code"] == 1
        events = body["data"]["list"]
        assert len(events) >= 1
        manual = [e for e in events if e["summary"] == "Merged Event"]
        assert len(manual) == 1
        assert manual[0]["driver"] == "manual"
        assert manual[0]["start_date_time"] == "2026-05-01 10:00:00.000"
        assert manual[0]["schedule_id"] == [cal_id]

    def test_event_create_multi_calendar(self, api_server):
        """Manual event with comma-separated schedule_ids appears for each calendar."""
        device_id = get_device_id(api_server["url"], "cal-uuid-evt-003")
        for name in ("Cal X", "Cal Y"):
            requests.post(
                f"{api_server['url']}/api/calendar/external/link",
                json={
                    "url": "https://calendar.google.com/multi.ics",
                    "device_id": device_id,
                    "name": name,
                    "driver": "google",
                },
            )
        resp = requests.get(
            f"{api_server['url']}/api/calendar/index",
            params={"device_id": device_id},
        )
        cal_ids = [c["id"] for c in resp.json()["data"]["list"]]
        assert len(cal_ids) == 2

        # Create event linked to both calendars
        requests.post(
            f"{api_server['url']}/api/calendar/event/create",
            json={
                "summary": "Multi Cal Event",
                "schedule_id": ",".join(cal_ids),
                "start_date_time": "2026-06-01 09:00:00.000",
                "end_date_time": "2026-06-01 10:00:00.000",
                "device_id": device_id,
                "description": "",
            },
        )

        # Event appears when requesting either calendar alone
        for cal_id in cal_ids:
            resp = requests.get(
                f"{api_server['url']}/api/calendar/events",
                params={"schedule_id": cal_id, "device_id": device_id},
            )
            events = resp.json()["data"]["list"]
            matching = [e for e in events
                        if e["summary"] == "Multi Cal Event"]
            assert len(matching) == 1
            assert set(matching[0]["schedule_id"]) == set(cal_ids)
