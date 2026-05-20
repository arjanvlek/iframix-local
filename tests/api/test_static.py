"""Static download page + privacy policy."""
import json
import os

import pytest
import requests

from tests.helpers import login, get_device_id


class TestPrivacyPolicy:
    """GET /download/xieyi/index.html — privacy policy page"""

    def test_serves_privacy_policy(self, api_server):
        """Returns the privacy policy HTML page."""
        # Create the xieyi directory and index.html in the test webapp dir
        xieyi_dir = os.path.join(
            str(api_server["tmp_path"]), "webapp", "download", "xieyi")
        os.makedirs(xieyi_dir, exist_ok=True)
        with open(os.path.join(xieyi_dir, "index.html"), "w") as f:
            f.write("<html><body>Privacy Policy</body></html>")

        resp = requests.get(
            f"{api_server['url']}/download/xieyi/index.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["Content-Type"]
        assert "Privacy Policy" in resp.text

    def test_returns_404_for_missing_file(self, api_server):
        """Returns 404 for non-existent files under /download/xieyi/."""
        resp = requests.get(
            f"{api_server['url']}/download/xieyi/nonexistent.html")
        assert resp.status_code == 404


class TestPackageProject:
    """GET /project/api/captcha/package/project — download page backend"""

    def test_returns_package_info(self, api_server):
        """Returns iFramixPro package info with both platform items."""
        resp = requests.get(
            f"{api_server['url']}/project/api/captcha/package/project",
            params={"name": "iFramixPro"},
        )
        body = resp.json()
        assert body["code"] == 1
        data = body["data"]
        assert data["project_name"] == "iFramixPro"
        assert data["url"] == "https://ifp.ga.codethriving.com/download"
        assert len(data["items"]) == 2
        android = data["items"][0]
        assert android["store_type"] == "android"
        assert android["version"] == "2.2.27"
        ios = data["items"][1]
        assert ios["store_type"] == "ios"
        assert ios["store_address"].startswith("https://apps.apple.com/")
