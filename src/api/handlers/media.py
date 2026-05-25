"""Media and photo handler methods (list, serve, upload, delete, token)."""

import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import ssl
import threading
import time
from email.parser import BytesParser
from email.policy import compat32

import paho.mqtt.publish as mqtt_publish

from src.api import config
from src.api.persistence import (
    load_media_settings, load_sessions, save_media_settings,
)
from src.api.utils import (
    generate_msg_id, generate_upload_token, get_exif_metadata,
    get_image_size, scan_photos,
)

logger = logging.getLogger(__name__)


def _format_fnumber(f):
    """Format an aperture as ``f/2.8`` / ``f/4`` (no trailing .0)."""
    return f"f/{int(f)}" if f == int(f) else f"f/{f:.1f}"


def _format_shutter_speed(rational):
    """Format an EXIF ExposureTime ``(num, den)`` rational as a
    shutter-speed string, matching how cameras and photo apps display
    it:

    - Whole-second exposures: ``"30s"``, ``"2s"``.
    - Sub-second exposures simplifying to ``1/N``: ``"1/250s"``.
    - Everything else: decimal seconds with one digit, ``"1.5s"``.

    Returns ``None`` if the rational is missing or invalid so the
    caption builder can simply skip the field.
    """
    if not isinstance(rational, tuple) or len(rational) != 2:
        return None
    num, den = rational
    if num <= 0 or den <= 0:
        return None
    g = math.gcd(num, den)
    num //= g
    den //= g
    if den == 1:
        return f"{num}s"
    if num == 1:
        return f"1/{den}s"
    return f"{num/den:.1f}s"


# Catalog sizes the webapp uses on 16:9 displays. The same id range (1..5
# horizontal, 1..4 vertical) is also valid on 4:3 displays — those have 10
# entries per orientation but the first 4-5 are exact matches via the
# webapp's ``HL`` snap function, so a value picked from this range works on
# every supported display without further clamping.
_AI_TEMPLATE_RANGE_HORIZONTAL = 5
_AI_TEMPLATE_RANGE_VERTICAL = 4


def _pick_ai_template_for_image(filepath):
    """Return ``(template_id, template_type)`` matched to image orientation.

    Reads the image's pixel dimensions and picks:

    - ``template_type=2`` (vertical) + ``template_id`` in 1..4 for portrait
      images (height greater than width). The webapp's vertical templates
      lay the image into a tall area, which preserves portrait composition.
    - ``template_type=1`` (horizontal) + ``template_id`` in 1..5 for
      landscape and square images (width greater than or equal to height).
      Square images default to horizontal because that matches the
      orientation most iPads are mounted in.

    Falls back to horizontal if the dimensions cannot be read (e.g. the
    file is malformed or the format is not JPEG/PNG).
    """
    try:
        width, height = get_image_size(filepath)
    except Exception:
        width, height = 0, 0
    if width > 0 and height > 0 and height > width:
        return random.randint(1, _AI_TEMPLATE_RANGE_VERTICAL), 2
    return random.randint(1, _AI_TEMPLATE_RANGE_HORIZONTAL), 1


def _assign_ai_template(media_id, settings, filepath, *, device_id=None):
    """Pick a template matched to the photo and persist it.

    Mutates ``settings`` in place; the caller is responsible for calling
    ``save_media_settings(settings)``. Idempotent: if an existing entry
    already has a non-zero ``template_id`` and a valid ``template_type``,
    that entry is returned unchanged so admin-edited values survive
    subsequent ``mediaList`` calls.

    Returns the (possibly pre-existing) ``(template_id, template_type)``
    pair so callers can include it in MQTT payloads.
    """
    existing = settings.get(media_id, {})
    tid = int(existing.get("template_id") or 0)
    ttype = int(existing.get("template_type") or 0)
    if tid > 0 and ttype in (1, 2):
        return tid, ttype

    tid, ttype = _pick_ai_template_for_image(filepath)

    existing.setdefault("display", "")
    existing["template_id"] = tid
    existing["template_type"] = ttype
    if device_id is not None and "device_id" not in existing:
        existing["device_id"] = int(device_id)
    settings[media_id] = existing
    return tid, ttype


def build_ai_remark(filename, filepath):
    """Return the AI-caption ``remark`` JSON for an AI photo record.

    The webapp does ``JSON.parse(remark)`` and reads ``.title`` / ``.desc``
    when ``status === 2``; a null remark crashes it. We don't run AI
    locally, so we synthesise a caption from EXIF:

    - ``title`` is the capture time from DateTimeOriginal (falling back
      to the file's mtime when EXIF is absent).
    - ``desc`` joins the camera model, aperture, shutter speed, and
      ISO (whichever are present) with a middle-dot separator, e.g.
      ``"Canon EOS 5D Mark IV · f/2.8 · 1/250s · ISO 400"``.
      Each field is included only when the corresponding EXIF tag was
      readable; cameras that strip ExposureTime simply lose the
      shutter-speed segment, the rest of the caption is unaffected.
      Falls back to the filename stem when none of those tags are
      present (screenshots, stripped metadata, etc.).
    """
    meta = get_exif_metadata(filepath)

    exif_dt = meta.get("datetime")
    # EXIF DateTime is "YYYY:MM:DD HH:MM:SS"; parse the first 16 chars
    # (drop seconds) and format as "April 20, 2026 · 16.34".
    if exif_dt and len(exif_dt) >= 16 and exif_dt[4] == ":":
        tm = time.strptime(exif_dt[:16], "%Y:%m:%d %H:%M")
    else:
        try:
            mtime = os.path.getmtime(filepath)
        except OSError:
            mtime = time.time()
        tm = time.localtime(mtime)
    title = (f"{time.strftime('%B', tm)} {tm.tm_mday}, {tm.tm_year} \u00b7 "
             f"{time.strftime('%H.%M', tm)}")

    parts = []
    if meta.get("model"):
        parts.append(meta["model"])
    if meta.get("aperture"):
        parts.append(_format_fnumber(meta["aperture"]))
    shutter = _format_shutter_speed(meta.get("shutter_speed"))
    if shutter:
        parts.append(shutter)
    if meta.get("iso"):
        parts.append(f"ISO {meta['iso']}")
    desc = " \u00b7 ".join(parts) if parts else os.path.splitext(filename)[0]

    return json.dumps({"title": title, "desc": desc})


class MediaMixin:

    def _find_display_uuid(self, device_id):
        """Look up the display device UUID from a numeric device_id."""
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            return None
        sessions = load_sessions()
        for session_uuid, sess in sessions.items():
            if sess.get("id") == device_id:
                return session_uuid
        return None

    def _build_media_record_by_id(self, media_id, device_id, display,
                                    template_id, template_type):
        """Find a photo file by media_id and build a full media record."""
        host = self.headers.get("Host", "ifp.ga.codethriving.com")
        scheme = ("https" if isinstance(self.connection, ssl.SSLSocket)
                  else "http")
        base_url = f"{scheme}://{host}"

        for media_type, base_dir, url_prefix in (
            ("normal", config.PHOTOS_DIR, "/photos"),
            ("ai", config.PHOTOS_AI_DIR, "/photos_with_ai"),
        ):
            directory = os.path.join(base_dir, str(device_id))
            for filename, filepath in scan_photos(directory):
                file_hash = int.from_bytes(
                    hashlib.sha256(filename.encode()).digest()[:8], "big")
                mid = str(file_hash % (10**18))
                if mid != media_id:
                    continue
                name, ext = os.path.splitext(filename)
                suffix = ext.lstrip(".")
                mtime = int(os.path.getmtime(filepath))
                asset_id = (file_hash % 100000) + 1
                url_filename = filename
                if media_type == "ai":
                    w, h = get_image_size(filepath)
                    url_filename = f"{name}_{w}_{h}{ext}"
                return {
                    "id": media_id,
                    "device_id": device_id,
                    "title": "",
                    "status": 2,
                    "display": display,
                    "fill_mode": 0,
                    "template_id": template_id,
                    "template_type": template_type,
                    "type": media_type,
                    "asset_id": asset_id,
                    "remark": (build_ai_remark(filename, filepath)
                               if media_type == "ai" else None),
                    "created_id": 1,
                    "created_at": mtime,
                    "deleted_at": None,
                    "asset": {
                        "id": asset_id,
                        "file_path": (f"{url_prefix}/{device_id}"
                                      f"/{url_filename}"),
                        "filename": filename,
                        "suffix": suffix,
                        "more": "",
                        "width": None,
                        "height": None,
                        "url": (f"{base_url}{url_prefix}"
                                f"/{device_id}/{url_filename}"),
                    },
                }
        return None

    def handle_media_list(self, params):
        """Return media from local photo directories."""
        device_id = params.get("device_id", ["0"])[0]
        page = params.get("page", ["1"])[0]
        limit = params.get("limit", ["300"])[0]
        media_type = params.get("type", ["normal"])[0]

        host = self.headers.get("Host", "ifp.ga.codethriving.com")
        scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        base_url = f"{scheme}://{host}"

        if media_type == "ai":
            base_dir = config.PHOTOS_AI_DIR
            url_prefix = "/photos_with_ai"
        else:
            base_dir = config.PHOTOS_DIR
            url_prefix = "/photos"

        directory = os.path.join(base_dir, str(device_id))
        photos = scan_photos(directory)

        media_settings = load_media_settings()
        settings_changed = False

        records = []
        for i, (filename, filepath) in enumerate(photos):
            name, ext = os.path.splitext(filename)
            suffix = ext.lstrip(".")
            mtime = int(os.path.getmtime(filepath))
            # Stable IDs derived from full filename hash
            file_hash = int.from_bytes(hashlib.sha256(filename.encode()).digest()[:8], "big")
            media_id = str(file_hash % (10**18))
            asset_id = (file_hash % 100000) + 1

            if media_type == "ai":
                w, h = get_image_size(filepath)
                url_filename = f"{name}_{w}_{h}{ext}"
            else:
                url_filename = filename

            stored = media_settings.get(media_id, {})
            template_id = stored.get("template_id", 0)
            template_type = stored.get("template_type", 0)
            # AI photos must carry a non-zero template_id, otherwise the
            # webapp falls back to Math.random() on every page load and
            # different reloads show different templates. Backfill on
            # first read so the choice is stable thereafter.
            if media_type == "ai" and (
                    int(template_id or 0) <= 0
                    or int(template_type or 0) not in (1, 2)):
                template_id, template_type = _assign_ai_template(
                    media_id, media_settings, filepath,
                    device_id=device_id)
                stored = media_settings[media_id]
                settings_changed = True
            records.append({
                "id": media_id,
                "device_id": int(device_id),
                "title": "",
                "status": 2,
                "display": stored.get("display", ""),
                "fill_mode": 0,
                "template_id": template_id,
                "template_type": template_type,
                "type": media_type,
                "asset_id": asset_id,
                "remark": (build_ai_remark(filename, filepath)
                           if media_type == "ai" else None),
                "created_id": 1,
                "created_at": mtime,
                "deleted_at": None,
                "asset": {
                    "id": asset_id,
                    "file_path": f"{url_prefix}/{device_id}/{url_filename}",
                    "filename": filename,
                    "suffix": suffix,
                    "more": "",
                    "width": None,
                    "height": None,
                    "url": f"{base_url}{url_prefix}/{device_id}/{url_filename}",
                },
            })

        if settings_changed:
            save_media_settings(media_settings)

        logger.info(
            "[MEDIA LIST] device=%s type=%s -> %d photo(s)",
            device_id, media_type, len(records))
        self.respond_success({
            "pagination": {
                "page": page,
                "limit": limit,
                "totalCount": len(records),
            },
            "list": records,
        })

    def handle_photo_serve(self, path):
        """Serve a photo from the photos or photos_with_ai directory.

        URL format: /photos/{device_id}/{filename} or
        /photos_with_ai/{device_id}/{filename}
        """
        if path.startswith("/photos_with_ai/"):
            base_dir = config.PHOTOS_AI_DIR
            rest = path[len("/photos_with_ai/"):]
        else:
            base_dir = config.PHOTOS_DIR
            rest = path[len("/photos/"):]

        # rest is "{device_id}/{filename}" or just "{filename}" (legacy)
        parts = rest.split("/", 1)
        if len(parts) == 2:
            device_id, filename = parts
        else:
            device_id, filename = "0", parts[0]

        # Try exact match first, then strip _{w}_{h} dimension suffix
        # (added for AI photos so the webapp can extract dimensions from URL)
        safe_name = os.path.basename(filename)
        file_path = os.path.join(base_dir, device_id, safe_name)
        if not os.path.isfile(file_path):
            stripped = re.sub(r"_\d+_\d+(\.\w+)$", r"\1", safe_name)
            file_path = os.path.join(base_dir, device_id, stripped)

        real_base = os.path.realpath(base_dir)
        if not os.path.realpath(file_path).startswith(real_base):
            self.send_error(403, "Forbidden")
            return
        self.respond_file(
            file_path, cache_control="public, max-age=31536000, immutable")

    def handle_asset_upload(self):
        """Accept a multipart file upload and save to the photos directory.

        This is a local replacement for the Qiniu upload flow. Accepts
        multipart/form-data with a 'file' field and optional 'x:suffix'
        and 'key' fields.  Uses email.parser.BytesParser for robust
        multipart parsing (handles case-insensitive headers from
        different HTTP clients, including the Qiniu SDK).
        """
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.respond_json(
                {"code": 0, "msg": "expected multipart/form-data"}, status=400)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        # Wrap as a MIME message so BytesParser can handle boundary
        # splitting, case-insensitive header matching, and binary payloads.
        mime_header = f"Content-Type: {content_type}\r\n\r\n".encode()
        msg = BytesParser(policy=compat32).parsebytes(mime_header + raw)

        file_data = None
        suffix = "jpg"
        key = ""

        if msg.is_multipart():
            for part in msg.get_payload():
                name = part.get_param("name", header="content-disposition")
                if name == "file":
                    file_data = part.get_payload(decode=True)
                elif name == "x:suffix":
                    payload = part.get_payload(decode=True)
                    if payload:
                        suffix = payload.decode("utf-8", errors="replace").strip()
                elif name == "key":
                    payload = part.get_payload(decode=True)
                    if payload:
                        key = payload.decode("utf-8", errors="replace").strip()

        if not file_data:
            self.respond_json(
                {"code": 0, "msg": "no file in upload"}, status=400)
            return

        # Save to temp directory; final location determined by setMedia
        os.makedirs(config.PHOTOS_TEMP_DIR, exist_ok=True)

        # Generate filename from key or timestamp
        if key:
            filename = os.path.basename(key)
        else:
            ts = int(time.time())
            filename = f"{ts}.{suffix}"

        # Sanitize filename
        filename = re.sub(r"[^\w._-]", "_", filename)
        filepath = os.path.join(config.PHOTOS_TEMP_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(file_data)

        asset_id = random.randint(10000, 99999)

        # Track pending upload so setMedia can move it to the right directory
        with config.pending_uploads_lock:
            config.pending_uploads[str(asset_id)] = filename

        host = self.headers.get("Host", "ifp.ga.codethriving.com")
        scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        base_url = f"{scheme}://{host}"

        logger.info(
            "[ASSET UPLOAD] saved %s (%d bytes) to temp, asset_id=%s",
            filename, len(file_data), asset_id)
        self.respond_success({
            "file_path": f"photos/{filename}",
            "filename": filename,
            "height": None,
            "id": asset_id,
            "more": "",
            "suffix": suffix,
            "url": f"{base_url}/photos/{filename}",
            "width": None,
        })

    def handle_asset_uploader(self):
        """Accept a direct multipart upload from iFramix Pro app 2.2.29+.

        The new app skips the Qiniu token flow and POSTs the file directly
        as multipart/form-data with fields ``more``, ``driver`` (e.g. ``r2``)
        and ``file`` (the ``filename`` in content-disposition looks like
        ``YYYYMMDD/<millis>_<w>_<h>.jpg``). The follow-up call to
        ``/api/ipad/media/setMedia`` still decides normal vs ai and moves the
        file out of the temp directory, same as the old upload flow.
        """
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.respond_json(
                {"code": 0, "msg": "expected multipart/form-data"}, status=400)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        mime_header = f"Content-Type: {content_type}\r\n\r\n".encode()
        msg = BytesParser(policy=compat32).parsebytes(mime_header + raw)

        file_data = None
        client_filename = ""
        more = ""

        if msg.is_multipart():
            for part in msg.get_payload():
                name = part.get_param("name", header="content-disposition")
                if name == "file":
                    file_data = part.get_payload(decode=True)
                    client_filename = part.get_filename() or ""
                elif name == "more":
                    payload = part.get_payload(decode=True)
                    if payload:
                        more = payload.decode("utf-8", errors="replace")

        if not file_data:
            self.respond_json(
                {"code": 0, "msg": "no file in upload"}, status=400)
            return

        os.makedirs(config.PHOTOS_TEMP_DIR, exist_ok=True)

        basename = os.path.basename(client_filename) if client_filename else ""
        if basename:
            filename = re.sub(r"[^\w._-]", "_", basename)
            suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        else:
            suffix = "jpg"
            filename = f"{int(time.time())}.{suffix}"

        filepath = os.path.join(config.PHOTOS_TEMP_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(file_data)

        asset_id = random.randint(10000, 99999)
        with config.pending_uploads_lock:
            config.pending_uploads[str(asset_id)] = filename

        host = self.headers.get("Host", "ifp.ga.codethriving.com")
        scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        base_url = f"{scheme}://{host}"

        logger.info(
            "[ASSET UPLOADER] saved %s (%d bytes) to temp, asset_id=%s",
            filename, len(file_data), asset_id)
        self.respond_success({
            "id": asset_id,
            "file_path": f"photos/{filename}",
            "filename": filename,
            "suffix": suffix,
            "more": more,
            "width": None,
            "height": None,
            "url": f"{base_url}/photos/{filename}",
        })

    def handle_set_media(self, body):
        """Classify uploaded photos and move them to the correct directory.

        Called after asset upload(s) to assign each photo as 'normal' or 'ai',
        which determines whether it goes to photos/ or photos_with_ai/.
        Photos are stored in a subdirectory per device_id.
        """
        asset_ids = body.get("asset_ids", [])
        media_type = body.get("type", "normal")
        device_id = str(body.get("device_id", 0))

        if media_type == "ai":
            target_dir = os.path.join(config.PHOTOS_AI_DIR, device_id)
        else:
            target_dir = os.path.join(config.PHOTOS_DIR, device_id)
        os.makedirs(target_dir, exist_ok=True)

        moved = []
        moved_files = []
        missing = []
        for aid in asset_ids:
            aid_str = str(aid)
            with config.pending_uploads_lock:
                filename = config.pending_uploads.pop(aid_str, None)
            if filename is None:
                missing.append(aid_str)
                continue
            src = os.path.join(config.PHOTOS_TEMP_DIR, filename)
            dst = os.path.join(target_dir, filename)
            if os.path.isfile(src):
                shutil.move(src, dst)
                moved.append(aid_str)
                moved_files.append((filename, dst))
            else:
                missing.append(aid_str)

        # Store device_id in media_settings for each moved file. For AI
        # photos, also pre-assign a template matched to the image's
        # orientation so the webapp doesn't fall back to its own
        # Math.random() on every reload.
        new_templates = {}
        if moved_files:
            settings = load_media_settings()
            for filename, dst in moved_files:
                file_hash = int.from_bytes(
                    hashlib.sha256(filename.encode()).digest()[:8], "big")
                mid = str(file_hash % (10**18))
                if mid not in settings:
                    settings[mid] = {}
                settings[mid]["device_id"] = int(device_id)
                if media_type == "ai":
                    tid, ttype = _assign_ai_template(
                        mid, settings, dst, device_id=device_id)
                    new_templates[mid] = (tid, ttype)
            save_media_settings(settings)

        # Publish MQTT notification to display device
        target_uuid = self._find_display_uuid(device_id)
        if target_uuid and moved_files:
            host = self.headers.get("Host", "ifp.ga.codethriving.com")
            scheme = ("https" if isinstance(self.connection, ssl.SSLSocket)
                      else "http")
            base_url = f"{scheme}://{host}"
            url_prefix = "/photos_with_ai" if media_type == "ai" else "/photos"

            new_records = []
            for filename, filepath in moved_files:
                name, ext = os.path.splitext(filename)
                suffix = ext.lstrip(".")
                mtime = int(os.path.getmtime(filepath))
                file_hash = int.from_bytes(
                    hashlib.sha256(filename.encode()).digest()[:8], "big")
                media_id = str(file_hash % (10**18))
                asset_id = (file_hash % 100000) + 1
                url_filename = filename
                if media_type == "ai":
                    w, h = get_image_size(filepath)
                    url_filename = f"{name}_{w}_{h}{ext}"
                tid, ttype = new_templates.get(media_id, (0, 0))
                # AI photos get status=2 immediately so the webapp's
                # ``isAiLoad`` branch renders the template right away.
                # Without it the webapp shows the bare image (no overlay)
                # while it waits for an AI worker that does not exist
                # in this offline replacement.
                status = 2 if media_type == "ai" else 0
                new_records.append({
                    "id": media_id,
                    "device_id": int(device_id),
                    "title": "",
                    "status": status,
                    "display": "",
                    "fill_mode": 0,
                    "template_id": tid,
                    "template_type": ttype,
                    "type": media_type,
                    "asset_id": asset_id,
                    "remark": (build_ai_remark(filename, filepath)
                               if media_type == "ai" else None),
                    "created_id": 1,
                    "created_at": mtime,
                    "deleted_at": None,
                    "asset": {
                        "id": asset_id,
                        "file_path": f"{url_prefix}/{device_id}/{url_filename}",
                        "filename": filename,
                        "suffix": suffix,
                        "more": "",
                        "width": None,
                        "height": None,
                        "url": (f"{base_url}{url_prefix}"
                                f"/{device_id}/{url_filename}"),
                    },
                })

            if new_records:
                msg = json.dumps({
                    "uuid": target_uuid,
                    "msg_id": generate_msg_id(),
                    "event": "ipad/media/create",
                    "data": new_records,
                })
                try:
                    mqtt_publish.single(
                        f"/s2c/{target_uuid}",
                        payload=msg, qos=1,
                        hostname=config.MQTT_BROKER_HOST,
                        port=config.MQTT_BROKER_PORT,
                        auth={"username": config.MQTT_USER,
                              "password": config.MQTT_PASS},
                    )
                except Exception:
                    logger.exception(
                        "[SET MEDIA] MQTT publish to %s failed", target_uuid)

        logger.info(
            "[SET MEDIA] device=%s type=%s moved=%s missing=%s",
            device_id, media_type, moved, missing)
        self.respond_success(True)

    def handle_del_media(self, body):
        """Delete photos by media ID.

        Body: {'id': ['606223218751598448', ...], 'device_id': 29540}
        The 'id' field contains media IDs as returned by mediaList, computed
        as str(file_hash % (10**18)) where file_hash = int.from_bytes(
        sha256(filename.encode()).digest()[:8], "big").
        """
        media_ids = set(str(mid) for mid in body.get("id", []))
        device_id = str(body.get("device_id", 0))

        if not media_ids:
            self.respond_success(True)
            return

        # Look up display device for MQTT notification
        target_uuid = self._find_display_uuid(body.get("device_id"))

        # Respond immediately; scan and delete in a background thread
        self.respond_success(True)

        def _delete():
            deleted = []
            deleted_ids = []
            for base_dir in (config.PHOTOS_DIR, config.PHOTOS_AI_DIR):
                directory = os.path.join(base_dir, device_id)
                for filename, filepath in scan_photos(directory):
                    file_hash = int.from_bytes(
                        hashlib.sha256(filename.encode()).digest()[:8], "big")
                    mid = str(file_hash % (10**18))
                    if mid in media_ids:
                        os.remove(filepath)
                        deleted.append(filename)
                        deleted_ids.append(mid)
            logger.info(
                "[DEL MEDIA] device=%s requested=%d deleted=%s",
                device_id, len(media_ids), deleted)
            # Publish MQTT notification to display device
            if deleted_ids and target_uuid:
                msg = json.dumps({
                    "uuid": target_uuid,
                    "msg_id": generate_msg_id(),
                    "event": "ipad/media/delete",
                    "data": deleted_ids,
                })
                try:
                    mqtt_publish.single(
                        f"/s2c/{target_uuid}",
                        payload=msg, qos=1,
                        hostname=config.MQTT_BROKER_HOST,
                        port=config.MQTT_BROKER_PORT,
                        auth={"username": config.MQTT_USER,
                              "password": config.MQTT_PASS},
                    )
                except Exception:
                    logger.exception(
                        "[DEL MEDIA] MQTT publish to %s failed", target_uuid)

        threading.Thread(target=_delete, daemon=True).start()

    def handle_media_update(self, body):
        """Update per-photo display settings.

        Body: ``{'id': '<media_id>', 'display':
        '{"positionX":50,"positionY":16}', 'template_id': <int>,
        'template_type': <int>}``. Stores the display string and template
        choice keyed by media ID in media_settings. For AI photos
        ``template_id`` (1..5 horizontal / 1..4 vertical on 16:9 displays,
        1..10 on 4:3) and ``template_type`` (1=horizontal, 2=vertical)
        determine which layout the iPad webapp renders; for non-AI photos
        they are stored verbatim and ignored by the webapp.
        """
        media_id = str(body.get("id", ""))
        display = body.get("display", "")

        if not media_id:
            self.respond_success(True)
            return

        template_id = body.get("template_id", 0)
        template_type = body.get("template_type", 0)

        settings = load_media_settings()
        existing = settings.get(media_id, {})
        existing["display"] = display
        existing["template_id"] = template_id
        existing["template_type"] = template_type
        settings[media_id] = existing
        device_id = existing.get("device_id")
        save_media_settings(settings)

        # Publish MQTT notification with full media record to display device
        # (the webapp JS reads id, title, remark, status, and asset.url)
        if device_id:
            target_uuid = self._find_display_uuid(device_id)
            if target_uuid:
                record = self._build_media_record_by_id(
                    media_id, int(device_id), display, template_id,
                    template_type)
                if record:
                    msg = json.dumps({
                        "uuid": target_uuid,
                        "msg_id": generate_msg_id(),
                        "event": "ipad/media/status",
                        "data": record,
                    })
                    try:
                        mqtt_publish.single(
                            f"/s2c/{target_uuid}",
                            payload=msg, qos=1,
                            hostname=config.MQTT_BROKER_HOST,
                            port=config.MQTT_BROKER_PORT,
                            auth={"username": config.MQTT_USER,
                                  "password": config.MQTT_PASS},
                        )
                    except Exception:
                        logger.exception(
                            "[MEDIA UPDATE] MQTT publish to %s failed",
                            target_uuid)

        logger.info(
            "[MEDIA UPDATE] id=%s display=%s", media_id, display)
        self.respond_success(True)

    def handle_asset_token(self, body):
        """Return a Qiniu-style upload token for local photo storage.

        The token format is ``AccessKey:Sign:EncodedPolicy`` matching what
        the native app's Qiniu SDK expects.  The embedded policy points
        the callback URL at our local upload endpoint so uploads stay
        offline.
        """
        expire = body.get("expire", 3600)
        token = generate_upload_token(expire)
        self.respond_success({
            "token": token,
            "domain": "/photos/",
        })
        logger.info("[ASSET TOKEN] issued Qiniu-style token")

    def handle_qiniu_query(self, params):
        """Return Qiniu region lookup pointing upload domains at this server.

        The native app's Qiniu SDK calls ``GET /v4/query?ak=...&bucket=...``
        on ``api.qiniu.com`` after obtaining an upload token.  With DNS
        redirected to this server, we return ``ifp.ga.codethriving.com`` as
        the upload domain so the SDK uploads to us instead of Qiniu.
        """
        host = "ifp.ga.codethriving.com"
        logger.info(
            "[QINIU QUERY] ak=%s bucket=%s -> %s",
            params.get("ak", [None])[0],
            params.get("bucket", [None])[0], host)
        self.respond_json({
            "hosts": [
                {
                    "region": "z2",
                    "ttl": 86400,
                    "up": {
                        "domains": [host],
                        "old": [host],
                    },
                    "io": {"domains": [host]},
                    "io_src": {"domains": [host]},
                    "uc": {"domains": [host]},
                    "rs": {"domains": [host]},
                    "rsf": {"domains": [host]},
                    "api": {"domains": [host]},
                    "s3": {"domains": [host],
                           "region_alias": "cn-south-1"},
                }
            ],
            "ttl": 86400,
        })
