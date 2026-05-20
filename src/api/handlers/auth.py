"""Authentication and login handler methods."""

import json
import logging
import random
import time
import uuid
from urllib.parse import unquote

from src.api import config
from src.api.persistence import (
    load_bindings, load_devices, load_sessions,
    save_bindings, save_sessions,
)
from src.api.devices import session_to_device_record
from src.api.utils import generate_token

logger = logging.getLogger(__name__)


class AuthMixin:

    def handle_login(self, body):
        """Return a JWT-like token and user/device info matching the real server."""
        username = body.get("username", "local")

        # Extract device identity from native app headers
        header_device_uuid = self.headers.get("XX-Device-Uuid")
        header_device_name = self.headers.get("XX-Device-Name")
        header_device_type = self.headers.get("XX-Device-Type")
        header_device_version = self.headers.get("XX-Device-Version")
        header_is_ipad = self.headers.get("XX-Device-Is-Ipad")
        header_device_origin = self.headers.get("XX-Device-Origin", "")
        user_agent = self.headers.get("User-Agent", "")

        # Try to extract cached device info from user-agent JSON blob
        ua_device = {}
        ua_icharger_mac = None
        try:
            json_start = user_agent.index("{")
            ua_data = json.loads(user_agent[json_start:])
            ua_device = ua_data.get("device", {})
            icharger = ua_device.get("icharger")
            if isinstance(icharger, dict):
                ua_icharger_mac = icharger.get("mac")
        except (ValueError, json.JSONDecodeError):
            pass

        now = int(time.time())

        sessions = load_sessions()
        devices = load_devices()

        # Look up existing session by device UUID
        if header_device_uuid and header_device_uuid in sessions:
            session = sessions[header_device_uuid]
            session["last_login"] = now
            session["user"] = username
            # Update charger binding from UA if not already set
            if not session.get("icharger_mac") and ua_icharger_mac:
                session["icharger_mac"] = ua_icharger_mac
            save_sessions(sessions)
            # Sync binding to bindings for the router
            bound_mac = session.get("icharger_mac")
            if bound_mac:
                bindings = load_bindings()
                bindings[bound_mac] = header_device_uuid
                save_bindings(bindings)
            device_record = session_to_device_record(session, devices)
            logger.info(
                "[LOGIN] user=%s existing device=%s",
                username, header_device_uuid)
        else:
            # Create a new persistent session
            device_uuid = header_device_uuid or str(uuid.uuid4())
            device_id = ua_device.get("id") or random.randint(1000, 99999)

            # Determine device properties from headers / UA / defaults
            if header_device_name:
                device_name = unquote(header_device_name)
            elif ua_device.get("device_name"):
                device_name = ua_device["device_name"]
            elif "iPad" in user_agent:
                device_name = "iPad-WebApp"
            elif "iPhone" in user_agent:
                device_name = "iPhone-WebApp"
            else:
                device_name = "WebApp"

            is_native = bool(header_device_uuid)
            session = {
                "id": device_id,
                "uuid": device_uuid,
                "device_name": device_name,
                "device_type": header_device_type or ua_device.get(
                    "device_type", "ios"),
                "ios_version": header_device_version or ua_device.get(
                    "ios_version", ""),
                "width": ua_device.get("width", 0),
                "height": ua_device.get("height", 0),
                "user_id": ua_device.get("user_id", 1),
                "user": username,
                "is_ipad": 1 if (header_is_ipad or "").lower() == "true"
                          else ua_device.get("is_ipad", 0),
                "is_h5": 0 if is_native else 1,
                "bind_at": now,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "icharger_mac": ua_icharger_mac or "",
                "last_login": now,
            }
            sessions[device_uuid] = session
            save_sessions(sessions)
            # Sync binding to bindings for the router
            if ua_icharger_mac:
                bindings = load_bindings()
                bindings[ua_icharger_mac] = device_uuid
                save_bindings(bindings)
            device_record = session_to_device_record(session, devices)
            logger.info(
                "[LOGIN] user=%s new device=%s", username, device_uuid)

        # Controller devices (origin=control) get device=null; display
        # devices get a slim record without the extra online/icharger fields
        # that only appear on device-index / device-info endpoints.
        if header_device_origin == "control":
            login_device = None
        else:
            login_device = {k: v for k, v in device_record.items()
                           if k not in ("is_online", "online", "icharger",
                                        "user")}

        self.respond_success({
            "token": "local-icharguard-" + generate_token(),
            "user": {
                "sex": 0,
                "birthday": 0,
                "user_login": "",
                "user_nickname": "",
                "user_email": username,
                "avatar": "",
                "mobile": "",
                "id": 1,
            },
            "device": login_device,
        })

    def handle_webhook_auth(self, body):
        """Return an MQTT auth token for the webapp's WebSocket connection."""
        client_id = body.get("clientid", "?")
        token = generate_token()
        logger.info("[WEBHOOK AUTH] clientid=%s token=%s", client_id, token)
        self.respond_success(token)
