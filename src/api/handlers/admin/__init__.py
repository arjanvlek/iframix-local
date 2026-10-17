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
are served from ``assets/static/`` at ``/admin/assets/...``.

Package layout:

* ``mixin.py`` — ``AdminMixin``, the HTTP handlers behind ``/admin/*``
* ``page_template.py`` — assembles the page shell from ``assets/``
  (``admin.html`` + ``admin.css`` + the ``assets/js/`` scripts)
* ``charger_rows.py`` — the chargers table body (also the 10s fragment)
* ``device_nav.py`` — the sidebar device rows
* ``device_views.py`` — one detail view per device (header + tab bar)
* ``device_panels.py`` — the tab panels and their style / module pickers
* ``display.py`` — session filtering, aspect / orientation, webapp version
* ``presence.py`` — online / active heuristics and "seen ... ago"
* ``icons.py`` — the inline SVG line icons
"""

from src.api.handlers.admin.mixin import AdminMixin

__all__ = ["AdminMixin"]
