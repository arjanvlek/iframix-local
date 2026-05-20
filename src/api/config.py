"""Global configuration constants, file paths, and shared state."""

import os
import threading

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.path.join(SCRIPT_DIR, "icharguard.db")
PHOTOS_DIR = os.path.join(SCRIPT_DIR, "photos")
PHOTOS_AI_DIR = os.path.join(SCRIPT_DIR, "photos_with_ai")
PHOTOS_TEMP_DIR = os.path.join(SCRIPT_DIR, "photos_temp")
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
WEBAPP_DIR = os.path.join(SCRIPT_DIR, "webapp")
WEATHER_ICONS_DIR = os.path.join(SCRIPT_DIR, "weather_icons")
MOSQUITTO_WS_HOST = "localhost"
MOSQUITTO_WS_PORT = 9001
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_USER = "iframix_local_api"
MQTT_PASS = "notvalidated"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
INDEX_HTML_FILE = "index.html"

# Tracks pending uploads: asset_id (str) -> filename (str)
# Populated by handle_asset_upload(), consumed by handle_set_media()
# This is in-memory state, not persisted to the database.
pending_uploads = {}
pending_uploads_lock = threading.Lock()
