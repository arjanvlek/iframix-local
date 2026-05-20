# Weather

In the real product, weather is retrieved from QWeather (a Chinese weather information provider) via the cloud server, returning a 30-day forecast.

In this local implementation, weather data comes from **[Open-Meteo](https://open-meteo.com)** instead. No API key, no signup, free for non-commercial use, and globally available. 
Open-Meteo serves up to a 16-day forecast, which is short of the original 30 days but enough for the app's weather station view.

The Open-Meteo response is adapted in-process to the QWeather field shape the webapps and native apps expect. 
WMO weather codes are mapped to QWeather icon codes so the existing icon URLs at `iframixcn.codethriving.com/weather_icons/{code}.png` still resolve. 
City search uses Open-Meteo's geocoding endpoint with the same QWeather-shape adapter.

Forecast and city-search results are cached in-memory for **30 minutes** by the same city and unit type (Imperial / Metric), 
so many devices polling the same city only hit Open-Meteo once per half hour. Only successful responses are cached; transient errors retry immediately.

Weather settings (city + °C/°F unit + weather-station style) are stored per display device.

## Weather icons

The bundled webapp loads weather-station icons from `iframixcn.codethriving.com/weather_icons/{code}.png`.

To serve everything locally:

1. Add a DNS override pointing `iframixcn.codethriving.com` at the local server.
2. Include the hostname in the server certificate's `subjectAltName` list (the openssl one-liner in [api-server.md](api-server.md) already does this).
3. Pull the icon PNGs once with the fetch script:

   ```bash
   python3 scripts/fetch-weather-icons.py
   ```

The PNGs themselves are copyrighted by QWeather and intentionally not committed to the repo, so each user has to fetch them locally. 
The script resolves `iframixcn.codethriving.com` via the system resolver, pins the connection to the resulting IP 
(so it still works on a host that already overrides DNS for that name back at itself), and writes the QWeather catalog (day + night variants) into 
the `weather_icons/` directory next to the API server. 
Re-run with `--force` to refetch, or pass `--dest` / `--base-url` to target a custom location or a different upstream.
