"""GET /api/ipad/icharger2/index (charger readings)."""
import json
import sqlite3
import time

import pytest
import requests

from tests.helpers import login, get_device_id


class TestIcharger2Index:
    """GET /api/ipad/icharger2/index"""

    def test_empty_for_unknown_mac(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/icharger2/index",
            params={"mac": "00:00:00:00:00:00", "limit": "-1"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"]["list"] == []
        assert body["data"]["pagination"]["totalCount"] == 0

    def test_pagination_structure(self, api_server):
        resp = requests.get(
            f"{api_server['url']}/api/ipad/icharger2/index",
            params={"mac": "00:00:00:00:00:00", "limit": "-1"},
        )
        pagination = resp.json()["data"]["pagination"]
        assert "page" in pagination
        assert "limit" in pagination
        assert "totalCount" in pagination

    def test_returns_readings(self, api_server):
        """Readings in the database are returned with correct formatting."""
        import sqlite3
        db_path = str(api_server["tmp_path"] / "test.db")
        conn = sqlite3.connect(db_path)
        mac = "94:51:DC:66:96:7E"
        now = int(time.time())
        conn.execute(
            "INSERT INTO charger_readings (id, mac, voltage, current_, add_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (1001, mac, 5.14, 0.31, now))
        conn.execute(
            "INSERT INTO charger_readings (id, mac, voltage, current_, add_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (1002, mac, 5.12, 0.15, now - 10))
        conn.commit()
        conn.close()

        resp = requests.get(
            f"{api_server['url']}/api/ipad/icharger2/index",
            params={"mac": mac, "limit": "-1"},
        )
        body = resp.json()
        assert body["code"] == 1
        assert body["data"]["pagination"]["totalCount"] == 2
        records = body["data"]["list"]
        assert len(records) == 2
        # Newest first
        assert records[0]["add_time"] >= records[1]["add_time"]
        # Formatted as 2 decimal places
        assert records[0]["voltage"] == "5.14"
        assert records[0]["current"] == "0.31"
        assert records[1]["voltage"] == "5.12"
        assert records[1]["current"] == "0.15"
        # IDs are strings
        assert isinstance(records[0]["id"], str)

    def test_filters_by_mac(self, api_server):
        """Only readings matching the requested MAC are returned."""
        import sqlite3
        db_path = str(api_server["tmp_path"] / "test.db")
        conn = sqlite3.connect(db_path)
        now = int(time.time())
        conn.execute(
            "INSERT INTO charger_readings (id, mac, voltage, current_, add_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (2001, "AA:BB:CC:DD:EE:FF", 5.0, 0.1, now))
        conn.execute(
            "INSERT INTO charger_readings (id, mac, voltage, current_, add_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (2002, "11:22:33:44:55:66", 4.0, 0.2, now))
        conn.commit()
        conn.close()

        resp = requests.get(
            f"{api_server['url']}/api/ipad/icharger2/index",
            params={"mac": "AA:BB:CC:DD:EE:FF", "limit": "-1"},
        )
        body = resp.json()
        assert body["data"]["pagination"]["totalCount"] == 1
        assert body["data"]["list"][0]["mac"] == "AA:BB:CC:DD:EE:FF"
