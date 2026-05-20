"""Login and webhook auth."""
import json

import pytest
import requests

from tests.helpers import login, get_device_id


class TestLogin:

    def test_controller_device_is_null(self, api_server):
        """Controller device (xx-device-origin: control) gets device=null."""
        data = login(api_server["url"], "ctrl-uuid-001", origin="control")
        assert data["data"]["device"] is None

    def test_display_device_is_populated(self, api_server):
        """Display device (xx-device-origin: view) gets a populated device record."""
        data = login(api_server["url"], "view-uuid-001", origin="view")
        device = data["data"]["device"]
        assert device is not None
        assert "id" in device
        assert "uuid" in device

    def test_display_device_excludes_extra_fields(self, api_server):
        """Display device record should NOT have is_online, online, icharger, user
        (those only appear on device-index / device-info endpoints)."""
        data = login(api_server["url"], "view-uuid-002", origin="view")
        device = data["data"]["device"]
        assert "is_online" not in device
        assert "online" not in device
        assert "icharger" not in device
        assert "user" not in device

    def test_display_device_has_core_fields(self, api_server):
        """Display device record has all core fields from the spec."""
        data = login(api_server["url"], "view-uuid-003", origin="view")
        device = data["data"]["device"]
        for field in ("id", "uuid", "device_name", "device_type", "is_ipad",
                      "is_h5", "ios_version", "width", "height", "user_id",
                      "bind_at", "created_at", "deleted_at"):
            assert field in device, f"Missing field: {field}"

    def test_user_object_fields(self, api_server):
        """User object matches the spec structure."""
        data = login(api_server["url"], "user-uuid-001", origin="control")
        user = data["data"]["user"]
        for field in ("sex", "birthday", "user_login", "user_nickname",
                      "user_email", "avatar", "mobile", "id"):
            assert field in user, f"Missing user field: {field}"

    def test_user_email_matches_login(self, api_server):
        """user_email should reflect the login username."""
        data = login(api_server["url"], "email-uuid-001", origin="control")
        assert data["data"]["user"]["user_email"] == "test@example.com"

    def test_token_present(self, api_server):
        """Response includes a non-empty token string."""
        data = login(api_server["url"], "token-uuid-001", origin="control")
        token = data["data"]["token"]
        assert isinstance(token, str)
        assert len(token) > 0


class TestWebhookAuth:

    def test_returns_alphanumeric_string(self, api_server):
        """Returns a random alphanumeric string as the MQTT password."""
        resp = requests.post(
            f"{api_server['url']}/api/webhook/auth",
            json={"clientid": "view_test-device"},
        )
        body = resp.json()
        assert body["code"] == 1
        token = body["data"]
        assert isinstance(token, str)
        assert len(token) > 0
        assert token.isalnum()
