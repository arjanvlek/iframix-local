"""Hidden per-device detail views: header, tab bar and tab panels."""

import html as _html

from src.api.handlers.admin.device_panels import (
    calendars_panel, clock_panel, photos_panel, playback_panel,
    remove_panel, weather_panel,
)
from src.api.handlers.admin.display import (
    classify_display_aspect, classify_display_orientation, real_sessions,
)
from src.api.handlers.admin.icons import device_icon_name, icon
from src.api.handlers.admin.presence import fmt_ago, is_online

# The tab panels carry no per-device values, so they are rendered once.
_TAB_PANELS = "\n".join(panel() for panel in (
    photos_panel, clock_panel, weather_panel, calendars_panel,
    playback_panel, remove_panel,
))


def build_device_views(sessions):
    """Render one hidden detail view (tabbed settings) per session."""
    views = ""
    for sess in real_sessions(sessions):
        sess_id = sess.get("id", 0)
        uuid = sess.get("uuid", "")
        raw_name = sess.get("device_name") or f"Device #{sess_id}"
        name = _html.escape(raw_name)
        device_type = _html.escape(sess.get("device_type") or "ios")
        width = sess.get("width") or 0
        height = sess.get("height") or 0
        aspect = classify_display_aspect(width, height)
        orientation = classify_display_orientation(width, height)
        online = is_online(sess)
        # presence-chip / seen-tag are stable hooks for the page's
        # 10s background presence refresh (GET /admin/devices).
        chip = ('<span class="chip presence-chip online">'
                '<span class="dot online"></span>Online</span>'
                if online else
                '<span class="chip presence-chip offline">'
                '<span class="dot offline"></span>Offline</span>')
        res_tag = (f'<span class="tag">{width}&times;{height}</span>'
                   if width and height else "")
        seen = fmt_ago(max(sess.get("last_login") or 0,
                            sess.get("last_active") or 0))

        views += f"""
        <div class="view device-view" id="view-device-{sess_id}"
             data-device-id="{sess_id}"
             data-uuid="{_html.escape(uuid, quote=True)}"
             data-aspect="{aspect}"
             data-orientation="{orientation}"
             data-name="{_html.escape(raw_name, quote=True)}">
          <div class="page fade-in">
            <div class="detail-head">
                <div class="detail-ico">
                    {icon(device_icon_name(raw_name), 26)}</div>
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
                        data-tab="photos">{icon('image', 16)}Photos
                    <span class="tcount"></span></button>
                <button class="tab" type="button"
                        data-tab="clock">{icon('clock', 16)}Flip
                    clock</button>
                <button class="tab" type="button"
                        data-tab="weather">{icon('cloud', 16)}Weather</button>
                <button class="tab" type="button"
                        data-tab="calendars">{icon('calendar', 16)}Calendars
                    <span class="tcount"></span></button>
                <button class="tab" type="button"
                        data-tab="playback">{icon('play', 16)}Playback</button>
                <button class="tab remove-tab" type="button"
                        data-tab="remove">{icon('alert', 15)}Remove</button>
            </div>

            {_TAB_PANELS}
          </div>
        </div>"""
    return views
