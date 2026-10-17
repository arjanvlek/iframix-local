"""Server-side AI template auto-assignment."""
import base64
import json
import os
import time

import pytest
import requests

from tests.helpers import login, get_device_id, make_png


class TestAITemplateAssignment:
    """Auto-assigned templates for AI photos.

    The webapp falls back to ``Math.random()`` whenever an AI photo's
    ``template_id`` is 0 on the server, so reload-stable templates require
    the API to assign one and persist it. Two trigger points:

    * On ``setMedia`` when an AI photo is moved out of the temp dir.
    * On ``mediaList`` when an AI photo is read for the first time and
      no value is stored yet (covers files dropped into ``photos_with_ai``
      directly without going through ``setMedia``).

    The assignment must:

    - Use the display's orientation as ``template_type`` when the
      display's session has reported its dimensions (see
      ``TestAITemplateFollowsDisplayOrientation``); the tests in this
      class use device ``42``, which has no session, so the photo's own
      orientation decides (portrait → 2, landscape → 1).
    - Stay within the 16:9 catalog ranges (1..5 landscape, 1..4
      portrait) so it works on every supported display without clamping.
    - Be stable across repeated reads.
    - Skip already-assigned photos so admin edits aren't overwritten.
    """

    @staticmethod
    def _png_with_dimensions(width, height):
        """Return a real PNG of the given dimensions.

        The Pillow-based ``get_image_size`` decodes the header of a
        genuine image, so the fixture is a real (flat-colour, hence tiny)
        PNG rather than a hand-built byte stub.
        """
        return make_png(width, height)

    def _drop_ai_photo(self, api_server, filename, width, height,
                       device_id="42"):
        """Drop a fake AI photo into ``photos_with_ai/<device>/`` directly."""
        device_dir = str(
            api_server["tmp_path"] / "photos_with_ai" / device_id)
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, filename), "wb") as f:
            f.write(self._png_with_dimensions(width, height))

    def _list_ai(self, api_server, device_id="42"):
        return requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": device_id, "page": 1, "limit": 50,
                    "type": "ai"},
        ).json()["data"]["list"]

    def test_landscape_image_gets_horizontal_template(self, api_server):
        """A wider-than-tall image is assigned template_type=1 (1..5)."""
        self._drop_ai_photo(api_server, "wide.png", 1920, 1080)
        records = self._list_ai(api_server)
        assert len(records) == 1
        record = records[0]
        assert record["template_type"] == 1
        assert 1 <= record["template_id"] <= 5

    def test_portrait_image_gets_vertical_template(self, api_server):
        """A taller-than-wide image is assigned template_type=2 (1..4)."""
        self._drop_ai_photo(api_server, "tall.png", 1080, 1920)
        records = self._list_ai(api_server)
        assert len(records) == 1
        record = records[0]
        assert record["template_type"] == 2
        assert 1 <= record["template_id"] <= 4

    def test_square_image_defaults_to_horizontal(self, api_server):
        """Square images default to horizontal (most iPads run landscape)."""
        self._drop_ai_photo(api_server, "square.png", 800, 800)
        record = self._list_ai(api_server)[0]
        assert record["template_type"] == 1
        assert 1 <= record["template_id"] <= 5

    def test_unreadable_dimensions_default_to_horizontal(self, api_server):
        """If get_image_size returns 0, fall back to horizontal."""
        # Random bytes — neither a JPEG nor a PNG, so get_image_size
        # returns (0, 0) and the helper falls through to horizontal.
        device_dir = str(api_server["tmp_path"] / "photos_with_ai" / "42")
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, "bogus.png"), "wb") as f:
            f.write(b"not an image at all")
        record = self._list_ai(api_server)[0]
        assert record["template_type"] == 1
        assert 1 <= record["template_id"] <= 5

    def test_assignment_is_stable_across_reads(self, api_server):
        """Repeated mediaList calls return the same template."""
        self._drop_ai_photo(api_server, "stable.png", 1920, 1080)
        first = self._list_ai(api_server)[0]
        for _ in range(5):
            again = self._list_ai(api_server)[0]
            assert again["template_id"] == first["template_id"]
            assert again["template_type"] == first["template_type"]

    def test_admin_edit_is_preserved(self, api_server):
        """An explicit /api/ipad/media/update wins over auto-assign.

        Once the admin (or the iPad app) saves a template, subsequent
        mediaList calls must not overwrite it with a fresh random pick.
        """
        self._drop_ai_photo(api_server, "edit.png", 1920, 1080)
        media_id = self._list_ai(api_server)[0]["id"]
        # Pick a template_id that the auto-assignment can't accidentally
        # land on (auto picks 1..5; we use 4 with template_type=2 which
        # auto-horizontal would never combine).
        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": media_id, "display": "",
                  "template_id": 4, "template_type": 2},
        )
        record = self._list_ai(api_server)[0]
        assert record["template_id"] == 4
        assert record["template_type"] == 2

    def test_normal_photos_are_not_assigned(self, api_server):
        """The auto-assignment only fires for type=ai photos."""
        device_dir = str(api_server["tmp_path"] / "photos" / "42")
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, "normal.png"), "wb") as f:
            f.write(self._png_with_dimensions(1920, 1080))
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 42, "page": 1, "limit": 10,
                    "type": "normal"},
        )
        record = resp.json()["data"]["list"][0]
        assert record["template_id"] == 0
        assert record["template_type"] == 0

    def test_set_media_assigns_template_immediately(self, api_server):
        """setMedia for an AI photo persists a template right away.

        Without this, the first call to mediaList would pick the template
        — which means the iPad would get template=0 in the MQTT
        ``ipad/media/create`` event that fires from setMedia, then a
        different value on the next reload. We want them to agree.
        """
        png = self._png_with_dimensions(1920, 1080)
        upload_resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("ai.png", png, "image/png")},
            data={"x:suffix": "png"},
        )
        asset_id = str(upload_resp.json()["data"]["id"])
        requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 42, "asset_ids": [asset_id], "type": "ai"},
        )
        record = self._list_ai(api_server)[0]
        # The template was rolled inside setMedia, before mediaList
        # was hit, so the value here came from the persisted record.
        assert record["template_type"] == 1
        assert 1 <= record["template_id"] <= 5

    def test_set_media_assigns_vertical_for_portrait(self, api_server):
        """setMedia respects the image's orientation."""
        png = self._png_with_dimensions(720, 1280)
        upload_resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("portrait.png", png, "image/png")},
            data={"x:suffix": "png"},
        )
        asset_id = str(upload_resp.json()["data"]["id"])
        requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 42, "asset_ids": [asset_id], "type": "ai"},
        )
        record = self._list_ai(api_server)[0]
        assert record["template_type"] == 2
        assert 1 <= record["template_id"] <= 4

    def test_independent_templates_per_photo(self, api_server):
        """Each photo gets its own template choice."""
        self._drop_ai_photo(api_server, "a.png", 1920, 1080)
        self._drop_ai_photo(api_server, "b.png", 1080, 1920)
        records = {r["asset"]["filename"]: r for r in self._list_ai(api_server)}
        assert records["a.png"]["template_type"] == 1
        assert records["b.png"]["template_type"] == 2

    def test_helper_pure_function(self, tmp_path):
        """Unit-level: _pick_ai_template_for_image picks per orientation.

        Hits the helper directly so the orientation logic is covered
        without HTTP plumbing in between.
        """
        from src.api.handlers.media import _pick_ai_template_for_image

        def _png(w, h):
            path = tmp_path / f"img_{w}x{h}.png"
            path.write_bytes(make_png(w, h))
            return str(path)

        # Sample many calls to confirm both the type and the id range.
        for _ in range(50):
            tid, ttype = _pick_ai_template_for_image(_png(1920, 1080))
            assert ttype == 1
            assert 1 <= tid <= 5
            tid, ttype = _pick_ai_template_for_image(_png(1080, 1920))
            assert ttype == 2
            assert 1 <= tid <= 4
            tid, ttype = _pick_ai_template_for_image(_png(800, 800))
            assert ttype == 1
            assert 1 <= tid <= 5


class TestAITemplateFollowsDisplayOrientation:
    """``template_type`` is the DISPLAY orientation, not the photo's.

    The display webapp selects its Gallery Mode catalog from its own
    orientation and ignores a stored ``template_id`` whose
    ``template_type`` does not match (verified on an iPad 4 with webapp
    2.3.8, ``docs/gallery-mode-templates-2.3.8.md`` §1). So when the
    display's session has reported its dimensions, the auto-assignment
    must use that orientation; only sessions without dimensions fall
    back to the photo's orientation (covered by the class above, whose
    device ``42`` has no session).
    """

    def _seed_display(self, base_url, uuid, width, height):
        device_id = get_device_id(base_url, uuid)
        requests.post(
            f"{base_url}/api/ipad/device/bindUser",
            json={"uuid": uuid, "device_name": "Frame",
                  "device_type": "ios", "ios_version": "16.0",
                  "width": width, "height": height},
        )
        return str(device_id)

    def _drop_and_list(self, api_server, device_id, filename, w, h):
        device_dir = str(
            api_server["tmp_path"] / "photos_with_ai" / device_id)
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, filename), "wb") as f:
            f.write(make_png(w, h))
        items = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": device_id, "page": 1, "limit": 50,
                    "type": "ai"},
        ).json()["data"]["list"]
        return {os.path.basename(i["asset"]["url"]).split("_")[0]: i
                for i in items}

    def test_portrait_photo_on_landscape_display_gets_type_1(
            self, api_server):
        dev = self._seed_display(api_server["url"], "ori-land", 1024, 768)
        recs = self._drop_and_list(api_server, dev, "tall.png", 600, 900)
        rec = recs["tall"]
        assert rec["template_type"] == 1
        assert 1 <= rec["template_id"] <= 5

    def test_landscape_photo_on_portrait_display_gets_type_2(
            self, api_server):
        dev = self._seed_display(api_server["url"], "ori-port", 768, 1024)
        recs = self._drop_and_list(api_server, dev, "wide.png", 900, 600)
        rec = recs["wide"]
        assert rec["template_type"] == 2
        assert 1 <= rec["template_id"] <= 4

    def test_session_without_dimensions_falls_back_to_photo(
            self, api_server):
        # login only: width/height stay 0 → photo orientation decides
        dev = str(get_device_id(api_server["url"], "ori-nodims"))
        recs = self._drop_and_list(api_server, dev, "tall.png", 600, 900)
        assert recs["tall"]["template_type"] == 2

    def test_set_media_uses_display_orientation(self, api_server):
        """The setMedia path (upload → classify) also follows the display."""
        dev = self._seed_display(api_server["url"], "ori-set", 1024, 768)
        png = make_png(600, 900)
        up = requests.post(
            f"{api_server['url']}/api/user/asset/uploader",
            files={"file": ("tall.png", png, "image/png")},
            data={"more": "1", "driver": "local"},
        ).json()
        asset_id = str(up["data"]["id"])
        requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": int(dev), "asset_ids": [asset_id],
                  "type": "ai"},
        )
        recs = self._drop_and_list(api_server, dev, "unused.png", 100, 100)
        assert recs["tall"]["template_type"] == 1

    def test_helper_prefers_display_type(self, tmp_path):
        from src.api.handlers.media import _pick_ai_template_for_image
        p = tmp_path / "tall.png"
        p.write_bytes(make_png(600, 900))
        for _ in range(10):
            tid, ttype = _pick_ai_template_for_image(str(p), 1)
            assert ttype == 1 and 1 <= tid <= 5
            tid, ttype = _pick_ai_template_for_image(str(p), 2)
            assert ttype == 2 and 1 <= tid <= 4
            tid, ttype = _pick_ai_template_for_image(str(p), None)
            assert ttype == 2
