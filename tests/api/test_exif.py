"""EXIF parsing and AI-photo remark synthesis."""
import json
import os
import time

import pytest
import requests

from tests.helpers import (
    login, get_device_id, build_jpeg_with_exif, jpeg_with_datetime,
)


class TestExifDatetime:
    """Unit tests for get_exif_datetime_original (hand-rolled EXIF reader)."""

    def test_reads_datetime_original_from_exif_ifd(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        path = tmp_path / "dto.jpg"
        path.write_bytes(jpeg_with_datetime("2023:07:14 09:30:45"))
        assert get_exif_datetime_original(str(path)) == "2023:07:14 09:30:45"

    def test_falls_back_to_datetime_digitized(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        path = tmp_path / "dtd.jpg"
        path.write_bytes(
            jpeg_with_datetime("2019:01:02 03:04:05", tag=0x9004))
        assert get_exif_datetime_original(str(path)) == "2019:01:02 03:04:05"

    def test_falls_back_to_ifd0_datetime_tag(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        path = tmp_path / "ifd0.jpg"
        path.write_bytes(jpeg_with_datetime(
            "2020:12:31 23:59:58", tag=0x0132, in_ifd0=True))
        assert get_exif_datetime_original(str(path)) == "2020:12:31 23:59:58"

    def test_returns_none_for_non_jpeg(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        path = tmp_path / "img.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
        assert get_exif_datetime_original(str(path)) is None

    def test_returns_none_for_jpeg_without_exif(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        path = tmp_path / "plain.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        assert get_exif_datetime_original(str(path)) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        from src.api.utils import get_exif_datetime_original
        assert get_exif_datetime_original(
            str(tmp_path / "does-not-exist.jpg")) is None


class TestExifMetadata:
    """Unit tests for get_exif_metadata — the richer reader that also
    extracts camera model (0x0110), aperture (0x829D), and ISO (0x8827).
    """

    def test_reads_model_aperture_iso_together(self, tmp_path):
        from src.api.utils import get_exif_metadata
        path = tmp_path / "cam.jpg"
        path.write_bytes(build_jpeg_with_exif(
            ifd0_entries=[(0x0110, 2, "Canon EOS 5D Mark IV")],
            exif_entries=[
                (0x9003, 2, "2023:07:14 09:30:45"),
                (0x829D, 5, (28, 10)),   # f/2.8
                (0x8827, 3, 400),        # ISO 400 (SHORT)
            ],
        ))
        meta = get_exif_metadata(str(path))
        assert meta == {
            "datetime": "2023:07:14 09:30:45",
            "model": "Canon EOS 5D Mark IV",
            "aperture": 2.8,
            "iso": 400,
        }

    def test_iso_as_long_type(self, tmp_path):
        """Some cameras store ISO as LONG (type 4) instead of SHORT."""
        from src.api.utils import get_exif_metadata
        path = tmp_path / "iso_long.jpg"
        path.write_bytes(build_jpeg_with_exif(
            exif_entries=[(0x8827, 4, 12800)],
        ))
        assert get_exif_metadata(str(path)).get("iso") == 12800

    def test_aperture_with_zero_denominator_is_skipped(self, tmp_path):
        """A broken rational (den=0) must not crash or yield inf."""
        from src.api.utils import get_exif_metadata
        path = tmp_path / "broken.jpg"
        path.write_bytes(build_jpeg_with_exif(
            exif_entries=[(0x829D, 5, (28, 0))],
        ))
        assert "aperture" not in get_exif_metadata(str(path))

    def test_missing_tags_are_absent_not_none(self, tmp_path):
        """Callers use ``meta.get(key)`` — absent keys are preferred
        over explicit None so the caption builder can treat the dict
        uniformly."""
        from src.api.utils import get_exif_metadata
        path = tmp_path / "datetime_only.jpg"
        path.write_bytes(jpeg_with_datetime("2023:07:14 09:30:45"))
        meta = get_exif_metadata(str(path))
        assert meta == {"datetime": "2023:07:14 09:30:45"}

    def test_empty_dict_when_no_exif(self, tmp_path):
        from src.api.utils import get_exif_metadata
        path = tmp_path / "plain.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        assert get_exif_metadata(str(path)) == {}


class TestBuildAiRemark:
    """Unit tests for build_ai_remark — the AI photo caption JSON builder.

    The webapp's getMqttMediaStatus reads JSON.parse(remark).title and
    .desc when status === 2, so both fields must be populated to avoid
    a TypeError in the webapp.
    """

    def test_title_from_exif_datetime_desc_from_camera_info(self, tmp_path):
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "IMG_6995.JPG"
        path.write_bytes(build_jpeg_with_exif(
            ifd0_entries=[(0x0110, 2, "Canon EOS 5D Mark IV")],
            exif_entries=[
                (0x9003, 2, "2023:07:14 09:30:45"),
                (0x829D, 5, (28, 10)),
                (0x8827, 3, 400),
            ],
        ))
        remark = json.loads(build_ai_remark("IMG_6995.JPG", str(path)))
        assert remark == {
            "title": "July 14, 2023 · 09.30",
            "desc": "Canon EOS 5D Mark IV \u00b7 f/2.8 \u00b7 ISO 400",
        }

    def test_desc_uses_only_available_exif_fields(self, tmp_path):
        """Partial EXIF (only model + ISO, no aperture) must still
        produce a meaningful desc — just skip the missing field."""
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "partial.jpg"
        path.write_bytes(build_jpeg_with_exif(
            ifd0_entries=[(0x0110, 2, "NIKON Z 6")],
            exif_entries=[
                (0x9003, 2, "2024:05:01 12:00:00"),
                (0x8827, 3, 800),
            ],
        ))
        remark = json.loads(build_ai_remark("partial.jpg", str(path)))
        assert remark["desc"] == "NIKON Z 6 \u00b7 ISO 800"

    def test_aperture_formatted_without_trailing_zero(self, tmp_path):
        """f/4.0 should render as 'f/4', f/2.8 as 'f/2.8'."""
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "int_aperture.jpg"
        path.write_bytes(build_jpeg_with_exif(
            exif_entries=[(0x829D, 5, (40, 10))],  # f/4.0 exactly
        ))
        remark = json.loads(build_ai_remark("int_aperture.jpg", str(path)))
        assert remark["desc"] == "f/4"

    def test_desc_falls_back_to_filename_when_no_camera_exif(self, tmp_path):
        """Screenshots, stripped uploads, etc. have no camera tags —
        desc should fall back to the filename stem so captions stay
        meaningful. Per user preference: option 1."""
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "random_upload_1712345.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        known_ts = time.mktime(
            time.strptime("2022-01-15 14:22", "%Y-%m-%d %H:%M"))
        os.utime(str(path), (known_ts, known_ts))
        remark = json.loads(build_ai_remark(path.name, str(path)))
        assert remark == {
            "title": "January 15, 2022 · 14.22",
            "desc": "random_upload_1712345",
        }

    def test_desc_falls_back_to_filename_when_only_datetime_in_exif(
            self, tmp_path):
        """If EXIF has a datetime but no model/aperture/ISO, the desc
        fallback still kicks in (the datetime drives title, not desc)."""
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "holiday.jpg"
        path.write_bytes(jpeg_with_datetime("2023:07:14 09:30:45"))
        remark = json.loads(build_ai_remark("holiday.jpg", str(path)))
        assert remark == {
            "title": "July 14, 2023 · 09.30",
            "desc": "holiday",
        }

    def test_output_is_valid_json_string(self, tmp_path):
        """The webapp does JSON.parse(remark) directly, so the return
        value must be a string, not a dict."""
        from src.api.handlers.media import build_ai_remark
        path = tmp_path / "x.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        result = build_ai_remark("x.jpg", str(path))
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert set(parsed.keys()) == {"title", "desc"}
