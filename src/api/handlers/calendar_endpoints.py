"""Calendar handler methods (link, index, events, sync)."""

import json
import logging
import time
import urllib.request

import paho.mqtt.publish as mqtt_publish

from src.api import config
from src.api.persistence import (
    load_calendar_events, load_calendars, load_sessions,
    save_calendar_events, save_calendars,
)
from src.api.utils import generate_msg_id

logger = logging.getLogger(__name__)


class CalendarMixin:

    def handle_calendar_link(self, body):
        """Add an external calendar (iCal URL) to a device."""
        url = body.get("url", "")
        device_id = body.get("device_id")
        name = body.get("name", "")
        driver = body.get("driver", "")

        cal_id = f"C{generate_msg_id()}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "id": cal_id,
            "device_id": device_id,
            "driver": driver,
            "name": name,
            "url": url,
            "update_at": now,
        }

        calendars = load_calendars()
        calendars.append(entry)
        save_calendars(calendars)

        logger.info(
            "[CALENDAR LINK] device=%s name=%s driver=%s id=%s",
            device_id, name, driver, cal_id)
        self.respond_success(True)

    def handle_calendar_index(self, params):
        """List calendars linked to a device."""
        device_id = params.get("device_id", [None])[0]
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            device_id = None

        calendars = load_calendars()

        records = []
        for cal in calendars:
            if device_id is not None and cal.get("device_id") != device_id:
                continue
            records.append({
                "id": cal["id"],
                "uuid": None,
                "driver": cal.get("driver", ""),
                "update_at": cal.get("update_at", ""),
                "name": cal.get("name", ""),
                "linsence": cal.get("url", ""),
                "icon": None,
            })

        logger.info(
            "[CALENDAR INDEX] device=%s -> %d calendar(s)",
            device_id, len(records))
        self.respond_success({
            "pagination": {
                "page": 1,
                "limit": 10,
                "totalCount": len(records),
            },
            "list": records,
        })

    def handle_calendar_events(self, params):
        """Get events from linked calendars by fetching their iCal URLs.

        schedule_id can be a single ID or comma-separated list of IDs.
        Events from all matching calendars are combined in the response,
        including manually created events stored in calendar_events.
        """
        raw_schedule_id = params.get("schedule_id", [None])[0]
        schedule_ids = ([sid.strip() for sid in raw_schedule_id.split(",")
                         if sid.strip()]
                        if raw_schedule_id else [])
        schedule_id_set = set(schedule_ids)

        calendars = load_calendars()

        # Fall back to all calendars for the device if no schedule_id given
        if not schedule_id_set:
            raw_device_id = params.get("device_id", [None])[0]
            if raw_device_id:
                try:
                    device_id_int = int(raw_device_id)
                    schedule_id_set = {
                        cal["id"] for cal in calendars
                        if cal.get("device_id") == device_id_int
                    }
                except (ValueError, TypeError):
                    pass

        # Fetch and parse events from each matching calendar's iCal URL
        cal_entries = [cal for cal in calendars
                       if cal["id"] in schedule_id_set]
        all_events = []
        for cal_entry in cal_entries:
            ical_url = cal_entry.get("url", "")
            try:
                req = urllib.request.Request(ical_url, headers={
                    "User-Agent": "iCharGuard/1.0",
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ical_text = resp.read().decode("utf-8", errors="replace")
                all_events.extend(
                    self._parse_ical_events(ical_text, cal_entry["id"]))
            except Exception:
                logger.exception(
                    "[CALENDAR EVENTS] Failed to fetch iCal for %s",
                    cal_entry["id"])

        # Update last-sync timestamps for all fetched calendars
        if cal_entries:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            fetched_ids = {cal["id"] for cal in cal_entries}
            calendars = load_calendars()
            for cal in calendars:
                if cal["id"] in fetched_ids:
                    cal["update_at"] = now
            save_calendars(calendars)

        # Merge in manually created events for the requested calendars
        manual_events = load_calendar_events()
        for evt in manual_events:
            if schedule_id_set.intersection(evt.get("schedule_id", [])):
                all_events.append(evt)

        logger.info(
            "[CALENDAR EVENTS] schedule=%s -> %d event(s)",
            raw_schedule_id, len(all_events))
        self.respond_success({
            "pagination": {
                "page": 1,
                "limit": 10,
                "totalCount": len(all_events),
            },
            "list": all_events,
        })

    def _parse_ical_events(self, ical_text, schedule_id):
        """Parse iCal text into event records matching the API format.

        Uses basic string parsing to avoid requiring the icalendar library.
        """
        events = []
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        in_event = False
        event = {}

        for line in ical_text.splitlines():
            # Handle line unfolding (continuation lines start with space/tab)
            line = line.rstrip("\r")

            if line == "BEGIN:VEVENT":
                in_event = True
                event = {}
            elif line == "END:VEVENT" and in_event:
                in_event = False
                event_id = f"E{generate_msg_id()}"
                events.append({
                    "id": event_id,
                    "summary": event.get("SUMMARY", ""),
                    "driver": "google",
                    "rules": None,
                    "uuid": event.get("UID", ""),
                    "start_date_time": self._ical_date_to_str(
                        event.get("DTSTART", "")),
                    "end_date_time": self._ical_date_to_str(
                        event.get("DTEND", "")),
                    "description": event.get("DESCRIPTION", ""),
                    "update_at": now,
                    "schedule_id": [schedule_id],
                })
            elif in_event:
                # Strip property parameters (e.g. DTSTART;VALUE=DATE:20260101)
                if ":" in line:
                    key_part, _, value = line.partition(":")
                    key = key_part.split(";")[0]
                    event[key] = value

        return events

    @staticmethod
    def _ical_date_to_str(value):
        """Convert an iCal date/datetime string to 'YYYY-MM-DD HH:MM:SS'."""
        if not value:
            return ""
        # Remove trailing Z (UTC indicator)
        value = value.rstrip("Z")
        try:
            if len(value) == 8:  # YYYYMMDD
                return f"{value[:4]}-{value[4:6]}-{value[6:8]} 00:00:00"
            elif len(value) >= 15:  # YYYYMMDDTHHMMSS
                return (f"{value[:4]}-{value[4:6]}-{value[6:8]} "
                        f"{value[9:11]}:{value[11:13]}:{value[13:15]}")
        except (IndexError, ValueError):
            pass
        return value

    def _find_display_uuid(self, device_id):
        """Look up the display device UUID from a numeric device_id."""
        if device_id is None:
            return None
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            return None
        sessions = load_sessions()
        for session_uuid, sess in sessions.items():
            if sess.get("id") == device_id:
                return session_uuid
        return None

    def _lookup_schedules(self, schedule_ids):
        """Return (schedules list, device_id) from calendar IDs."""
        calendars = load_calendars()
        schedules = []
        device_id = None
        for sid in schedule_ids:
            for cal in calendars:
                if cal["id"] == sid:
                    schedules.append({"name": cal["name"], "id": cal["id"]})
                    if device_id is None:
                        device_id = cal.get("device_id")
                    break
        return schedules, device_id

    def _publish_calendar_event_mqtt(self, device_id, verb, origin):
        """Publish ipad/calendar-event/refresh MQTT to the display device."""
        target_uuid = self._find_display_uuid(device_id)
        if not target_uuid:
            return
        msg = json.dumps({
            "uuid": target_uuid,
            "msg_id": generate_msg_id(),
            "event": "ipad/calendar-event/refresh",
            "data": {"verb": verb, "device_origin": origin},
        })
        try:
            mqtt_publish.single(
                f"/s2c/{target_uuid}",
                payload=msg, qos=1,
                hostname=config.MQTT_BROKER_HOST,
                port=config.MQTT_BROKER_PORT,
                auth={"username": config.MQTT_USER,
                      "password": config.MQTT_PASS},
            )
        except Exception:
            logger.exception(
                "[CALENDAR EVENT MQTT] publish to %s failed", target_uuid)

    def handle_calendar_event_create(self, body):
        """Manually add an event to one or more calendars."""
        schedule_id_raw = body.get("schedule_id", "")
        schedule_ids = [sid.strip() for sid in schedule_id_raw.split(",")
                        if sid.strip()]

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        event_id = f"E{generate_msg_id()}"
        event = {
            "id": event_id,
            "summary": body.get("summary", ""),
            "driver": "manual",
            "rules": None,
            "uuid": "",
            "start_date_time": body.get("start_date_time", ""),
            "end_date_time": body.get("end_date_time", ""),
            "description": body.get("description", ""),
            "update_at": now,
            "schedule_id": schedule_ids,
        }

        events = load_calendar_events()
        events.append(event)
        save_calendar_events(events)

        # Build response with schedule names
        schedules, device_id = self._lookup_schedules(schedule_ids)
        if device_id is None:
            device_id = body.get("device_id")

        response = {
            "user_id": 1,
            "summary": event["summary"],
            "schedule_id": schedule_ids[0] if schedule_ids else "",
            "start_date_time": event["start_date_time"],
            "end_date_time": event["end_date_time"],
            "device_id": device_id,
            "description": event["description"],
            "id": event_id,
            "schedules": schedules,
        }

        self._publish_calendar_event_mqtt(device_id, "create", "view")

        logger.info(
            "[CALENDAR EVENT CREATE] id=%s schedule=%s summary=%s",
            event_id, schedule_id_raw, body.get("summary", ""))
        self.respond_success(response)

    def handle_calendar_event_update(self, body):
        """Update an existing manual calendar event."""
        event_id = body.get("id")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        updated_event = None

        events = load_calendar_events()
        for evt in events:
            if evt["id"] == event_id:
                for key in ("summary", "start_date_time",
                            "end_date_time", "description"):
                    if key in body:
                        evt[key] = body[key]
                evt["update_at"] = now
                updated_event = evt
                break
        save_calendar_events(events)

        if not updated_event:
            logger.info(
                "[CALENDAR EVENT UPDATE] id=%s not found", event_id)
            self.respond_success(True)
            return

        schedule_ids = updated_event.get("schedule_id", [])
        schedules, device_id = self._lookup_schedules(schedule_ids)

        response = {
            "id": updated_event["id"],
            "summary": updated_event.get("summary", ""),
            "icon": None,
            "uuid": updated_event.get("uuid"),
            "schedule_id": schedule_ids[0] if schedule_ids else "",
            "user_id": 1,
            "device_id": device_id,
            "start_date_time": updated_event.get("start_date_time", ""),
            "end_date_time": updated_event.get("end_date_time", ""),
            "rules": None,
            "status": 1,
            "driver": updated_event.get("driver", "default"),
            "description": updated_event.get("description", ""),
            "update_at": updated_event["update_at"],
            "schedules": schedules,
        }

        self._publish_calendar_event_mqtt(device_id, "update", "view")

        logger.info(
            "[CALENDAR EVENT UPDATE] id=%s summary=%s",
            event_id, updated_event.get("summary", ""))
        self.respond_success(response)

    def handle_calendar_event_delete(self, body):
        """Delete a manual calendar event."""
        event_id = body.get("id")
        device_id = None

        events = load_calendar_events()
        for evt in events:
            if evt["id"] == event_id:
                schedule_ids = evt.get("schedule_id", [])
                _, device_id = self._lookup_schedules(schedule_ids)
                break
        events = [e for e in events if e["id"] != event_id]
        save_calendar_events(events)

        self._publish_calendar_event_mqtt(device_id, "delete", "view")

        logger.info("[CALENDAR EVENT DELETE] id=%s", event_id)
        self.respond_success(1)

    def handle_calendar_update(self, body):
        """Rename a linked calendar."""
        cal_id = body.get("id")
        name = body.get("name", "")

        device_id = None
        calendars = load_calendars()
        for cal in calendars:
            if cal["id"] == cal_id:
                cal["name"] = name
                cal["update_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                device_id = cal.get("device_id")
                break
        save_calendars(calendars)

        # Notify display device about the calendar rename
        target_uuid = self._find_display_uuid(device_id)
        if target_uuid:
            msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/calendar/refresh",
                "data": {"verb": "update", "device_origin": "control"},
            })
            try:
                mqtt_publish.single(
                    f"/s2c/{target_uuid}",
                    payload=msg, qos=1,
                    hostname=config.MQTT_BROKER_HOST,
                    port=config.MQTT_BROKER_PORT,
                    auth={"username": config.MQTT_USER,
                          "password": config.MQTT_PASS},
                )
            except Exception:
                logger.exception(
                    "[CALENDAR UPDATE] MQTT publish to %s failed",
                    target_uuid)

        logger.info("[CALENDAR UPDATE] id=%s name=%s", cal_id, name)
        self.respond_success(True)

    def handle_calendar_delete(self, body):
        """Delete a linked calendar by ID."""
        cal_id = body.get("id")

        calendars = load_calendars()
        calendars = [c for c in calendars if c["id"] != cal_id]
        save_calendars(calendars)

        logger.info("[CALENDAR DELETE] id=%s", cal_id)
        self.respond_success(True)

    def handle_calendar_synchronize(self, body):
        """Trigger calendar sync by calendar ID and notify display device via MQTT."""
        cal_id = body.get("id")

        # Look up the calendar to find the device_id
        calendars = load_calendars()
        device_id = None
        for cal in calendars:
            if cal["id"] == cal_id:
                device_id = cal.get("device_id")
                break

        if device_id is None:
            logger.info(
                "[CALENDAR SYNCHRONIZE] id=%s (calendar not found)", cal_id)
            self.respond_success(True)
            return

        # Delegate to the existing device-synchronize logic
        self.handle_calendar_sync({"device_id": device_id})

    def handle_calendar_sync(self, body):
        """Trigger calendar sync for a device and notify via MQTT."""
        device_id = body.get("device_id")

        # Find the display device UUID for MQTT notification
        target_uuid = None
        if device_id is not None:
            try:
                device_id = int(device_id)
            except (ValueError, TypeError):
                device_id = None
        if device_id is not None:
            sessions = load_sessions()
            for session_uuid, sess in sessions.items():
                if sess.get("id") == device_id:
                    target_uuid = session_uuid
                    break

        if target_uuid:
            msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/calendar/refresh",
                "data": {
                    "verb": "synchronize",
                    "device_origin": "control",
                },
            })
            try:
                mqtt_publish.single(
                    f"/s2c/{target_uuid}",
                    payload=msg,
                    qos=1,
                    hostname=config.MQTT_BROKER_HOST,
                    port=config.MQTT_BROKER_PORT,
                    auth={"username": config.MQTT_USER,
                          "password": config.MQTT_PASS},
                )
                logger.info(
                    "[CALENDAR SYNC] device=%s -> notified %s",
                    device_id, target_uuid)
            except Exception:
                logger.exception(
                    "[CALENDAR SYNC] MQTT publish to %s failed",
                    target_uuid)
        else:
            logger.info(
                "[CALENDAR SYNC] device=%s (no matching session for MQTT)",
                device_id)

        self.respond_success(True)
