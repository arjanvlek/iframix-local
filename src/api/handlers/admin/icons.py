"""Inline SVG line icons for the server-rendered admin markup."""

ICON_PATHS = {
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


def icon(name, size=16):
    """Inline SVG icon matching the design's line-icon set."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{ICON_PATHS[name]}</svg>'
    )


def device_icon_name(name):
    """Tablet for iPads, smartphone for iPhone/iPod, monitor otherwise."""
    lowered = (name or "").lower()
    if "ipad" in lowered:
        return "tablet"
    if "iphone" in lowered or "ipod" in lowered:
        return "smartphone"
    return "monitor"
