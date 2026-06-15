"""Load and save functions for all persistent state, backed by SQLite.

Each function opens its own connection and closes it when done, relying
on SQLite WAL mode for concurrency rather than Python threading locks.

The function signatures return the same data structures as the old
JSON-based layer (dicts and lists) so callers require minimal changes.
"""

import json

from src.db import get_connection


# --- Devices ---

def load_devices():
    """Load all devices as {uuid: info_dict}.

    `charging_switch` carries the desired state (what the controller app
    last asked for). `charging_switch_reported` carries the actual state
    the charger last echoed back over MQTT (may be None if the firmware
    never includes that field).
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM devices").fetchall()
        result = {}
        for row in rows:
            result[row["uuid"]] = {
                "uuid": row["uuid"],
                "mac": row["mac"],
                "firmware": row["firmware"],
                "wifi_name": row["wifi_name"],
                "voltage": row["voltage"],
                "current": row["current_"],
                "battery": row["battery"],
                "charging_switch": row["charging_switch"],
                "charging_switch_reported":
                    row["charging_switch_reported"],
                "admin_switch": row["admin_switch"],
                "polling": row["polling"],
                "cloud_id": row["cloud_id"],
                "last_seen": row["last_seen"],
                "mode": row["mode"],
            }
        return result
    finally:
        conn.close()


def save_devices(devices):
    """Save all devices (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM devices")
        for uuid, info in devices.items():
            conn.execute("""
                INSERT INTO devices
                    (uuid, mac, firmware, wifi_name, voltage, current_,
                     battery, charging_switch, charging_switch_reported,
                     admin_switch, polling, cloud_id, last_seen, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid,
                info.get("mac"),
                info.get("firmware"),
                info.get("wifi_name"),
                info.get("voltage"),
                info.get("current"),
                info.get("battery"),
                info.get("charging_switch"),
                info.get("charging_switch_reported"),
                info.get("admin_switch"),
                info.get("polling"),
                info.get("cloud_id"),
                info.get("last_seen"),
                info.get("mode") or "manual",
            ))
        conn.commit()
    finally:
        conn.close()


_DEVICE_COL_MAP = {"current": "current_"}


def update_device_fields(uuid, **fields):
    """Update only the named fields on a single device row.

    Use this instead of load_devices/mutate/save_devices so concurrent writers
    touching disjoint columns (e.g. the router updating voltage/current while
    the API updates battery) don't clobber each other.
    """
    if not fields:
        return
    assignments = ", ".join(
        f"{_DEVICE_COL_MAP.get(k, k)} = ?" for k in fields)
    values = list(fields.values()) + [uuid]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE devices SET {assignments} WHERE uuid = ?", values)
        conn.commit()
    finally:
        conn.close()


def insert_device_if_missing(uuid, **fields):
    """Insert a device row with the given fields if uuid has no row yet."""
    cols = ["uuid"] + [_DEVICE_COL_MAP.get(k, k) for k in fields]
    placeholders = ", ".join(["?"] * len(cols))
    values = [uuid, *fields.values()]
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT OR IGNORE INTO devices ({', '.join(cols)}) "
            f"VALUES ({placeholders})",
            values)
        conn.commit()
    finally:
        conn.close()


# --- Charger readings ---

def load_charger_readings(mac):
    """Load all charger readings for a MAC address, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, mac, voltage, current_, add_time "
            "FROM charger_readings WHERE mac = ? ORDER BY add_time DESC",
            (mac,)).fetchall()
        return [{
            "id": str(row["id"]),
            "mac": row["mac"],
            "voltage": f"{row['voltage']:.2f}",
            "current": f"{row['current_']:.2f}",
            "add_time": row["add_time"],
        } for row in rows]
    finally:
        conn.close()


# --- Sessions ---

def _row_to_session(row):
    """Convert a sessions table row to the dict format handlers expect."""
    return {
        "uuid": row["uuid"],
        "id": row["id"],
        "device_name": row["device_name"],
        "device_type": row["device_type"],
        "ios_version": row["ios_version"],
        "width": row["width"],
        "height": row["height"],
        "user_id": row["user_id"],
        "user": row["user"],
        "is_ipad": row["is_ipad"],
        "is_h5": row["is_h5"],
        "bind_at": row["bind_at"],
        "created_at": row["created_at"],
        "last_login": row["last_login"],
        "last_active": row["last_active"],
        "last_disconnected_at": row["last_disconnected_at"],
        "icharger_mac": row["icharger_mac"],
        "screensaver": json.loads(row["screensaver_json"] or "[]"),
        "display": json.loads(row["display_json"] or "[]"),
        # None (not {}) when the device has never saved playback
        # settings — the GET endpoint translates that into the cloud's
        # empty-array response.
        "playback": (json.loads(row["playback_json"])
                     if row["playback_json"] else None),
    }


def load_sessions():
    """Load all sessions as {uuid: session_dict}."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        return {row["uuid"]: _row_to_session(row) for row in rows}
    finally:
        conn.close()


def save_sessions(sessions):
    """Save all sessions (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions")
        for sess_uuid, sess in sessions.items():
            _insert_session(conn, sess_uuid, sess)
        conn.commit()
    finally:
        conn.close()


def delete_session(sess_uuid):
    """Delete a single session row by UUID."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE uuid = ?", (sess_uuid,))
        conn.commit()
    finally:
        conn.close()


def touch_session_last_active(sess_uuid, timestamp):
    """Update only the `last_active` column on a single session row.

    A no-op when the uuid has no row (an unknown device never creates a
    session here). Touches no other column so it can run concurrently with
    full-row writes without clobbering them.
    """
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET last_active = ? WHERE uuid = ?",
            (timestamp, sess_uuid))
        conn.commit()
    finally:
        conn.close()


def _insert_session(conn, sess_uuid, sess):
    """Insert a single session row."""
    conn.execute("""
        INSERT OR REPLACE INTO sessions
            (uuid, id, device_name, device_type, ios_version,
             width, height, user_id, user, is_ipad, is_h5,
             bind_at, created_at, last_login, last_active,
             last_disconnected_at,
             icharger_mac, screensaver_json, display_json, playback_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sess_uuid,
        sess.get("id", 0),
        sess.get("device_name"),
        sess.get("device_type"),
        sess.get("ios_version"),
        sess.get("width", 0),
        sess.get("height", 0),
        sess.get("user_id", 1),
        sess.get("user", "local"),
        sess.get("is_ipad", 0),
        sess.get("is_h5", 0),
        sess.get("bind_at"),
        sess.get("created_at"),
        sess.get("last_login"),
        sess.get("last_active", 0),
        sess.get("last_disconnected_at", 0),
        sess.get("icharger_mac", ""),
        json.dumps(sess.get("screensaver", [])),
        json.dumps(sess.get("display", [])),
        (json.dumps(sess["playback"])
         if sess.get("playback") is not None else None),
    ))


# --- Bindings ---

def load_bindings():
    """Load charger MAC -> device UUID bindings as a dict."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM bindings").fetchall()
        return {row["charger_mac"]: row["device_uuid"] for row in rows}
    finally:
        conn.close()


def save_bindings(bindings):
    """Save all bindings (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM bindings")
        for mac, device_uuid in bindings.items():
            conn.execute(
                "INSERT INTO bindings (charger_mac, device_uuid) VALUES (?, ?)",
                (mac, device_uuid))
        conn.commit()
    finally:
        conn.close()


def delete_bindings_for_device(device_uuid):
    """Delete every binding that points at the given controller/display UUID."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM bindings WHERE device_uuid = ?", (device_uuid,))
        conn.commit()
    finally:
        conn.close()


# --- Weather config ---

def _row_to_weather_dict(row):
    # ``weather_template_id`` was added in schema v7. Some test fixtures
    # and older DBs may still have rows that predate it — ``sqlite3.Row``
    # raises IndexError on missing columns, so fall back to the default
    # (style 0, matching the iFramix 2.2.29 webapp's 0-based catalog).
    try:
        weather_template_id = row["weather_template_id"]
    except (IndexError, KeyError):
        weather_template_id = 0
    if weather_template_id is None:
        weather_template_id = 0
    return {
        "city": row["city"],
        "city_id": row["city_id"],
        "lat": row["lat"],
        "lon": row["lon"],
        "unit": row["unit"],
        "weather_template_id": weather_template_id,
    }


def load_weather_config(device_id):
    """Load the weather configuration for ``device_id``.

    Returns ``None`` when the device has no saved row. There is no
    global fallback — unconfigured devices are expected to show a
    "please configure in the controller device first" prompt.
    """
    if device_id is None:
        return None
    try:
        did = int(device_id)
    except (ValueError, TypeError):
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM device_weather_config WHERE device_id = ?",
            (did,)).fetchone()
        if row is None:
            return None
        return _row_to_weather_dict(row)
    finally:
        conn.close()


def lookup_weather_config_by_city_id(city_id):
    """Return any device's weather row matching ``city_id``.

    Used by the forecast endpoint when the caller passes ``city_id`` but
    no device ``id`` — we still need lat/lon to query Open-Meteo, and any
    device that previously saved this city carries the same coordinates.
    """
    if not city_id:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM device_weather_config WHERE city_id = ? LIMIT 1",
            (str(city_id),)).fetchone()
        if row is None:
            return None
        return _row_to_weather_dict(row)
    finally:
        conn.close()


def save_weather_config(cfg, device_id):
    """Save the weather configuration for ``device_id``.

    Returns ``True`` on a successful write, ``False`` when ``device_id``
    cannot be coerced to an integer (no global/anonymous storage now
    that weather is strictly per-device).
    """
    if device_id is None:
        return False
    try:
        did = int(device_id)
    except (ValueError, TypeError):
        return False
    conn = get_connection()
    try:
        raw_template_id = cfg.get("weather_template_id")
        if raw_template_id is None:
            weather_template_id = 0
        else:
            try:
                weather_template_id = int(raw_template_id)
            except (ValueError, TypeError):
                weather_template_id = 0
        # Clamp to the 0..3 range the iFramix 2.2.29 webapp ships.
        if weather_template_id < 0 or weather_template_id > 3:
            weather_template_id = 0
        conn.execute("""
            INSERT OR REPLACE INTO device_weather_config
                (device_id, city, city_id, lat, lon, unit,
                 weather_template_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            did,
            cfg.get("city", ""),
            cfg.get("city_id", ""),
            cfg.get("lat", ""),
            cfg.get("lon", ""),
            cfg.get("unit", 1),
            weather_template_id,
        ))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_weather_config_for_device(device_id):
    """Delete the per-device weather row (if any) for ``device_id``."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM device_weather_config WHERE device_id = ?",
            (int(device_id),))
        conn.commit()
    finally:
        conn.close()


# --- Calendars ---

def load_calendars():
    """Load all calendars as a list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM calendars").fetchall()
        return [{
            "id": row["id"],
            "device_id": row["device_id"],
            "driver": row["driver"],
            "name": row["name"],
            "url": row["url"],
            "update_at": row["update_at"],
        } for row in rows]
    finally:
        conn.close()


def save_calendars(calendars):
    """Save all calendars (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM calendars")
        for cal in calendars:
            conn.execute("""
                INSERT INTO calendars
                    (id, device_id, driver, name, url, update_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cal["id"],
                cal.get("device_id"),
                cal.get("driver", ""),
                cal.get("name", ""),
                cal.get("url", ""),
                cal.get("update_at", ""),
            ))
        conn.commit()
    finally:
        conn.close()


def delete_calendars_for_device(device_id):
    """Delete every calendar linked to ``device_id`` and return their IDs."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id FROM calendars WHERE device_id = ?",
            (device_id,)).fetchall()
        cal_ids = [row["id"] for row in rows]
        conn.execute(
            "DELETE FROM calendars WHERE device_id = ?", (device_id,))
        conn.commit()
        return cal_ids
    finally:
        conn.close()


# --- Calendar events ---

def load_calendar_events():
    """Load all manual calendar events as a list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM calendar_events").fetchall()
        return [{
            "id": row["id"],
            "summary": row["summary"],
            "driver": row["driver"],
            "uuid": row["uuid"],
            "start_date_time": row["start_date_time"],
            "end_date_time": row["end_date_time"],
            "description": row["description"],
            "update_at": row["update_at"],
            "schedule_id": json.loads(row["schedule_ids_json"] or "[]"),
        } for row in rows]
    finally:
        conn.close()


def delete_calendar_events_by_schedule_ids(cal_ids):
    """Delete any manual event whose schedule_id list overlaps ``cal_ids``.

    ``schedule_ids_json`` is a JSON-encoded list, so do the filter in
    Python rather than trying to express the overlap in SQL.
    """
    if not cal_ids:
        return
    cal_id_set = set(cal_ids)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, schedule_ids_json FROM calendar_events").fetchall()
        doomed = []
        for row in rows:
            try:
                sched = json.loads(row["schedule_ids_json"] or "[]")
            except json.JSONDecodeError:
                sched = []
            if cal_id_set.intersection(sched):
                doomed.append(row["id"])
        if doomed:
            placeholders = ",".join(["?"] * len(doomed))
            conn.execute(
                f"DELETE FROM calendar_events WHERE id IN ({placeholders})",
                doomed)
            conn.commit()
    finally:
        conn.close()


def save_calendar_events(events):
    """Save all calendar events (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM calendar_events")
        for evt in events:
            conn.execute("""
                INSERT INTO calendar_events
                    (id, summary, driver, uuid, start_date_time,
                     end_date_time, description, update_at,
                     schedule_ids_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                evt["id"],
                evt.get("summary", ""),
                evt.get("driver", "manual"),
                evt.get("uuid", ""),
                evt.get("start_date_time", ""),
                evt.get("end_date_time", ""),
                evt.get("description", ""),
                evt.get("update_at", ""),
                json.dumps(evt.get("schedule_id", [])),
            ))
        conn.commit()
    finally:
        conn.close()


# --- AI albums ---

def load_ai_albums():
    """Load AI album configs as {device_id_str: albums_list}."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM ai_albums").fetchall()
        return {
            str(row["device_id"]): json.loads(row["albums_json"] or "[]")
            for row in rows
        }
    finally:
        conn.close()


def save_ai_albums(albums):
    """Save all AI album configs (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM ai_albums")
        for device_id, album_list in albums.items():
            conn.execute(
                "INSERT INTO ai_albums (device_id, albums_json) VALUES (?, ?)",
                (int(device_id), json.dumps(album_list)))
        conn.commit()
    finally:
        conn.close()


def delete_ai_albums_for_device(device_id):
    """Delete the AI album row for ``device_id`` (if any)."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM ai_albums WHERE device_id = ?", (int(device_id),))
        conn.commit()
    finally:
        conn.close()


# --- Media settings ---

def load_media_settings():
    """Load media settings as {media_id: settings_dict}."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM media_settings").fetchall()
        return {
            row["media_id"]: {
                "device_id": row["device_id"],
                "display": row["display"],
                "template_id": row["template_id"],
                "template_type": row["template_type"],
            }
            for row in rows
        }
    finally:
        conn.close()


def save_media_settings(settings):
    """Save all media settings (full replace)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM media_settings")
        for mid, s in settings.items():
            conn.execute("""
                INSERT INTO media_settings
                    (media_id, device_id, display, template_id, template_type)
                VALUES (?, ?, ?, ?, ?)
            """, (
                mid,
                s.get("device_id"),
                s.get("display", ""),
                s.get("template_id", 0),
                s.get("template_type", 0),
            ))
        conn.commit()
    finally:
        conn.close()


def delete_media_settings_for_device(device_id):
    """Delete every media_settings row for ``device_id``."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM media_settings WHERE device_id = ?",
            (int(device_id),))
        conn.commit()
    finally:
        conn.close()


# --- Photo metadata cache (admin grid sort: upload / capture date) ---

def load_photo_metadata(device_id, media_type):
    """Return {filename: {"file_mtime": float, "capture_time": int|None}}
    for one device + media type. Backs the admin grid's upload/capture
    sort without re-reading every image header on each page request."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT filename, file_mtime, capture_time FROM photo_metadata "
            "WHERE device_id = ? AND media_type = ?",
            (int(device_id), media_type)).fetchall()
        return {
            r["filename"]: {
                "file_mtime": r["file_mtime"],
                "capture_time": r["capture_time"],
            }
            for r in rows
        }
    except (ValueError, TypeError):
        return {}
    finally:
        conn.close()


def upsert_photo_metadata(device_id, media_type, filename, file_mtime,
                          capture_time):
    """Insert or refresh one photo's cached mtime + EXIF capture time."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO photo_metadata
                (device_id, media_type, filename, file_mtime, capture_time)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id, media_type, filename) DO UPDATE SET
                file_mtime = excluded.file_mtime,
                capture_time = excluded.capture_time
        """, (int(device_id), media_type, filename, float(file_mtime),
              capture_time))
        conn.commit()
    except (ValueError, TypeError):
        pass
    finally:
        conn.close()


def upsert_photo_metadata_batch(rows):
    """Insert or refresh many photo metadata rows in ONE transaction.

    ``rows`` is an iterable of ``(device_id, media_type, filename,
    file_mtime, capture_time)`` tuples. A cold photo-heavy device can have
    hundreds of new/changed files in a single admin grid request; routing
    each through ``upsert_photo_metadata`` would open a fresh connection
    and fsync a separate commit per row (hundreds of fsyncs on an SD card).
    This opens one connection and issues a single ``executemany`` + commit.
    Non-numeric device_ids are skipped (mirrors the single-row helper);
    if every row is unusable the function is a no-op."""
    prepared = []
    for device_id, media_type, filename, file_mtime, capture_time in rows:
        try:
            prepared.append((int(device_id), media_type, filename,
                             float(file_mtime), capture_time))
        except (ValueError, TypeError):
            continue
    if not prepared:
        return
    conn = get_connection()
    try:
        conn.executemany("""
            INSERT INTO photo_metadata
                (device_id, media_type, filename, file_mtime, capture_time)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id, media_type, filename) DO UPDATE SET
                file_mtime = excluded.file_mtime,
                capture_time = excluded.capture_time
        """, prepared)
        conn.commit()
    finally:
        conn.close()


def delete_photo_metadata(device_id, media_type, filename):
    """Drop one photo's cached metadata row (on delMedia removal)."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM photo_metadata WHERE device_id = ? "
            "AND media_type = ? AND filename = ?",
            (int(device_id), media_type, filename))
        conn.commit()
    except (ValueError, TypeError):
        pass
    finally:
        conn.close()


def delete_photo_metadata_for_device(device_id):
    """Drop every photo_metadata row for a device (both media types).
    Called by unbindUser cleanup."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM photo_metadata WHERE device_id = ?",
            (int(device_id),))
        conn.commit()
    except (ValueError, TypeError):
        pass
    finally:
        conn.close()
