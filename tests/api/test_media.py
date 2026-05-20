"""Photo upload, mediaList, setMedia, delMedia, photo serving."""
import base64
import json
import os
import time

import pytest
import requests

from tests.helpers import login, get_device_id


class TestMediaAndPhotos:
    """Photo listing, upload, and serving.

    The local server serves photos from local directories instead of
    Qiniu CDN. URLs are local paths (/photos/...).
    """

    def test_media_list_empty(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"]["list"] == []

    def test_media_list_with_photo(self, api_server):
        """A JPEG in the device's photos directory appears in the media list."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, "test.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        body = resp.json()
        assert len(body["data"]["list"]) == 1
        photo = body["data"]["list"][0]
        assert photo["type"] == "normal"
        assert photo["status"] == 2
        assert photo["device_id"] == 1
        assert photo["asset"]["suffix"] == "jpg"
        assert photo["asset"]["url"] == f"{api_server['url']}/photos/1/test.jpg"

    def test_media_list_per_device_isolation(self, api_server):
        """Photos for one device are not returned for another device."""
        for dev_id in ("1", "2"):
            device_dir = str(api_server["tmp_path"] / "photos" / dev_id)
            os.makedirs(device_dir, exist_ok=True)
            with open(os.path.join(device_dir, f"photo_{dev_id}.jpg"), "wb") as f:
                f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        resp1 = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        resp2 = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 2, "page": 1, "limit": 10, "type": "normal"},
        )
        list1 = resp1.json()["data"]["list"]
        list2 = resp2.json()["data"]["list"]
        assert len(list1) == 1
        assert len(list2) == 1
        assert list1[0]["asset"]["filename"] == "photo_1.jpg"
        assert list2[0]["asset"]["filename"] == "photo_2.jpg"

    def test_media_list_url_is_full_url(self, api_server):
        """Asset url must be a full URL (scheme + host), not just a path."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, "1776107930467_1776107930969_640_1136.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        url = resp.json()["data"]["list"][0]["asset"]["url"]
        assert url.startswith("http://")
        assert "1776107930467_1776107930969_640_1136.jpg" in url

    def test_media_pagination_string_types(self, api_server):
        """Per the original server, page and limit are strings in media pagination."""
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": "1", "limit": "10", "type": "normal"},
        )
        pagination = resp.json()["data"]["pagination"]
        assert isinstance(pagination["page"], str)
        assert isinstance(pagination["limit"], str)

    def test_media_record_fields(self, api_server):
        """Each media record has all expected fields from the spec."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, "fields.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        record = resp.json()["data"]["list"][0]
        for field in ("id", "device_id", "title", "status", "display",
                      "fill_mode", "template_id", "template_type", "type",
                      "asset_id", "remark", "created_id", "created_at",
                      "deleted_at", "asset"):
            assert field in record, f"Missing media field: {field}"

        asset = record["asset"]
        for field in ("id", "file_path", "filename", "suffix", "more",
                      "width", "height", "url"):
            assert field in asset, f"Missing asset field: {field}"

    def test_photo_serve(self, api_server):
        """Photos can be served directly by device_id and filename."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        with open(os.path.join(device_dir, "serve_test.jpg"), "wb") as f:
            f.write(content)

        resp = requests.get(f"{api_server['url']}/photos/1/serve_test.jpg")
        assert resp.status_code == 200
        assert resp.content == content

    def test_asset_upload(self, api_server):
        """POST /api/user/asset/upload saves to temp dir, not final dir."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("upload.jpg", content, "image/jpeg")},
            data={"x:suffix": "jpg"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"]["suffix"] == "jpg"
        assert "url" in body["data"]
        assert "file_path" in body["data"]

        # File should be in temp dir, not in photos/
        filename = body["data"]["filename"]
        temp_dir = str(api_server["tmp_path"] / "photos_temp")
        photos_dir = str(api_server["tmp_path"] / "photos")
        assert os.path.isfile(os.path.join(temp_dir, filename))
        assert not os.path.isfile(os.path.join(photos_dir, filename))

    def test_asset_upload_url_is_full(self, api_server):
        """Asset upload returns a full URL (scheme + host), not just a path."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("fullurl.jpg", content, "image/jpeg")},
            data={"x:suffix": "jpg"},
        )
        url = resp.json()["data"]["url"]
        assert url.startswith("http://") or url.startswith("https://")

    def test_asset_uploader(self, api_server):
        """POST /api/user/asset/uploader (app 2.2.29+) saves to temp dir."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/uploader",
            files={"file": ("20260423/1776897394863_4624_3468.jpg", content, "application/octet-stream")},
            data={"more": "", "driver": "r2"},
        )
        body = resp.json()
        assert body["code"] == 1
        data = body["data"]
        # Real server keeps only the basename of the uploaded filename
        assert data["filename"] == "1776897394863_4624_3468.jpg"
        assert data["suffix"] == "jpg"
        assert data["more"] == ""
        assert data["width"] is None
        assert data["height"] is None
        assert (data["url"].startswith("http://")
                or data["url"].startswith("https://"))

        # File lands in temp dir, not photos/
        temp_dir = str(api_server["tmp_path"] / "photos_temp")
        assert os.path.isfile(os.path.join(temp_dir, data["filename"]))

    def test_asset_uploader_then_set_media(self, api_server):
        """The uploader flow integrates with setMedia the same as /upload."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        upload_resp = requests.post(
            f"{api_server['url']}/api/user/asset/uploader",
            files={"file": ("20260423/1776897394863_4624_3468.jpg", content, "application/octet-stream")},
            data={"more": "", "driver": "r2"},
        )
        asset_id = str(upload_resp.json()["data"]["id"])
        filename = upload_resp.json()["data"]["filename"]

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 29540, "asset_ids": [asset_id], "type": "normal"},
        )
        assert resp.json()["code"] == 1
        photos_dir = str(api_server["tmp_path"] / "photos" / "29540")
        assert os.path.isfile(os.path.join(photos_dir, filename))

    def test_set_media_normal(self, api_server):
        """setMedia with type=normal moves file from temp to photos/{device_id}/."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        upload_resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("normal.jpg", content, "image/jpeg")},
            data={"x:suffix": "jpg"},
        )
        asset_id = str(upload_resp.json()["data"]["id"])
        filename = upload_resp.json()["data"]["filename"]

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 29540, "asset_ids": [asset_id], "type": "normal"},
        )
        assert resp.json()["code"] == 1

        device_dir = str(api_server["tmp_path"] / "photos" / "29540")
        temp_dir = str(api_server["tmp_path"] / "photos_temp")
        assert os.path.isfile(os.path.join(device_dir, filename))
        assert not os.path.isfile(os.path.join(temp_dir, filename))

    def test_set_media_ai(self, api_server):
        """setMedia with type=ai moves file from temp to photos_with_ai/{device_id}/."""
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        upload_resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            files={"file": ("ai_photo.jpg", content, "image/jpeg")},
            data={"x:suffix": "jpg"},
        )
        asset_id = str(upload_resp.json()["data"]["id"])
        filename = upload_resp.json()["data"]["filename"]

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 29540, "asset_ids": [asset_id], "type": "ai"},
        )
        assert resp.json()["code"] == 1

        device_dir = str(api_server["tmp_path"] / "photos_with_ai" / "29540")
        temp_dir = str(api_server["tmp_path"] / "photos_temp")
        assert os.path.isfile(os.path.join(device_dir, filename))
        assert not os.path.isfile(os.path.join(temp_dir, filename))

    def test_set_media_multiple_assets(self, api_server):
        """setMedia can move multiple assets at once."""
        asset_ids = []
        filenames = []
        for i in range(3):
            content = b"\xff\xd8\xff\xe0" + bytes([i]) * 50
            resp = requests.post(
                f"{api_server['url']}/api/user/asset/upload",
                files={"file": (f"multi_{i}.jpg", content, "image/jpeg")},
                data={"x:suffix": "jpg"},
            )
            data = resp.json()["data"]
            asset_ids.append(str(data["id"]))
            filenames.append(data["filename"])

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 29540, "asset_ids": asset_ids, "type": "normal"},
        )
        assert resp.json()["code"] == 1

        device_dir = str(api_server["tmp_path"] / "photos" / "29540")
        for filename in filenames:
            assert os.path.isfile(os.path.join(device_dir, filename))

    def test_set_media_unknown_asset_id(self, api_server):
        """setMedia with unknown asset_ids still returns success."""
        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/setMedia",
            json={"device_id": 29540, "asset_ids": ["99999"], "type": "normal"},
        )
        assert resp.json()["code"] == 1

    def test_del_media(self, api_server):
        """delMedia deletes a photo by its media ID."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        filepath = os.path.join(device_dir, "delete_me.jpg")
        with open(filepath, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        # Get the media ID from the list endpoint
        list_resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        media_id = list_resp.json()["data"]["list"][0]["id"]

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/delMedia",
            json={"device_id": 1, "id": [media_id]},
        )
        assert resp.json()["code"] == 1

        # Deletion happens in a background thread; wait briefly
        time.sleep(0.2)
        assert not os.path.isfile(filepath)

    def test_del_media_preserves_other_photos(self, api_server):
        """delMedia only removes the targeted photo, not others."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        for name in ("keep.jpg", "remove.jpg"):
            with open(os.path.join(device_dir, name), "wb") as f:
                f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        list_resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        records = list_resp.json()["data"]["list"]
        target = next(r for r in records if r["asset"]["filename"] == "remove.jpg")

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/delMedia",
            json={"device_id": 1, "id": [target["id"]]},
        )
        assert resp.json()["code"] == 1

        time.sleep(0.2)
        assert not os.path.isfile(os.path.join(device_dir, "remove.jpg"))
        assert os.path.isfile(os.path.join(device_dir, "keep.jpg"))

    def test_del_media_multiple(self, api_server):
        """delMedia can delete multiple photos in a single request."""
        device_dir = str(api_server["tmp_path"] / "photos" / "1")
        os.makedirs(device_dir, exist_ok=True)
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            with open(os.path.join(device_dir, name), "wb") as f:
                f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        list_resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        records = list_resp.json()["data"]["list"]
        del_ids = [r["id"] for r in records if r["asset"]["filename"] in ("a.jpg", "c.jpg")]

        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/delMedia",
            json={"device_id": 1, "id": del_ids},
        )
        assert resp.json()["code"] == 1

        time.sleep(0.2)
        assert not os.path.isfile(os.path.join(device_dir, "a.jpg"))
        assert os.path.isfile(os.path.join(device_dir, "b.jpg"))
        assert not os.path.isfile(os.path.join(device_dir, "c.jpg"))
