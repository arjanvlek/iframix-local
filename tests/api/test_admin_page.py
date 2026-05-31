"""Admin /admin HTML page + display-aspect classifier."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestAdminPage:
    """GET /admin renders display-device cards with a ``data-aspect``
    attribute that drives the AI-photo template-picker modal.

    The aspect classification matches the iPad webapp's ``setMaxSize``
    logic: longer/shorter side ratio compared to 4/3 vs 16/9, picking
    whichever is closer. The webapp's catalog has 10 templates per
    orientation on 4:3 and 5/4 on 16:9; the picker uses the attribute
    to show the right number of buttons.
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
        from src.api.handlers.admin import _classify_display_aspect
        assert _classify_display_aspect(2048, 1536) == "4x3"
        assert _classify_display_aspect(1536, 2048) == "4x3"
        assert _classify_display_aspect(1024, 768) == "4x3"
        assert _classify_display_aspect(1920, 1080) == "16x9"
        assert _classify_display_aspect(1366, 768) == "16x9"
        assert _classify_display_aspect(0, 0) == "16x9"
        assert _classify_display_aspect(None, None) == "16x9"
        assert _classify_display_aspect("foo", "bar") == "16x9"
        assert _classify_display_aspect(-1, 100) == "16x9"

    def test_picker_modal_emitted_with_dynamic_count(self, api_server):
        """The modal HTML is shipped with an empty ``.template-grid``
        and ``.template-hint`` — the JS populates both on open based on
        ``data-aspect`` on the card. Confirm the static HTML doesn't
        hardcode 5 buttons or a horizontal-only hint anymore."""
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # The grid must be present but empty in the static HTML.
        assert '<div class="template-grid"></div>' in resp.text
        assert '<div class="template-hint"></div>' in resp.text
        # And the JS must read data-aspect off the card.
        assert "card.dataset.aspect" in resp.text

    def test_photo_delete_buttons_rendered_per_section(self, api_server):
        """Each device card ships a "Delete selected" button for both
        the normal and AI photo sections, and the JS wires bulk delete
        to the same delMedia endpoint the display app uses."""
        self.seed_session(api_server["url"], "del-uuid", 1920, 1080)
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # One delete button per section (normal + ai).
        assert resp.text.count('class="btn off tiny photo-del-btn"') == 2
        assert 'data-photo-type="normal"' in resp.text
        assert 'data-photo-type="ai"' in resp.text
        # Bulk delete posts to the delMedia endpoint.
        assert "/api/ipad/media/delMedia" in resp.text
        assert "deleteSelectedPhotos" in resp.text

    def test_picker_modal_ships_svg_preview_generator(self, api_server):
        """The modal renders SVG layout previews on each button rather
        than plain numbers. The generator function and the marker
        class for the selected-state tint must both be present.
        """
        resp = requests.get(f"{api_server['url']}/admin")
        assert resp.status_code == 200
        # Generator function and per-aspect branches.
        assert "_templatePreviewSvg" in resp.text
        # Tints the text-panel rect blue when the button is selected.
        assert "preview-text-bg" in resp.text
        # The button creator should call the generator (not write a
        # plain number anymore).
        assert "btn.innerHTML = _templatePreviewSvg" in resp.text
