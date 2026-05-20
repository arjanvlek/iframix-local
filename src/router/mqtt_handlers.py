"""MQTT callback handlers for the router (headless mode event processing)."""

import json
import logging
import time

from src.router import config
from src.router.persistence import (
    load_bindings, load_sessions, register_device,
    save_bindings, save_sessions, save_charger_reading,
)

logger = logging.getLogger(__name__)


def on_connect(client, userdata, flags, reason_code, properties):
    port = userdata.get("port", "?")
    logger.info("Router connected to port %s (%s)", port, reason_code)
    if not userdata.get("interactive"):
        client.subscribe("#", qos=1)
        logger.info(
            "Subscribed to all topics on port %s "
            "— waiting for devices to check in...", port)


def on_message(client, userdata, msg, properties=None):
    if userdata.get("interactive"):
        return

    # Log every message regardless of topic or content (DEBUG: high volume)
    port = userdata.get("port", "?")
    try:
        payload_str = msg.payload.decode()
    except Exception:
        payload_str = repr(msg.payload)
    logger.debug("[MQTT:%s] %s %s", port, msg.topic, payload_str)

    # Only process charger events from the charger-to-server topic
    if msg.topic != "/mqtt/cts/message":
        return

    try:
        payload = json.loads(payload_str)
        event = payload.get("event", "")
        data = payload.get("data", {})
        device_uuid = data.get("uuid", "")

        if not device_uuid:
            return

        # Auto-register every device that reports in
        register_device(device_uuid, data)

        logger.info("[RX] %s from %s", event, device_uuid)

        # When a charger announces its config, respond to confirm
        # binding and set default charging parameters
        if event == "ipad/icharger/set_config":
            _handle_set_config(client, device_uuid, data)
        elif event == "ipad/icharger/set_info":
            _handle_set_info(device_uuid, data)

    except Exception:
        logger.exception("Error processing message")


def _handle_set_config(client, device_uuid, data):
    """Respond to a charger set_config event with binding confirmation."""
    # Step 2: Respond to charger with get_config
    response = {
        "msg_id": config.generate_msg_id(),
        "event": "ipad/icharger/get_config",
        "data": {
            "bind_status": 1,
            "polling": 15,
            "battery": 0,         # 0 = no limit
            "charging_switch": 1  # charging: 1 = ON, 0 = OFF
        }
    }
    topic = f"/mqtt/s2c/{device_uuid}"
    client.publish(topic, json.dumps(response), qos=1)
    logger.info("[TX] Sent get_config to charger %s", device_uuid)

    # Step 3: Notify the bound controller device (tablet/phone)
    charger_mac = data.get("mac", "")
    if not charger_mac:
        return

    bindings = load_bindings()
    bound_device_uuid = bindings.get(charger_mac)
    sessions = load_sessions()

    # If no binding exists, pair with the most recently
    # active controller device (the one on the pairing screen)
    if not bound_device_uuid or bound_device_uuid not in sessions:
        best_uuid = None
        best_login = 0
        for sess_uuid, sess in sessions.items():
            login = sess.get("last_login", 0)
            if login > best_login:
                best_login = login
                best_uuid = sess_uuid
        if best_uuid:
            bound_device_uuid = best_uuid
            bindings[charger_mac] = bound_device_uuid
            save_bindings(bindings)
            sessions[bound_device_uuid]["icharger_mac"] = charger_mac
            save_sessions(sessions)
            logger.info(
                "[BIND] Auto-paired charger %s -> device %s",
                charger_mac, bound_device_uuid)

    if not bound_device_uuid:
        return

    session = sessions.get(bound_device_uuid, {})
    device_topic = f"/s2c/{bound_device_uuid}"

    # 3a: Bind event to controller device
    bind_msg = {
        "uuid": bound_device_uuid,
        "msg_id": config.generate_msg_id(),
        "event": "ipad/icharger/bind",
        "data": {
            "id": session.get("id", 0),
            "max_battery": 100,
            "wifi_name": data.get("wifi_name", ""),
            "icharger_mac": charger_mac,
            "battery": 0,
            "charging_switch": 1,
            "firmware": data.get("firmware", ""),
            "created_at": int(time.time()),
            "suffix": "",
        }
    }
    client.publish(device_topic, json.dumps(bind_msg), qos=1)

    # 3b: Get config event to controller device
    config_msg = {
        "uuid": bound_device_uuid,
        "msg_id": config.generate_msg_id(),
        "event": "ipad/icharger/get_config",
        "data": {
            "bind_status": 1,
            "polling": 15,
            "battery": 0,
            "charging_switch": 1,
        }
    }
    client.publish(device_topic, json.dumps(config_msg), qos=1)
    logger.info(
        "[TX] Notified device %s of charger bind (%s)",
        bound_device_uuid, charger_mac)


def _handle_set_info(device_uuid, data):
    """Persist a charger reading from a set_info event."""
    mac = data.get("mac")
    voltage = data.get("voltage")
    current = data.get("current")
    if mac is None or voltage is None or current is None:
        return
    reading_id = config.generate_msg_id()
    add_time = int(time.time())
    save_charger_reading(mac, voltage, current, reading_id, add_time)
