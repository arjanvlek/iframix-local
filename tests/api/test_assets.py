"""Asset upload tokens + Qiniu compatibility shim."""
import base64
import json
import time

import pytest
import requests

from tests.helpers import login, get_device_id


class TestAssetToken:
    """POST /api/user/asset/token"""

    def test_returns_local_domain(self, api_server):
        """Returns local /photos/ path instead of Qiniu CDN domain."""
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/token",
            json={"expire": 3600},
        )
        body = resp.json()
        assert body["code"] == 1
        assert "token" in body["data"]
        assert "domain" in body["data"]
        assert body["data"]["domain"] == "/photos/"

    def test_token_is_qiniu_format(self, api_server):
        """Token has Qiniu format: AccessKey:Sign:EncodedPolicy."""
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/token",
            json={"expire": 3600},
        )
        token = resp.json()["data"]["token"]
        parts = token.split(":")
        assert len(parts) == 3, f"expected 3 colon-separated parts, got {len(parts)}"

        # Part 1: access key (non-empty string)
        assert len(parts[0]) > 0

        # Part 2: base64-encoded HMAC-SHA1 (decodes to 20 bytes)
        sign_bytes = base64.b64decode(parts[1])
        assert len(sign_bytes) == 20

        # Part 3: base64-encoded JSON policy
        policy = json.loads(base64.b64decode(parts[2]))
        assert "callbackUrl" in policy
        assert "/api/user/asset/upload" in policy["callbackUrl"]
        assert "deadline" in policy
        assert policy["deadline"] > int(time.time())


class TestQiniuQuery:
    """GET /v4/query — Qiniu SDK region lookup (api.qiniu.com redirected)"""

    def test_returns_hosts(self, api_server):
        """Returns hosts list with local upload domain."""
        resp = requests.get(
            f"{api_server['url']}/v4/query",
            params={"ak": "testkey", "bucket": "flosscn"},
        )
        body = resp.json()
        assert "hosts" in body
        assert len(body["hosts"]) == 1
        host = body["hosts"][0]
        assert host["region"] == "z2"
        assert "ifp.ga.codethriving.com" in host["up"]["domains"]

    def test_upload_to_root(self, api_server):
        """POST / with multipart upload works (Qiniu SDK upload path)."""

        boundary = "testboundary123"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="token"\r\n\r\n'
            f"faketoken\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="key"\r\n\r\n'
            f"default/1/test.jpg\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="x:suffix"\r\n\r\n'
            f"jpg\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="test.jpg"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
            f"fakejpegdata\r\n"
            f"--{boundary}--\r\n"
        )
        resp = requests.post(
            f"{api_server['url']}/",
            data=body.encode(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        result = resp.json()
        assert result["code"] == 1
        assert result["data"]["suffix"] == "jpg"

    def test_upload_with_lowercase_headers(self, api_server):
        """Qiniu SDK sends lowercase content-disposition headers."""
        boundary = "----dio-boundary-1234567890"
        body = (
            f"--{boundary}\r\n"
            f'content-disposition: form-data; name="token"\r\n\r\n'
            f"faketoken\r\n"
            f"--{boundary}\r\n"
            f'content-disposition: form-data; name="key"\r\n\r\n'
            f"default/1/qiniu_test.jpg\r\n"
            f"--{boundary}\r\n"
            f'content-disposition: form-data; name="x:suffix"\r\n\r\n'
            f"jpg\r\n"
            f"--{boundary}\r\n"
            f'content-disposition: form-data; name="file"; '
            f'filename="qiniu_test.jpg"\r\n'
            f"content-type: application/octet-stream\r\n\r\n"
            f"fakejpegdata\r\n"
            f"--{boundary}--\r\n"
        )
        resp = requests.post(
            f"{api_server['url']}/api/user/asset/upload",
            data=body.encode(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        result = resp.json()
        assert result["code"] == 1
        assert result["data"]["filename"] == "qiniu_test.jpg"
