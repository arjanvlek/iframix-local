"""Device management handler methods (bind, unbind, list, info, battery)."""

import json
import logging
import os
import shutil
import time

import paho.mqtt.publish as mqtt_publish

from src.api import config
from src.api.persistence import (
    delete_ai_albums_for_device, delete_bindings_for_device,
    delete_calendar_events_by_schedule_ids, delete_calendars_for_device,
    delete_media_settings_for_device, delete_photo_metadata_for_device,
    delete_session, delete_weather_config_for_device,
    load_bindings, load_charger_readings, load_devices, load_sessions,
    save_bindings, save_devices, save_sessions,
    update_device_fields, insert_device_if_missing,
)
from src.api.devices import (
    device_to_info_record, device_to_list_record,
    session_to_device_record, session_to_index_record,
)
from src.api.utils import (
    build_id_map, generate_msg_id, publish_charging_switch,
)

logger = logging.getLogger(__name__)


def _remove_device_directories(device_uuid, device_id):
    """Delete the on-disk photo and log trees for one display device.

    Each directory is best-effort: a missing tree is fine (nothing to
    delete) and a failure on one tree should not stop the others, so we
    log and continue rather than aborting the unbind.
    """
    targets = [
        os.path.join(config.PHOTOS_DIR, str(device_id)),
        os.path.join(config.PHOTOS_AI_DIR, str(device_id)),
        os.path.join(config.THUMBNAILS_DIR, "normal", str(device_id)),
        os.path.join(config.THUMBNAILS_DIR, "ai", str(device_id)),
        os.path.join(config.LOGS_DIR, device_uuid),
    ]
    for path in targets:
        if not os.path.isdir(path):
            continue
        try:
            shutil.rmtree(path)
        except OSError:
            logger.exception(
                "[UNBIND USER] Failed to remove directory %s", path)


class DeviceEndpointsMixin:

    def handle_bind_user(self, body):
        """Update display device info after login (screen size, name, etc.)."""
        device_uuid = body.get("uuid") or self.headers.get("XX-Device-Uuid")

        if device_uuid:
            sessions = load_sessions()
            if device_uuid in sessions:
                session = sessions[device_uuid]
                for key in ("device_name", "device_type", "ios_version",
                            "width", "height"):
                    if key in body:
                        session[key] = body[key]
                save_sessions(sessions)
                logger.info(
                    "[BIND USER] updated device=%s name=%s %sx%s",
                    device_uuid, session.get("device_name"),
                    session.get("width"), session.get("height"))
            else:
                logger.info(
                    "[BIND USER] device=%s not found in sessions",
                    device_uuid)

        self.respond_success(True)

    def handle_unbind_user(self, body):
        """Remove a display/controller device session and all its data.

        Called by the controller app when the user removes a device and by
        the admin panel's Delete button. Deletes the session row, any
        charger binding that pointed at this device, every per-device
        SQLite row (calendars + the manual events that referenced them,
        AI album config, per-photo media settings) and the on-disk photo
        and log directories.
        """
        device_id = body.get("id")
        if device_id is None:
            self.respond_json({"code": 0, "msg": "missing id"}, status=400)
            return

        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        removed_uuid = None
        charger_mac = None

        sessions = load_sessions()
        for sess_uuid, sess in sessions.items():
            if sess.get("id") == device_id:
                charger_mac = sess.get("icharger_mac") or None
                removed_uuid = sess_uuid
                break

        if not removed_uuid:
            logger.info("[UNBIND USER] No session with id=%s", device_id)
            self.respond_success(True)
            return

        delete_session(removed_uuid)
        delete_bindings_for_device(removed_uuid)
        cal_ids = delete_calendars_for_device(device_id)
        delete_calendar_events_by_schedule_ids(cal_ids)
        delete_ai_albums_for_device(device_id)
        delete_media_settings_for_device(device_id)
        delete_weather_config_for_device(device_id)
        delete_photo_metadata_for_device(device_id)

        _remove_device_directories(removed_uuid, device_id)

        logger.info(
            "[UNBIND USER] Removed device=%s (id=%s, charger=%s, "
            "calendars=%d)",
            removed_uuid, device_id, charger_mac or "none", len(cal_ids))
        self.respond_success(True)

    def handle_unbind(self, body):
        """Unbind a charger from its device."""
        device_id = body.get("device_id")

        devices = load_devices()
        id_map = build_id_map(devices)
        charger_uuid = id_map.get(device_id)

        if not charger_uuid or charger_uuid not in devices:
            logger.info("[UNBIND] Unknown device_id=%s", device_id)
            self.respond_success(True)
            return

        charger_mac = devices[charger_uuid].get("mac", "")

        # Find and update the session that has this charger bound
        bound_device_uuid = None
        bindings = load_bindings()
        bound_device_uuid = bindings.pop(charger_mac, None)
        if bound_device_uuid:
            save_bindings(bindings)

        if bound_device_uuid:
            sessions = load_sessions()
            if bound_device_uuid in sessions:
                sessions[bound_device_uuid]["icharger_mac"] = ""
                save_sessions(sessions)

            # Publish unbind event to the controller device's MQTT topic
            unbind_msg = json.dumps({
                "uuid": bound_device_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/icharger/unbind",
                "data": {},
            })
            try:
                mqtt_publish.single(
                    f"/s2c/{bound_device_uuid}",
                    payload=unbind_msg,
                    qos=1,
                    hostname=config.MQTT_BROKER_HOST,
                    port=config.MQTT_BROKER_PORT,
                    auth={"username": config.MQTT_USER,
                          "password": config.MQTT_PASS},
                )
            except Exception:
                logger.exception("[UNBIND] MQTT publish failed")

            logger.info(
                "[UNBIND] charger=%s unbound from device=%s",
                charger_mac, bound_device_uuid)
        else:
            logger.info(
                "[UNBIND] No binding found for charger mac=%s", charger_mac)

        self.respond_success(True)

    def handle_device_list(self, body):
        """Return registered devices with their associated chargers."""
        devices = load_devices()
        sessions = load_sessions()
        records = []

        for sess in sessions.values():
            records.append(session_to_device_record(sess, devices))

        # If no sessions exist yet, fall back to charger-based records
        # so the webapp still works before any login has occurred
        if not records:
            id_map = build_id_map(devices)
            uuid_to_id = {v: k for k, v in id_map.items()}
            for device_uuid, info in sorted(devices.items()):
                if device_uuid.startswith("_"):
                    continue
                device_id = uuid_to_id.get(device_uuid, 0)
                records.append(
                    device_to_list_record(device_uuid, info, device_id))

        logger.info("[DEVICE LIST] returning %d device(s)", len(records))
        self.respond_success({
            "pagination": {
                "page": 1,
                "limit": -1,
                "totalCount": len(records),
            },
            "list": records,
        })

    def handle_device_index(self, params):
        """Return controller device sessions with charger bindings (native app format)."""
        limit = params.get("limit", ["20"])[0]
        records = []

        sessions = load_sessions()
        devices = load_devices()
        bindings = load_bindings()

        for sess in sessions.values():
            records.append(session_to_index_record(sess, devices, bindings))

        # Sort by bind_at descending (most recently bound first)
        records.sort(key=lambda r: r["bind_at"], reverse=True)

        logger.info("[DEVICE INDEX] returning %d device(s)", len(records))
        self.respond_success({
            "pagination": {
                "page": 1,
                "limit": limit,
                "totalCount": len(records),
            },
            "list": records,
        })

    def handle_device_info(self, device_id):
        """Return info for a single device by ID."""
        if device_id is None:
            self.respond_json({"code": 0, "msg": "missing id"}, status=400)
            return

        try:
            device_id = int(device_id)
        except ValueError:
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        # Check persistent sessions first (devices created during login)
        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                devices = load_devices()
                record = session_to_device_record(sess, devices)
                logger.info(
                    "[DEVICE INFO] id=%s -> session %s",
                    device_id, sess["uuid"])
                self.respond_success(record)
                return

        # Fall back to charger devices
        devices = load_devices()
        id_map = build_id_map(devices)
        matched_uuid = id_map.get(device_id)

        if matched_uuid and matched_uuid in devices:
            info = devices[matched_uuid]
            record = device_to_info_record(matched_uuid, info, device_id)
            logger.info(
                "[DEVICE INFO] id=%s -> %s", device_id, matched_uuid)
            self.respond_success(record)
        else:
            logger.info("[DEVICE INFO] id=%s not found", device_id)
            self.respond_json({"code": 0, "msg": "not found"}, status=404)

    def handle_device_update(self, body):
        """Refresh a display device's own session metadata (app 2.3.1+).

        The 2.3.1 display app periodically posts its identity
        (``{id, uuid, device_name, device_type, ios_version, width,
        height}``) so the server-side record tracks renames, OS updates
        and resolution changes without a re-login. Only the metadata
        fields present in the body are updated; the response is a plain
        success, matching the cloud server.
        """
        device_id = body.get("id")
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        updatable = ("device_name", "device_type", "ios_version",
                     "width", "height")
        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                for field in updatable:
                    if field in body and body[field] is not None:
                        sess[field] = body[field]
                save_sessions(sessions)
                logger.info(
                    "[DEVICE UPDATE] id=%s name=%s %sx%s",
                    device_id, sess.get("device_name"),
                    sess.get("width"), sess.get("height"))
                break
        else:
            logger.info("[DEVICE UPDATE] id=%s not found", device_id)

        self.respond_success(True)

    def _maybe_auto_publish(self, uuid, device_info, charging_switch):
        """Publish an MQTT charging_switch command if the charger is in auto mode.

        Auto mode forwards every refersh-battery call to the charger,
        even when the requested state matches the stored desired state.
        Manual mode leaves the physical charger untouched — the admin
        page's Enable/Disable buttons drive MQTT there.
        """
        if device_info.get("mode") != "auto":
            return
        if charging_switch is None:
            return
        try:
            publish_charging_switch(uuid, int(charging_switch))
        except Exception:
            logger.exception("[BATTERY] MQTT publish failed for %s", uuid)

    def handle_battery(self, body):
        """Store the controller app's latest battery limit and charge command.

        The controller app posts this when the user edits the per-charger
        settings (battery cap + on/off toggle). Both fields are desired
        state set by the user — `charging_switch` is the command "should
        the charger be on", not a live reading of whether current is
        flowing. Live voltage/current come from the charger itself via
        MQTT set_info and are handled by the router.
        """
        device_id = body.get("id")
        battery = body.get("battery")
        charging_switch = body.get("charging_switch")

        devices = load_devices()
        id_map = build_id_map(devices)
        matched_uuid = id_map.get(device_id)

        if matched_uuid and matched_uuid in devices:
            update_device_fields(matched_uuid, battery=battery, charging_switch=charging_switch)
            mac = devices[matched_uuid].get("mac", "?")
            logger.info(
                "[BATTERY] %s (%s): %s%% charge_command=%s",
                matched_uuid, mac, battery,
                "ON" if charging_switch else "OFF")
            self._maybe_auto_publish(matched_uuid, devices[matched_uuid],
                                     charging_switch)
        else:
            # Try to associate this cloud ID with a device that has
            # no cloud_id yet (the app sends IDs assigned by the real
            # cloud server, which differ from our hash-based IDs)
            candidates = [
                uid for uid, info in devices.items()
                if not uid.startswith("_") and info.get("cloud_id") is None
            ]
            if len(candidates) == 1:
                matched_uuid = candidates[0]
                update_device_fields(
                    matched_uuid, battery=battery, charging_switch=charging_switch, cloud_id=device_id)
                mac = devices[matched_uuid].get("mac", "?")
                logger.info(
                    "[BATTERY] Mapped cloud id=%s -> %s (%s): %s%%",
                    device_id, matched_uuid, mac, battery)
                self._maybe_auto_publish(matched_uuid, devices[matched_uuid],
                                         charging_switch)
            else:
                unmatched_key = f"_unmatched_id_{device_id}"
                insert_device_if_missing(
                    unmatched_key,
                    cloud_id=device_id,
                    battery=battery,
                    charging_switch=charging_switch,
                    last_seen=time.time(),
                )
                update_device_fields(
                    unmatched_key,
                    battery=battery,
                    charging_switch=charging_switch,
                    last_seen=time.time(),
                )
                n = len(candidates)
                logger.info(
                    "[BATTERY] Unmatched id=%s: %s%% "
                    "(%d candidate(s), cannot auto-map)",
                    device_id, battery, n)

        self.respond_success(True)

    def handle_icharger_index(self, mac, params):
        """Return charger voltage/current history by MAC address."""
        limit = params.get("limit", ["10"])[0]

        if not mac:
            self.respond_success({
                "pagination": {"page": 1, "limit": limit, "totalCount": 0},
                "list": [],
            })
            return

        records = load_charger_readings(mac)

        logger.info(
            "[ICHARGER INDEX] mac=%s -> %d reading(s)", mac, len(records))

        self.respond_success({
            "pagination": {
                "page": 1,
                "limit": limit,
                "totalCount": len(records),
            },
            "list": records,
        })
