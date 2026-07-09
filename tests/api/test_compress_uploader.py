"""POST /api/user/asset/compress/uploader (iFramix Pro app 2.3.3+).

The display webapp posts ``{driver: "r2", file_path: <asset url>, width,
height}`` when a pre-resized variant of a photo failed to load, and
expects back a URL for a resized copy. Against the cloud this only fires
for R2-hosted photos; the local implementation resolves the URL to the
local photo, generates the variant with Pillow, and serves it from
``/photos_compressed/``.
"""
import io
import os
import time

import requests
from PIL import Image


def _write_jpeg(path, width, height, color=(40, 90, 160)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (width, height), color).save(path, "JPEG")


def _photo_url(api_server, device_id, filename, ai=False):
    prefix = "photos_with_ai" if ai else "photos"
    return f"{api_server['url']}/{prefix}/{device_id}/{filename}"


def _compress(api_server, file_path, width=None, height=None):
    body = {"driver": "r2", "file_path": file_path}
    if width is not None:
        body["width"] = width
    if height is not None:
        body["height"] = height
    return requests.post(
        f"{api_server['url']}/api/user/asset/compress/uploader", json=body)


class TestCompressUploader:

    def test_generates_and_serves_resized_variant(self, api_server):
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "big.jpg")
        _write_jpeg(src, 800, 600)

        resp = _compress(
            api_server, _photo_url(api_server, 1, "big.jpg"),
            width=200, height=150)
        body = resp.json()
        assert body["code"] == 1
        url = body["data"]
        assert url == (f"{api_server['url']}/photos_compressed/normal/1"
                       f"/big.jpg/200x150.jpg")

        served = requests.get(url)
        assert served.status_code == 200
        with Image.open(io.BytesIO(served.content)) as im:
            assert im.format == "JPEG"
            assert im.size == (200, 150)

    def test_aspect_ratio_preserved_within_box(self, api_server):
        """Image.thumbnail fits within the box; a landscape source asked
        into a square box is constrained by its width."""
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "wide.jpg")
        _write_jpeg(src, 800, 400)

        resp = _compress(
            api_server, _photo_url(api_server, 1, "wide.jpg"),
            width=200, height=200)
        url = resp.json()["data"]
        served = requests.get(url)
        with Image.open(io.BytesIO(served.content)) as im:
            assert im.size == (200, 100)

    def test_ai_photo_with_dimension_suffix_resolves(self, api_server):
        """AI asset URLs carry the _{w}_{h} suffix the server itself adds;
        the compress endpoint must strip it to find the source file."""
        src = os.path.join(
            str(api_server["tmp_path"]), "photos_with_ai", "1", "art.jpg")
        _write_jpeg(src, 640, 480)

        resp = _compress(
            api_server, _photo_url(api_server, 1, "art_640_480.jpg", ai=True),
            width=100, height=75)
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == (
            f"{api_server['url']}/photos_compressed/ai/1"
            f"/art.jpg/100x75.jpg")
        served = requests.get(body["data"])
        assert served.status_code == 200
        with Image.open(io.BytesIO(served.content)) as im:
            assert im.size == (100, 75)

    def test_source_already_small_returns_original_url(self, api_server):
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "small.jpg")
        _write_jpeg(src, 100, 80)

        original_url = _photo_url(api_server, 1, "small.jpg")
        resp = _compress(api_server, original_url, width=400, height=300)
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == original_url

    def test_missing_width_returns_original_url(self, api_server):
        """The app omits the dimensions when it has no usable
        photoMaxWidth — nothing to compress then."""
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "nodim.jpg")
        _write_jpeg(src, 800, 600)

        original_url = _photo_url(api_server, 1, "nodim.jpg")
        resp = _compress(api_server, original_url)
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] == original_url

    def test_missing_height_constrains_width_only(self, api_server):
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "tall.jpg")
        _write_jpeg(src, 400, 800)

        resp = _compress(
            api_server, _photo_url(api_server, 1, "tall.jpg"), width=200)
        url = resp.json()["data"]
        served = requests.get(url)
        with Image.open(io.BytesIO(served.content)) as im:
            assert im.size == (200, 400)

    def test_unknown_photo_fails_with_nonzero_code(self, api_server):
        """The webapp treats data.code != 1 as failure and memoises it."""
        resp = _compress(
            api_server, _photo_url(api_server, 1, "missing.jpg"),
            width=200, height=150)
        assert resp.json()["code"] != 1

    def test_non_photo_path_fails(self, api_server):
        for bad in (f"{api_server['url']}/static/js/app.js",
                    "/etc/passwd",
                    "https://levifafafafa.top/default/883/photo.jpg",
                    ""):
            resp = _compress(api_server, bad, width=200, height=150)
            assert resp.json()["code"] != 1, bad

    def test_variant_is_cached_on_disk(self, api_server):
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "cache.jpg")
        _write_jpeg(src, 800, 600)

        url = _photo_url(api_server, 1, "cache.jpg")
        first = _compress(api_server, url, width=200, height=150)
        variant = os.path.join(
            str(api_server["tmp_path"]), "photos_compressed", "normal", "1",
            "cache.jpg", "200x150.jpg")
        assert os.path.isfile(variant)
        mtime = os.path.getmtime(variant)

        second = _compress(api_server, url, width=200, height=150)
        assert second.json()["data"] == first.json()["data"]
        assert os.path.getmtime(variant) == mtime  # not regenerated

    def test_serve_rejects_bad_variant_paths(self, api_server):
        base = f"{api_server['url']}/photos_compressed"
        for path in ("/normal/1/x.jpg/evil.txt",
                     "/normal/1/x.jpg/200x150.png",
                     "/weird/1/x.jpg/200x150.jpg",
                     "/normal/nodigit/x.jpg/200x150.jpg",
                     "/normal/1/200x150.jpg"):
            resp = requests.get(base + path)
            assert resp.status_code == 404, path

    def test_del_media_removes_variants(self, api_server):
        """delMedia drops a photo's compressed variants with the photo."""
        import hashlib
        src = os.path.join(
            str(api_server["tmp_path"]), "photos", "1", "gone.jpg")
        _write_jpeg(src, 800, 600)
        _compress(api_server, _photo_url(api_server, 1, "gone.jpg"),
                  width=200, height=150)
        variants_dir = os.path.join(
            str(api_server["tmp_path"]), "photos_compressed", "normal", "1",
            "gone.jpg")
        assert os.path.isdir(variants_dir)

        file_hash = int.from_bytes(
            hashlib.sha256(b"gone.jpg").digest()[:8], "big")
        media_id = str(file_hash % (10 ** 18))
        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/delMedia",
            json={"id": [media_id], "device_id": 1})
        assert resp.json()["code"] == 1

        # Deletion runs in a background thread
        for _ in range(50):
            if not os.path.isdir(variants_dir):
                break
            time.sleep(0.1)
        assert not os.path.isfile(src)
        assert not os.path.isdir(variants_dir)
