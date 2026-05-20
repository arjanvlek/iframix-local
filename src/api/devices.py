"""Functions that build API device records from internal data structures."""

import time

from src.api.persistence import load_bindings
from src.api.utils import build_id_map


def find_charger_for_session(session, devices):
    """Look up charger info from devices.json for a session's bound charger MAC."""
    mac = session.get("icharger_mac")
    if not mac:
        # Fall back to bindings.json (reverse lookup by device UUID)
        bindings = load_bindings()
        for bound_mac, bound_uuid in bindings.items():
            if bound_uuid == session.get("uuid"):
                mac = bound_mac
                break
    if not mac:
        return []
    id_map = build_id_map(devices)
    uuid_to_id = {v: k for k, v in id_map.items()}
    for device_uuid, info in devices.items():
        if device_uuid.startswith("_"):
            continue
        if info.get("mac") == mac:
            device_id = uuid_to_id.get(device_uuid, 0)
            last_seen = int(info.get("last_seen", time.time()))
            return {
                "id": device_id,
                "max_battery": 100,
                "wifi_name": info.get("wifi_name", ""),
                "icharger_mac": mac,
                "battery": info.get("battery", "0.00"),
                "charging_switch":
                    info.get("charging_switch")
                    if info.get("charging_switch") is not None else 1,
                "firmware": info.get("firmware", ""),
                "created_at": last_seen,
                "suffix": "",
            }
    return []


def session_to_device_record(session, devices):
    """Build an API device record from a persistent session."""
    icharger = find_charger_for_session(session, devices)
    now = int(time.time())
    created_at = session.get("created_at",
                             time.strftime("%Y-%m-%d %H:%M:%S"))
    bind_at = session.get("bind_at", now)
    return {
        "id": session["id"],
        "uuid": session["uuid"],
        "device_name": session.get("device_name", "Device"),
        "device_type": session.get("device_type", "ios"),
        "is_ipad": session.get("is_ipad", 0),
        "is_h5": session.get("is_h5", 0),
        "ios_version": session.get("ios_version", ""),
        "width": session.get("width", 0),
        "height": session.get("height", 0),
        "user_id": session.get("user_id", 1),
        "bind_at": bind_at,
        "created_at": created_at,
        "deleted_at": None,
        "is_online": 1 if (now - session.get("last_login", 0)) < 300 else 0,
        "online": {
            "start_connected_at": session.get("last_login", bind_at),
            "last_disconnected_at": 0,
        },
        "icharger": icharger,
        "user": session.get("user", "local@icharguard"),
    }


def device_to_list_record(device_uuid, info, device_id):
    """Convert internal device info to the format returned by /api/ipad/device/list."""
    last_seen = int(info.get("last_seen", time.time()))
    mac = info.get("mac", "")
    icharger = {"id": device_id, "mac": mac} if mac and mac != "?" else None
    return {
        "id": device_id,
        "uuid": device_uuid,
        "device_name": info.get("wifi_name", "iCharGuard"),
        "device_type": "ios",
        "is_ipad": 0,
        "is_h5": 0,
        "ios_version": "",
        "width": 0,
        "height": 0,
        "user_id": 1,
        "bind_at": last_seen,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_seen)),
        "deleted_at": None,
        "is_online": 1 if (time.time() - last_seen) < 120 else 0,
        "online": {
            "start_connected_at": last_seen,
            "last_disconnected_at": 0,
        },
        "icharger": icharger,
    }


def device_to_info_record(device_uuid, info, device_id):
    """Convert internal device info to the format returned by /api/ipad/device/info."""
    last_seen = int(info.get("last_seen", time.time()))
    mac = info.get("mac", "")
    icharger = {"id": device_id, "mac": mac} if mac and mac != "?" else []
    return {
        "id": device_id,
        "uuid": device_uuid,
        "device_name": info.get("wifi_name", "iCharGuard"),
        "device_type": "ios",
        "is_ipad": 0,
        "is_h5": 0,
        "ios_version": "",
        "width": 0,
        "height": 0,
        "user_id": 1,
        "bind_at": last_seen,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_seen)),
        "deleted_at": None,
        "is_online": 1 if (time.time() - last_seen) < 120 else 0,
        "icharger": icharger,
        "user": "local@icharguard",
    }


def session_to_index_record(session, devices, bindings):
    """Build a device record for /api/ipad/device/index from a session.

    The icharger field is a simple {id, mac} dict or None, determined by
    looking up the session's bound charger MAC in bindings and devices.
    """
    now = int(time.time())
    created_at = session.get("created_at",
                             time.strftime("%Y-%m-%d %H:%M:%S"))
    bind_at = session.get("bind_at", now)

    # Find bound charger via session's icharger_mac
    icharger = None
    mac = session.get("icharger_mac")
    if not mac:
        # Also check bindings (reverse lookup: find MAC bound to this device)
        for bound_mac, bound_device_uuid in bindings.items():
            if bound_device_uuid == session["uuid"]:
                mac = bound_mac
                break
    if mac:
        id_map = build_id_map(devices)
        uuid_to_id = {v: k for k, v in id_map.items()}
        for device_uuid, info in devices.items():
            if device_uuid.startswith("_"):
                continue
            if info.get("mac") == mac:
                charger_id = uuid_to_id.get(device_uuid, 0)
                icharger = {"id": charger_id, "mac": mac}
                break

    return {
        "id": session["id"],
        "uuid": session["uuid"],
        "device_name": session.get("device_name", "Device"),
        "device_type": session.get("device_type", "ios"),
        "is_ipad": session.get("is_ipad", 0),
        "is_h5": session.get("is_h5", 0),
        "ios_version": session.get("ios_version", ""),
        "width": session.get("width", 0),
        "height": session.get("height", 0),
        "user_id": session.get("user_id", 1),
        "bind_at": bind_at,
        "created_at": created_at,
        "deleted_at": None,
        "is_online": 1 if (now - session.get("last_login", 0)) < 300 else 0,
        "online": {
            "start_connected_at": session.get("last_login", bind_at),
            "last_disconnected_at": session.get("last_disconnected_at", 0),
        },
        "icharger": icharger,
    }
