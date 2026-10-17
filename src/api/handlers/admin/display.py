"""Display-device helpers: session filtering, aspect / orientation
classification, and the webapp version the displays are served."""

import os
import re

from src.api import config


def real_sessions(sessions):
    """Display-device sessions, without internal ``_``-prefixed ones,
    sorted by name then id."""
    real = [
        s for s in sessions.values()
        if not s.get("uuid", "").startswith("_")
    ]
    real.sort(key=lambda s: (s.get("device_name") or "", s.get("id", 0)))
    return real


def classify_display_aspect(width, height):
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


def classify_display_orientation(width, height):
    """Return ``"landscape"`` or ``"portrait"`` for given session dimensions.

    The display webapp picks its Gallery Mode template catalog from its
    *own* orientation (``isRow``, derived from ``window.orientation``),
    not from the photo's, and it stores that orientation as
    ``template_type`` (1 = landscape, 2 = portrait). A stored
    ``template_type`` that does not match the display's orientation makes
    the webapp ignore ``template_id`` altogether (verified on an iPad 4
    with webapp 2.3.8 — see ``docs/gallery-mode-templates-2.3.8.md``
    §1). The admin picker therefore needs the display orientation, which
    this helper derives from the session's last reported dimensions
    (``width >= height`` → landscape). Missing or unusable dimensions
    default to ``"landscape"``, the orientation most frames are mounted
    in.
    """
    try:
        w = int(width or 0)
        h = int(height or 0)
    except (TypeError, ValueError):
        return "landscape"
    if w <= 0 or h <= 0:
        return "landscape"
    return "portrait" if h > w else "landscape"


_APP_VERSION_RE = re.compile(r"appVersion\s*=\s*'(\d+(?:\.\d+)+)'")


def served_webapp_version():
    """Return the iFramix Pro webapp version this server serves.

    The admin panel's Gallery Mode template picker must offer the catalog
    of the bundle the displays actually load (webapp 2.3.8 trimmed the
    4:3 catalog from 10 + 10 to 8 + 7 layouts). ``--webapp-version``
    selects ``index-<version>.html``, so the version is taken from that
    file name first. The default ``index.html`` is identified by the
    ``window.appVersion`` string inside it, falling back to
    ``config.WEBAPP_DEFAULT_VERSION`` when the file cannot be read (e.g.
    in tests, which point ``WEBAPP_DIR`` at an empty directory).
    """
    name = config.INDEX_HTML_FILE or "index.html"
    m = re.fullmatch(r"index-(\d+(?:\.\d+)+)\.html", name)
    if m:
        return m.group(1)
    try:
        with open(os.path.join(config.WEBAPP_DIR, name),
                  encoding="utf-8", errors="replace") as fh:
            found = _APP_VERSION_RE.search(fh.read(65536))
        if found:
            return found.group(1)
    except OSError:
        pass
    return config.WEBAPP_DEFAULT_VERSION
