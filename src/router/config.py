"""Global configuration constants and shared state for the MQTT router."""

import os
import random
import threading
import time

BROKER_HOST = "localhost"
BROKER_PORT = 1883
BROKER_WS_PORT = 9001
MQTT_USER = "iframix_local_router"
MQTT_PASS = "notvalidated"

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.path.join(SCRIPT_DIR, "icharguard.db")

# Device registry — maps device UUID -> latest known info (in-memory cache)
devices = {}
devices_lock = threading.Lock()


def generate_msg_id():
    """Generate a snowflake-style message ID (timestamp_ms << 22 | random)."""
    return (int(time.time() * 1000) << 22) | random.randint(0, (1 << 22) - 1)
