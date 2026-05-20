"""Router-side narrow-update persistence (set_info must not clobber API fields)."""
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


class TestRouterRegisterDevicePreservesApiFields:
    """register_device must never touch battery / polling / cloud_id, so a
    concurrent API update (e.g. /refersh-battery) survives a subsequent
    set_info from the charger."""

    def test_battery_survives_router_setinfo(self, db):
        """The exact reported scenario: router loads a device with
        battery='100', API updates it to '42', router processes a set_info
        with new voltage/current. Battery must remain '42' in the DB.
        """
        from src.router.persistence import load_devices, register_device
        from src.api.persistence import update_device_fields
        from src.router import config as router_config

        _seed_device(
            "dev-1", mac="AA:BB", firmware="fw1", wifi_name="w",
            voltage=1.0, current_=2.0, battery="100",
            charging_switch=1, polling=15, last_seen=time.time(),
        )

        # Router startup populates its read-only cache with stale battery.
        load_devices()
        assert router_config.devices["dev-1"]["battery"] == "100"

        # API narrow update (what handle_battery now calls).
        update_device_fields("dev-1", battery="42")

        # Router receives a set_info; payload has no battery field.
        register_device("dev-1", {
            "uuid": "dev-1", "mac": "AA:BB",
            "voltage": 5.5, "current": 6.6, "charging_switch": 1,
        })

        d = _read_device("dev-1")
        assert d["battery"] == "42", "router clobbered API's battery update"
        assert d["voltage"] == 5.5
        assert d["current"] == 6.6

    def test_router_writes_reported_column_not_desired(self, db):
        """`charging_switch` in the MQTT payload is the charger echoing its
        actual state. It must land in `charging_switch_reported`, never in
        `charging_switch` (which holds the controller app's desired state)."""
        from src.router.persistence import register_device
        from src.api.persistence import update_device_fields

        _seed_device(
            "dev-split", mac="11:22", charging_switch=1,
            last_seen=time.time(),
        )
        # App sets desired = 1 (ON).
        update_device_fields("dev-split", charging_switch=1)

        # Charger reports that it's actually OFF (e.g. it ignored the
        # command, is between pulses, or the user disabled it physically).
        register_device("dev-split", {
            "uuid": "dev-split", "mac": "11:22", "charging_switch": 0,
        })

        d = _read_device("dev-split")
        assert d["charging_switch"] == 1, (
            "router must not overwrite the desired-state column")
        assert d["charging_switch_reported"] == 0, (
            "router must store the charger's echoed value in the "
            "reported-state column")

    def test_api_desired_update_preserves_router_reported(self, db):
        """The symmetric case: after the router persists a reported value,
        the API updating the desired value must not blow away the report."""
        from src.router.persistence import register_device
        from src.api.persistence import update_device_fields

        register_device("dev-sym-cs", {
            "uuid": "dev-sym-cs", "mac": "33:44", "charging_switch": 1,
        })
        update_device_fields("dev-sym-cs", battery="55", charging_switch=0)

        d = _read_device("dev-sym-cs")
        assert d["charging_switch"] == 0
        assert d["charging_switch_reported"] == 1

    def test_reported_derived_from_current_when_payload_lacks_switch(
            self, db):
        """Observed firmware omits `charging_switch` from `set_info` and
        only reports voltage / current. Infer the reported state from the
        current: above the noise threshold (0.5 V) = charging, at or
        below = not charging."""
        from src.router.persistence import register_device

        # Clearly charging.
        register_device("dev-cur-on", {
            "uuid": "dev-cur-on", "mac": "55:55",
            "voltage": 5.1, "current": 1.23,
        })
        assert _read_device("dev-cur-on")["charging_switch_reported"] == 1

        # Zero power — off.
        register_device("dev-cur-off", {
            "uuid": "dev-cur-off", "mac": "66:66",
            "voltage": 0.0, "current": 0.0,
        })
        assert _read_device("dev-cur-off")["charging_switch_reported"] == 0

        # Just under the threshold — treat as off (measurement noise, not
        # an active charge cycle).
        register_device("dev-cur-noise", {
            "uuid": "dev-cur-noise", "mac": "67:67",
            "voltage": 0.4, "current": 0.05,
        })
        assert (_read_device("dev-cur-noise")["charging_switch_reported"]
                == 0)

    def test_explicit_reported_in_payload_wins_over_current_inference(
            self, db):
        """If a firmware DOES include charging_switch in the payload, it
        is authoritative — don't overwrite with the current-based guess."""
        from src.router.persistence import register_device

        register_device("dev-explicit", {
            "uuid": "dev-explicit", "mac": "77:77",
            "voltage": 5.0, "current": 0.0,
            "charging_switch": 1,  # Charger says it IS charging
        })
        # Payload's own value wins.
        assert (_read_device("dev-explicit")["charging_switch_reported"]
                == 1)

    def test_power_inference_leaves_desired_untouched(self, db):
        """The power-based inference must only write the reported
        column, never the desired column."""
        from src.router.persistence import register_device
        from src.api.persistence import insert_device_if_missing

        # API (or admin toggle) has set desired = ON.
        insert_device_if_missing("dev-d2", charging_switch=1)

        # Charger then reports zero power — actual state is OFF.
        register_device("dev-d2", {
            "uuid": "dev-d2", "mac": "88:88",
            "voltage": 0.0, "current": 0.0,
        })

        d = _read_device("dev-d2")
        assert d["charging_switch"] == 1, (
            "inference must not touch the desired-state column")
        assert d["charging_switch_reported"] == 0

    def test_polling_and_cloud_id_are_never_overwritten_by_router(self, db):
        """Fields the router has no business touching must stay untouched
        regardless of what the MQTT payload contains."""
        from src.router.persistence import register_device

        _seed_device(
            "dev-2", mac="CC:DD", polling=30, cloud_id=12345,
            battery="77", last_seen=time.time(),
        )

        register_device("dev-2", {
            "uuid": "dev-2", "mac": "CC:DD",
            "voltage": 9.9, "current": 8.8,
            "polling": 999, "cloud_id": 99999, "battery": "0",
        })

        d = _read_device("dev-2")
        assert d["polling"] == 30
        assert d["cloud_id"] == 12345
        assert d["battery"] == "77"
        assert d["voltage"] == 9.9
        assert d["current"] == 8.8

    def test_partial_payload_only_updates_present_fields(self, db):
        """A set_info that only carries voltage/current must not null out
        wifi_name / firmware / mac from a previous set_config."""
        from src.router.persistence import register_device

        register_device("dev-3", {
            "uuid": "dev-3", "mac": "EE:FF", "firmware": "fw7",
            "wifi_name": "home", "charging_switch": 1,
        })
        register_device("dev-3", {
            "uuid": "dev-3", "voltage": 3.3, "current": 4.4,
        })

        d = _read_device("dev-3")
        assert d["mac"] == "EE:FF"
        assert d["firmware"] == "fw7"
        assert d["wifi_name"] == "home"
        assert d["voltage"] == 3.3
        assert d["current"] == 4.4


class TestRouterRegisterDeviceCreation:
    """register_device must still create new rows for devices that report in
    for the first time (no row in the DB yet)."""

    def test_first_setinfo_creates_row(self, db):
        from src.router.persistence import register_device

        register_device("dev-new", {
            "uuid": "dev-new", "mac": "11:22",
            "voltage": 1.1, "current": 2.2, "charging_switch": 1,
        })

        d = _read_device("dev-new")
        assert d is not None
        assert d["mac"] == "11:22"
        assert d["voltage"] == 1.1
        assert d["current"] == 2.2
        # Payload's `charging_switch` is the charger's reported state.
        assert d["charging_switch_reported"] == 1
        # Desired state was never set — controller app hasn't spoken yet.
        assert d["charging_switch"] is None
        # Other fields not in the payload stay NULL.
        assert d["battery"] is None
        assert d["polling"] is None
        assert d["cloud_id"] is None

    def test_new_device_log_only_on_first_insert(self, db, caplog):
        from src.router.persistence import register_device

        with caplog.at_level(logging.INFO, logger="src.router.persistence"):
            register_device("dev-log", {"uuid": "dev-log", "mac": "AA:00"})
            after_first = caplog.text
            caplog.clear()
            register_device("dev-log", {"uuid": "dev-log", "voltage": 1.0})
            after_second = caplog.text

        assert "[NEW] Discovered iCharGuard: dev-log" in after_first
        assert "[NEW]" not in after_second
