"""Server-side AI template auto-assignment."""
import base64
import json
import os
import struct
import time

import pytest
import requests

from tests.helpers import login, get_device_id


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

    - Match the image's orientation (portrait → vertical, landscape →
      horizontal) so the template visually fits the photo.
    - Stay within the 16:9 catalog ranges (1..5 horizontal, 1..4
      vertical) so it works on every supported iPad without clamping.
    - Be stable across repeated reads.
    - Skip already-assigned photos so admin edits aren't overwritten.
    """

    @staticmethod
    def _png_with_dimensions(width, height):
        """Build a minimal PNG file just long enough for get_image_size.

        ``get_image_size`` reads the first 30 bytes. We need: 8-byte
        signature, 4-byte chunk length, 4-byte chunk type, 8-byte
        width+height, plus a few trailing bytes. The file is not a valid
        PNG to a strict decoder, but the dimension reader does not care.
        """
        import struct
        return (b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR"
                + struct.pack(">II", width, height)
                + b"\x08\x02\x00\x00\x00")

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
        import struct
        from src.api.handlers.media import _pick_ai_template_for_image

        def _png(w, h):
            path = tmp_path / f"img_{w}x{h}.png"
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR"
                + struct.pack(">II", w, h)
                + b"\x08\x02\x00\x00\x00")
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
