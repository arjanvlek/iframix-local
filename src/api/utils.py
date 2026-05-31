"""Utility functions shared across the API server."""

import base64
import hashlib
import hmac
import json
import os
import random
import string
import time

import paho.mqtt.publish as mqtt_publish
from PIL import ExifTags, Image

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
    """Return ``(width, height)`` in pixels, or ``(0, 0)`` when the file
    cannot be read as an image.

    Backed by Pillow, which parses only the header to learn the size
    (it does not decode the full pixel data), so this stays cheap even
    for large photos.
    """
    try:
        with Image.open(filepath) as im:
            return im.size
    except Exception:
        return 0, 0


def _rational_tuple(value):
    """Coerce an EXIF rational to a plain ``(num, den)`` int tuple.

    Pillow returns rationals as ``IFDRational``, which exposes the raw
    ``numerator``/``denominator`` exactly as stored (unreduced), so a
    value like ``10/1500`` survives as ``(10, 1500)`` for the
    shutter-speed formatter to gcd-reduce. Returns ``None`` for values
    that are not rational-like.
    """
    if isinstance(value, tuple) and len(value) == 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    num = getattr(value, "numerator", None)
    den = getattr(value, "denominator", None)
    if num is None or den is None:
        return None
    try:
        return int(num), int(den)
    except (TypeError, ValueError):
        return None


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

    Reads via Pillow's EXIF support. Returns ``{}`` when the file isn't
    a readable image or carries no EXIF.
    """
    try:
        with Image.open(filepath) as im:
            exif = im.getexif()
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        return {}

    meta = {}
    dt = exif_ifd.get(0x9003) or exif_ifd.get(0x9004) or exif.get(0x0132)
    if isinstance(dt, str) and dt.rstrip("\x00 "):
        meta["datetime"] = dt.rstrip("\x00 ")
    model = exif.get(0x0110)
    if isinstance(model, str) and model.rstrip("\x00 "):
        meta["model"] = model.rstrip("\x00 ")
    aperture = _rational_tuple(exif_ifd.get(0x829D))
    if aperture and aperture[0] > 0 and aperture[1] > 0:
        meta["aperture"] = aperture[0] / aperture[1]
    shutter = _rational_tuple(exif_ifd.get(0x829A))
    if shutter and shutter[0] > 0 and shutter[1] > 0:
        meta["shutter_speed"] = shutter
    iso = exif_ifd.get(0x8827)
    # ISOSpeedRatings can be a single value or a sequence (SHORT count>1);
    # the first entry is the effective ISO.
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if isinstance(iso, int) and iso > 0:
        meta["iso"] = iso
    return meta


def get_exif_datetime_original(filepath):
    """Return the EXIF DateTimeOriginal (``"YYYY:MM:DD HH:MM:SS"``) or
    ``None`` if the file isn't a readable image, carries no EXIF, or
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
