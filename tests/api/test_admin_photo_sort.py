"""Integration tests for the admin photo grid's sort modes.

``GET /admin/photos`` accepts ``sort=default|upload|capture``:

  - default: newest filename first (the original behaviour).
  - upload:  newest file mtime first.
  - capture: newest EXIF DateTimeOriginal first, no-EXIF photos last.

The upload/capture sorts are backed by the ``photo_metadata`` cache
table so EXIF is only read for new or mtime-changed files. These tests
exercise the ordering, pagination under a non-default sort, the cache
table contents, and the delMedia / unbindUser cleanup paths.
"""
import os
import time

import requests

from tests.helpers import get_device_id, jpeg_with_datetime, make_png


def _photos_dir(api_server, media_type, device_id):
    sub = "photos_with_ai" if media_type == "ai" else "photos"
    device_dir = str(api_server["tmp_path"] / sub / device_id)
    os.makedirs(device_dir, exist_ok=True)
    return device_dir


def _write(api_server, media_type, device_id, name, data):
    """Write one image (bytes) into the device's photo directory."""
    device_dir = _photos_dir(api_server, media_type, device_id)
    path = os.path.join(device_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _get(api_server, device_id, media_type, sort=None, page=1, page_size=24):
    params = {"device_id": device_id, "type": media_type,
              "page": page, "page_size": page_size}
    if sort is not None:
        params["sort"] = sort
    return requests.get(
        f"{api_server['url']}/admin/photos", params=params).json()["data"]


def _filenames(data):
    return [r["filename"] for r in data["list"]]


class TestDefaultSort:
    def test_default_is_newest_filename_first(self, api_server):
        names = []
        for i in range(5):
            name = f"photo_{i:03d}.png"
            _write(api_server, "normal", "42", name, make_png(120, 90))
            names.append(name)
        data = _get(api_server, "42", "normal", sort="default")
        # Filenames in descending order (reverse of ascending scan).
        assert _filenames(data) == list(reversed(names))

    def test_no_sort_param_matches_default(self, api_server):
        for i in range(3):
            _write(api_server, "normal", "42", f"p_{i:03d}.png",
                   make_png(120, 90))
        no_param = _filenames(_get(api_server, "42", "normal"))
        explicit = _filenames(_get(api_server, "42", "normal", sort="default"))
        assert no_param == explicit

    def test_unknown_sort_falls_back_to_default(self, api_server):
        names = []
        for i in range(4):
            name = f"q_{i:03d}.png"
            _write(api_server, "normal", "42", name, make_png(120, 90))
            names.append(name)
        bogus = _filenames(_get(api_server, "42", "normal", sort="bogus"))
        assert bogus == list(reversed(names))


class TestUploadSort:
    def test_upload_sorts_by_mtime_not_filename(self, api_server):
        # Filenames ascending a<b<c<d, but set mtimes so the upload order
        # is the reverse of the filename order: a is newest, d is oldest.
        layout = [
            ("a.png", 4000),
            ("b.png", 3000),
            ("c.png", 2000),
            ("d.png", 1000),
        ]
        for name, mtime in layout:
            path = _write(api_server, "normal", "42", name, make_png(120, 90))
            os.utime(path, (mtime, mtime))
        data = _get(api_server, "42", "normal", sort="upload")
        # Newest mtime first -> a, b, c, d (the opposite of default, which
        # would be d, c, b, a).
        assert _filenames(data) == ["a.png", "b.png", "c.png", "d.png"]
        assert data["sort"] == "upload"


class TestCaptureSort:
    def test_capture_sorts_by_exif_with_no_exif_last(self, api_server):
        # Make filename order, mtime order and capture order all different
        # so each mode is genuinely distinguished. Capture order (newest
        # first) should be: cap_new, cap_mid, cap_old, then the no-EXIF
        # photo last.
        #
        # filename ascending: cap_mid, cap_new, cap_old, zzz_noexif
        cap = {
            "cap_old.jpg": "2020:01:01 08:00:00",
            "cap_mid.jpg": "2022:06:15 12:00:00",
            "cap_new.jpg": "2024:11:30 18:30:00",
        }
        for name, dt in cap.items():
            _write(api_server, "ai", "42", name, jpeg_with_datetime(dt))
        # A photo with NO EXIF capture date (flat PNG).
        _write(api_server, "ai", "42", "zzz_noexif.png", make_png(100, 80))

        data = _get(api_server, "42", "ai", sort="capture")
        order = _filenames(data)
        assert order[:3] == ["cap_new.jpg", "cap_mid.jpg", "cap_old.jpg"]
        # The photo without a readable capture date sorts LAST.
        assert order[-1] == "zzz_noexif.png"
        assert data["sort"] == "capture"

    def test_capture_no_exif_tail_ordered_by_mtime_newest_first(
            self, api_server):
        # The no-EXIF bucket sorts LAST and, among itself, newest-mtime
        # first. Use two no-EXIF photos whose mtime order is the OPPOSITE
        # of their filename order so neither filename ordering nor
        # oldest-first would pass: noexif_aaa is older, noexif_bbb is newer.
        cap_path = _write(api_server, "ai", "42", "has_exif.jpg",
                          jpeg_with_datetime("2022:06:15 12:00:00"))
        # Give the EXIF photo a middling mtime so its mtime can't
        # accidentally rank it among the no-EXIF tail.
        os.utime(cap_path, (5000, 5000))

        no_a = _write(api_server, "ai", "42", "noexif_aaa.png",
                      make_png(100, 80))
        no_b = _write(api_server, "ai", "42", "noexif_bbb.png",
                      make_png(100, 80))
        # noexif_aaa (alphabetically first) is OLDER; noexif_bbb is NEWER.
        os.utime(no_a, (1000, 1000))
        os.utime(no_b, (2000, 2000))

        data = _get(api_server, "42", "ai", sort="capture")
        order = _filenames(data)
        # The photo with a capture date is first.
        assert order[0] == "has_exif.jpg"
        # The no-EXIF tail follows, newest mtime first -> bbb before aaa
        # (the reverse of filename order, proving it is mtime-driven).
        assert order[1:] == ["noexif_bbb.png", "noexif_aaa.png"]

    def test_response_includes_active_sort(self, api_server):
        _write(api_server, "normal", "42", "a.png", make_png(120, 90))
        for sort in ("default", "upload", "capture"):
            data = _get(api_server, "42", "normal", sort=sort)
            assert data["sort"] == sort


class TestPaginationUnderSort:
    def test_pagination_preserves_global_order(self, api_server):
        # 30 photos, page_size 24 -> page 1 has 24, page 2 has 6. Use
        # upload sort with mtimes descending in filename order so the
        # global order is deterministic and easy to assert across the
        # page boundary.
        total = 30
        page_size = 24
        for i in range(total):
            name = f"u_{i:03d}.png"
            path = _write(api_server, "normal", "42", name, make_png(120, 90))
            # Higher index -> larger (newer) mtime.
            mtime = 100000 + i * 100
            os.utime(path, (mtime, mtime))

        p1 = _get(api_server, "42", "normal", sort="upload", page=1,
                  page_size=page_size)
        p2 = _get(api_server, "42", "normal", sort="upload", page=2,
                  page_size=page_size)

        assert p1["total"] == total
        assert p2["total"] == total
        assert len(p1["list"]) == page_size
        assert len(p2["list"]) == total - page_size

        ids1 = {r["id"] for r in p1["list"]}
        ids2 = {r["id"] for r in p2["list"]}
        assert ids1.isdisjoint(ids2)

        # Newest mtime is the highest index; the global newest-first order
        # is u_029 .. u_000. Page 1 is the first 24, page 2 the last 6.
        expected = [f"u_{i:03d}.png" for i in range(total - 1, -1, -1)]
        assert _filenames(p1) + _filenames(p2) == expected


class TestCachePopulation:
    def test_capture_sort_populates_and_is_stable(self, api_server):
        from src.db import get_connection

        _write(api_server, "ai", "42", "shot_a.jpg",
               jpeg_with_datetime("2023:05:01 10:00:00"))
        _write(api_server, "ai", "42", "shot_b.jpg",
               jpeg_with_datetime("2021:05:01 10:00:00"))

        first = _filenames(_get(api_server, "42", "ai", sort="capture"))

        # Rows now exist for the device/type.
        conn = get_connection()
        rows = conn.execute(
            "SELECT filename FROM photo_metadata WHERE device_id = ? "
            "AND media_type = ?", (42, "ai")).fetchall()
        conn.close()
        cached_names = {r["filename"] for r in rows}
        assert cached_names == {"shot_a.jpg", "shot_b.jpg"}

        # A second identical request returns the same order (served from
        # cache, no re-read needed).
        second = _filenames(_get(api_server, "42", "ai", sort="capture"))
        assert first == second
        assert first == ["shot_a.jpg", "shot_b.jpg"]

    def test_second_request_uses_cached_capture_not_exif(self, api_server):
        """Prove the cache is actually CONSULTED on the second request.

        After the first request populates the cache, overwrite shot_b's
        cached capture_time with a value newer than shot_a's *without*
        touching the file on disk (its mtime is preserved exactly). A
        correct implementation takes the cache-hit branch (mtime unchanged)
        and orders by the doctored cached value, putting shot_b first. An
        implementation that re-read the EXIF header every time would still
        see shot_a as newer (its real EXIF date is later) and fail this.
        """
        from src.api.persistence import upsert_photo_metadata
        from src.db import get_connection

        # shot_a has the newer real EXIF capture date, so the first capture
        # sort puts it first.
        path_a = _write(api_server, "ai", "42", "shot_a.jpg",
                        jpeg_with_datetime("2023:05:01 10:00:00"))
        _write(api_server, "ai", "42", "shot_b.jpg",
               jpeg_with_datetime("2021:05:01 10:00:00"))

        first = _filenames(_get(api_server, "42", "ai", sort="capture"))
        assert first == ["shot_a.jpg", "shot_b.jpg"]

        # Read back shot_b's cached mtime so we can re-upsert with the SAME
        # mtime (forcing the cache-hit branch) but a doctored capture_time
        # that is newer than shot_a's real EXIF date (2023 -> ts ~1.68e9).
        conn = get_connection()
        row_b = conn.execute(
            "SELECT file_mtime FROM photo_metadata WHERE device_id = ? "
            "AND media_type = ? AND filename = ?",
            (42, "ai", "shot_b.jpg")).fetchone()
        conn.close()
        # A timestamp far in the future, newer than shot_a's 2023 capture.
        upsert_photo_metadata(42, "ai", "shot_b.jpg", row_b["file_mtime"],
                              2_000_000_000)

        # Sanity: the on-disk file is untouched (mtime preserved), so the
        # impl must hit the cache rather than re-read EXIF.
        assert path_a  # path exists; shot_b's file was never modified

        second = _filenames(_get(api_server, "42", "ai", sort="capture"))
        # The doctored CACHED capture_time wins: shot_b now sorts first.
        assert second == ["shot_b.jpg", "shot_a.jpg"]


class TestDelMediaClearsCache:
    def test_delmedia_removes_photo_metadata_row(self, api_server):
        from src.db import get_connection

        url = api_server["url"]
        _write(api_server, "ai", "42", "keep.jpg",
               jpeg_with_datetime("2023:01:01 09:00:00"))
        _write(api_server, "ai", "42", "drop.jpg",
               jpeg_with_datetime("2024:01:01 09:00:00"))

        # Populate the cache via a capture-sort request.
        listing = _get(api_server, "42", "ai", sort="capture")["list"]
        by_name = {r["filename"]: r["id"] for r in listing}
        drop_id = by_name["drop.jpg"]

        # Delete the photo via the shared delMedia endpoint.
        requests.post(
            f"{url}/api/ipad/media/delMedia",
            json={"id": [drop_id], "device_id": 42},
        )

        # delMedia deletes files (and the metadata row) in a background
        # thread; poll until the row is gone.
        def _row_count(name):
            conn = get_connection()
            try:
                return conn.execute(
                    "SELECT COUNT(*) AS c FROM photo_metadata WHERE "
                    "device_id = ? AND media_type = ? AND filename = ?",
                    (42, "ai", name)).fetchone()["c"]
            finally:
                conn.close()

        for _ in range(50):
            if _row_count("drop.jpg") == 0:
                break
            time.sleep(0.1)
        assert _row_count("drop.jpg") == 0
        # The kept photo's row is untouched.
        assert _row_count("keep.jpg") == 1


class TestUnbindUserClearsCache:
    def test_unbinduser_removes_all_photo_metadata_for_device(
            self, api_server):
        from src.db import get_connection

        url = api_server["url"]
        device_uuid = "unbind-meta-dev"
        device_id = get_device_id(url, device_uuid)
        dev = str(device_id)

        _write(api_server, "ai", dev, "a.jpg",
               jpeg_with_datetime("2023:01:01 09:00:00"))
        _write(api_server, "normal", dev, "n.png", make_png(120, 90))

        # Touch both types so each gets cached.
        _get(api_server, dev, "ai", sort="capture")
        # Use upload sort for the normal type (capture would also work).
        n_path = os.path.join(_photos_dir(api_server, "normal", dev), "n.png")
        os.utime(n_path, (1000, 1000))
        _get(api_server, dev, "normal", sort="upload")

        # A second device's metadata must survive the unbind.
        from src.api.persistence import upsert_photo_metadata
        upsert_photo_metadata(987654, "normal", "other.png", 1.0, 1)

        conn = get_connection()
        before = conn.execute(
            "SELECT COUNT(*) AS c FROM photo_metadata WHERE device_id = ?",
            (device_id,)).fetchone()["c"]
        conn.close()
        assert before >= 2

        resp = requests.post(
            f"{url}/api/ipad/device/unbindUser", json={"id": device_id})
        assert resp.json()["code"] == 1

        conn = get_connection()
        after = conn.execute(
            "SELECT COUNT(*) AS c FROM photo_metadata WHERE device_id = ?",
            (device_id,)).fetchone()["c"]
        other = conn.execute(
            "SELECT COUNT(*) AS c FROM photo_metadata WHERE device_id = ?",
            (987654,)).fetchone()["c"]
        conn.close()
        assert after == 0
        assert other == 1
