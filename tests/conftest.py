"""Shared fixtures for iCharGuard integration tests.

Provides:
- A Mosquitto MQTT broker running in Docker via Testcontainers (session-scoped)
- An API server instance per test with isolated state (function-scoped)
- An MQTT message collector for verifying published messages (function-scoped)
- A router subprocess for MQTT event handling tests (function-scoped)
"""
import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
from testcontainers.core.container import DockerContainer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MOSQUITTO_CONF = os.path.join(TESTS_DIR, "mosquitto.conf")

# Ensure PROJECT_ROOT is on sys.path so `from src.db import ...` works
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _import_api_module():
    """Import icharguard-api.py using importlib (hyphenated filename can't use regular import)."""
    spec = importlib.util.spec_from_file_location(
        "icharguard_api",
        os.path.join(PROJECT_ROOT, "icharguard-api.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wait_for_port(host, port, timeout=30):
    """Wait until a TCP port is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except (socket.error, OSError):
            time.sleep(0.3)
    raise TimeoutError(f"Port {host}:{port} not ready after {timeout}s")


@pytest.fixture(scope="session")
def mosquitto():
    """Start a Mosquitto MQTT broker in Docker via Testcontainers.

    Session-scoped: one broker is shared across all tests for speed.
    The broker allows anonymous connections so any client can connect.
    """
    container = (
        DockerContainer("eclipse-mosquitto:2")
        .with_exposed_ports(1883, 9001)
        .with_volume_mapping(MOSQUITTO_CONF, "/mosquitto/config/mosquitto.conf", "ro")
    )
    container.start()

    host = container.get_container_host_ip()
    mqtt_port = int(container.get_exposed_port(1883))
    ws_port = int(container.get_exposed_port(9001))
    _wait_for_port(host, mqtt_port)

    yield {"host": host, "mqtt_port": mqtt_port, "ws_port": ws_port}

    container.stop()


@pytest.fixture
def api_server(mosquitto, tmp_path):
    """Start an API server instance with isolated test state.

    Each test gets a fresh module import with patched config pointing
    to a temp SQLite database, ensuring full isolation between tests.
    """
    from src.db import init_db, set_db_path

    mod = _import_api_module()
    cfg = mod.config

    # Set up isolated SQLite database for this test
    db_path = str(tmp_path / "test.db")
    cfg.DB_FILE = db_path
    set_db_path(db_path)
    init_db(db_path)

    # Patch file paths for photos and logs (still filesystem-based)
    cfg.PHOTOS_DIR = str(tmp_path / "photos")
    cfg.PHOTOS_AI_DIR = str(tmp_path / "photos_with_ai")
    cfg.PHOTOS_TEMP_DIR = str(tmp_path / "photos_temp")
    cfg.LOGS_DIR = str(tmp_path / "logs")
    cfg.WEBAPP_DIR = str(tmp_path / "webapp")

    # Patch MQTT connection settings to use test broker
    cfg.MQTT_BROKER_HOST = mosquitto["host"]
    cfg.MQTT_BROKER_PORT = mosquitto["mqtt_port"]
    cfg.MOSQUITTO_WS_HOST = mosquitto["host"]
    cfg.MOSQUITTO_WS_PORT = mosquitto["ws_port"]

    # Don't proxy weather/city to the cloud in tests
    cfg.QWEATHER_KEY = ""

    # Create required directories
    os.makedirs(str(tmp_path / "photos"), exist_ok=True)
    os.makedirs(str(tmp_path / "photos_with_ai"), exist_ok=True)
    os.makedirs(str(tmp_path / "photos_temp"), exist_ok=True)

    # Reset pending uploads tracking between tests
    with cfg.pending_uploads_lock:
        cfg.pending_uploads.clear()

    # Start HTTP server on a random available port
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod.APIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "url": f"http://127.0.0.1:{port}",
        "module": mod,
        "tmp_path": tmp_path,
        "mosquitto": mosquitto,
    }

    server.shutdown()


class MQTTCollector:
    """MQTT client that subscribes to topics and collects received messages.

    Used in tests to verify that API endpoints publish the correct MQTT events.
    """

    def __init__(self, host, port):
        self.messages = []
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"test_collector_{uuid.uuid4().hex[:8]}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.loop_start()
        if not self._connected.wait(timeout=5):
            raise TimeoutError("MQTT collector failed to connect")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self._connected.set()

    def _on_message(self, client, userdata, msg, properties=None):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload
        with self._lock:
            self.messages.append({"topic": msg.topic, "payload": payload})

    def subscribe(self, topic, qos=1):
        self.client.subscribe(topic, qos=qos)
        time.sleep(0.2)  # Allow broker to process subscription

    def wait_for_messages(self, count=1, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if len(self.messages) >= count:
                    return list(self.messages)
            time.sleep(0.05)
        with self._lock:
            return list(self.messages)

    def clear(self):
        with self._lock:
            self.messages.clear()

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


@pytest.fixture
def mqtt_collector(mosquitto):
    """An MQTT message collector for verifying published messages."""
    collector = MQTTCollector(mosquitto["host"], mosquitto["mqtt_port"])
    yield collector
    collector.close()


def _copy_router_script(tmp_path):
    """Copy icharguard-router.py into tmp_path so its SCRIPT_DIR (derived
    from __file__) resolves to tmp_path — that puts the SQLite database in
    the test's isolated temp directory automatically.
    """
    original = os.path.join(PROJECT_ROOT, "icharguard-router.py")
    with open(original) as f:
        source = f.read()
    copied = str(tmp_path / "icharguard-router.py")
    with open(copied, "w") as f:
        f.write(source)
    return copied


@pytest.fixture
def router(mosquitto, tmp_path):
    """Start the router as a subprocess connected to the test broker.

    Runs in headless mode. Waits for the router to connect and subscribe
    before yielding.
    """
    script = _copy_router_script(tmp_path)
    # The copied script runs from tmp_path but needs to import src.router
    # from the project root, so add it to PYTHONPATH for the subprocess.
    # Broker settings are passed via env vars (the script reads them from
    # os.environ) so the subprocess talks to the test container, not any
    # mosquitto that happens to be running on localhost:1883.
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env["BROKER_HOST"] = mosquitto["host"]
    env["BROKER_PORT"] = str(mosquitto["mqtt_port"])
    env["BROKER_WS_PORT"] = str(mosquitto["ws_port"])

    proc = subprocess.Popen(
        [sys.executable, "-u", script, "--headless"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )

    # Wait for both MQTT clients (TCP + WebSocket) to connect and subscribe
    subscriptions_seen = 0
    deadline = time.time() + 15
    while time.time() < deadline:
        line = proc.stdout.readline().decode().strip()
        if "Subscribed to" in line:
            subscriptions_seen += 1
            if subscriptions_seen >= 2:
                break
        if proc.poll() is not None:
            output = proc.stdout.read().decode()
            raise RuntimeError(f"Router exited unexpectedly:\n{output}")
    else:
        proc.terminate()
        raise TimeoutError("Router did not connect within 15 seconds")

    yield {"process": proc, "tmp_path": tmp_path}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
