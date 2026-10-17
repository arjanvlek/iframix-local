"""Sidebar device rows (the master list)."""

import html as _html

from src.api.handlers.admin.display import real_sessions
from src.api.handlers.admin.icons import device_icon_name, icon
from src.api.handlers.admin.presence import is_online


def build_device_nav(sessions):
    """Render the sidebar device rows (master list)."""
    display_sessions = real_sessions(sessions)
    if not display_sessions:
        return ('<div class="no-match" style="display:block">'
                'No display devices registered yet. They appear here '
                'after the iFramix app or webapp logs in.</div>')

    rows = ""
    for sess in display_sessions:
        sess_id = sess.get("id", 0)
        name = sess.get("device_name") or f"Device #{sess_id}"
        width = sess.get("width") or 0
        height = sess.get("height") or 0
        sub = (f"{width}&times;{height} &middot; id {sess_id}"
               if width and height else f"id {sess_id}")
        online = is_online(sess)
        dot = "online" if online else "offline"
        dot_title = "Online" if online else "Offline"
        search = _html.escape(f"{name} {sess_id}".lower(), quote=True)
        rows += f"""
            <button class="device-row" type="button"
                    data-view="device-{sess_id}" data-search="{search}">
                <span class="device-ico">
                    {icon(device_icon_name(name), 18)}</span>
                <span class="device-meta">
                    <span class="device-name">{_html.escape(name)}</span>
                    <span class="device-sub">{sub}</span>
                </span>
                <span class="dot {dot}" title="{dot_title}"></span>
            </button>"""
    return rows
