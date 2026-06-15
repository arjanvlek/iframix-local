"""Admin panel handler for charger control and display-device settings.

The /admin page is a local addition, not part of the original iFramix
Pro cloud API.  It is a master-detail single page (implemented from the
Claude Design handoff bundle "iframix-admin"):

* A sidebar lists the Chargers view plus every display device (with an
  online/offline dot derived from the most recent of the session's
  ``last_login`` / ``last_active``, the same <5 min heuristic
  ``devices.py`` uses for ``is_online``).
* The Chargers view is a table with two charging columns:
  - **Charge cmd**: the desired on/off state — the last instruction
    the controller app sent via ``refersh-battery`` (stored in the
    ``charging_switch`` column). This is the app's wish only; it does
    not drive the charger in manual mode.
  - **Status**: the actual on/off state — the last value the charger
    itself echoed back over MQTT (stored in
    ``charging_switch_reported``; may stay blank if the firmware never
    sends it).
  A single Power on/off button pushes a new charge command and records
  it in the ``admin_switch`` column; in auto mode it is rendered
  disabled ("Controlled by app") because ``/admin/toggle`` rejects with
  409 there. "Pending" means the charger has not yet echoed back the
  driving command: ``admin_switch`` vs reported in manual mode, the
  app's ``charging_switch`` vs reported in auto mode.
* Each display device gets a tabbed detail panel (Photos / Flip clock /
  Weather / Playback / Calendars / Remove) wired to the same REST
  endpoints that the native controller app uses, so the side-effects
  (MQTT notifications to the display device) are identical.

Static assets (clock/weather style screenshots, bundled woff2 fonts)
are served from ``admin_assets/static/`` at ``/admin/assets/...``.
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
_STATIC_DIR = _ASSETS_DIR / "static"
_ADMIN_CSS = (_ASSETS_DIR / "admin.css").read_text(encoding="utf-8")
_ADMIN_JS = (_ASSETS_DIR / "admin.js").read_text(encoding="utf-8")
_ADMIN_HTML_TEMPLATE = (
    (_ASSETS_DIR / "admin.html").read_text(encoding="utf-8")
    .replace("__ADMIN_CSS__", _ADMIN_CSS)
    .replace("__ADMIN_JS__", _ADMIN_JS)
)

_STATIC_CONTENT_TYPES = {
    ".png": "image/png",
    ".woff2": "font/woff2",
}

# A display device counts as online when the most recent of its
# session's last_login / last_active is within the last 5 minutes —
# the same heuristic devices.py uses to compute ``is_online`` for the
# native app's device list.
_ONLINE_WINDOW_SECONDS = 300

_CLOCK_STYLES = [
    (1, "Classic", "clocks/01-classic.png"),
    (2, "Red Plated", "clocks/02-red-plated.png"),
    (3, "Rainbow Prism", "clocks/03-rainbow-prism.png"),
    (4, "Black &amp; White", "clocks/04-black-and-white.png"),
    (5, "Gold Plated", "clocks/05-gold-plated.png"),
]
# weather_template_id is 0-based (0..3), matching the iFramix 2.2.29
# webapp's weather-station catalog.
_WEATHER_STYLES = [
    (0, "Classic", "weather/01-classic.png"),
    (1, "High Contrast", "weather/02-high-contrast.png"),
    (2, "Soft Toned", "weather/03-soft-toned.png"),
    (3, "Weather Station", "weather/04-weather-station.png"),
]
# Playback modules exactly as iFramix Pro 2.3.1 posts them, with the
# labels the native app shows (album = Photos, album_ai = AI Photos,
# screensaver = Flip Clock, weather = Weather, calendar = Calendar).
_PLAYBACK_MODULES = [
    ("album", "Photos"),
    ("album_ai", "AI Photos"),
    ("screensaver", "Flip Clock"),
    ("weather", "Weather"),
    ("calendar", "Calendar"),
]


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


_ICON_PATHS = {
    "monitor": ('<rect x="2" y="3" width="20" height="14" rx="2"/>'
                '<path d="M8 21h8M12 17v4"/>'),
    "tablet": ('<rect x="4" y="2" width="16" height="20" rx="2.5"/>'
               '<path d="M11 18h2"/>'),
    "smartphone": ('<rect x="6.5" y="2" width="11" height="20" rx="2.5"/>'
                   '<path d="M11 18h2"/>'),
    "search": ('<circle cx="11" cy="11" r="7"/>'
               '<path d="m21 21-4.3-4.3"/>'),
    "upload": ('<path d="M12 16V4M7 9l5-5 5 5"/>'
               '<path d="M5 16v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/>'),
    "trash": ('<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2'
              'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'),
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "cloud": ('<path d="M17.5 19a4.5 4.5 0 0 0 .5-9 6 6 0 0 0-11.6-1.5'
              'A4 4 0 0 0 6 19h11.5Z"/>'),
    "calendar": ('<rect x="3" y="4" width="18" height="17" rx="2"/>'
                 '<path d="M3 9h18M8 2v4M16 2v4"/>'),
    "image": ('<rect x="3" y="3" width="18" height="18" rx="2"/>'
              '<circle cx="8.5" cy="8.5" r="1.5"/>'
              '<path d="m21 15-5-5L5 21"/>'),
    "info": ('<circle cx="12" cy="12" r="9"/>'
             '<path d="M12 11v5M12 8h.01"/>'),
    "wifi": ('<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0'
             'M12 19.5h.01"/>'),
    "sparkle": ('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5'
                'M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>'),
    "power": '<path d="M12 4v8"/><path d="M7 6a8 8 0 1 0 10 0"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "alert": ('<path d="M12 9v4M12 17h.01"/>'
              '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17'
              'a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'),
}


def _icon(name, size=16):
    """Inline SVG icon matching the design's line-icon set."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{_ICON_PATHS[name]}</svg>'
    )


def _device_icon_name(name):
    """Tablet for iPads, smartphone for iPhone/iPod, monitor otherwise."""
    lowered = (name or "").lower()
    if "ipad" in lowered:
        return "tablet"
    if "iphone" in lowered or "ipod" in lowered:
        return "smartphone"
    return "monitor"


def _fmt_ago(timestamp):
    """Human '3m ago' style formatting; 'never' for missing values."""
    if not timestamp:
        return "never"
    age = time.time() - timestamp
    if age < 0:
        age = 0
    if age < 60:
        return f"{int(age)}s ago"
    if age < 3600:
        return f"{int(age / 60)}m ago"
    if age < 86400:
        return f"{int(age / 3600)}h {int(age % 3600 / 60):02d}m ago"
    return (f"{int(age / 86400)}d {int(age % 86400 / 3600)}h "
            f"{int(age % 3600 / 60):02d}m ago")


def _is_online(session):
    """Online when the most recent of ``last_login`` / ``last_active``
    is within ``_ONLINE_WINDOW_SECONDS`` (missing values treated as 0).
    """
    last_seen = max(session.get("last_login") or 0,
                    session.get("last_active") or 0)
    return (time.time() - last_seen) < _ONLINE_WINDOW_SECONDS


def _playback_module_switches():
    """Render one labelled toggle switch per playback module."""
    rows = ""
    for value, label in _PLAYBACK_MODULES:
        rows += f"""
                        <label class="module-row" data-module="{value}">
                            <span class="module-name">{label}</span>
                            <span class="switch">
                                <input type="checkbox" checked>
                                <span class="track"><span class="knob">
                                </span></span>
                            </span>
                        </label>"""
    return rows


def _playback_module_select(css_class, empty_label=None):
    """Render a module ``<select>``, optionally with an empty first option."""
    options = (f'<option value="">{empty_label}</option>'
               if empty_label else "")
    for value, label in _PLAYBACK_MODULES:
        options += f'<option value="{value}">{label}</option>'
    return f'<select class="input {css_class}">{options}</select>'


def _style_tiles(styles, grid_name):
    """Render the visual style-picker tiles (real device screenshots)."""
    tiles = ""
    for value, label, img in styles:
        tiles += f"""
                <button class="style-tile" type="button" data-value="{value}"
                        aria-pressed="false">
                    <div class="preview"><img
                        src="/admin/assets/{img}" alt="" loading="lazy"></div>
                    <span class="label">{label}<span class="check">
                        {_icon('check', 14)}</span></span>
                </button>"""
    return (f'<div class="style-grid" data-style-grid="{grid_name}">'
            f'{tiles}\n            </div>')


class AdminMixin:

    def _build_charger_rows(self, devices):
        """Render the chargers table body (also the 10s refresh fragment)."""
        rows = ""
        for uuid, info in sorted(devices.items()):
            if uuid.startswith("_"):
                continue

            mac = info.get("mac", "?")
            wifi = info.get("wifi_name", "?")
            firmware = info.get("firmware", "?")

            battery = info.get("battery")
            try:
                battery_pct = int(float(battery))
            except (TypeError, ValueError):
                battery_pct = None
            if battery_pct is not None:
                low = " low" if battery_pct <= 30 else ""
                battery_cell = (
                    '<div class="batt">'
                    f'<div class="batt-track"><div class="batt-fill{low}" '
                    f'style="width:{max(0, min(100, battery_pct))}%">'
                    '</div></div>'
                    f'<span class="mono">{battery_pct}%</span></div>'
                )
            else:
                battery_cell = '<span class="cell-dim">&mdash;</span>'

            command = info.get("charging_switch")
            admin_cmd = info.get("admin_switch")
            mode = info.get("mode") or "manual"
            if command == 1:
                command_cell = '<span class="chip on">ON</span>'
            elif command == 0:
                command_cell = '<span class="chip off">OFF</span>'
            else:
                command_cell = '<span class="cell-dim">&mdash;</span>'

            reported = info.get("charging_switch_reported")
            if reported == 1:
                status_cell = ('<span class="statedot on">'
                               '<span class="d"></span>ON</span>')
                status_attr = "on"
            elif reported == 0:
                status_cell = ('<span class="statedot off">'
                               '<span class="d"></span>OFF</span>')
                status_attr = "off"
            else:
                status_cell = '<span class="cell-dim">&mdash;</span>'
                status_attr = "unknown"
            # Flag the status as pending while the charger has not yet
            # echoed back the command that actually drives it. The
            # driving command differs by mode: in manual mode only the
            # admin's Power button drives the charger (admin_switch),
            # while charging_switch is just the app's non-driving wish;
            # in auto mode the app's charging_switch genuinely drives the
            # charger. The charger only confirms once it processes the
            # command and reports back (which can take until its next
            # poll, or until it reconnects if it is currently offline).
            if mode == "auto":
                pending = (command is not None and reported is not None
                           and command != reported)
            else:
                pending = (admin_cmd is not None and reported is not None
                           and admin_cmd != reported)
            if pending:
                status_cell += (
                    '<span class="pending-note" title="The charger has '
                    'not yet confirmed the last power command. It '
                    'updates on its next report.">P</span>'
                )

            auto_pressed = "true" if mode == "auto" else "false"
            manual_pressed = "false" if mode == "auto" else "true"
            mode_cell = (
                '<div class="seg sm accent">'
                f'<button type="button" aria-pressed="{auto_pressed}" '
                f'data-value="auto" onclick="setMode(\'{uuid}\', \'auto\')">'
                'Auto</button>'
                f'<button type="button" aria-pressed="{manual_pressed}" '
                f'data-value="manual" '
                f'onclick="setMode(\'{uuid}\', \'manual\')">Manual</button>'
                '</div>'
            )

            # The Power button is a command control, so in manual mode its
            # label follows the admin's last click (admin_switch): clicking
            # "Power off" flips it to "Power on" on the next refresh, giving
            # immediate, refresh-stable feedback even while the charger has
            # not yet confirmed. Before the admin has ever clicked it, fall
            # back to the charger's reported state, then to the app's
            # command, so the button reflects reality. The Status column
            # separately tracks what the charger last reported.
            effective_on = (
                admin_cmd if admin_cmd is not None
                else (reported if reported is not None else command))
            if mode == "auto":
                # /admin/toggle rejects auto-mode chargers with 409 —
                # render the design's button disabled with a hint.
                power_cell = (
                    '<div class="tcell-actions">'
                    '<span class="auto-note">Controlled by app</span>'
                    '</div>'
                )
            elif effective_on == 1:
                power_cell = (
                    '<div class="tcell-actions">'
                    f'<button class="btn sm ghost-danger" type="button" '
                    f'onclick="toggle(\'{uuid}\', false)">'
                    f'{_icon("power", 14)}Power off</button>'
                    '</div>'
                )
            else:
                power_cell = (
                    '<div class="tcell-actions">'
                    f'<button class="btn sm ok" type="button" '
                    f'onclick="toggle(\'{uuid}\', true)">'
                    f'{_icon("power", 14)}Power on</button>'
                    '</div>'
                )

            ago = _fmt_ago(info.get("last_seen", 0))
            voltage = (f"{info['voltage']:.2f}"
                       if info.get("voltage") else "&mdash;")
            current = (f"{info['current']:.2f}"
                       if info.get("current") else "&mdash;")
            # The voltage/current cells get stable hook classes only; the
            # client (refreshChargers in admin.js) adds the .flash class
            # after a refresh solely when a cell's value actually changed,
            # rather than flashing every charging row on every 10s swap.
            rows += f"""
            <tr data-uuid="{uuid}" data-status="{status_attr}">
                <td class="mono">{mac}</td>
                <td><span class="wifi-cell mono">
                    <span class="w-ico">{_icon('wifi', 14)}</span>{wifi}
                </span></td>
                <td class="mono cell-dim">{firmware}</td>
                <td class="mono cell-voltage"><span class="metric">{voltage}
                    <span class="u">V</span></span></td>
                <td class="mono cell-current"><span class="metric">{current}
                    <span class="u">A</span></span></td>
                <td>{battery_cell}</td>
                <td>{command_cell}</td>
                <td>{status_cell}</td>
                <td>{mode_cell}</td>
                <td class="cell-dim cell-nowrap">{ago}</td>
                <td>{power_cell}</td>
            </tr>"""

        if not rows:
            rows = ('<tr class="empty-row"><td colspan="11">'
                    'No chargers registered yet</td></tr>')
        return rows

    def _real_sessions(self, sessions):
        real = [
            s for s in sessions.values()
            if not s.get("uuid", "").startswith("_")
        ]
        real.sort(key=lambda s: (s.get("device_name") or "", s.get("id", 0)))
        return real

    def _build_device_nav(self, sessions):
        """Render the sidebar device rows (master list)."""
        real_sessions = self._real_sessions(sessions)
        if not real_sessions:
            return ('<div class="no-match" style="display:block">'
                    'No display devices registered yet. They appear here '
                    'after the iFramix app or webapp logs in.</div>')

        rows = ""
        for sess in real_sessions:
            sess_id = sess.get("id", 0)
            name = sess.get("device_name") or f"Device #{sess_id}"
            width = sess.get("width") or 0
            height = sess.get("height") or 0
            sub = (f"{width}&times;{height} &middot; id {sess_id}"
                   if width and height else f"id {sess_id}")
            online = _is_online(sess)
            dot = "online" if online else "offline"
            dot_title = "Online" if online else "Offline"
            search = _html.escape(f"{name} {sess_id}".lower(), quote=True)
            rows += f"""
                <button class="device-row" type="button"
                        data-view="device-{sess_id}" data-search="{search}">
                    <span class="device-ico">
                        {_icon(_device_icon_name(name), 18)}</span>
                    <span class="device-meta">
                        <span class="device-name">{_html.escape(name)}</span>
                        <span class="device-sub">{sub}</span>
                    </span>
                    <span class="dot {dot}" title="{dot_title}"></span>
                </button>"""
        return rows

    def _build_device_views(self, sessions):
        """Render one hidden detail view (tabbed settings) per session."""
        views = ""
        for sess in self._real_sessions(sessions):
            sess_id = sess.get("id", 0)
            uuid = sess.get("uuid", "")
            raw_name = sess.get("device_name") or f"Device #{sess_id}"
            name = _html.escape(raw_name)
            device_type = _html.escape(sess.get("device_type") or "ios")
            width = sess.get("width") or 0
            height = sess.get("height") or 0
            aspect = _classify_display_aspect(width, height)
            online = _is_online(sess)
            # presence-chip / seen-tag are stable hooks for the page's
            # 10s background presence refresh (GET /admin/devices).
            chip = ('<span class="chip presence-chip online">'
                    '<span class="dot online"></span>Online</span>'
                    if online else
                    '<span class="chip presence-chip offline">'
                    '<span class="dot offline"></span>Offline</span>')
            res_tag = (f'<span class="tag">{width}&times;{height}</span>'
                       if width and height else "")
            seen = _fmt_ago(max(sess.get("last_login") or 0,
                                sess.get("last_active") or 0))

            views += f"""
            <div class="view device-view" id="view-device-{sess_id}"
                 data-device-id="{sess_id}"
                 data-uuid="{_html.escape(uuid, quote=True)}"
                 data-aspect="{aspect}"
                 data-name="{_html.escape(raw_name, quote=True)}">
              <div class="page fade-in">
                <div class="detail-head">
                    <div class="detail-ico">
                        {_icon(_device_icon_name(raw_name), 26)}</div>
                    <div class="detail-meta">
                        <h1 class="detail-title">{name}</h1>
                        <div class="detail-tags">
                            {chip}
                            <span class="tag">{device_type}</span>
                            {res_tag}
                            <span class="tag">id {sess_id}</span>
                            <span class="tag seen-tag">seen {seen}</span>
                        </div>
                    </div>
                </div>

                <div class="tabs">
                    <button class="tab active" type="button"
                            data-tab="photos">{_icon('image', 16)}Photos
                        <span class="tcount"></span></button>
                    <button class="tab" type="button"
                            data-tab="clock">{_icon('clock', 16)}Flip
                        clock</button>
                    <button class="tab" type="button"
                            data-tab="weather">{_icon('cloud', 16)}Weather</button>
                    <button class="tab" type="button"
                            data-tab="calendars">{_icon('calendar', 16)}Calendars
                        <span class="tcount"></span></button>
                    <button class="tab" type="button"
                            data-tab="playback">{_icon('play', 16)}Playback</button>
                    <button class="tab remove-tab" type="button"
                            data-tab="remove">{_icon('alert', 15)}Remove</button>
                </div>

                <div class="tab-panel active" data-panel="photos">
                    <div class="upload-kind-row">
                        <div class="seg accent" data-seg="upload-kind">
                            <button type="button" data-value="normal"
                                    aria-pressed="true">
                                {_icon('image', 15)}Normal</button>
                            <button type="button" data-value="ai"
                                    aria-pressed="false">
                                {_icon('sparkle', 15)}AI</button>
                        </div>
                        <span class="note">New uploads go to the
                            <b class="kind-label">Normal</b> album</span>
                    </div>
                    <div class="dropzone">
                        <input type="file" accept="image/*" multiple hidden>
                        <div class="dz-ico">{_icon('upload', 20)}</div>
                        <div>
                            <div class="dz-title">Drag photos here, or click
                                to browse</div>
                            <div class="dz-sub">JPG or PNG &middot; added to
                                the <span class="kind-label">Normal</span>
                                album</div>
                        </div>
                    </div>
                    <div class="gallery-bar">
                        <div class="seg accent" data-seg="filter">
                            <button type="button" data-value="all"
                                    aria-pressed="true">All
                                <span class="fcount" data-fcount="all">0</span>
                            </button>
                            <button type="button" data-value="normal"
                                    aria-pressed="false">Normal
                                <span class="fcount"
                                      data-fcount="normal">0</span></button>
                            <button type="button" data-value="ai"
                                    aria-pressed="false">AI
                                <span class="fcount" data-fcount="ai">0</span>
                            </button>
                        </div>
                        <span class="spacer"></span>
                        <button class="btn sm ghost-danger delete-selected"
                                type="button" hidden>
                            {_icon('trash', 14)}Delete selected
                            (<span class="del-count">0</span>)</button>
                        <div class="muted-sort">
                            <label>Sort</label>
                            <select class="input photo-sort">
                                <option value="default">File name</option>
                                <option value="upload">Upload date</option>
                                <option value="capture">Capture date
                                    (EXIF)</option>
                            </select>
                        </div>
                    </div>
                    <div class="grid-photos"></div>
                    <div class="empty photos-empty" hidden></div>
                    <div class="photo-more"></div>
                </div>

                <div class="tab-panel" data-panel="clock">
                    <label class="field-label">Time format</label>
                    <div class="seg accent" data-seg="clock-format">
                        <button type="button" data-value="1"
                                aria-pressed="false">12-hour</button>
                        <button type="button" data-value="2"
                                aria-pressed="false">24-hour</button>
                    </div>
                    <div class="field-block">
                        <label class="field-label">Clock style</label>
                        {_style_tiles(_CLOCK_STYLES, 'clock')}
                    </div>
                    <div class="save-row">
                        <button class="btn primary clock-save" type="button">
                            {_icon('check', 15)}Save clock</button>
                    </div>
                </div>

                <div class="tab-panel" data-panel="weather">
                    <label class="field-label">City</label>
                    <div class="row" style="max-width:460px;">
                        <input type="text" class="input city-query"
                               placeholder="Search city (e.g. Amsterdam)">
                        <button class="btn city-search-btn" type="button">
                            {_icon('search', 15)}Search</button>
                    </div>
                    <div class="city-results"></div>
                    <div class="current-city"></div>
                    <div class="field-block">
                        <label class="field-label">Units</label>
                        <div class="seg accent" data-seg="unit">
                            <button type="button" data-value="1"
                                    aria-pressed="false">&deg;C&nbsp;
                                Celsius</button>
                            <button type="button" data-value="2"
                                    aria-pressed="false">&deg;F&nbsp;
                                Fahrenheit</button>
                        </div>
                    </div>
                    <div class="field-block">
                        <label class="field-label">Widget style</label>
                        {_style_tiles(_WEATHER_STYLES, 'weather')}
                    </div>
                    <div class="save-row">
                        <button class="btn primary weather-save"
                                type="button">
                            {_icon('check', 15)}Save weather</button>
                    </div>
                </div>

                <div class="tab-panel" data-panel="calendars">
                    <div class="form-grid">
                        <div>
                            <label class="field-label">Provider</label>
                            <select class="input cal-driver">
                                <option value="google">Google
                                    Calendar</option>
                                <option value="icloud">Apple iCloud</option>
                                <option value="outlook">Outlook / Microsoft
                                    365</option>
                                <option value="manual">Other (ICS
                                    URL)</option>
                            </select>
                        </div>
                        <div>
                            <label class="field-label">Display name
                                <span class="opt">(optional)</span></label>
                            <input type="text" class="input cal-name-input"
                                   placeholder="e.g. Family, Work">
                        </div>
                        <div>
                            <label class="field-label">Calendar URL</label>
                            <div class="row">
                                <input type="url" class="input cal-url-input"
                                       placeholder="https://&hellip;/basic.ics">
                                <button class="btn primary cal-add-btn"
                                        type="button">
                                    {_icon('plus', 15)}Add</button>
                            </div>
                        </div>
                    </div>
                    <div class="cal-list"></div>
                </div>

                <div class="tab-panel" data-panel="playback">
                    <label class="field-label">Playback mode</label>
                    <div class="seg accent" data-seg="playback-mode">
                        <button type="button" data-value="random"
                                aria-pressed="true">Random</button>
                        <button type="button" data-value="fixed"
                                aria-pressed="false">Fixed</button>
                    </div>
                    <p class="hint">Playback automatically switches the
                        display between modules. Random mode shows a new
                        random module on an interval; fixed mode shows a
                        default module with daily time-rule overrides.</p>

                    <div class="playback-random">
                        <div class="field-block">
                            <label class="field-label">Switch
                                interval</label>
                            <div class="row" style="max-width:260px;">
                                <input type="number" class="input
                                    playback-interval" min="1" max="240"
                                    step="1" value="15">
                                <span class="unit-suffix">min</span>
                            </div>
                            <p class="hint">Between 1 and 240 minutes.</p>
                        </div>
                        <div class="field-block">
                            <label class="field-label">Random playback
                                modules <span class="opt module-count">
                                </span></label>
                            <div class="module-list">
                                {_playback_module_switches()}
                            </div>
                            <p class="hint">On = included in random
                                playback; off = excluded from random
                                switching.</p>
                        </div>
                    </div>

                    <div class="playback-fixed" hidden>
                        <div class="field-block" style="max-width:320px;">
                            <label class="field-label">Default
                                module</label>
                            {_playback_module_select(
                                'playback-default', 'Not set')}
                            <p class="hint">Shown whenever no time rule
                                matches the current time.</p>
                        </div>
                        <div class="field-block">
                            <label class="field-label">Time rules
                                <span class="opt">(repeat daily)</span>
                            </label>
                            <div class="rule-list"></div>
                            <div class="rule-form">
                                <div>
                                    <label class="field-label">Start
                                        time</label>
                                    <input type="time" class="input
                                        rule-start">
                                </div>
                                <div>
                                    <label class="field-label">End
                                        time</label>
                                    <input type="time" class="input
                                        rule-end">
                                </div>
                                <div>
                                    <label class="field-label">Module</label>
                                    {_playback_module_select('rule-module')}
                                </div>
                                <div class="rule-form-actions">
                                    <button class="btn rule-cancel-btn"
                                            type="button" hidden>
                                        Cancel</button>
                                    <button class="btn primary rule-add-btn"
                                            type="button">
                                        {_icon('plus', 15)}<span
                                            class="rule-add-label">Add
                                            rule</span></button>
                                </div>
                            </div>
                            <p class="hint">Rules take effect daily and
                                cannot overlap. Outside every rule the
                                default module is shown.</p>
                        </div>
                    </div>

                    <div class="save-row">
                        <button class="btn primary playback-save"
                                type="button">
                            {_icon('check', 15)}Save playback</button>
                    </div>
                </div>

                <div class="tab-panel" data-panel="remove">
                    <div class="danger-zone">
                        <div class="dz-text">
                            <h4>Remove this display device</h4>
                            <p>Deletes the device's session, charger binding,
                            calendars, AI album config, photo settings, and
                            its <code>photos/</code>,
                            <code>photos_with_ai/</code> and
                            <code>logs/</code> directories. This cannot be
                            undone.</p>
                        </div>
                        <button class="btn ghost-danger delete-device-btn"
                                type="button">
                            {_icon('trash', 15)}Delete device</button>
                        <div class="danger-actions confirm-row" hidden>
                            <button class="btn confirm-cancel"
                                    type="button">Cancel</button>
                            <button class="btn danger confirm-yes"
                                    type="button">
                                {_icon('trash', 15)}Yes, delete</button>
                        </div>
                    </div>
                </div>
              </div>
            </div>"""
        return views

    def handle_admin_page(self):
        """Serve the admin control page.

        This page is a local-only addition to the offline controller. It
        is not part of the original iFramix Pro cloud API.  It combines
        charger on/off control with per-display-device settings panels
        that call the same REST endpoints as the native controller app.
        """
        devices = load_devices()
        sessions = load_sessions()
        real_sessions = self._real_sessions(sessions)
        charger_count = sum(
            1 for uuid in devices if not uuid.startswith("_"))
        online = sum(1 for s in real_sessions if _is_online(s))

        html_body = (
            _ADMIN_HTML_TEMPLATE
            .replace("__ADMIN_ROWS__", self._build_charger_rows(devices))
            .replace("__ADMIN_NAV__", self._build_device_nav(sessions))
            .replace("__ADMIN_DEVICE_VIEWS__",
                     self._build_device_views(sessions))
            .replace("__CHARGER_COUNT__", str(charger_count))
            .replace("__ONLINE_COUNT__",
                     f"{online}/{len(real_sessions)}")
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
        rows = self._build_charger_rows(load_devices())
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
        real_sessions = self._real_sessions(load_sessions())
        devices = [{
            "id": sess.get("id", 0),
            "online": _is_online(sess),
            "seen": _fmt_ago(max(sess.get("last_login") or 0,
                                 sess.get("last_active") or 0)),
        } for sess in real_sessions]
        self.respond_success({
            "online": sum(1 for d in devices if d["online"]),
            "total": len(devices),
            "devices": devices,
        })

    def handle_admin_asset(self, path):
        """Serve a static admin asset (style screenshots, fonts).

        Files live in ``admin_assets/static/`` and are addressed as
        ``/admin/assets/{relpath}``.  Only known extensions are served
        and the resolved path must stay inside the static directory.
        """
        rel = path[len("/admin/assets/"):]
        target = (_STATIC_DIR / rel).resolve()
        content_type = _STATIC_CONTENT_TYPES.get(target.suffix)
        if (content_type is None
                or not str(target).startswith(str(_STATIC_DIR.resolve()))
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
