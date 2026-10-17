"""``AdminMixin``: the HTTP handlers behind ``/admin/*``."""

import html as _html
import logging

from src.api.handlers.admin.charger_rows import build_charger_rows
from src.api.handlers.admin.device_nav import build_device_nav
from src.api.handlers.admin.device_views import build_device_views
from src.api.handlers.admin.display import (
    real_sessions, served_webapp_version,
)
from src.api.handlers.admin.page_template import (
    ADMIN_HTML_TEMPLATE, STATIC_CONTENT_TYPES, STATIC_DIR,
)
from src.api.handlers.admin.presence import (
    charger_is_online, fmt_ago, is_online,
)
from src.api.persistence import (
    load_devices, load_sessions, update_device_fields,
)
from src.api.utils import publish_charging_switch

logger = logging.getLogger(__name__)


class AdminMixin:

    def handle_admin_page(self):
        """Serve the admin control page.

        This page is a local-only addition to the offline controller. It
        is not part of the original iFramix Pro cloud API.  It combines
        charger on/off control with per-display-device settings panels
        that call the same REST endpoints as the native controller app.
        """
        devices = load_devices()
        sessions = load_sessions()
        display_sessions = real_sessions(sessions)
        chargers = [(uuid, info) for uuid, info in devices.items()
                    if not uuid.startswith("_")]
        charger_count = len(chargers)
        charger_online = sum(
            1 for _, info in chargers if charger_is_online(info))
        online = sum(1 for s in display_sessions if is_online(s))

        html_body = (
            ADMIN_HTML_TEMPLATE
            .replace("__ADMIN_ROWS__", build_charger_rows(devices))
            .replace("__ADMIN_NAV__", build_device_nav(sessions))
            .replace("__ADMIN_DEVICE_VIEWS__",
                     build_device_views(sessions))
            .replace("__CHARGER_COUNT__",
                     f"{charger_online}/{charger_count}")
            .replace("__ONLINE_COUNT__",
                     f"{online}/{len(display_sessions)}")
            .replace("__WEBAPP_VERSION__",
                     _html.escape(served_webapp_version(), quote=True))
        )

        body = html_body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def handle_admin_chargers(self):
        """Return just the chargers table body HTML.

        The admin page polls this every 10s to refresh charger rows in
        place, leaving the rest of the page (open device panels,
        in-flight forms) untouched.
        """
        rows = build_charger_rows(load_devices())
        body = rows.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def handle_admin_device_status(self):
        """Return display-device presence as JSON.

        Polled by the admin page every 10s (alongside the chargers
        fragment) so the sidebar online dots, the online counter, and
        each detail view's Online/Offline chip + "seen ..." tag stay
        current without a page reload.
        """
        display_sessions = real_sessions(load_sessions())
        devices = [{
            "id": sess.get("id", 0),
            "online": is_online(sess),
            "seen": fmt_ago(max(sess.get("last_login") or 0,
                                 sess.get("last_active") or 0)),
        } for sess in display_sessions]
        self.respond_success({
            "online": sum(1 for d in devices if d["online"]),
            "total": len(devices),
            "devices": devices,
        })

    def handle_admin_asset(self, path):
        """Serve a static admin asset (style screenshots, fonts).

        Files live in ``assets/static/`` and are addressed as
        ``/admin/assets/{relpath}``.  Only known extensions are served
        and the resolved path must stay inside the static directory.
        """
        rel = path[len("/admin/assets/"):]
        target = (STATIC_DIR / rel).resolve()
        content_type = STATIC_CONTENT_TYPES.get(target.suffix)
        if (content_type is None
                or not str(target).startswith(str(STATIC_DIR.resolve()))
                or not target.is_file()):
            self.respond_json(
                {"code": 0, "msg": "not found"}, status=404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.send_header(
            "Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(body)

    def handle_admin_toggle(self):
        """Toggle charging on/off for a charger via MQTT."""
        body = self.read_body()
        uuid = body.get("uuid")
        charging_on = body.get("charging_on")

        if not uuid or charging_on is None:
            self.respond_json(
                {"code": 0, "msg": "missing uuid or charging_on"}, status=400)
            return

        devices = load_devices()
        if uuid not in devices:
            self.respond_json(
                {"code": 0, "msg": "unknown device"}, status=404)
            return

        if devices[uuid].get("mode") == "auto":
            self.respond_json(
                {"code": 0, "msg": "charger is in auto mode"}, status=409)
            return

        try:
            publish_charging_switch(uuid, charging_on)
        except Exception as e:
            logger.exception("[ADMIN] MQTT publish failed")
            self.respond_json(
                {"code": 0, "msg": f"MQTT error: {e}"}, status=500)
            return

        # Record the admin's Power-button click in its own column.
        # `charging_switch` stays the controller app's wish; only
        # `admin_switch` drives the manual-mode button label and the
        # "pending" badge (compared against charging_switch_reported).
        # The charger's actual state lands in charging_switch_reported
        # via the router (derived from the current in the next set_info).
        update_device_fields(
            uuid, admin_switch=1 if charging_on else 0)

        state = "ON" if charging_on else "OFF"
        mac = devices[uuid].get("mac", "?")
        logger.info("[ADMIN] Charging %s -> %s (%s)", state, uuid, mac)
        self.respond_success({"admin_switch": 1 if charging_on else 0})

    def handle_admin_set_mode(self):
        """Switch a charger between manual and auto mode.

        When switching into auto, also push the currently stored desired
        charging_switch to the charger (if any) so the physical state
        syncs immediately rather than waiting for the next
        refersh-battery call from the app.
        """
        body = self.read_body()
        uuid = body.get("uuid")
        mode = body.get("mode")

        if not uuid or mode not in ("auto", "manual"):
            self.respond_json(
                {"code": 0, "msg": "missing uuid or invalid mode"},
                status=400)
            return

        devices = load_devices()
        if uuid not in devices:
            self.respond_json(
                {"code": 0, "msg": "unknown device"}, status=404)
            return

        # Reset the admin command on a mode switch so a stale click from
        # a previous session can't drive the button label / pending badge.
        update_device_fields(uuid, mode=mode, admin_switch=None)

        mac = devices[uuid].get("mac", "?")
        logger.info("[ADMIN] Mode %s -> %s (%s)", mode.upper(), uuid, mac)

        if mode == "auto":
            desired = devices[uuid].get("charging_switch")
            if desired is not None:
                try:
                    publish_charging_switch(uuid, int(desired))
                except Exception:
                    logger.exception(
                        "[ADMIN] MQTT publish failed on mode switch")

        self.respond_success({"mode": mode})
