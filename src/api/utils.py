"""Utility functions shared across the API server."""

import base64
import hashlib
import hmac
import json
import os
import random
import string
import struct
import time

import paho.mqtt.publish as mqtt_publish

from src.api import config

# Fixed secret key for signing local Qiniu-style upload tokens.
# This never reaches real Qiniu servers — only used to produce a
# well-formed token that the native app's Qiniu SDK can parse.
_UPLOAD_TOKEN_SECRET = b"local-icharguard-secret"


def generate_msg_id():
    """Generate a snowflake-style message ID (timestamp_ms << 22 | random)."""
    return (int(time.time() * 1000) << 22) | random.randint(0, (1 << 22) - 1)


def publish_charging_switch(uuid, charging_on):
    """Publish an ``ipad/icharger/charging_switch`` command to a charger.

    Raises the underlying paho exception on failure — callers are
    responsible for deciding whether to report it to the client.
    """
    msg = json.dumps({
        "msg_id": generate_msg_id(),
        "event": "ipad/icharger/charging_switch",
        "data": {
            "bind_status": 1,
            "polling": 15,
            "battery": 0,
            "charging_switch": 1 if charging_on else 0,
        }
    })
    mqtt_publish.single(
        f"/mqtt/s2c/{uuid}",
        payload=msg,
        qos=1,
        hostname=config.MQTT_BROKER_HOST,
        port=config.MQTT_BROKER_PORT,
        auth={"username": config.MQTT_USER,
              "password": config.MQTT_PASS},
    )


def generate_token():
    """Generate a random string for MQTT auth tokens."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=15))


def generate_upload_token(expire=3600):
    """Generate a Qiniu-style upload token for local photo uploads.

    Format: ``AccessKey:Sign:EncodedPolicy`` where Sign is
    base64(HMAC-SHA1(secret, EncodedPolicy)).
    """
    access_key = generate_token()

    policy = {
        "callbackUrl": (
            "https://ifp.ga.codethriving.com/api/user/asset/upload"
        ),
        "callbackBodyType": "application/json",
        "callbackBody": (
            '{"key":"$(key)","fname":"$(fname)","etag":"$(etag)",'
            '"fsize":"$(fsize)","more":"$(x:more)","suffix":"$(x:suffix)",'
            '"user_id":"0","driver":"qiniu"}'
        ),
        "scope": "flosscn",
        "deadline": int(time.time()) + expire,
    }

    encoded_policy = base64.b64encode(
        json.dumps(policy).encode()
    ).decode()

    sign = base64.b64encode(
        hmac.new(_UPLOAD_TOKEN_SECRET, encoded_policy.encode(), hashlib.sha1)
        .digest()
    ).decode()

    return f"{access_key}:{sign}:{encoded_policy}"


def get_image_size(filepath):
    """Get image dimensions from JPEG/PNG file headers."""
    with open(filepath, "rb") as f:
        header = f.read(30)
        # PNG
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", header[16:24])
        # JPEG
        if header[:2] == b"\xff\xd8":
            f.seek(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    break
                if marker[1] in (0xC0, 0xC1, 0xC2):
                    f.read(3)  # length + precision
                    h, w = struct.unpack(">HH", f.read(4))
                    return w, h
                length = struct.unpack(">H", f.read(2))[0]
                f.seek(length - 2, 1)
    return 0, 0


def _read_exif_ifd(tiff, offset, endian):
    """Read one IFD block and return a ``{tag: value}`` dict.

    Decodes the TIFF/EXIF entry types we actually consume:
    ASCII (strings), SHORT/LONG (ints, count=1), and RATIONAL
    (``(num, den)`` tuples, count=1). Other types are skipped. The
    rational form is preserved so callers like the shutter-speed
    formatter can render the original fraction (``1/250s``) without
    floating-point round-tripping.
    """
    out = {}
    if offset + 2 > len(tiff):
        return out
    count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
    base = offset + 2
    for i in range(count):
        ent = base + i * 12
        if ent + 12 > len(tiff):
            break
        tag, type_, n = struct.unpack(endian + "HHI", tiff[ent:ent + 8])
        value_field = tiff[ent + 8:ent + 12]
        if type_ == 2:  # ASCII
            if n <= 4:
                raw = value_field[:n]
            else:
                val_off = struct.unpack(endian + "I", value_field)[0]
                if val_off + n > len(tiff):
                    continue
                raw = tiff[val_off:val_off + n]
            out[tag] = raw.decode("ascii", errors="replace").rstrip("\x00 ")
        elif type_ == 3 and n == 1:  # SHORT, fits in first 2 bytes
            out[tag] = struct.unpack(endian + "H", value_field[:2])[0]
        elif type_ == 4 and n == 1:  # LONG, fits inline
            out[tag] = struct.unpack(endian + "I", value_field)[0]
        elif type_ == 5 and n == 1:  # RATIONAL (8 bytes, always at offset)
            val_off = struct.unpack(endian + "I", value_field)[0]
            if val_off + 8 > len(tiff):
                continue
            num, den = struct.unpack(
                endian + "II", tiff[val_off:val_off + 8])
            if den:
                out[tag] = (num, den)
    return out


def _extract_exif_ifds(filepath):
    """Walk JPEG segments to find the EXIF APP1, parse it, and return
    ``(ifd0, exif_ifd)`` dicts. Returns ``(None, None)`` if the file
    isn't a JPEG or has no EXIF segment.
    """
    try:
        with open(filepath, "rb") as f:
            if f.read(2) != b"\xff\xd8":
                return None, None
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    return None, None
                # Start-of-scan or end-of-image — no more metadata segments
                if marker[1] in (0xD9, 0xDA):
                    return None, None
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    return None, None
                seg_len = struct.unpack(">H", length_bytes)[0]
                data_len = seg_len - 2
                if marker[1] == 0xE1:  # APP1
                    data = f.read(data_len)
                    if data[:6] != b"Exif\x00\x00":
                        continue  # XMP or other APP1; keep scanning
                    tiff = data[6:]
                    if len(tiff) < 8:
                        return None, None
                    bo = tiff[:2]
                    if bo == b"II":
                        endian = "<"
                    elif bo == b"MM":
                        endian = ">"
                    else:
                        return None, None
                    if struct.unpack(endian + "H", tiff[2:4])[0] != 0x002A:
                        return None, None
                    ifd0_off = struct.unpack(endian + "I", tiff[4:8])[0]
                    ifd0 = _read_exif_ifd(tiff, ifd0_off, endian)
                    exif_ifd = {}
                    exif_off = ifd0.get(0x8769)
                    if isinstance(exif_off, int):
                        exif_ifd = _read_exif_ifd(tiff, exif_off, endian)
                    return ifd0, exif_ifd
                f.seek(data_len, 1)
    except (OSError, struct.error):
        return None, None


def get_exif_metadata(filepath):
    """Return a dict of caption-relevant EXIF tags, with missing keys
    absent. Possible keys:

    - ``datetime`` — ``"YYYY:MM:DD HH:MM:SS"`` from DateTimeOriginal
      (0x9003) → DateTimeDigitized (0x9004) → IFD0 DateTime (0x0132).
    - ``model`` — camera model string (0x0110).
    - ``aperture`` — FNumber as a float, e.g. ``2.8`` (0x829D).
    - ``shutter_speed`` — ExposureTime as a ``(num, den)`` tuple, e.g.
      ``(1, 250)`` for 1/250s or ``(2, 1)`` for a 2-second exposure
      (0x829A). Kept in rational form so the formatter can render the
      original fraction without floating-point round-tripping.
    - ``iso`` — ISOSpeedRatings as an int (0x8827).

    Hand-rolled reader; no Pillow dependency.
    """
    ifd0, exif_ifd = _extract_exif_ifds(filepath)
    if ifd0 is None:
        return {}

    meta = {}
    dt = exif_ifd.get(0x9003) or exif_ifd.get(0x9004) or ifd0.get(0x0132)
    if isinstance(dt, str) and dt:
        meta["datetime"] = dt
    model = ifd0.get(0x0110)
    if isinstance(model, str) and model:
        meta["model"] = model
    aperture = exif_ifd.get(0x829D)
    if isinstance(aperture, tuple):
        num, den = aperture
        if num > 0 and den > 0:
            meta["aperture"] = num / den
    shutter = exif_ifd.get(0x829A)
    if isinstance(shutter, tuple):
        num, den = shutter
        if num > 0 and den > 0:
            meta["shutter_speed"] = (num, den)
    iso = exif_ifd.get(0x8827)
    if isinstance(iso, int) and iso > 0:
        meta["iso"] = iso
    return meta


def get_exif_datetime_original(filepath):
    """Return the EXIF DateTimeOriginal (``"YYYY:MM:DD HH:MM:SS"``) or
    ``None`` if the file isn't a JPEG, has no EXIF APP1 segment, or
    lacks any date-time tag. Thin wrapper around ``get_exif_metadata``
    kept for call sites that only care about the capture timestamp.
    """
    return get_exif_metadata(filepath).get("datetime")


def scan_photos(directory):
    """Scan a directory for image files, return sorted list of (filename, path)."""
    if not os.path.isdir(directory):
        return []
    result = []
    for name in sorted(os.listdir(directory)):
        if os.path.splitext(name)[1].lower() in config.IMAGE_EXTENSIONS:
            result.append((name, os.path.join(directory, name)))
    return result


def build_id_map(devices):
    """Build a stable mapping of numeric device ID -> UUID.

    Uses a simple hash of the MAC address to generate deterministic IDs.
    The same MAC always produces the same ID across restarts.
    Also includes any cloud_id mappings that were learned from app requests.
    """
    id_map = {}
    for device_uuid, info in devices.items():
        if device_uuid.startswith("_"):
            continue
        # Cloud IDs learned from app requests take priority
        cloud_id = info.get("cloud_id")
        if cloud_id is not None:
            id_map[cloud_id] = device_uuid
        # Hash-based ID as fallback
        mac = info.get("mac", "")
        if mac and mac != "?":
            device_id = int.from_bytes(mac.encode()[:8], "big") % 100000
            if device_id not in id_map:
                id_map[device_id] = device_uuid
    return id_map
