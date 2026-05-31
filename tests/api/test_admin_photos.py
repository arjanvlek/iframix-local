"""Admin photo grid: paginated listing (/admin/photos) and on-demand
thumbnails (/admin/thumb).

Both are local-only additions used by the admin panel; they exist so a
display device with hundreds of photos loads quickly — the listing is
paginated and skips per-photo EXIF/caption work, and thumbnails are
downscaled by Pillow, cached on disk, and served with a long immutable
cache header.
"""
import io
import os
import time

import pytest
import requests
from PIL import Image

from tests.helpers import make_png


def _drop_photos(api_server, media_type, count, device_id="42",
                 width=1200, height=900):
    """Write ``count`` real PNGs into the device's photo directory."""
    sub = "photos_with_ai" if media_type == "ai" else "photos"
    device_dir = str(api_server["tmp_path"] / sub / device_id)
    os.makedirs(device_dir, exist_ok=True)
    names = []
    for i in range(count):
        # Zero-padded so the on-disk sort order is deterministic.
        name = f"photo_{i:03d}.png"
        with open(os.path.join(device_dir, name), "wb") as f:
            f.write(make_png(width, height))
        names.append(name)
    return names


class TestAdminPhotosPagination:
    def _get(self, api_server, device_id, media_type, page, page_size):
        return requests.get(
            f"{api_server['url']}/admin/photos",
            params={"device_id": device_id, "type": media_type,
                    "page": page, "page_size": page_size},
        ).json()["data"]

    def test_empty_device_returns_zero_total(self, api_server):
        data = self._get(api_server, "999", "normal", 1, 24)
        assert data["total"] == 0
        assert data["list"] == []

    def test_pagination_slices_the_directory(self, api_server):
        _drop_photos(api_server, "normal", 30)
        first = self._get(api_server, "42", "normal", 1, 24)
        assert first["total"] == 30
        assert first["page"] == 1
        assert len(first["list"]) == 24
        second = self._get(api_server, "42", "normal", 2, 24)
        assert second["total"] == 30
        assert len(second["list"]) == 6
        # No overlap between pages.
        ids1 = {r["id"] for r in first["list"]}
        ids2 = {r["id"] for r in second["list"]}
        assert ids1.isdisjoint(ids2)

    def test_newest_first_ordering(self, api_server):
        names = _drop_photos(api_server, "normal", 5)
        page = self._get(api_server, "42", "normal", 1, 24)
        # scan order is ascending by name; the endpoint reverses it so the
        # most recent upload (last name) is first.
        assert page["list"][0]["filename"] == names[-1]
        assert page["list"][-1]["filename"] == names[0]

    def test_page_size_is_clamped(self, api_server):
        _drop_photos(api_server, "normal", 3)
        data = self._get(api_server, "42", "normal", 1, 99999)
        assert data["page_size"] == 200  # clamped upper bound
        assert len(data["list"]) == 3

    def test_record_shape_normal(self, api_server):
        _drop_photos(api_server, "normal", 1)
        rec = self._get(api_server, "42", "normal", 1, 24)["list"][0]
        assert rec["type"] == "normal"
        assert rec["thumb_url"] == f"/admin/thumb/normal/42/{rec['filename']}"
        assert rec["url"] == f"/photos/42/{rec['filename']}"
        # Normal photos carry no template fields.
        assert "template_id" not in rec

    def test_ai_records_carry_assigned_template(self, api_server):
        # Portrait image -> vertical template (type 2, id 1..4).
        _drop_photos(api_server, "ai", 1, width=720, height=1280)
        rec = self._get(api_server, "42", "ai", 1, 24)["list"][0]
        assert rec["type"] == "ai"
        assert rec["template_type"] == 2
        assert 1 <= rec["template_id"] <= 4
        assert rec["thumb_url"].startswith("/admin/thumb/ai/42/")


class TestAdminThumb:
    def test_generates_downscaled_cached_thumbnail(self, api_server):
        names = _drop_photos(api_server, "normal", 1, width=1200, height=900)
        url = f"{api_server['url']}/admin/thumb/normal/42/{names[0]}"
        resp = requests.get(url)
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "image/jpeg"
        assert "immutable" in resp.headers.get("Cache-Control", "")
        # The thumbnail is downscaled to <=320px on the longest side.
        im = Image.open(io.BytesIO(resp.content))
        assert max(im.size) <= 320
        # And it's materially smaller than the source PNG.
        src = (api_server["tmp_path"] / "photos" / "42" / names[0])
        assert len(resp.content) < src.stat().st_size

        # The cache file lands under the patched THUMBNAILS_DIR.
        cached = (api_server["tmp_path"] / "thumbnails" / "normal" / "42"
                  / (names[0] + ".jpg"))
        assert cached.is_file()

        # A second request still succeeds (served from cache).
        assert requests.get(url).status_code == 200

    def test_ai_thumb_with_dimension_suffix_resolves(self, api_server):
        """AI photo URLs carry a _{w}_{h} suffix; the thumb endpoint must
        strip it to find the on-disk file."""
        names = _drop_photos(api_server, "ai", 1, width=800, height=600)
        stem, ext = os.path.splitext(names[0])
        suffixed = f"{stem}_800_600{ext}"
        resp = requests.get(
            f"{api_server['url']}/admin/thumb/ai/42/{suffixed}")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "image/jpeg"

    def test_missing_file_is_404(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/admin/thumb/normal/42/nope.png")
        assert resp.status_code == 404

    def test_bad_type_is_404(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/admin/thumb/bogus/42/x.png")
        assert resp.status_code == 404

    def test_path_traversal_is_rejected(self, api_server):
        # basename() strips the directory components, so a traversal
        # attempt resolves to a nonexistent file in the device dir -> 404.
        resp = requests.get(
            f"{api_server['url']}/admin/thumb/normal/42/..%2f..%2fetc%2fpasswd")
        assert resp.status_code == 404


class TestDeleteRemovesThumbnail:
    """Deleting a photo (app or admin, both go through delMedia) must also
    remove its cached thumbnail so the cache doesn't outlive the photo."""

    def test_delmedia_removes_cached_thumbnail(self, api_server):
        url = api_server["url"]
        names = _drop_photos(api_server, "ai", 1, width=800, height=600)
        listing = requests.get(
            f"{url}/admin/photos",
            params={"device_id": "42", "type": "ai", "page": 1,
                    "page_size": 24},
        ).json()["data"]["list"]
        media_id = listing[0]["id"]

        # Generate the thumbnail by requesting it.
        assert requests.get(url + listing[0]["thumb_url"]).status_code == 200
        cached = (api_server["tmp_path"] / "thumbnails" / "ai" / "42"
                  / (names[0] + ".jpg"))
        assert cached.is_file()

        # Delete the photo via the shared delMedia endpoint.
        requests.post(
            f"{url}/api/ipad/media/delMedia",
            json={"id": [media_id], "device_id": 42},
        )

        # delMedia removes files in a background thread; poll briefly.
        source = (api_server["tmp_path"] / "photos_with_ai" / "42"
                  / names[0])
        for _ in range(50):
            if not source.exists() and not cached.exists():
                break
            time.sleep(0.1)
        assert not source.exists()
        assert not cached.exists()
