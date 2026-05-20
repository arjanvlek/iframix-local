"""Admin panel handler for charger control and display-device settings.

The /admin page is a local addition, not part of the original iFramix
Pro cloud API.  It groups two sections in one page:

* A table of chargers (`load_devices`) with two charging columns:
  - **Charge command**: the desired on/off state — the last instruction
    the controller app sent (stored in the `charging_switch` column).
  - **Charger status**: the actual on/off state — the last value the
    charger itself echoed back over MQTT (stored in
    `charging_switch_reported`; may stay blank if the firmware never
    sends it).
  Enable/disable buttons push a new charge command.
* A grid of cards per display device (`load_sessions`) for uploading photos
  and editing flip-clock / weather / calendar settings — wired to the same
  REST endpoints that the native controller app uses, so the side-effects
  (MQTT notifications to the display device) are identical.
"""

import html as _html
import logging
import time
from pathlib import Path

from src.api.persistence import (
    load_devices, load_sessions, update_device_fields,
)
from src.api.utils import publish_charging_switch

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).parent / "admin_assets"
_ADMIN_CSS = (_ASSETS_DIR / "admin.css").read_text(encoding="utf-8")
_ADMIN_JS = (_ASSETS_DIR / "admin.js").read_text(encoding="utf-8")
_ADMIN_HTML_TEMPLATE = (
    (_ASSETS_DIR / "admin.html").read_text(encoding="utf-8")
    .replace("__ADMIN_CSS__", _ADMIN_CSS)
    .replace("__ADMIN_JS__", _ADMIN_JS)
)


def _classify_display_aspect(width, height):
    """Return ``"4x3"`` or ``"16x9"`` for given session dimensions.

    Mirrors the iPad webapp's ``setMaxSize`` rule: take the longer side
    over the shorter side and pick whichever of 4:3 or 16:9 is closer.
    Falls back to ``"16x9"`` when either dimension is missing or zero —
    that's the safer default since the broken ``mcol_*`` templates the
    admin's modal selects from are 16:9-specific. See
    ``docs/photos-ai-template-selection-2.2.29.md`` §3.1 for the webapp
    side of the same logic.
    """
    try:
        w = int(width or 0)
        h = int(height or 0)
    except (TypeError, ValueError):
        return "16x9"
    if w <= 0 or h <= 0:
        return "16x9"
    long_side, short_side = (w, h) if w >= h else (h, w)
    ratio = long_side / short_side
    if abs(ratio - 4 / 3) < abs(ratio - 16 / 9):
        return "4x3"
    return "16x9"


_ICON_SVG = (
    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="4" y="2" width="16" height="20" rx="2" ry="2"/>'
    '<line x1="12" y1="18" x2="12" y2="18"/></svg>'
)


class AdminMixin:

    def _build_charger_rows(self, devices):
        """Render the chargers table body."""
        rows = ""
        for uuid, info in sorted(devices.items()):
            if uuid.startswith("_"):
                continue

            mac = info.get("mac", "?")
            wifi = info.get("wifi_name", "?")
            firmware = info.get("firmware", "?")
            battery = info.get("battery")
            battery_str = f"{battery}%" if battery is not None else "&mdash;"

            def _cs_cell(value):
                if value == 1:
                    return '<span class="on">ON</span>'
                if value == 0:
                    return '<span class="off">OFF</span>'
                return "&mdash;"

            command_str = _cs_cell(info.get("charging_switch"))
            reported_str = _cs_cell(info.get("charging_switch_reported"))

            mode = info.get("mode") or "manual"
            if mode == "auto":
                mode_cell = (
                    '<div class="mode-btns">'
                    '<button class="btn on tiny" type="button" disabled>'
                    'Auto</button>'
                    f'<button class="btn neutral tiny" type="button" '
                    f'onclick="setMode(\'{uuid}\', \'manual\')">'
                    'Manual</button>'
                    '</div>'
                )
                actions_cell = (
                    '<span class="auto-note">Controlled by app</span>'
                )
            else:
                mode_cell = (
                    '<div class="mode-btns">'
                    f'<button class="btn neutral tiny" type="button" '
                    f'onclick="setMode(\'{uuid}\', \'auto\')">'
                    'Auto</button>'
                    '<button class="btn off tiny" type="button" disabled>'
                    'Manual</button>'
                    '</div>'
                )
                actions_cell = (
                    f'<button class="btn on" '
                    f'onclick="toggle(\'{uuid}\', true)">Enable</button> '
                    f'<button class="btn off" '
                    f'onclick="toggle(\'{uuid}\', false)">Disable</button>'
                )

            age = time.time() - info.get("last_seen", 0)
            if age < 60:
                ago = f"{int(age)}s ago"
            elif age < 3600:
                ago = f"{int(age / 60)}m ago"
            elif age < 86400:
                ago = f"{int(age / 3600)}h {int(age % 3600 / 60):02d}m ago"
            else:
                ago = (f"{int(age / 86400)}d {int(age % 86400 / 3600)}h "
                       f"{int(age % 3600 / 60):02d}m ago")

            voltage = (f"{info['voltage']:.2f}"
                       if info.get("voltage") else "&mdash;")
            current = (f"{info['current']:.2f}"
                       if info.get("current") else "&mdash;")

            rows += f"""
            <tr>
                <td>{mac}</td>
                <td>{wifi}</td>
                <td>{firmware}</td>
                <td>{voltage} V</td>
                <td>{current} A</td>
                <td>{battery_str}</td>
                <td>{command_str}</td>
                <td>{reported_str}</td>
                <td>{mode_cell}</td>
                <td>{ago}</td>
                <td>{actions_cell}</td>
            </tr>"""

        if not rows:
            rows = ('<tr><td colspan="11" class="empty">'
                    'No chargers registered yet</td></tr>')
        return rows

    def _build_device_cards(self, sessions):
        """Render a card per display session."""
        real_sessions = [
            s for s in sessions.values()
            if not s.get("uuid", "").startswith("_")
        ]
        if not real_sessions:
            return ('<div class="empty-card">'
                    'No display devices registered yet. They appear here '
                    'after the iFramix app or webapp logs in.</div>')

        real_sessions.sort(
            key=lambda s: (s.get("device_name") or "", s.get("id", 0)))

        cards = ""
        for sess in real_sessions:
            sess_id = sess.get("id", 0)
            uuid = sess.get("uuid", "")
            name = _html.escape(
                sess.get("device_name") or f"Device #{sess_id}")
            device_type = _html.escape(sess.get("device_type") or "ios")
            width = sess.get("width") or 0
            height = sess.get("height") or 0
            sub_parts = [device_type]
            if width and height:
                sub_parts.append(f"{width}&times;{height}")
            sub_parts.append(f"id {sess_id}")
            subtitle = " &middot; ".join(sub_parts)
            aspect = _classify_display_aspect(width, height)

            cards += f"""
            <div class="card" data-device-id="{sess_id}" data-uuid="{_html.escape(uuid, quote=True)}" data-aspect="{aspect}">
                <div class="card-head">
                    {_ICON_SVG}
                    <div class="meta">
                        <div class="name">{name}</div>
                        <div class="sub">{subtitle}</div>
                    </div>
                    <span class="chev">&#9656;</span>
                </div>
                <div class="panel">
                    <div class="note">
                        Charger binding is only available from the iFramix
                        app (requires Bluetooth).
                    </div>

                    <div class="subform" data-form="upload">
                        <h3>Photos</h3>
                        <input type="file" multiple accept="image/*">
                        <div class="row">
                            <label><input type="radio"
                                name="upload-type-{sess_id}" value="normal"
                                checked> Normal</label>
                            <label><input type="radio"
                                name="upload-type-{sess_id}" value="ai">
                                AI</label>
                            <button class="btn primary upload-btn"
                                    type="button"
                                    style="margin-left:auto;">Upload</button>
                        </div>
                        <div class="status"></div>
                        <div class="photo-section">
                            <div class="ps-label">
                                Normal (<span class="ps-count"
                                    data-photo-type="normal">0</span>)
                            </div>
                            <div class="photo-grid"
                                 data-photo-type="normal"></div>
                        </div>
                        <div class="photo-section">
                            <div class="ps-label">
                                AI (<span class="ps-count"
                                    data-photo-type="ai">0</span>)
                            </div>
                            <div class="photo-grid"
                                 data-photo-type="ai"></div>
                        </div>
                    </div>

                    <div class="subform" data-form="clock">
                        <h3>Flip clock</h3>
                        <div class="field-row">
                            <span class="field-label">Format</span>
                            <label><input type="radio"
                                name="clock-{sess_id}" value="1"> 12-hour</label>
                            <label><input type="radio"
                                name="clock-{sess_id}" value="2"> 24-hour</label>
                        </div>
                        <div class="field-row">
                            <span class="field-label">Style</span>
                            <label><input type="radio"
                                name="clock-style-{sess_id}" value="1"> 1</label>
                            <label><input type="radio"
                                name="clock-style-{sess_id}" value="2"> 2</label>
                            <label><input type="radio"
                                name="clock-style-{sess_id}" value="3"> 3</label>
                            <label><input type="radio"
                                name="clock-style-{sess_id}" value="4"> 4</label>
                            <label><input type="radio"
                                name="clock-style-{sess_id}" value="5"> 5</label>
                        </div>
                        <div class="row">
                            <button class="btn primary save-btn"
                                    type="button">Save</button>
                        </div>
                        <div class="status"></div>
                    </div>

                    <div class="subform" data-form="weather">
                        <h3>Weather</h3>
                        <div class="row">
                            <input type="text" class="city-query"
                                placeholder="Search city (e.g. Amsterdam)">
                            <button class="btn primary search-btn"
                                    type="button">Search</button>
                        </div>
                        <div class="city-results"></div>
                        <div class="current-city"></div>
                        <div class="field-row" style="margin-top:10px;">
                            <span class="field-label">Unit</span>
                            <label><input type="radio"
                                name="unit-{sess_id}" value="1"> &deg;C</label>
                            <label><input type="radio"
                                name="unit-{sess_id}" value="2"> &deg;F</label>
                        </div>
                        <div class="field-row">
                            <span class="field-label">Style</span>
                            <label><input type="radio"
                                name="weather-style-{sess_id}" value="0"> 1</label>
                            <label><input type="radio"
                                name="weather-style-{sess_id}" value="1"> 2</label>
                            <label><input type="radio"
                                name="weather-style-{sess_id}" value="2"> 3</label>
                            <label><input type="radio"
                                name="weather-style-{sess_id}" value="3"> 4</label>
                        </div>
                        <div class="row">
                            <button class="btn primary save-btn"
                                    type="button"
                                    style="margin-left:auto;">Save</button>
                        </div>
                        <div class="status"></div>
                    </div>

                    <div class="subform" data-form="calendar">
                        <h3>Calendars</h3>
                        <div class="row">
                            <select class="cal-driver">
                                <option value="google">Google Calendar</option>
                                <option value="outlook">Outlook</option>
                                <option value="icloud">iCloud</option>
                                <option value="manual">Manual iCal URL</option>
                            </select>
                        </div>
                        <div class="row">
                            <input type="text" class="cal-name"
                                placeholder="Display name (optional)">
                        </div>
                        <div class="row">
                            <input type="url" class="cal-url"
                                placeholder="https://.../basic.ics">
                            <button class="btn primary link-btn"
                                    type="button">Add</button>
                        </div>
                        <ul class="cal-list"></ul>
                        <div class="status"></div>
                    </div>

                    <div class="subform" data-form="delete">
                        <h3>Remove this display device</h3>
                        <p class="warn-text">
                            Deletes this device's session, charger binding,
                            calendars, AI album config, photo settings, and
                            its <code>photos/</code>, <code>photos_with_ai/</code>
                            and <code>logs/</code> directories. Cannot be
                            undone.
                        </p>
                        <div class="row">
                            <button class="btn off delete-btn" type="button"
                                    style="margin-left:auto;">Delete display device</button>
                        </div>
                        <div class="status"></div>
                    </div>
                </div>
            </div>"""
        return cards

    def handle_admin_page(self):
        """Serve the admin control page.

        This page is a local-only addition to the offline controller. It
        is not part of the original iFramix Pro cloud API.  It combines
        charger on/off control with a display-device settings panel that
        calls the same REST endpoints as the native controller app.
        """
        devices = load_devices()
        sessions = load_sessions()
        rows = self._build_charger_rows(devices)
        cards = self._build_device_cards(sessions)

        html_body = (
            _ADMIN_HTML_TEMPLATE
            .replace("__ADMIN_ROWS__", rows)
            .replace("__ADMIN_CARDS__", cards)
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
        place, leaving open settings cards untouched.
        """
        rows = self._build_charger_rows(load_devices())
        body = rows.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
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

        # Record the user's command in the desired-state column so the
        # admin table's "Charge command" cell reflects it immediately.
        # The charger's actual state lands in charging_switch_reported
        # via the router (derived from the current in the next set_info).
        update_device_fields(
            uuid, charging_switch=1 if charging_on else 0)

        state = "ON" if charging_on else "OFF"
        mac = devices[uuid].get("mac", "?")
        logger.info("[ADMIN] Charging %s -> %s (%s)", state, uuid, mac)
        self.respond_success({"charging_switch": 1 if charging_on else 0})

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

        update_device_fields(uuid, mode=mode)

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
