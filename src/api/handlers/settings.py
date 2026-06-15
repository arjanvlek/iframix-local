"""Device settings handler methods (screensaver, display, address, playback)."""

import json
import logging
import re

import paho.mqtt.publish as mqtt_publish

from src.api import config
from src.api.persistence import (
    load_ai_albums, load_sessions, load_weather_config,
    save_ai_albums, save_sessions, save_weather_config,
)
from src.api.utils import generate_msg_id

logger = logging.getLogger(__name__)

# Module identifiers used by the iFramix Pro 2.3.1 playback settings,
# exactly as the native app posts them: album = Photos, album_ai =
# Photos + AI, screensaver = Flip Clock, weather = Weather Station,
# calendar = Calendar.
PLAYBACK_MODULES = ("album", "album_ai", "screensaver", "weather", "calendar")

_PLAYBACK_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _normalize_playback_values(values):
    """Coerce a posted playback document into the canonical 2.3.1 shape.

    The app always posts the whole settings document (both the random
    and fixed sub-objects, regardless of the active mode), so this
    normalises rather than validates: unknown modules are dropped,
    the interval is clamped to the app's 1..240 minute picker range,
    and malformed rules are skipped. The result matches the shape the
    cloud server echoes back on GET and in the MQTT Playback event.
    """
    if not isinstance(values, dict):
        values = {}
    random_in = values.get("random") or {}
    fixed_in = values.get("fixed") or {}

    mode = values.get("mode")
    if mode not in ("random", "fixed"):
        mode = "random"

    try:
        interval = int(random_in.get("intervalMinutes", 15))
    except (TypeError, ValueError):
        interval = 15
    interval = max(1, min(240, interval))

    excluded = [m for m in (random_in.get("excludedModules") or [])
                if m in PLAYBACK_MODULES]

    default_module = fixed_in.get("defaultModule") or ""
    if default_module not in PLAYBACK_MODULES:
        default_module = ""

    rules = []
    for rule in (fixed_in.get("rules") or []):
        if not isinstance(rule, dict):
            continue
        start = str(rule.get("startTime") or "")
        end = str(rule.get("endTime") or "")
        module = rule.get("module")
        if module not in PLAYBACK_MODULES:
            continue
        if not (_PLAYBACK_TIME_RE.match(start)
                and _PLAYBACK_TIME_RE.match(end)):
            continue
        rules.append({"startTime": start, "endTime": end, "module": module})

    return {
        "mode": mode,
        "random": {
            "intervalMinutes": interval,
            "excludedModules": excluded,
        },
        "fixed": {
            "defaultModule": default_module,
            "rules": rules,
        },
        "isPlaying": bool(values.get("isPlaying", False)),
        "currentModule": str(values.get("currentModule") or ""),
    }


class SettingsMixin:

    def handle_screensaver_setting(self, params):
        """Return screensaver settings for a device."""
        device_id = params.get("id", [None])[0]
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_success([])
            return

        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                settings = sess.get("screensaver", [])
                result = settings[-1] if settings else {}
                logger.info(
                    "[SCREENSAVER GET] id=%s -> %s", device_id, result)
                self.respond_success(result)
                return

        logger.info("[SCREENSAVER GET] id=%s not found", device_id)
        self.respond_success({})

    def handle_screensaver_update(self, body):
        """Store screensaver settings and notify the target display device via MQTT."""
        device_id = body.get("id")
        values = body.get("values", {})

        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        target_uuid = None
        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                settings = [values]
                sess["screensaver"] = settings
                target_uuid = sess["uuid"]
                save_sessions(sessions)
                break

        if target_uuid:
            msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/device/setting/Screensaver",
                "data": values,
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
                    "[SCREENSAVER SET] id=%s values=%s -> notified %s",
                    device_id, values, target_uuid)
            except Exception:
                logger.exception(
                    "[SCREENSAVER SET] MQTT publish to %s failed",
                    target_uuid)
        else:
            logger.info(
                "[SCREENSAVER SET] id=%s values=%s "
                "(no matching session for MQTT)",
                device_id, values)

        self.respond_success(True)

    def handle_display_setting(self, params):
        """Return display settings for a device."""
        device_id = params.get("id", [None])[0]
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_success([])
            return

        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                settings = sess.get("display", [])
                logger.info("[DISPLAY GET] id=%s -> %s", device_id, settings)
                self.respond_success(settings)
                return

        logger.info("[DISPLAY GET] id=%s not found", device_id)
        self.respond_success([])

    def handle_display_update(self, body):
        """Store display settings and notify the target display device via MQTT."""
        device_id = body.get("id")
        values = body.get("values", {})

        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        target_uuid = None
        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                sess["display"] = values
                target_uuid = sess["uuid"]
                save_sessions(sessions)
                break

        if target_uuid:
            msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/device/setting/Display",
                "data": values,
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
                    "[DISPLAY SET] id=%s values=%s -> notified %s",
                    device_id, values, target_uuid)
            except Exception:
                logger.exception(
                    "[DISPLAY SET] MQTT publish to %s failed", target_uuid)
        else:
            logger.info(
                "[DISPLAY SET] id=%s values=%s "
                "(no matching session for MQTT)",
                device_id, values)

        self.respond_success(True)

    def handle_playback_setting(self, params):
        """Return playback-mode settings for a device (app 2.3.1+).

        Mirrors the cloud server: a device that has never saved playback
        settings gets an empty ``data`` array (the app then falls back
        to its built-in defaults), a configured device gets the full
        settings document back.
        """
        device_id = params.get("id", [None])[0]
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_success([])
            return

        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                playback = sess.get("playback")
                result = playback if playback is not None else []
                logger.info(
                    "[PLAYBACK GET] id=%s -> %s", device_id, result)
                self.respond_success(result)
                return

        logger.info("[PLAYBACK GET] id=%s not found", device_id)
        self.respond_success([])

    def handle_playback_update(self, body):
        """Store playback settings and notify the display device via MQTT.

        The app posts the whole settings document on every change (mode
        switch, interval change, module exclusion, default module, rule
        add/edit/delete), so storage is a full replace. The display
        device is notified with an ``ipad/device/setting/Playback``
        event carrying the same document, matching the cloud server.
        """
        device_id = body.get("id")
        values = _normalize_playback_values(body.get("values"))

        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        target_uuid = None
        sessions = load_sessions()
        for sess in sessions.values():
            if sess.get("id") == device_id:
                sess["playback"] = values
                target_uuid = sess["uuid"]
                save_sessions(sessions)
                break

        if target_uuid:
            msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/device/setting/Playback",
                "data": values,
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
                    "[PLAYBACK SET] id=%s mode=%s -> notified %s",
                    device_id, values["mode"], target_uuid)
            except Exception:
                logger.exception(
                    "[PLAYBACK SET] MQTT publish to %s failed", target_uuid)
        else:
            logger.info(
                "[PLAYBACK SET] id=%s mode=%s "
                "(no matching session for MQTT)",
                device_id, values["mode"])

        self.respond_success(True)

    def handle_address_update(self, body):
        """Update weather city and notify the target display device via MQTT."""
        city_name = body.get("city_name", "")
        city_id = body.get("city_id", "")
        lat = body.get("lat", "")
        lon = body.get("lon", "")
        device_id = body.get("id")

        # Normalize device id before persisting weather config
        if device_id is not None:
            try:
                device_id = int(device_id)
            except (ValueError, TypeError):
                device_id = None

        # Update the per-device weather config with the new city.
        # Preserve the unit from any existing row so the user's °C/°F
        # choice survives an address-only change; default to metric
        # otherwise. Without a device id there's nowhere to store it.
        existing = load_weather_config(device_id) if device_id is not None else None
        weather_cfg = {
            "city": city_name,
            "city_id": city_id,
            "lat": lat,
            "lon": lon,
            "unit": existing["unit"] if existing else 1,
            "weather_template_id": (
                existing["weather_template_id"] if existing else 0),
        }
        if device_id is not None:
            save_weather_config(weather_cfg, device_id)

        # Find the target display device by ID and notify via MQTT
        target_uuid = None
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
                "event": "ipad/device/setting/Address",
                "data": {
                    "lat": lat,
                    "lon": lon,
                    "city_id": city_id,
                    "city_name": city_name,
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
                    "[ADDRESS SET] id=%s city=%s (%s) -> notified %s",
                    device_id, city_name, city_id, target_uuid)
            except Exception:
                logger.exception(
                    "[ADDRESS SET] MQTT publish to %s failed", target_uuid)

            # Also publish Weather event so display refreshes weather
            weather_msg = json.dumps({
                "uuid": target_uuid,
                "msg_id": generate_msg_id(),
                "event": "ipad/device/setting/Weather",
                "data": {
                    "city": city_name,
                    "cityMsg": {
                        "id": city_id,
                        "name": city_name,
                        "lat": lat,
                        "lon": lon,
                    },
                    "unit": weather_cfg["unit"],
                    "weather_template_id": weather_cfg[
                        "weather_template_id"],
                },
            })
            try:
                mqtt_publish.single(
                    f"/s2c/{target_uuid}",
                    payload=weather_msg,
                    qos=1,
                    hostname=config.MQTT_BROKER_HOST,
                    port=config.MQTT_BROKER_PORT,
                    auth={"username": config.MQTT_USER,
                          "password": config.MQTT_PASS},
                )
            except Exception:
                logger.exception(
                    "[ADDRESS SET] Weather MQTT to %s failed", target_uuid)
        else:
            logger.info(
                "[ADDRESS SET] id=%s city=%s (%s) "
                "(no matching session for MQTT)",
                device_id, city_name, city_id)

        self.respond_success(True)

    def handle_weather_update(self, body):
        """Update weather settings (city, unit) and notify display via MQTT."""
        device_id = body.get("id")
        values = body.get("values", {})

        # Normalize device id so the per-device weather row is keyed correctly
        if device_id is not None:
            try:
                device_id = int(device_id)
            except (ValueError, TypeError):
                device_id = None

        city_msg = values.get("cityMsg", {})
        existing = load_weather_config(device_id) if device_id is not None else None
        # iFramix Pro 2.2.29 posts the chosen weather-station style as
        # ``weather_template_id`` (0..3, matching the webapp's 0-based
        # catalog). Older app versions don't send this field, so fall
        # back to whatever was previously saved (defaulting to style 0)
        # to keep their POSTs harmless.
        new_template_id = (
            values.get("weather_template_id")
            if "weather_template_id" in values
            else body.get("weather_template_id"))
        weather_cfg = {
            "city": values.get(
                "city", existing["city"] if existing else ""),
            "city_id": city_msg.get(
                "id", existing["city_id"] if existing else ""),
            "lat": city_msg.get(
                "lat", existing["lat"] if existing else ""),
            "lon": city_msg.get(
                "lon", existing["lon"] if existing else ""),
            "unit": values.get(
                "unit", existing["unit"] if existing else 1),
            "weather_template_id": (
                new_template_id
                if new_template_id is not None
                else (existing["weather_template_id"] if existing else 0)),
        }
        if device_id is not None:
            save_weather_config(weather_cfg, device_id)

        # Find the target display device and notify via MQTT
        target_uuid = None
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
                "event": "ipad/device/setting/Weather",
                "data": values,
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
                    "[WEATHER SET] id=%s city=%s weather_template_id=%s -> notified %s",
                    device_id, values.get("city"), values.get("weather_template_id"), target_uuid)
            except Exception:
                logger.exception(
                    "[WEATHER SET] MQTT publish to %s failed", target_uuid)
        else:
            logger.info(
                "[WEATHER SET] id=%s city=%s template_id=%s (no matching session for MQTT)",
                device_id, values.get("city"), values.get('weather_template_id'))

        self.respond_success(True)

    def handle_ai_albums_setting(self, params):
        """Return AI album names/themes for a device."""
        device_id = params.get("id", [None])[0]
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_success([])
            return

        albums = load_ai_albums()

        result = albums.get(str(device_id), [])
        logger.info(
            "[AI ALBUMS GET] id=%s -> %d album(s)", device_id, len(result))
        self.respond_success(result)

    def handle_ai_albums_update(self, body):
        """Save AI album names/themes for a device."""
        device_id = body.get("id")
        values = body.get("values", [])

        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            self.respond_json({"code": 0, "msg": "invalid id"}, status=400)
            return

        albums = load_ai_albums()
        albums[str(device_id)] = values
        save_ai_albums(albums)

        logger.info("[AI ALBUMS SET] id=%s values=%s", device_id, values)
        self.respond_success(True)
