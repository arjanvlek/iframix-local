"""Interactive CLI functions for the router."""

import json
import time

from src.router import config
from src.router.persistence import load_devices


def reload_devices_from_disk():
    """Reload device registry from the database (for interactive mode)."""
    with config.devices_lock:
        config.devices.clear()
        load_devices()


def resolve_device(target):
    """Resolve a user-provided target to a device UUID.

    Accepts:
      - A full UUID like IFP_94_51_DC_64_3F_82_A8_80
      - A partial match (e.g. '3F82' matches on MAC/wifi_name/UUID)
      - A 1-based index number from the device list
      - None/empty -> returns the only device if exactly one exists
    """
    with config.devices_lock:
        if not config.devices:
            print("No devices discovered yet. Wait for a device to check in.")
            return None

        # If only one device and no target specified, use it
        if not target and len(config.devices) == 1:
            return next(iter(config.devices))

        if not target:
            print("Multiple devices found. Specify a target "
                  "(use 'list' to see them).")
            return None

        # Try as index number
        try:
            idx = int(target)
            uuids = sorted(config.devices.keys())
            if 1 <= idx <= len(uuids):
                return uuids[idx - 1]
        except ValueError:
            pass

        # Try exact UUID match
        if target in config.devices:
            return target

        # Try partial/substring match against UUID, MAC, and wifi_name
        matches = []
        for uid, info in config.devices.items():
            searchable = (f"{uid} {info.get('mac', '')} "
                          f"{info.get('wifi_name', '')}").lower()
            if target.lower() in searchable:
                matches.append(uid)

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            print(f"Ambiguous target '{target}' matches "
                  f"{len(matches)} devices. Be more specific.")
            return None
        else:
            print(f"No device matching '{target}'.")
            return None


def send_charging_command(client, device_uuid, charging_on, battery_limit=0):
    """Send a charging switch command to a specific device."""
    msg = {
        "msg_id": config.generate_msg_id(),
        "event": "ipad/icharger/charging_switch",
        "data": {
            "bind_status": 1,
            "polling": 15,
            "battery": battery_limit,
            "charging_switch": 1 if charging_on else 0
        }
    }
    topic = f"/mqtt/s2c/{device_uuid}"
    client.publish(topic, json.dumps(msg), qos=1)
    state = "ON" if charging_on else "OFF"
    limit_str = f", limit {battery_limit}%" if battery_limit else ""
    print(f"[CMD] Charging {state}{limit_str} → {device_uuid}")


def print_device_list():
    """Print all discovered devices."""
    with config.devices_lock:
        if not config.devices:
            print("No devices discovered yet.")
            return
        print(f"\n{'#':<4} {'UUID':<40} {'MAC':<20} {'WiFi':<12} "
              f"{'V':>6} {'A':>6} {'Bat':>5} {'Last seen'}")
        print("-" * 118)
        for i, (uid, info) in enumerate(
                sorted(config.devices.items()), 1):
            age = time.time() - info["last_seen"]
            if age < 60:
                ago = f"{int(age)}s ago"
            elif age < 3600:
                ago = f"{int(age/60)}m ago"
            elif age < 86400:
                ago = (f"{int(age/3600)}h "
                       f"{int(age%3600/60):02d}m ago")
            else:
                ago = (f"{int(age/86400)}d {int(age%86400/3600)}h "
                       f"{int(age%3600/60):02d}m ago")
            v = (f"{info['voltage']:.2f}"
                 if info.get("voltage") else "—")
            a = (f"{info['current']:.2f}"
                 if info.get("current") else "—")
            bat = (f"{info['battery']}%"
                   if info.get("battery") is not None else "—")
            print(f"{i:<4} {uid:<40} {info['mac']:<20} "
                  f"{info['wifi_name']:<12} {v:>6} {a:>6} "
                  f"{bat:>5} {ago}")
        print()


def print_help():
    print("""
Commands:
  list                    — Show all discovered iCharGuard devices
  on [target]             — Enable charging (no battery limit)
  off [target]            — Disable charging
  limit <N> [target]      — Enable charging with battery limit at N%
  quit                    — Exit

Target can be:
  - Omitted (works automatically when only one device is connected)
  - A device number from 'list' (e.g. 1, 2)
  - A partial match on UUID, MAC, or WiFi name (e.g. '3F82')
  - A full device UUID
""")
