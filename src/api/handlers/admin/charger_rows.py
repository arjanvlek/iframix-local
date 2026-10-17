"""Chargers table body (the page render and the 10s refresh fragment)."""

from src.api.handlers.admin.icons import icon
from src.api.handlers.admin.presence import charger_is_online, fmt_ago


def build_charger_rows(devices):
    """Render the chargers table body (also the 10s refresh fragment)."""
    rows = ""
    for uuid, info in sorted(devices.items()):
        if uuid.startswith("_"):
            continue

        mac = info.get("mac", "?")
        wifi = info.get("wifi_name", "?")
        firmware = info.get("firmware", "?")

        # Active when the charger reported within the last 45 minutes.
        # The dot mirrors the display-device presence dot; rows carry
        # data-online so the 10s refresh can recompute the menu count.
        charger_online = charger_is_online(info)
        online_attr = "true" if charger_online else "false"
        dot_cls = "online" if charger_online else "offline"
        dot_title = ("Active" if charger_online
                     else "Inactive — no report in over 45 minutes")
        status_dot_cell = (
            f'<span class="dot {dot_cls}" title="{dot_title}"></span>')

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
                f'{icon("power", 14)}Power off</button>'
                '</div>'
            )
        else:
            power_cell = (
                '<div class="tcell-actions">'
                f'<button class="btn sm ok" type="button" '
                f'onclick="toggle(\'{uuid}\', true)">'
                f'{icon("power", 14)}Power on</button>'
                '</div>'
            )

        ago = fmt_ago(info.get("last_seen", 0))
        voltage = (f"{info['voltage']:.2f}"
                   if info.get("voltage") else "&mdash;")
        current = (f"{info['current']:.2f}"
                   if info.get("current") else "&mdash;")
        # The voltage/current cells get stable hook classes only; the
        # client (refreshChargers in assets/js/chargers.js) adds the
        # .flash class after a refresh solely when a cell's value actually
        # changed, rather than flashing every charging row on every 10s
        # swap.
        rows += f"""
        <tr data-uuid="{uuid}" data-status="{status_attr}"
            data-online="{online_attr}">
            <td class="cell-status">{status_dot_cell}</td>
            <td class="mono">{mac}</td>
            <td><span class="wifi-cell mono">
                <span class="w-ico">{icon('wifi', 14)}</span>{wifi}
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
        rows = ('<tr class="empty-row"><td colspan="12">'
                'No chargers registered yet</td></tr>')
    return rows
