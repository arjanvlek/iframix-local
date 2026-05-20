"""POST /api/ipad/media/update (display + template fields)."""
import json
import os

import pytest
import requests

from tests.helpers import login, get_device_id


class TestMediaUpdate:
    """POST /api/ipad/media/update

    Stores per-photo display settings (positionX, positionY) that are
    returned in mediaList responses.
    """

    def _create_photo(self, api_server, device_id="1", filename="test.jpg"):
        """Create a photo and return its media ID."""
        device_dir = str(api_server["tmp_path"] / "photos" / device_id)
        os.makedirs(device_dir, exist_ok=True)
        with open(os.path.join(device_dir, filename), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": device_id, "page": 1, "limit": 10, "type": "normal"},
        )
        records = resp.json()["data"]["list"]
        return next(r["id"] for r in records if r["asset"]["filename"] == filename)

    def test_update_returns_success(self, api_server):
        """Endpoint returns standard success response."""
        media_id = self._create_photo(api_server)
        resp = requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={
                "id": media_id,
                "display": '{"positionX":50,"positionY":16}',
                "template_id": 0,
                "template_type": 0,
            },
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"] is True

    def test_display_persisted_in_media_list(self, api_server):
        """After update, mediaList returns the stored display value."""
        media_id = self._create_photo(api_server)
        display = '{"positionX":50,"positionY":16}'

        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": media_id, "display": display, "template_id": 0, "template_type": 0},
        )

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        record = resp.json()["data"]["list"][0]
        assert record["display"] == display

    def test_display_default_empty_string(self, api_server):
        """Without an update, display is an empty string."""
        self._create_photo(api_server)
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        record = resp.json()["data"]["list"][0]
        assert record["display"] == ""

    def test_update_overwrites_previous(self, api_server):
        """A second update replaces the first."""
        media_id = self._create_photo(api_server)

        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": media_id, "display": '{"positionX":10,"positionY":20}', "template_id": 0, "template_type": 0},
        )
        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": media_id, "display": '{"positionX":80,"positionY":90}', "template_id": 0, "template_type": 0},
        )

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        assert resp.json()["data"]["list"][0]["display"] == '{"positionX":80,"positionY":90}'

    def test_update_independent_per_photo(self, api_server):
        """Display settings for one photo do not affect another."""
        id_a = self._create_photo(api_server, filename="a.jpg")
        id_b = self._create_photo(api_server, filename="b.jpg")

        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": id_a, "display": '{"positionX":1,"positionY":2}', "template_id": 0, "template_type": 0},
        )

        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        records = {r["id"]: r for r in resp.json()["data"]["list"]}
        assert records[id_a]["display"] == '{"positionX":1,"positionY":2}'
        assert records[id_b]["display"] == ""

    def test_template_fields_zero_for_normal(self, api_server):
        """Normal photos keep template_id/template_type = 0.

        Auto-assignment only kicks in for AI photos — for normal photos
        the fields stay at whatever the caller posted (0 here). See
        ``TestAITemplateAssignment`` for the AI side.
        """
        media_id = self._create_photo(api_server)
        requests.post(
            f"{api_server['url']}/api/ipad/media/update",
            json={"id": media_id, "display": '{"positionX":50,"positionY":50}', "template_id": 0, "template_type": 0},
        )
        resp = requests.get(
            f"{api_server['url']}/api/ipad/media/mediaList",
            params={"device_id": 1, "page": 1, "limit": 10, "type": "normal"},
        )
        record = resp.json()["data"]["list"][0]
        assert record["template_id"] == 0
        assert record["template_type"] == 0
