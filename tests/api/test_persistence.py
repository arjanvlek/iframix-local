"""API-side narrow-update persistence (refersh-battery preserves router-owned fields)."""
import logging
import time

import pytest


@pytest.fixture
def db(tmp_path):
    """Initialize an isolated SQLite DB for each test."""
    from src.db import init_db, set_db_path
    path = str(tmp_path / "test.db")
    set_db_path(path)
    init_db(path)
    yield path


def _read_device(uuid):
    from src.api.persistence import load_devices
    return load_devices().get(uuid)


def _seed_device(uuid, **fields):
    from src.db import get_connection
    cols = ["uuid"] + list(fields.keys())
    placeholders = ", ".join(["?"] * len(cols))
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO devices ({', '.join(cols)}) VALUES ({placeholders})",
            [uuid, *fields.values()])
        conn.commit()
    finally:
        conn.close()


class TestApiNarrowUpdates:
    """The API's update_device_fields / insert_device_if_missing helpers
    must only touch the named columns."""

    def test_update_device_fields_only_touches_named_columns(self, db):
        from src.api.persistence import update_device_fields

        _seed_device(
            "dev-4", mac="AA:AA", voltage=1.0, current_=2.0,
            battery="50", polling=10, last_seen=100.0,
        )

        update_device_fields("dev-4", battery="99")

        d = _read_device("dev-4")
        assert d["battery"] == "99"
        assert d["mac"] == "AA:AA"
        assert d["voltage"] == 1.0
        assert d["current"] == 2.0
        assert d["polling"] == 10
        assert d["last_seen"] == 100.0

    def test_update_device_fields_remaps_current_keyword(self, db):
        """`current` is a reserved-ish name in SQL; the helper remaps it to
        the `current_` column."""
        from src.api.persistence import update_device_fields

        _seed_device("dev-5", mac="BB:BB", voltage=0.0, current_=0.0)
        update_device_fields("dev-5", current=7.7, voltage=8.8)

        d = _read_device("dev-5")
        assert d["current"] == 7.7
        assert d["voltage"] == 8.8

    def test_update_device_fields_noop_on_empty(self, db):
        """Calling with no fields must not error and must not delete rows."""
        from src.api.persistence import update_device_fields

        _seed_device("dev-6", mac="CC:CC", battery="33")
        update_device_fields("dev-6")

        assert _read_device("dev-6")["battery"] == "33"

    def test_insert_device_if_missing_creates_row(self, db):
        from src.api.persistence import insert_device_if_missing

        insert_device_if_missing(
            "_unmatched_id_500",
            cloud_id=500, battery="88", charging_switch=1, last_seen=123.0,
        )

        d = _read_device("_unmatched_id_500")
        assert d is not None
        assert d["cloud_id"] == 500
        assert d["battery"] == "88"
        assert d["charging_switch"] == 1

    def test_insert_device_if_missing_does_not_overwrite(self, db):
        """Second call with the same uuid must not clobber existing fields
        (the API can race with itself on repeated unmatched reports)."""
        from src.api.persistence import insert_device_if_missing

        insert_device_if_missing(
            "_unmatched_id_501", cloud_id=501, battery="88")
        insert_device_if_missing(
            "_unmatched_id_501", cloud_id=501, battery="99")

        assert _read_device("_unmatched_id_501")["battery"] == "88"


class TestApiChargingSwitchPersistence:
    """The controller app sends `charging_switch` alongside `battery` via
    /api/ipad/device/refersh-battery. That value is the desired charging
    state the user set in the app, so it must be persisted — not dropped."""

    def test_update_device_fields_persists_charging_switch(self, db):
        from src.api.persistence import update_device_fields

        _seed_device("dev-cs", mac="EE:EE", battery="50", charging_switch=1)
        update_device_fields("dev-cs", battery="40", charging_switch=0)

        d = _read_device("dev-cs")
        assert d["battery"] == "40"
        assert d["charging_switch"] == 0

    def test_insert_device_if_missing_stores_charging_switch(self, db):
        from src.api.persistence import insert_device_if_missing

        insert_device_if_missing(
            "_unmatched_id_1", cloud_id=1, battery="80", charging_switch=1,
            last_seen=time.time())

        d = _read_device("_unmatched_id_1")
        assert d["charging_switch"] == 1
