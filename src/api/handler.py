"""Main API request handler and server entry point."""

import argparse
import http.server
import json
import logging
import mimetypes
import os
import signal
import ssl
import threading
from urllib.parse import urlparse, parse_qs

from src.api import activity, config
from src.db import init_db
from src.logging_setup import configure_access_log, configure_logging
from src.api.persistence import (
    load_bindings, load_calendars, load_devices, load_sessions,
)
from src.api.handlers.admin import AdminMixin
from src.api.handlers.auth import AuthMixin
from src.api.handlers.device_endpoints import DeviceEndpointsMixin
from src.api.handlers.settings import SettingsMixin
from src.api.handlers.weather import WeatherMixin
from src.api.handlers.calendar_endpoints import CalendarMixin
from src.api.handlers.media import MediaMixin
from src.api.handlers.download import DownloadMixin
from src.api.handlers.logs import LogsMixin
from src.api.handlers.websocket import WebSocketMixin

logger = logging.getLogger(__name__)


class APIHandler(
    AdminMixin,
    AuthMixin,
    DeviceEndpointsMixin,
    SettingsMixin,
    WeatherMixin,
    CalendarMixin,
    MediaMixin,
    DownloadMixin,
    LogsMixin,
    WebSocketMixin,
    http.server.BaseHTTPRequestHandler,
):
    # Set by main() after configure_access_log(); falls back to a stdout
    # logger so tests that import the module without going through main()
    # still get sensible behaviour.
    access_logger = logging.getLogger("access")

    def log_message(self, format, *args):
        # BaseHTTPRequestHandler's request log already wraps the request
        # line in quotes (its default format is '"%s" %s %s'), so don't
        # add extra quoting here.
        self.access_logger.info(
            "%s %s", self.address_string(), format % args)

    def handle_unimplemented(self, method, body=None):
        body_str = f" body={body}" if body else ""
        logger.info("[UNHANDLED %s] %s%s", method, self.path, body_str)
        self.respond_success({})

    def do_PUT(self):
        body = self.read_body()
        self.handle_unimplemented("PUT", body)

    def do_DELETE(self):
        self.handle_unimplemented("DELETE")

    def do_PATCH(self):
        body = self.read_body()
        self.handle_unimplemented("PATCH", body)

    def do_HEAD(self):
        self.handle_unimplemented("HEAD")

    def do_OPTIONS(self):
        self.handle_unimplemented("OPTIONS")

    def respond_success(self, data):
        """Send a successful JSON response matching the real server format."""
        self.respond_json({"code": 1, "msg": "SUCCESS", "data": data})

    def respond_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def respond_file(self, file_path, cache_control=None):
        """Serve a static file from the webapp directory."""
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            # For index.html, serve placeholder file if webapp assets have not yet been downloaded using fetch-webapp-assets.py script
            if os.path.basename(file_path) == "index.html" or os.path.basename(file_path) == config.INDEX_HTML_FILE:
                self.respond_file(os.path.join(config.WEBAPP_DIR, "index.placeholder.html"))
                return
            self.send_error(404, "File not found")
            return

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        elif os.path.basename(file_path) == "index.html" or os.path.basename(file_path) == config.INDEX_HTML_FILE:
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(content)

    def _track_device_activity(self):
        """Attribute this request to its device for presence tracking.

        Native apps send their identity in the XX-Device-Uuid header on every
        request. Best-effort and fully defensive — never break request
        handling over activity tracking.
        """
        try:
            device_uuid = self.headers.get("XX-Device-Uuid")
            if device_uuid:
                activity.record_activity(device_uuid)
        except Exception:  # noqa: BLE001
            pass

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}

    # --- POST routing ---

    def do_POST(self):
        self._track_device_activity()
        path = urlparse(self.path).path

        # Asset upload uses multipart/form-data — read_body() would consume
        # the binary data and fail on JSON parsing, so handle it before
        # reading the body as JSON.
        if path == "/api/user/asset/upload":
            self.handle_asset_upload()
            return

        # New upload endpoint introduced in iFramix Pro app 2.2.29 (bypasses
        # the Qiniu token dance; the app POSTs the file directly here).
        if path == "/api/user/asset/uploader":
            self.handle_asset_uploader()
            return

        # Qiniu SDK uploads to POST / on the upload domain.  With DNS
        # redirected, that lands here.
        if path == "/" and "multipart/form-data" in self.headers.get(
                "Content-Type", ""):
            self.handle_asset_upload()
            return

        if path == "/admin/toggle":
            self.handle_admin_toggle()
            return

        if path == "/admin/set-mode":
            self.handle_admin_set_mode()
            return

        body = self.read_body()

        if path == "/api/user/public/login":
            self.handle_login(body)
        elif path == "/api/webhook/auth":
            self.handle_webhook_auth(body)
        elif path == "/api/ipad/device/refersh-battery":
            self.handle_battery(body)
        elif path == "/api/ipad/device/bindUser":
            self.handle_bind_user(body)
        elif path == "/api/ipad/device/unbindUser":
            self.handle_unbind_user(body)
        elif path == "/api/ipad/device/list":
            self.handle_device_list(body)
        elif path == "/api/ipad/device/update":
            self.handle_device_update(body)
        elif path == "/api/ipad/icharger/unbind":
            self.handle_unbind(body)
        elif path == "/api/ipad/device/setting/screensaver":
            self.handle_screensaver_update(body)
        elif path == "/api/ipad/device/setting/address":
            self.handle_address_update(body)
        elif path == "/api/ipad/device/setting/weather":
            self.handle_weather_update(body)
        elif path == "/api/ipad/device/setting/display":
            self.handle_display_update(body)
        elif path == "/api/ipad/device/setting/playback":
            self.handle_playback_update(body)
        elif path == "/api/ipad/device/setting/ai_albums":
            self.handle_ai_albums_update(body)
        elif path == "/api/calendar/external/link":
            self.handle_calendar_link(body)
        elif path == "/api/calendar/update":
            self.handle_calendar_update(body)
        elif path == "/api/calendar/delete":
            self.handle_calendar_delete(body)
        elif path == "/api/calendar/event/create":
            self.handle_calendar_event_create(body)
        elif path == "/api/calendar/event/update":
            self.handle_calendar_event_update(body)
        elif path == "/api/calendar/event/delete":
            self.handle_calendar_event_delete(body)
        elif path == "/api/calendar/synchronize":
            self.handle_calendar_synchronize(body)
        elif path == "/api/calendar/device-synchronize":
            self.handle_calendar_sync(body)
        elif path == "/api/user/asset/token":
            self.handle_asset_token(body)
        elif path == "/api/ipad/media/setMedia":
            self.handle_set_media(body)
        elif path == "/api/ipad/media/delMedia":
            self.handle_del_media(body)
        elif path == "/api/ipad/media/update":
            self.handle_media_update(body)
        elif path == "/api/user/asset/compress/uploader":
            self.handle_compress_uploader(body)
        elif path == "/api/user/log/create":
            self.handle_log_create(body)
        elif path in ("/api/user/public/logout",
                       "/api/user/public/register",
                       "/api/user/public/passwordReset",
                       "/api/ipad/media/ai/refersh",
                       "/api/user/verificationCode/send"):
            self.respond_success(True)
        else:
            self.handle_unimplemented("POST", body)

    # --- GET routing ---

    def do_GET(self):
        self._track_device_activity()
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # WebSocket upgrade (App 2.2.x) -> proxy to Mosquitto's WebSocket listener
        if (path == "/websocket"
                and self.headers.get("Upgrade", "").lower() == "websocket"):
            self.handle_websocket_proxy()
            return

        # WebSocket upgrade (Legacy app up until 2.1.x) -> proxy to Mosquitto's WebSocket listener
        if (path == "/mqtt"
                and self.headers.get("Upgrade", "").lower() == "websocket"):
            self.handle_websocket_proxy()
            return

        # Admin panel
        if path == "/admin":
            self.handle_admin_page()
            return

        if path == "/admin/chargers":
            self.handle_admin_chargers()
            return

        if path == "/admin/devices":
            self.handle_admin_device_status()
            return

        if path == "/admin/photos":
            self.handle_admin_photos(params)
            return

        if path.startswith("/admin/thumb/"):
            self.handle_admin_thumb(path)
            return

        if path.startswith("/admin/assets/"):
            self.handle_admin_asset(path)
            return

        # API endpoints
        if path == "/api/ipad/device/index":
            self.handle_device_index(params)
        elif path == "/api/ipad/device/info":
            device_id = params.get("id", [None])[0]
            self.handle_device_info(device_id)
        elif path == "/api/ipad/icharger2/index":
            mac = params.get("mac", [None])[0]
            self.handle_icharger_index(mac, params)
        elif path == "/api/ipad/media/mediaList":
            self.handle_media_list(params)
        elif path == "/api/calendar/index":
            self.handle_calendar_index(params)
        elif path == "/api/calendar/events":
            self.handle_calendar_events(params)
        elif path == "/api/ipad/device/setting/weather":
            self.handle_weather_setting(params)
        elif path == "/api/ipad/device/setting/screensaver":
            self.handle_screensaver_setting(params)
        elif path == "/api/ipad/device/setting/display":
            self.handle_display_setting(params)
        elif path == "/api/ipad/device/setting/playback":
            self.handle_playback_setting(params)
        elif path == "/api/ipad/device/setting/ai_albums":
            self.handle_ai_albums_setting(params)
        elif path == "/api/ipad/device/setting/address":
            self.respond_success([])
        elif path == "/api/ipad/weather/weather":
            self.handle_weather_forecast(params)
        elif path == "/api/ipad/address/city":
            self.handle_city_search(params)
        elif path == "/api/user/verificationCode/push/email":
            self.respond_success(True)
        elif path == "/api/user/verificationCode/push/image":
            self.respond_success("")
        elif path == "/project/api/captcha/package/project":
            self.handle_package_project(params)
        # Qiniu SDK region lookup (api.qiniu.com DNS redirected here)
        elif path == "/v4/query":
            self.handle_qiniu_query(params)
        elif path.startswith("/api/"):
            self.handle_unimplemented("GET")
        # Static files / webapp
        elif path == "/" or path == "/index.html" or path == config.INDEX_HTML_FILE:
            self.respond_file(
                os.path.join(config.WEBAPP_DIR, config.INDEX_HTML_FILE))
        elif path.startswith("/static/"):
            safe_path = os.path.normpath(path.lstrip("/"))
            file_path = os.path.join(config.WEBAPP_DIR, safe_path)
            if not file_path.startswith(config.WEBAPP_DIR):
                self.send_error(403, "Forbidden")
                return
            self.respond_file(file_path)
        elif path == "/download":
            self.send_response(301)
            self.send_header("Location", "/download/")
            self.end_headers()
        elif path in ("/download/", "/download/#/index"):
            self.respond_file(
                os.path.join(config.WEBAPP_DIR, "download", "index.html"))
        elif path.startswith("/download/"):
            safe_path = os.path.normpath(path.lstrip("/"))
            file_path = os.path.join(config.WEBAPP_DIR, safe_path)
            if not file_path.startswith(config.WEBAPP_DIR):
                self.send_error(403, "Forbidden")
                return
            self.respond_file(file_path)
        elif path == "/pad1":
            self.send_response(301)
            self.send_header("Location", "/pad1/")
            self.end_headers()
        elif path == "/pad1/":
            self.respond_file(
                os.path.join(config.WEBAPP_DIR, "pad1", "index.html"))
        elif path.startswith("/pad1/"):
            safe_path = os.path.normpath(path.lstrip("/"))
            file_path = os.path.join(config.WEBAPP_DIR, safe_path)
            if not file_path.startswith(config.WEBAPP_DIR):
                self.send_error(403, "Forbidden")
                return
            self.respond_file(file_path)
        elif (path.startswith("/photos/")
              or path.startswith("/photos_with_ai/")):
            self.handle_photo_serve(path)
        elif path.startswith("/photos_compressed/"):
            self.handle_compressed_photo_serve(path)
        elif path.startswith("/weather_icons/"):
            self.handle_weather_icon_serve(path)
        else:
            self.send_error(404, "Not found")


def main():
    parser = argparse.ArgumentParser(description="iCharGuard API Server")
    parser.add_argument("--port", type=int, default=443,
                        help="Port to listen on (default: 443)")
    parser.add_argument("--no-ssl", action="store_true",
                        help="Disable HTTPS (use plain HTTP, for testing)")
    parser.add_argument("--cert",
                        default=os.path.join(config.SCRIPT_DIR, "server.crt"),
                        help="Path to SSL certificate (default: server.crt)")
    parser.add_argument("--key",
                        default=os.path.join(config.SCRIPT_DIR, "server.key"),
                        help="Path to SSL private key (default: server.key)")
    parser.add_argument("--mosquitto-ws-port", type=int, default=9001,
                        help="Mosquitto WebSocket listener port (default: 9001)")
    parser.add_argument("--webapp-version", default="",
                        help="Use a custom version for the webapp resources")
    parser.add_argument("--log-file", default=None,
                        help="Write INFO/DEBUG output to this file instead of stdout")
    parser.add_argument("--error-log-file", default=None,
                        help="Write WARNING/ERROR output to this file instead of stderr")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Minimum log level to emit (default: INFO). "
                             "DEBUG additionally enables MQTT traffic logging.")
    parser.add_argument("--access-log-file", default=None,
                        help="Write per-request HTTP access logs to this file. "
                             "Default: stdout (mixed with other INFO output).")
    args = parser.parse_args()

    configure_logging(args.log_file, args.error_log_file, args.log_level)
    APIHandler.access_logger = configure_access_log(args.access_log_file)

    config.MOSQUITTO_WS_PORT = args.mosquitto_ws_port
    config.INDEX_HTML_FILE = f"index-{args.webapp_version}.html" if args.webapp_version else "index.html"

    # Initialize SQLite database
    init_db(config.DB_FILE)

    server = http.server.ThreadingHTTPServer(
        ("0.0.0.0", args.port), APIHandler)

    if not args.no_ssl:
        if not os.path.exists(args.cert) or not os.path.exists(args.key):
            logger.error(
                "SSL certificate not found (%s, %s). Generate one with:\n"
                "  openssl req -x509 -newkey rsa:2048 -keyout server.key "
                "-out server.crt -days 365 -nodes "
                "-subj '/CN=ifp.ga.codethriving.com' "
                "-addext 'subjectAltName=DNS:ifp.ga.codethriving.com,"
                "DNS:api.qiniu.com,DNS:upload-z2.qiniup.com,"
                "DNS:up-z2.qiniup.com,DNS:iframixcn.codethriving.com'\n"
                "Or run with --no-ssl for testing.",
                args.cert, args.key)
            return
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.cert, args.key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        proto = "HTTPS"
    else:
        proto = "HTTP"

    devices = load_devices()
    sessions = load_sessions()
    bindings = load_bindings()
    calendars = load_calendars()
    webapp_available = os.path.isdir(config.WEBAPP_DIR) and os.path.isfile(
        os.path.join(config.WEBAPP_DIR, config.INDEX_HTML_FILE))
    logger.info("iCharGuard API Server (%s on port %s)", proto, args.port)
    logger.info("Database: %s", config.DB_FILE)
    logger.info(
        "Loaded %d charger(s), %d session(s), %d binding(s), %d calendar(s)",
        len(devices), len(sessions), len(bindings), len(calendars))
    if args.webapp_version:
        logger.info("Webapp version: %s", args.webapp_version)
    else:
        logger.info("Webapp version: default")
    if webapp_available:
        logger.info("Serving webapp from %s", config.WEBAPP_DIR)
    else:
        logger.info(
            "Webapp not found at %s (API-only mode)", config.WEBAPP_DIR)
    logger.info(
        "WebSocket proxy: /websocket -> Mosquitto WS on port %s",
        config.MOSQUITTO_WS_PORT)
    logger.info(
        "Weather: forecast via Open-Meteo (per-device city, 30-min cache)")
    logger.info("Waiting for app connections...")
    logger.info("Ready at %s://localhost:%s", proto.lower(), args.port)
    logger.info("Admin panel ready at %s://localhost:%s/admin", proto.lower(), args.port)

    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    shutdown.wait()
    server.shutdown()
    logger.info("Shutting down.")
