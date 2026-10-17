"""Tab panels of a display-device detail view.

The panels carry no per-device values: ``assets/js/device/view.js``
wires them to the device's REST endpoints using the ``data-*``
attributes of the surrounding view.
"""

from src.api.handlers.admin.icons import icon

CLOCK_STYLES = [
    (1, "Classic", "clocks/01-classic.png"),
    (2, "Red Plated", "clocks/02-red-plated.png"),
    (3, "Rainbow Prism", "clocks/03-rainbow-prism.png"),
    (4, "Black &amp; White", "clocks/04-black-and-white.png"),
    (5, "Gold Plated", "clocks/05-gold-plated.png"),
]
# weather_template_id is 0-based (0..3), matching the iFramix 2.2.29
# webapp's weather-station catalog.
WEATHER_STYLES = [
    (0, "Classic", "weather/01-classic.png"),
    (1, "High Contrast", "weather/02-high-contrast.png"),
    (2, "Soft Toned", "weather/03-soft-toned.png"),
    (3, "Weather Station", "weather/04-weather-station.png"),
]
# Playback modules exactly as iFramix Pro 2.3.1 posts them, with the
# labels the native app shows (album = Photos, album_ai = Gallery Mode,
# screensaver = Flip Clock, weather = Weather, calendar = Calendar).
PLAYBACK_MODULES = [
    ("album", "Photos"),
    ("album_ai", "Gallery Mode"),
    ("screensaver", "Flip Clock"),
    ("weather", "Weather"),
    ("calendar", "Calendar"),
]


def playback_module_switches():
    """Render one labelled toggle switch per playback module."""
    rows = ""
    for value, label in PLAYBACK_MODULES:
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


def playback_module_select(css_class, empty_label=None):
    """Render a module ``<select>``, optionally with an empty first option."""
    options = (f'<option value="">{empty_label}</option>'
               if empty_label else "")
    for value, label in PLAYBACK_MODULES:
        options += f'<option value="{value}">{label}</option>'
    return f'<select class="input {css_class}">{options}</select>'


def style_tiles(styles, grid_name):
    """Render the visual style-picker tiles (real device screenshots)."""
    tiles = ""
    for value, label, img in styles:
        tiles += f"""
                <button class="style-tile" type="button" data-value="{value}"
                        aria-pressed="false">
                    <div class="preview"><img
                        src="/admin/assets/{img}" alt="" loading="lazy"></div>
                    <span class="label">{label}<span class="check">
                        {icon('check', 14)}</span></span>
                </button>"""
    return (f'<div class="style-grid" data-style-grid="{grid_name}">'
            f'{tiles}\n            </div>')


def photos_panel():
    """Photos tab: upload kind, dropzone and gallery."""
    return f"""
        <div class="tab-panel active" data-panel="photos">
            <div class="upload-kind-row">
                <div class="seg accent" data-seg="upload-kind">
                    <button type="button" data-value="normal"
                            aria-pressed="true">
                        {icon('image', 15)}Normal</button>
                    <button type="button" data-value="ai"
                            aria-pressed="false">
                        {icon('sparkle', 15)}Gallery Mode</button>
                </div>
                <span class="note">New uploads go to the
                    <b class="kind-label">Normal</b> album</span>
            </div>
            <div class="dropzone">
                <input type="file" accept="image/*" multiple hidden>
                <div class="dz-ico">{icon('upload', 20)}</div>
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
                            aria-pressed="false">Gallery Mode
                        <span class="fcount" data-fcount="ai">0</span>
                    </button>
                </div>
                <span class="spacer"></span>
                <button class="btn sm ghost-danger delete-selected"
                        type="button" hidden>
                    {icon('trash', 14)}Delete selected
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
        </div>"""


def clock_panel():
    """Flip clock tab: time format and clock style."""
    return f"""
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
                {style_tiles(CLOCK_STYLES, 'clock')}
            </div>
            <div class="save-row">
                <button class="btn primary clock-save" type="button">
                    {icon('check', 15)}Save clock</button>
            </div>
        </div>"""


def weather_panel():
    """Weather tab: city, units and widget style."""
    return f"""
        <div class="tab-panel" data-panel="weather">
            <label class="field-label">City</label>
            <div class="row" style="max-width:460px;">
                <input type="text" class="input city-query"
                       placeholder="Search city (e.g. Amsterdam)">
                <button class="btn city-search-btn" type="button">
                    {icon('search', 15)}Search</button>
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
                {style_tiles(WEATHER_STYLES, 'weather')}
            </div>
            <div class="save-row">
                <button class="btn primary weather-save"
                        type="button">
                    {icon('check', 15)}Save weather</button>
            </div>
        </div>"""


def calendars_panel():
    """Calendars tab: link form and calendar list."""
    return f"""
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
                            {icon('plus', 15)}Add</button>
                    </div>
                </div>
            </div>
            <div class="cal-list"></div>
        </div>"""


def playback_panel():
    """Playback tab: random / fixed playback mode."""
    return f"""
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
                        {playback_module_switches()}
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
                    {playback_module_select(
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
                            {playback_module_select('rule-module')}
                        </div>
                        <div class="rule-form-actions">
                            <button class="btn rule-cancel-btn"
                                    type="button" hidden>
                                Cancel</button>
                            <button class="btn primary rule-add-btn"
                                    type="button">
                                {icon('plus', 15)}<span
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
                    {icon('check', 15)}Save playback</button>
            </div>
        </div>"""


def remove_panel():
    """Remove tab: danger zone with inline confirm."""
    return f"""
        <div class="tab-panel" data-panel="remove">
            <div class="danger-zone">
                <div class="dz-text">
                    <h4>Remove this display device</h4>
                    <p>Deletes the device's session, charger binding,
                    calendars, Gallery Mode config, photo settings, and
                    its <code>photos/</code>,
                    <code>photos_with_ai/</code> and
                    <code>logs/</code> directories. This cannot be
                    undone.</p>
                </div>
                <button class="btn ghost-danger delete-device-btn"
                        type="button">
                    {icon('trash', 15)}Delete device</button>
                <div class="danger-actions confirm-row" hidden>
                    <button class="btn confirm-cancel"
                            type="button">Cancel</button>
                    <button class="btn danger confirm-yes"
                            type="button">
                        {icon('trash', 15)}Yes, delete</button>
                </div>
            </div>
        </div>"""
