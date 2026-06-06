"""Unit tests for the photo_metadata cache helpers and the EXIF
datetime parser that backs the admin grid's upload/capture sort.

These call the persistence functions directly against the temp database
the ``api_server`` fixture wires up, so no HTTP round-trip is needed.
"""

from src.api.persistence import (
    delete_photo_metadata, delete_photo_metadata_for_device,
    load_photo_metadata, upsert_photo_metadata,
    upsert_photo_metadata_batch,
)
from src.api.utils import exif_datetime_to_timestamp


class TestExifDatetimeToTimestamp:
    def test_full_datetime_parses_to_int(self):
        ts = exif_datetime_to_timestamp("2024:03:15 12:30:45")
        assert isinstance(ts, int)

    def test_minute_precision_datetime_parses_to_int(self):
        ts = exif_datetime_to_timestamp("2024:03:15 12:30")
        assert isinstance(ts, int)

    def test_full_is_later_than_minute_of_same_clock(self):
        # The :45 seconds variant is strictly after the truncated-minute one.
        full = exif_datetime_to_timestamp("2024:03:15 12:30:45")
        minute = exif_datetime_to_timestamp("2024:03:15 12:30")
        assert full > minute

    def test_empty_string_is_none(self):
        assert exif_datetime_to_timestamp("") is None

    def test_none_is_none(self):
        assert exif_datetime_to_timestamp(None) is None

    def test_garbage_is_none(self):
        assert exif_datetime_to_timestamp("garbage") is None

    def test_non_string_is_none(self):
        assert exif_datetime_to_timestamp(12345) is None


class TestPhotoMetadataCache:
    def test_upsert_then_load_round_trips(self, api_server):
        upsert_photo_metadata(42, "normal", "a.jpg", 1000.0, 1700000000)
        rows = load_photo_metadata(42, "normal")
        assert "a.jpg" in rows
        assert rows["a.jpg"]["file_mtime"] == 1000.0
        assert rows["a.jpg"]["capture_time"] == 1700000000

    def test_capture_time_none_round_trips(self, api_server):
        upsert_photo_metadata(42, "normal", "b.png", 2000.0, None)
        rows = load_photo_metadata(42, "normal")
        assert rows["b.png"]["capture_time"] is None
        assert rows["b.png"]["file_mtime"] == 2000.0

    def test_second_upsert_updates_in_place(self, api_server):
        upsert_photo_metadata(42, "ai", "c.jpg", 1000.0, 100)
        upsert_photo_metadata(42, "ai", "c.jpg", 3000.0, 999)
        rows = load_photo_metadata(42, "ai")
        # Updated in place — no duplicate row, latest values win.
        assert len(rows) == 1
        assert rows["c.jpg"]["file_mtime"] == 3000.0
        assert rows["c.jpg"]["capture_time"] == 999

    def test_media_type_is_scoped(self, api_server):
        upsert_photo_metadata(42, "normal", "shared.jpg", 1.0, 1)
        upsert_photo_metadata(42, "ai", "shared.jpg", 2.0, 2)
        normal = load_photo_metadata(42, "normal")
        ai = load_photo_metadata(42, "ai")
        assert normal["shared.jpg"]["file_mtime"] == 1.0
        assert ai["shared.jpg"]["file_mtime"] == 2.0

    def test_delete_removes_single_row(self, api_server):
        upsert_photo_metadata(42, "normal", "x.jpg", 1.0, 1)
        upsert_photo_metadata(42, "normal", "y.jpg", 2.0, 2)
        delete_photo_metadata(42, "normal", "x.jpg")
        rows = load_photo_metadata(42, "normal")
        assert "x.jpg" not in rows
        assert "y.jpg" in rows

    def test_delete_for_device_clears_both_media_types(self, api_server):
        upsert_photo_metadata(42, "normal", "n.jpg", 1.0, 1)
        upsert_photo_metadata(42, "ai", "a.jpg", 2.0, 2)
        # A second device's rows must survive.
        upsert_photo_metadata(99, "normal", "other.jpg", 3.0, 3)

        delete_photo_metadata_for_device(42)

        assert load_photo_metadata(42, "normal") == {}
        assert load_photo_metadata(42, "ai") == {}
        assert "other.jpg" in load_photo_metadata(99, "normal")

    def test_non_numeric_device_id_is_noop(self, api_server):
        # Mirrors the swallowed ValueError contract — no crash, empty load.
        upsert_photo_metadata("not-a-number", "normal", "z.jpg", 1.0, 1)
        assert load_photo_metadata("not-a-number", "normal") == {}


class TestPhotoMetadataBatch:
    def test_batch_inserts_many_rows_in_one_call(self, api_server):
        upsert_photo_metadata_batch([
            (42, "ai", "a.jpg", 10.0, 100),
            (42, "ai", "b.jpg", 20.0, None),
            (42, "ai", "c.jpg", 30.0, 300),
        ])
        rows = load_photo_metadata(42, "ai")
        assert set(rows) == {"a.jpg", "b.jpg", "c.jpg"}
        assert rows["b.jpg"]["capture_time"] is None
        assert rows["c.jpg"]["file_mtime"] == 30.0

    def test_batch_upserts_in_place(self, api_server):
        upsert_photo_metadata(42, "normal", "x.jpg", 1.0, 1)
        upsert_photo_metadata_batch([
            (42, "normal", "x.jpg", 9.0, 999),
            (42, "normal", "y.jpg", 5.0, 555),
        ])
        rows = load_photo_metadata(42, "normal")
        assert len(rows) == 2
        assert rows["x.jpg"]["file_mtime"] == 9.0
        assert rows["x.jpg"]["capture_time"] == 999

    def test_batch_skips_non_numeric_device_id(self, api_server):
        # Non-numeric device_ids are skipped; the valid rows still land.
        upsert_photo_metadata_batch([
            ("bad", "normal", "skip.jpg", 1.0, 1),
            (42, "normal", "keep.jpg", 2.0, 2),
        ])
        assert load_photo_metadata("bad", "normal") == {}
        assert "keep.jpg" in load_photo_metadata(42, "normal")

    def test_batch_empty_is_noop(self, api_server):
        upsert_photo_metadata_batch([])
        assert load_photo_metadata(42, "normal") == {}
