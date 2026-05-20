"""Open-Meteo weather backend with QWeather-shaped responses.

Provides forecast and city-search data to the iFramix apps without an API key.
All responses are adapted to the QWeather field contract the webapps expect.
A 30-minute in-memory TTL cache, keyed by location/unit/lang for forecasts and
keyword/lang/adm for geocoding, protects upstream from repeated hits.
"""

import json
import logging
import threading
import time
import urllib.request
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30 * 60

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_cache = {}
_cache_lock = threading.Lock()


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= time.time():
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key, value, ttl=CACHE_TTL_SECONDS):
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)


# WMO weather codes -> (QWeather icon code, English text, Chinese text).
#
# Targets QWeather icons served at iframixcn.codethriving.com/weather_icons/{code}.png.
# The bundled 2.2.x webapp uses a protocol-relative `//iframixcn.codethriving.com/...`
# URL so the request inherits the page's scheme; app 2.1.3 hardcodes `http://...`.
# See CLAUDE.md / scripts/fetch-weather-icons.py for the local serving setup.
#
# Coverage: every WMO code Open-Meteo documents in its `weather_code` field is
# mapped (0-3, 45/48, 51-57, 61-67, 71-77, 80-86, 95/96/99 — 27 codes total),
# and every target icon is a code that exists in the QWeather S1 catalog
# (see https://dev.qweather.com/en/docs/resource/icons/). Codes Open-Meteo
# does not emit (the gaps like 4..44, 46..47, 50, 52, 54, 58..60, 62, 64,
# 68..70, 72, 74, 76, 78..79, 83..84, 87..94, 97..98) intentionally have no
# entry — they would never be looked up. Unknown values fall through
# `_describe()` to QWeather's 999 "Unknown" icon.
_WMO_MAP = {
    # Sun / cloud (Open-Meteo 0..3 -> QWeather 100..104)
    0:  ("100", "Clear", "晴"),
    1:  ("102", "Mostly clear", "少云"),
    2:  ("103", "Partly cloudy", "晴间多云"),
    3:  ("104", "Overcast", "阴"),
    # Fog (Open-Meteo 45/48 -> QWeather 501 "Fog" / 514 "Heavy Fog")
    45: ("501", "Fog", "雾"),
    48: ("514", "Depositing rime fog", "浓雾"),
    # Drizzle (Open-Meteo 51..57 -> QWeather 309 "Drizzle Rain" / 313 "Freezing Rain")
    51: ("309", "Light drizzle", "毛毛雨"),
    53: ("309", "Drizzle", "毛毛雨"),
    55: ("309", "Dense drizzle", "毛毛雨"),
    56: ("313", "Light freezing drizzle", "冻雨"),
    57: ("313", "Freezing drizzle", "冻雨"),
    # Rain (Open-Meteo 61..67 -> QWeather 305..307 / 313 "Freezing Rain")
    61: ("305", "Light rain", "小雨"),
    63: ("306", "Moderate rain", "中雨"),
    65: ("307", "Heavy rain", "大雨"),
    66: ("313", "Light freezing rain", "冻雨"),
    67: ("313", "Freezing rain", "冻雨"),
    # Snow (Open-Meteo 71..77 -> QWeather 400..402)
    71: ("400", "Light snow", "小雪"),
    73: ("401", "Moderate snow", "中雪"),
    75: ("402", "Heavy snow", "大雪"),
    77: ("400", "Snow grains", "小雪"),
    # Rain showers (Open-Meteo 80..82 -> QWeather 300 "Shower Rain" / 301 "Heavy Shower Rain")
    80: ("300", "Rain showers", "阵雨"),
    81: ("300", "Rain showers", "阵雨"),
    82: ("301", "Violent rain showers", "强阵雨"),
    # Snow showers (Open-Meteo 85/86 -> QWeather 407 "Snow Flurry" / 410 "Heavy Snow to Snowstorm")
    85: ("407", "Snow showers", "阵雪"),
    86: ("410", "Heavy snow showers", "大雪转暴雪"),
    # Thunderstorm (Open-Meteo 95/96/99 -> QWeather 302 "Thundershower" / 304 "Hail")
    95: ("302", "Thunderstorm", "雷阵雨"),
    96: ("304", "Thunderstorm with hail", "雷阵雨伴有冰雹"),
    99: ("304", "Thunderstorm with heavy hail", "雷阵雨伴有冰雹"),
}


def _describe(code, lang):
    icon, en, zh = _WMO_MAP.get(code, ("999", "Unknown", "未知"))
    text = zh if lang == "zh" else en
    return icon, text


def _stringify_temp(value):
    if value is None:
        return ""
    return str(int(round(float(value))))


def _stringify_int(value):
    if value is None:
        return ""
    return str(int(round(float(value))))


def _stringify_precip(value):
    if value is None:
        return "0.0"
    return f"{float(value):.1f}"


def _stringify(value):
    if value is None:
        return ""
    return str(value)


def _time_of_day(value):
    """Extract ``HH:MM`` from an Open-Meteo ISO8601 local time string.

    QWeather returns sunrise/sunset as bare ``HH:MM``, and the webapp's
    weather station renders the value verbatim — passing the full
    ``YYYY-MM-DDTHH:MM`` shows the date too.
    """
    if value is None:
        return ""
    text = str(value)
    sep = text.find("T")
    if sep == -1:
        return text
    return text[sep + 1:sep + 6]


def _http_get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _daily_mean(daily_times, hourly_times, hourly_values):
    """Average ``hourly_values`` across each calendar day in ``daily_times``.

    Both time arrays are local ISO8601 strings produced by Open-Meteo with
    ``timezone=auto`` (``YYYY-MM-DDTHH:MM``), so day boundaries already match.
    """
    if not hourly_times or not hourly_values:
        return [None] * len(daily_times)
    buckets = {}
    for ts, value in zip(hourly_times, hourly_values):
        if value is None:
            continue
        day = ts[:10]
        bucket = buckets.setdefault(day, [0.0, 0])
        bucket[0] += float(value)
        bucket[1] += 1
    out = []
    for day_ts in daily_times:
        day = day_ts[:10]
        bucket = buckets.get(day)
        if bucket and bucket[1] > 0:
            out.append(bucket[0] / bucket[1])
        else:
            out.append(None)
    return out


def fetch_forecast(lat, lon, lang):
    """Return up to 16 days of forecast as QWeather-shaped dicts.

    Always requests metric units (°C, km/h, mm) — the webapp performs its
    own °C↔°F conversion based on the per-device ``unit`` setting it
    receives from ``/api/ipad/device/setting/weather``, so returning
    Fahrenheit here would double-convert. ``lang`` is "en" or "zh" (any
    other value falls back to English). Returns ``[]`` on upstream errors;
    caches only successful, non-empty results for 30 minutes.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return []
    lang_code = "zh" if lang == "zh" else "en"
    cache_key = ("forecast", round(lat_f, 4), round(lon_f, 4), lang_code)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    qs = urlencode({
        "latitude": lat_f,
        "longitude": lon_f,
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "sunrise", "sunset", "precipitation_sum", "wind_speed_10m_max",
            "uv_index_max",
        ]),
        "hourly": "relative_humidity_2m,surface_pressure,visibility",
        "timezone": "auto",
        "forecast_days": 16,
    })
    url = f"{_FORECAST_URL}?{qs}"

    try:
        data = _http_get_json(url)
    except Exception:
        logger.exception("[WEATHER] Open-Meteo forecast error")
        return []

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        logger.warning("[WEATHER] Open-Meteo returned no daily entries")
        return []

    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    sunrise = daily.get("sunrise") or []
    sunset = daily.get("sunset") or []
    precip = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    uv = daily.get("uv_index_max") or []

    hourly = data.get("hourly") or {}
    humidity_daily = _daily_mean(
        times, hourly.get("time") or [], hourly.get("relative_humidity_2m") or [])
    pressure_daily = _daily_mean(
        times, hourly.get("time") or [], hourly.get("surface_pressure") or [])
    visibility_daily = _daily_mean(
        times, hourly.get("time") or [], hourly.get("visibility") or [])

    def at(arr, i):
        return arr[i] if i < len(arr) else None

    out = []
    for i, day_ts in enumerate(times):
        code = at(codes, i)
        icon, text = _describe(int(code) if code is not None else -1, lang_code)
        out.append({
            "fxDate": day_ts,
            "iconDay": icon,
            "iconNight": icon,
            "textDay": text,
            "textNight": text,
            "tempMax": _stringify_temp(at(tmax, i)),
            "tempMin": _stringify_temp(at(tmin, i)),
            "sunrise": _time_of_day(at(sunrise, i)),
            "sunset": _time_of_day(at(sunset, i)),
            "humidity": _stringify_int(humidity_daily[i]),
            "pressure": _stringify_int(pressure_daily[i]),
            "precip": _stringify_precip(at(precip, i)),
            "windSpeedDay": _stringify_int(at(wind, i)),
            "uvIndex": _stringify_int(at(uv, i)),
            "vis": _stringify_int(
                None if visibility_daily[i] is None else visibility_daily[i] / 1000.0),
            "cloud": "",
            "moonPhase": "",
        })

    _cache_put(cache_key, out)
    return out


def search_cities(keyword, lang, adm):
    """Return up to 10 city matches as QWeather-shaped dicts.

    ``adm`` is an optional admin1 filter (case-insensitive). Returns ``[]``
    on errors; caches only successful, non-empty results for 30 minutes.
    """
    if not keyword:
        return []
    lang_code = "zh" if lang == "zh" else "en"
    adm_norm = (adm or "").strip().lower()
    cache_key = ("geocode", keyword.strip().lower(), lang_code, adm_norm)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    qs = urlencode({
        "name": keyword,
        "count": 10,
        "language": lang_code,
        "format": "json",
    })
    url = f"{_GEOCODING_URL}?{qs}"

    try:
        data = _http_get_json(url)
    except Exception:
        logger.exception("[CITY SEARCH] Open-Meteo geocoding error")
        return []

    raw = data.get("results") or []
    results = []
    for loc in raw:
        admin1 = loc.get("admin1") or ""
        if adm_norm and admin1.lower() != adm_norm:
            continue
        loc_id = loc.get("id")
        loc_id_str = str(loc_id) if loc_id is not None else ""
        results.append({
            "city_id": loc_id_str,
            "lang": lang_code,
            "name": loc.get("name", "") or "",
            "adm1": admin1,
            "adm2": loc.get("admin2") or "",
            "country": loc.get("country", "") or "",
            "rank": "",
            "lat": _stringify(loc.get("latitude")),
            "lon": _stringify(loc.get("longitude")),
            "id": loc_id_str,
        })

    if results:
        _cache_put(cache_key, results)
    return results
