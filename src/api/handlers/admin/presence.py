"""Online / active heuristics and "seen ... ago" formatting."""

import time

# A display device counts as online when the most recent of its
# session's last_login / last_active is within the last 5 minutes —
# the same heuristic devices.py uses to compute ``is_online`` for the
# native app's device list.
ONLINE_WINDOW_SECONDS = 300

# A charger counts as active when its last set_info report
# (``last_seen``) arrived within the last 45 minutes. Chargers report
# far less frequently than display devices chatter (a parked charger
# only wakes on its polling interval), so they get a much wider window
# than the 5-minute display-device heuristic above.
CHARGER_ONLINE_WINDOW_SECONDS = 45 * 60


def fmt_ago(timestamp):
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


def is_online(session):
    """Online when the most recent of ``last_login`` / ``last_active``
    is within ``ONLINE_WINDOW_SECONDS`` (missing values treated as 0).
    """
    last_seen = max(session.get("last_login") or 0,
                    session.get("last_active") or 0)
    return (time.time() - last_seen) < ONLINE_WINDOW_SECONDS


def charger_is_online(info):
    """Active when the charger's last report (``last_seen``) is within
    ``CHARGER_ONLINE_WINDOW_SECONDS`` (missing value treated as 0).
    """
    return (time.time() - (info.get("last_seen") or 0)
            ) < CHARGER_ONLINE_WINDOW_SECONDS
