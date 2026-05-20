"""Main entry point logic for the MQTT router."""

import argparse
import logging
import signal
import threading
import uuid

import paho.mqtt.client as mqtt

from src.db import init_db
from src.logging_setup import configure_logging
from src.router import config
from src.router.persistence import load_devices
from src.router.mqtt_handlers import on_connect, on_message
from src.router.cli import (
    print_device_list, print_help, reload_devices_from_disk,
    resolve_device, send_charging_command,
)

logger = logging.getLogger(__name__)


def run():
    parser = argparse.ArgumentParser(
        description="iCharGuard Local Router")
    parser.add_argument(
        "--headless", action="store_true",
        help="Run without interactive CLI "
             "(for use as a background service)")
    parser.add_argument(
        "--log-file", default=None,
        help="Write INFO/DEBUG output to this file instead of stdout")
    parser.add_argument(
        "--error-log-file", default=None,
        help="Write WARNING/ERROR output to this file instead of stderr")
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Minimum log level to emit (default: INFO). "
             "DEBUG additionally enables MQTT traffic logging.")
    args = parser.parse_args()
    configure_logging(args.log_file, args.error_log_file, args.log_level)
    interactive = not args.headless

    # Initialize SQLite database
    init_db(config.DB_FILE)

    load_devices()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"router_{uuid.uuid4().hex[:8]}",
        userdata={"interactive": interactive, "port": config.BROKER_PORT})
    client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=60)

    # WebSocket client for logging messages on port 9001
    ws_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"router_ws_{uuid.uuid4().hex[:8]}",
        transport="websockets",
        userdata={"interactive": interactive, "port": config.BROKER_WS_PORT})
    ws_client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
    ws_client.on_connect = on_connect
    ws_client.on_message = on_message
    ws_client.connect(config.BROKER_HOST, config.BROKER_WS_PORT, keepalive=60)

    if args.headless:
        _run_headless(client, ws_client)
    else:
        _run_interactive(client, ws_client)


def _run_headless(client, ws_client):
    logger.info("iCharGuard Local Router (headless mode)")
    shutdown = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    client.loop_start()
    ws_client.loop_start()
    shutdown.wait()
    ws_client.loop_stop()
    ws_client.disconnect()
    client.loop_stop()
    client.disconnect()
    logger.info("Disconnected.")


def _run_interactive(client, ws_client):
    import readline  # noqa: F401 — enables arrow-key history

    client.loop_start()
    ws_client.loop_start()
    print("iCharGuard Local CLI")
    print("Type 'help' for commands.\n")

    try:
        while True:
            raw = input("> ").strip()
            if not raw:
                continue
            parts = raw.split()
            cmd = parts[0].lower()

            if cmd == "help":
                print_help()

            elif cmd == "list":
                reload_devices_from_disk()
                print_device_list()

            elif cmd == "on":
                reload_devices_from_disk()
                target = parts[1] if len(parts) > 1 else None
                uid = resolve_device(target)
                if uid:
                    send_charging_command(client, uid, True, 0)

            elif cmd == "off":
                reload_devices_from_disk()
                target = parts[1] if len(parts) > 1 else None
                uid = resolve_device(target)
                if uid:
                    send_charging_command(client, uid, False, 0)

            elif cmd == "limit":
                if len(parts) < 2:
                    print("Usage: limit <percentage> [target]")
                    continue
                try:
                    pct = int(parts[1])
                except ValueError:
                    print("Usage: limit <percentage> [target]")
                    continue
                reload_devices_from_disk()
                target = parts[2] if len(parts) > 2 else None
                uid = resolve_device(target)
                if uid:
                    send_charging_command(client, uid, True, pct)

            elif cmd == "quit":
                break

            else:
                print("Unknown command. Type 'help' for usage.")

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        ws_client.loop_stop()
        ws_client.disconnect()
        client.loop_stop()
        client.disconnect()
        print("\nDisconnected.")
