"""Weather forecast and city search handler methods."""

import logging
import os
import re

from src.api import config, open_meteo
from src.api.persistence import (
    load_weather_config,
    lookup_weather_config_by_city_id,
)

logger = logging.getLogger(__name__)

_WEATHER_ICON_NAME_RE = re.compile(r"^\d{3}\.png$")


class WeatherMixin:

    def handle_weather_setting(self, params):
        """Return the configured weather city for a device.

        When the device has never had its weather configured we return
        an empty data object so the display device shows its
        "no relevant city information, please setup in the controller
        device first" prompt — there is no longer a global default.
        """
        device_id = params.get("id", ["?"])[0]
        weather_cfg = load_weather_config(device_id)
        if weather_cfg is None:
            logger.info("[WEATHER SETTING] id=%s (not configured)", device_id)
            self.respond_success({})
            return
        city = weather_cfg["city"]
        city_id = weather_cfg["city_id"]
        data = {
            "city": city,
            "cityMsg": {
                "id": city_id,
                "name": city,
                "lat": weather_cfg["lat"],
                "lon": weather_cfg["lon"],
            },
            "unit": weather_cfg["unit"],
            "weather_template_id": weather_cfg.get(
                "weather_template_id", 0),
        }
        logger.info(
            "[WEATHER SETTING] id=%s city=%s (%s) template_id=%s", device_id, city, city_id, data['weather_template_id'])
        self.respond_success(data)

    def handle_weather_forecast(self, params):
        """Return forecast days from Open-Meteo (QWeather-shaped, 30-min cached)."""
        lang = params.get("lang", ["en"])[0]
        device_id = params.get("id", [None])[0]
        city_id = params.get("city_id", [""])[0]

        cfg = load_weather_config(device_id) if device_id else None
        if cfg is None and city_id:
            cfg = lookup_weather_config_by_city_id(city_id)
        if cfg is None:
            logger.warning(
                "[WEATHER] no lat/lon for id=%s city_id=%s",
                device_id, city_id)
            self.respond_success([])
            return

        days = open_meteo.fetch_forecast(cfg["lat"], cfg["lon"], lang)
        logger.info("[WEATHER] open-meteo -> %d day(s)", len(days))
        self.respond_success(days)

    def handle_city_search(self, params):
        """Return city matches from Open-Meteo geocoding (QWeather-shaped)."""
        keyword = params.get("keyword", [""])[0]
        if not keyword:
            self.respond_success([])
            return
        lang = params.get("lang", ["en"])[0]
        adm = params.get("adm", [""])[0]
        results = open_meteo.search_cities(keyword, lang, adm)
        logger.info(
            "[CITY SEARCH] open-meteo '%s' -> %d result(s)",
            keyword, len(results))
        self.respond_success(results)

    def handle_weather_icon_serve(self, path):
        """Serve a weather icon PNG from the local weather_icons/ directory.

        Mirrors the URL the webapp hardcodes
        (``http://iframixcn.codethriving.com/weather_icons/{code}.png``) so a
        DNS override for that hostname can resolve locally. Icon files are
        copyrighted by QWeather and not committed to the repo — populate the
        directory via ``scripts/fetch-weather-icons.sh``.
        """
        rest = path[len("/weather_icons/"):]
        safe_name = os.path.basename(rest)
        if not _WEATHER_ICON_NAME_RE.match(safe_name):
            self.send_error(404, "Not found")
            return
        file_path = os.path.join(config.WEATHER_ICONS_DIR, safe_name)
        if not os.path.isfile(file_path):
            self.send_error(404, "Not found")
            return
        self.respond_file(
            file_path, cache_control="public, max-age=31536000, immutable")
