"""Asynchronous per-device `last_active` presence tracking."""
import time

import requests

from src.api import activity
from src.api.persistence import load_sessions
from tests.helpers import login


def _flush_activity():
    """Drain the async activity writer so writes are visible to assertions."""
    activity.flush(timeout=5)


class TestMigration:

    def test_seeded_session_has_last_active_default_zero(self, api_server):
        """A freshly logged-in session row carries a last_active value.

        The login flow sets last_active = last_login, so it is non-zero, but
        the column itself exists (proving the v9 migration ran) and is an int.
        """
        login(api_server["url"], "migrate-uuid-001", origin="view")
        sessions = load_sessions()
        sess = sessions["migrate-uuid-001"]
        assert "last_active" in sess
        assert isinstance(sess["last_active"], int)
        assert sess["last_active"] > 0


class TestHttpHook:

    def test_get_request_with_device_header_bumps_last_active(
            self, api_server):
        """A GET carrying XX-Device-Uuid updates the session's last_active."""
        activity.reset_for_tests()
        login(api_server["url"], "active-uuid-001", origin="view")

        # Force last_active stale so we can observe a new write.
        from src.api.persistence import touch_session_last_active
        touch_session_last_active("active-uuid-001", 1)
        activity.reset_for_tests()

        before = int(time.time())
        resp = requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            headers={"XX-Device-Uuid": "active-uuid-001"},
        )
        assert resp.status_code == 200
        _flush_activity()

        sess = load_sessions()["active-uuid-001"]
        assert sess["last_active"] >= before


class TestThrottle:

    def test_two_rapid_requests_write_once(self, api_server):
        """Two requests within the throttle window only schedule one write."""
        activity.reset_for_tests()
        login(api_server["url"], "throttle-uuid-001", origin="view")

        from src.api.persistence import touch_session_last_active
        touch_session_last_active("throttle-uuid-001", 1)
        activity.reset_for_tests()

        for _ in range(2):
            requests.get(
                f"{api_server['url']}/api/ipad/device/index",
                headers={"XX-Device-Uuid": "throttle-uuid-001"},
            )
        _flush_activity()

        # Both requests landed in the same WRITE_INTERVAL window, so the
        # throttle map records exactly one scheduled write for the device.
        with activity._throttle_lock:
            assert "throttle-uuid-001" in activity._last_written
        sess = load_sessions()["throttle-uuid-001"]
        assert sess["last_active"] > 1

    def test_unknown_uuid_creates_no_session_row(self, api_server):
        """A request for an unknown device must not create a session row."""
        activity.reset_for_tests()
        requests.get(
            f"{api_server['url']}/api/ipad/device/index",
            headers={"XX-Device-Uuid": "ghost-uuid-001"},
        )
        _flush_activity()

        # touch_session_last_active is a no-op for an uuid with no row.
        assert "ghost-uuid-001" not in load_sessions()


class TestMissingHeader:

    def test_request_without_header_enqueues_nothing(self, api_server):
        """No XX-Device-Uuid header => no activity recorded for any device."""
        activity.reset_for_tests()
        requests.get(f"{api_server['url']}/api/ipad/device/index")
        _flush_activity()

        with activity._throttle_lock:
            assert activity._last_written == {}
