"""Admin page shell, assembled once at import time from ``assets/``.

``admin.html`` holds the page skeleton with ``__ADMIN_CSS__`` /
``__ADMIN_JS__`` placeholders; the stylesheet and the scripts under
``assets/js/`` are inlined into it so the page needs one request only.
The scripts share one global scope, so they are concatenated in
dependency order: ``core.js`` first (it carries ``"use strict"``),
``main.js`` last (it wires the page once everything is defined).
"""

from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"
STATIC_DIR = ASSETS_DIR / "static"
_JS_DIR = ASSETS_DIR / "js"

_SCRIPT_FILES = [
    "core.js",
    "navigation.js",
    "chargers.js",
    "live-refresh.js",
    "device/state.js",
    "device/photos.js",
    "device/photo-upload.js",
    "device/flip-clock.js",
    "device/weather.js",
    "device/playback.js",
    "device/calendars.js",
    "device/remove.js",
    "device/lightbox.js",
    "gallery-templates/catalog.js",
    "gallery-templates/preview-kit.js",
    "gallery-templates/preview-4x3.js",
    "gallery-templates/preview-4x3-legacy.js",
    "gallery-templates/preview-16x9.js",
    "gallery-templates/preview.js",
    "gallery-templates/modal.js",
    "device/view.js",
    "main.js",
]

STATIC_CONTENT_TYPES = {
    ".png": "image/png",
    ".woff2": "font/woff2",
}


def _read(path):
    return path.read_text(encoding="utf-8")


ADMIN_JS = "\n".join(_read(_JS_DIR / name) for name in _SCRIPT_FILES)
ADMIN_CSS = _read(ASSETS_DIR / "admin.css")
ADMIN_HTML_TEMPLATE = (
    _read(ASSETS_DIR / "admin.html")
    .replace("__ADMIN_CSS__", ADMIN_CSS)
    .replace("__ADMIN_JS__", ADMIN_JS)
)
