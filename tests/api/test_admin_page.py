"""Admin /admin HTML page + display-aspect classifier."""
import json
import os

import pytest
import requests

from tests.helpers import login, get_device_id


class TestAdminPage:
    """GET /admin renders display-device cards with a ``data-aspect``
    attribute that drives the AI-photo template-picker modal.

    The aspect classification matches the iPad webapp's ``setMaxSize``
    logic: longer/shorter side ratio compared to 4/3 vs 16/9, picking
    whichever is closer. The webapp's 4:3 catalog has 8 landscape / 7
    portrait templates on 2.3.8 (10 per orientation on 2.3.1-2.3.5) and
    5 / 4 on 16:9; the picker combines the attribute with
    ``data-orientation`` and ``<body data-webapp-version>`` to show the
    right buttons (see TestAdminDisplayOrientation and
    TestAdminWebappVersion below).
    """

    def seed_session(self, base_url, uuid, width, height):
        """Login + bindUser so a session lands in the sessions table."""
        login(base_url, uuid, origin="view")
        requests.post(
            f"{base_url}/api/ipad/device/bindUser",
            json={
                "uuid": uuid,
                "device_name": "TestDisplay",
                "device_type": "ios",
                "ios_version": "16.0",
                "width": width,
                "height": height,
            },
        )

    def _aspect_for(self, base_url, uuid):
        """Render /admin and return data-aspect for ``uuid``'s card."""
        import re
        resp = requests.get(f"{base_url}/admin")
        assert resp.status_code == 200
        # Cards are emitted with data-uuid="<uuid>" data-aspect="...".
        # Pin the order to the order the handler emits to avoid ambiguity.
        m = re.search(
            r'data-uuid="' + re.escape(uuid) + r'"\s+data-aspect="([^"]+)"',
            resp.text,
        )
        assert m, f"no card for uuid {uuid} in /admin"
        return m.group(1)

    def test_4x3_for_ipad_dimensions(self, api_server):
        """A 2048x1536 display (classic iPad) classifies as 4:3."""
        self.seed_session(api_server["url"], "asp-uuid-4x3", 2048, 1536)
        assert self._aspect_for(api_server["url"], "asp-uuid-4x3") == "4x3"

    def test_4x3_for_portrait_ipad_dimensions(self, api_server):
        """Orientation does not change the aspect class — 1536x2048 is
        still 4:3 (longer / shorter = 1.333)."""
        self.seed_session(api_server["url"], "asp-uuid-portrait", 1536, 2048)
        assert self._aspect_for(
            api_server["url"], "asp-uuid-portrait") == "4x3"

    def test_16x9_for_widescreen(self, api_server):
        """A 1920x1080 display classifies as 16:9."""
        self.seed_session(api_server["url"], "asp-uuid-16x9", 1920, 1080)
        assert self._aspect_for(api_server["url"], "asp-uuid-16x9") == "16x9"

    def test_4x3_for_square_ish(self, api_server):
        """A 1000x1000 display is closer to 4:3 (1.0 vs 1.333) than to
        16:9 (vs 1.778), so it classifies as 4:3."""
        self.seed_session(api_server["url"], "asp-uuid-square", 1000, 1000)
        assert self._aspect_for(api_server["url"], "asp-uuid-square") == "4x3"

    def test_default_aspect_when_dimensions_missing(self, api_server):
        """Sessions without recorded dimensions default to 16:9.

        A bare login (no bindUser) leaves width=0 and height=0, which
        the classifier can't divide. We default to 16:9 because that's
        the safer fallback for the picker — picking from the smaller
        catalog avoids surfacing template ids the iPad webapp would
        clamp anyway. ``setMaxSize`` on the webapp side eventually
        overwrites ``width``/``height`` once the iPad reports its
        dimensions, so this is only the no-data initial state.
        """
        login(api_server["url"], "asp-uuid-empty", origin="view")
        # Skip bindUser so width/height stay at 0.
        assert self._aspect_for(
            api_server["url"], "asp-uuid-empty") == "16x9"

    def test_classifier_unit(self):
        """Direct unit test of the classifier for edge cases.

        Hits the helper without HTTP plumbing so unusual dimensions
        (negatives, strings, None) are easy to cover.
        """
        from src.api.handlers.admin.display import classify_display_aspect
        assert classify_display_aspect(2048, 1536) == "4x3"
        assert classify_display_aspect(1536, 2048) == "4x3"
        assert classify_display_aspect(1024, 768) == "4x3"
        assert classify_display_aspect(1920, 1080) == "16x9"
        assert classify_display_aspect(1366, 768) == "16x9"
        assert classify_display_aspect(0, 0) == "16x9"
        assert classify_display_aspect(None, None) == "16x9"
        assert classify_display_aspect("foo", "bar") == "16x9"
        assert classify_display_aspect(-1, 100) == "16x9"

    def test_picker_modal_emitted_with_dynamic_count(self, api_server):
        """The modal HTML is shipped with an empty ``.template-grid``
        and ``.template-hint`` — the JS populates both on open based on
        ``data-aspect`` on the device view. Confirm the static HTML
        doesn't hardcode 5 buttons or a horizontal-only hint."""
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # The grid and hint must be present but empty in the static HTML.
        assert 'class="tpl-list template-grid"' in resp.text
        assert '<span class="template-hint"></span>' in resp.text
        # And the JS must read data-aspect off the device view.
        assert "view.dataset.aspect" in resp.text
        # The option count is derived per aspect/orientation at runtime.
        assert "_templatePickerSpec" in resp.text

    def test_photo_bulk_delete_wired_per_device(self, api_server):
        """Each device view ships a single "Delete selected" button for
        the photo gallery (selection spans normal + AI photos), and the
        JS wires bulk delete to the same delMedia endpoint the display
        app uses."""
        self.seed_session(api_server["url"], "del-uuid", 1920, 1080)
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # One bulk-delete button per device view.
        n_views = resp.text.count('class="view device-view"')
        assert n_views >= 1
        assert resp.text.count("delete-selected") >= n_views
        # Bulk delete posts to the delMedia endpoint.
        assert "/api/ipad/media/delMedia" in resp.text
        assert "deleteSelectedPhotos" in resp.text

    def test_picker_modal_ships_svg_preview_generator(self, api_server):
        """The modal renders SVG layout previews (with the photo
        composited in) rather than plain numbers. The generator
        function and the marker class for the selected-state tint must
        both be present.
        """
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # Generator function and per-aspect branches.
        assert "_templatePreviewSvg" in resp.text
        # Tints the text-panel rect when the option is selected.
        assert "preview-text-bg" in resp.text
        # The option builder calls the generator with the photo URL
        # composited in, and the live preview re-renders on selection.
        assert "_templatePreviewSvg(_tplCtx.aspect, i, m.url, _tplCtx.templateType," in resp.text
        assert "updateTemplatePreview" in resp.text

    def test_device_status_endpoint(self, api_server):
        """GET /admin/devices returns the presence JSON the page polls
        every 10s to refresh the sidebar dots, the online counter, and
        each detail view's Online/Offline chip + "seen ..." tag.

        A freshly logged-in session must count as online (its login just
        stamped last_login/last_active).
        """
        self.seed_session(api_server["url"], "status-uuid", 1920, 1080)
        resp = requests.get(f"{api_server['url']}/admin/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1
        d = data["data"]
        assert d["total"] >= 1
        assert 0 <= d["online"] <= d["total"]
        assert len(d["devices"]) == d["total"]
        rec = next(r for r in d["devices"]
                   if r["seen"].endswith("ago") or r["seen"] == "never")
        assert set(rec) == {"id", "online", "seen"}
        # The just-seeded session logged in moments ago -> online.
        assert any(r["online"] for r in d["devices"])
        assert d["online"] == sum(1 for r in d["devices"] if r["online"])

    def test_page_wires_device_status_polling(self, api_server):
        """The served page must poll /admin/devices on the same 10s
        interval as the chargers fragment and carry the stable hooks
        (presence-chip / seen-tag) the updater rewrites."""
        self.seed_session(api_server["url"], "poll-uuid", 1920, 1080)
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        assert "refreshDeviceStatus" in resp.text
        assert '"/admin/devices"' in resp.text
        assert 'class="chip presence-chip' in resp.text
        assert 'class="tag seen-tag"' in resp.text

    def test_page_ships_live_refresh_toggle(self, api_server):
        """The topbar "Live · 10s" pill is a button that pauses/resumes
        the 10s background refresh; paused state hides the pulsing dot
        and flips the pill + sidebar-foot labels."""
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # The pill is a button with the toggle id, and the JS guards the
        # interval on the live flag.
        assert 'id="live-toggle"' in resp.text
        assert "setLiveRefresh" in resp.text
        assert "if (!liveRefresh) return;" in resp.text
        # Paused wording for both the pill and the sidebar foot ships
        # with the page.
        assert "Auto-refresh paused" in resp.text
        assert '"Paused"' in resp.text


class TestAdminDisplayOrientation:
    """GET /admin renders a ``data-orientation`` attribute next to
    ``data-aspect`` on every device view.

    The display webapp picks its Gallery Mode template catalog from its
    own orientation and stores that orientation as ``template_type``
    (1 = landscape, 2 = portrait); a mismatching ``template_type`` makes
    it ignore ``template_id`` (verified on an iPad 4 with webapp 2.3.8,
    ``docs/gallery-mode-templates-2.3.8.md``). The admin picker reads the
    attribute to offer the right catalog and to save the right
    ``template_type``.
    """

    def _orientation_for(self, base_url, uuid):
        import re
        resp = requests.get(f"{base_url}/admin")
        assert resp.status_code == 200
        m = re.search(
            r'data-uuid="' + re.escape(uuid) +
            r'"\s+data-aspect="[^"]+"\s+data-orientation="([^"]+)"',
            resp.text,
        )
        assert m, f"no data-orientation for uuid {uuid} in /admin"
        return m.group(1)

    def test_landscape_for_wide_dimensions(self, api_server):
        TestAdminPage().seed_session(
            api_server["url"], "ori-uuid-land", 2048, 1536)
        assert self._orientation_for(
            api_server["url"], "ori-uuid-land") == "landscape"

    def test_portrait_for_tall_dimensions(self, api_server):
        TestAdminPage().seed_session(
            api_server["url"], "ori-uuid-port", 1536, 2048)
        assert self._orientation_for(
            api_server["url"], "ori-uuid-port") == "portrait"

    def test_default_landscape_when_dimensions_missing(self, api_server):
        login(api_server["url"], "ori-uuid-empty", origin="view")
        assert self._orientation_for(
            api_server["url"], "ori-uuid-empty") == "landscape"

    def test_classifier_unit(self):
        from src.api.handlers.admin.display import classify_display_orientation
        assert classify_display_orientation(1024, 768) == "landscape"
        assert classify_display_orientation(768, 1024) == "portrait"
        assert classify_display_orientation(1000, 1000) == "landscape"
        assert classify_display_orientation(0, 0) == "landscape"
        assert classify_display_orientation(None, "x") == "landscape"

    def test_page_ships_orientation_aware_catalog(self, api_server):
        """The inlined admin scripts carry the 2.3.8 catalogs (8 landscape /
        7 portrait names) and derives template_type from the view."""
        resp = requests.get(f"{api_server['url']}/admin")
        assert "TPL_META_4X3_LANDSCAPE" in resp.text
        assert "TPL_META_4X3_PORTRAIT" in resp.text
        assert "function displayTemplateType(view)" in resp.text
        for name in ("Legacy side ribbon", "Glass pillar", "Classic bottom"):
            assert name in resp.text


class TestAdminWebappVersion:
    """GET /admin stamps ``<body data-webapp-version="...">`` with the
    webapp version this server serves, so the Gallery Mode template
    picker can offer the 2.3.8 catalog (8 landscape / 7 portrait 4:3
    layouts) for the default bundle and the 2.3.1–2.3.5 catalog (10 per
    orientation) when an older bundle is served with
    ``--webapp-version``.
    """

    def _body_version(self, base_url):
        import re
        resp = requests.get(f"{base_url}/admin")
        assert resp.status_code == 200
        m = re.search(r'<body data-webapp-version="([^"]*)">', resp.text)
        assert m, "no data-webapp-version on <body>"
        return m.group(1)

    def test_default_bundle_reports_default_version(self, api_server):
        """The test WEBAPP_DIR has no index.html, so the version falls
        back to config.WEBAPP_DEFAULT_VERSION."""
        cfg = api_server["module"].config
        assert cfg.INDEX_HTML_FILE == "index.html"
        assert self._body_version(api_server["url"]) == \
            cfg.WEBAPP_DEFAULT_VERSION

    def test_version_read_from_default_index_file(self, api_server):
        cfg = api_server["module"].config
        os.makedirs(cfg.WEBAPP_DIR, exist_ok=True)
        with open(os.path.join(cfg.WEBAPP_DIR, "index.html"), "w") as fh:
            fh.write("<script>window.appVersion = '9.9.9'; //H5</script>")
        assert self._body_version(api_server["url"]) == "9.9.9"

    def test_versioned_index_file_wins(self, api_server):
        cfg = api_server["module"].config
        cfg.INDEX_HTML_FILE = "index-2.3.5.html"
        try:
            assert self._body_version(api_server["url"]) == "2.3.5"
        finally:
            cfg.INDEX_HTML_FILE = "index.html"

    def test_page_ships_version_aware_catalog_helpers(self, api_server):
        resp = requests.get(f"{api_server['url']}/admin")
        for token in ("function servedWebappVersion()",
                      "function legacy4x3Catalog()",
                      "function templateEffect(",
                      "TPL_META_4X3_LEGACY",
                      "Auto (orientation mismatch)",
                      "(shows as "):
            assert token in resp.text, token


class TestAdminScriptBundle:
    """The admin page inlines the scripts under ``admin/assets/js/`` in
    the order listed in ``page_template._SCRIPT_FILES``. A script that is
    missing from the list would silently never reach the browser."""

    def test_every_script_file_is_listed(self):
        from src.api.handlers.admin import page_template
        js_dir = page_template.ASSETS_DIR / "js"
        on_disk = {p.relative_to(js_dir).as_posix()
                   for p in js_dir.rglob("*.js")}
        listed = page_template._SCRIPT_FILES
        assert len(listed) == len(set(listed))
        assert set(listed) == on_disk

    def test_strict_mode_comes_first_and_init_last(self):
        from src.api.handlers.admin import page_template
        assert page_template._SCRIPT_FILES[0] == "core.js"
        assert page_template._SCRIPT_FILES[-1] == "main.js"
        js = page_template.ADMIN_JS
        first_code = next(line for line in js.splitlines()
                          if line.strip() and not line.startswith("//"))
        assert first_code == '"use strict";'
