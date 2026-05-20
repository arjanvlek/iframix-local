"""Response envelope shape ({code, msg, data})."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestResponseEnvelope:
    """All responses should use the standard {code, msg, data} envelope."""

    def test_success_envelope_format(self, api_server):
        resp = requests.post(
            f"{api_server['url']}/api/webhook/auth",
            json={"clientid": "test"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["msg"] == "SUCCESS"
        assert "data" in body

    def test_error_response_has_code_and_msg(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/info",
            params={"id": "invalid"},
        )
        body = resp.json()
        assert "code" in body
        assert "msg" in body
