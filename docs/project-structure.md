# Project Structure

```
icharguard-router.py     # MQTT router entry point (thin wrapper)
icharguard-api.py        # REST API server entry point (thin wrapper)
docker-compose.yml       # Mosquitto MQTT broker (ports 1883 + 9001)
requirements.txt         # Runtime dependencies
requirements-test.txt    # Test-only dependencies
pytest.ini               # Pytest configuration
server.crt / server.key  # Self-signed TLS cert + key for the API server (gitignored in practice)
src/
  __init__.py
  db.py                  # SQLite connection helper + schema migrations (v1..v7)
  logging_setup.py       # Stdlib logging configuration shared by both entry points
  router/                # MQTT router implementation
    __init__.py
    config.py            #   Constants, shared device registry, generate_msg_id
    persistence.py       #   Load/save for devices, bindings, sessions, charger readings
    mqtt_handlers.py     #   MQTT callbacks with auto-pairing logic
    cli.py               #   Interactive CLI (device resolution, commands, display)
    main.py              #   run() with argparse, headless/interactive modes
  api/                   # REST API server implementation
    __init__.py
    config.py            #   Constants, file paths, thread locks
    persistence.py       #   Load/save for all SQLite-backed state (devices, sessions,
                         #     bindings, calendars, media_settings, ai_albums,
                         #     device_weather_config, charger_readings)
    utils.py             #   Shared utilities (snowflake IDs, tokens, image size, EXIF)
    devices.py           #   Device record builder functions
    open_meteo.py        #   Open-Meteo forecast + geocoding adapter, 30-min TTL cache
    handler.py           #   APIHandler class (routing, base HTTP) + main()
    handlers/            #   Feature handler mixins
      __init__.py
      auth.py            #     Login, webhook auth
      device_endpoints.py#     Device bind/unbind, list, info, battery, charger history
      settings.py        #     Screensaver, display, address, weather, AI albums
      weather.py         #     Weather forecast, city search, weather-icon serving
      calendar_endpoints.py#   Calendar link, index, events (incl. manual CRUD), sync
      media.py           #     Per-device photo listing, serving, both upload flows
                         #       (Qiniu-style + 2.2.29+ direct uploader), setMedia,
                         #       AI template auto-assignment, per-photo settings
      admin.py           #     /admin HTML, /admin/chargers refresh fragment,
                         #       /admin/toggle, /admin/set-mode (manual/auto)
      admin_assets/      #     Static admin-panel resources (extracted from inline HTML)
        admin.html       #       Page template
        admin.css        #       Styles
        admin.js         #       Client-side logic (uploads, modals, SVG previews)
      download.py        #     Download page package info, privacy policy
      logs.py            #     POST /api/user/log/create. Native-app client telemetry
                         #       (2.2.29+) appended to logs/{device_uuid}/client.log
      websocket.py       #     WebSocket proxy to Mosquitto (/websocket and /mqtt)
webapp/                  #   iFramix Pro web interface (Vue 2 SPA)
  index.html             #   Active entry point (carries the local hostname/MQTT patch). 
                         #   Retrieved from `scripts/fetch-webapp-assets.py`
  index.html.orig        #   Pristine cloud-built entry point, kept as a backup before
                         #     the local patch is applied.
  index.placeholder.html #   Template index.html which is served when `fetch-webapp-assets.py` has not yet been run
  static/                #   Content-hashed CSS/JS/image/font bundles, multi-version
                         #     (see ASSETS_PER_APP_VERSION.md for the per-file mapping)
    css/                 #     Versioned CSS bundles
    js/                  #     Versioned JS bundles
    images/              #     Bundled image assets
    fonts/               #     Bundled fonts
    assets/              #     Misc bundled assets
  download/              #   App download/install page (Vite-built Vue SPA, served at /download)
    index.html           #     Download page entry point
    xieyi/               #     Privacy policy page (static HTML)
      index.html
  pad1/                  #   Ultra-legacy iPad 1 web-app (separate Vue 2 SPA, served at /pad1)
    index.html           #     Entry point; main webapp redirects iOS < 9 here
    ipad-static/         #     Versioned asset bundles
                         #     (see ASSETS_PER_APP_VERSION_PAD1.md)
weather_icons/           # QWeather PNG icons (gitignored, populated by fetch script)
photos/                  # Per-device normal photos (gitignored, photos/{device_id}/)
photos_with_ai/          # Per-device AI photos (gitignored, photos_with_ai/{device_id}/)
photos_temp/             # Two-step upload staging (gitignored)
logs/                    # Native-app client telemetry (gitignored, logs/{device_uuid}/client.log)
scripts/
  fetch-webapp-assets.py          # Pull the main webapp bundles into webapp/
  fetch-pad1-webapp-assets.py     # Pull the iPad 1 webapp bundles into webapp/pad1/
  fetch-download-assets.py        # Pull the /download page bundles into webapp/download/
  fetch-weather-icons.py          # Pull the QWeather S1 PNG catalog into weather_icons/
  apply-local-index-html-patch.sh # Re-apply the local hostname/MQTT patch to a fresh
                                  # cloud-built webapp/index.html (idempotent)
docs/
  architecture.md                        # Architecture + MQTT message flow
  router.md                              # MQTT router options + CLI commands
  api-server.md                          # Backend API server options + cert generation
  admin-page.md                          # Browser admin panel reference
  photos.md                              # Local AI mode + upload flow
  weather.md                             # Open-Meteo adapter + weather icons
  testing.md                             # Test suite setup + coverage
  project-structure.md                   # This file
  debian-background-service-setup.md     # systemd unit for the headless router
  debian-api-server-setup.md             # Production deployment guide for the API
tests/                                   # Integration test suite
  __init__.py
  conftest.py                            #   Fixtures (Testcontainers, API server, collector)
  helpers.py                             #   Shared helpers (login, EXIF JPEG builders, seed_*)
  mosquitto.conf                         #   Mosquitto config for the test broker
  test_logging.py                        #   Logging setup tests
  test_persistence_concurrency.py        #   Cross-cutting persistence (clobber, migration)
  api/                                   #   Per-feature API endpoint tests
    __init__.py
    test_auth.py                         #     Login + webhook auth
    test_devices.py                      #     Index/info/bind/unbind
    test_battery.py                      #     refersh-battery (desired charging_switch)
    test_admin_charger.py                #     Admin toggle + auto/manual mode + set-mode
    test_admin_page.py                   #     /admin HTML page
    test_charger_history.py              #     Charger reading history endpoint
    test_charger_unbind.py               #     Unbind cleanup across all per-device data
    test_calendar.py                     #     External calendars + manual events
    test_media.py                        #     mediaList/setMedia/delMedia, uploaders
    test_media_update.py                 #     /api/ipad/media/update (display + template)
    test_ai_templates.py                 #     AI template auto-assignment by orientation
    test_exif.py                         #     EXIF parsing + AI remark synthesis
    test_screensaver.py                  #     Flip-clock styles + 12h/24h
    test_display.py                      #     Screen position/scale settings
    test_address.py                      #     Address (city) update + weather propagation
    test_weather.py                      #     Per-device weather + template_id round-trip
    test_assets.py                       #     Asset upload tokens + Qiniu shim
    test_static.py                       #     Download page + privacy policy
    test_envelope.py                     #     Response envelope shape
    test_persistence.py                  #     API-side narrow-update persistence
  router/                                #   Per-scenario router/MQTT tests
    __init__.py
    test_set_config.py                   #     Charger set_config -> get_config response
    test_set_info.py                     #     Device registration + reading history
    test_auto_pairing.py                 #     Auto-pair charger to controller
    test_persistence.py                  #     Router-side narrow-update persistence
```

## Top-level documentation

- `README.md`: project overview and quick-start guide.
- `COMPATIBILITY.md`: which picture frame features work with which app version.
- `ASSETS_PER_APP_VERSION.md`: minified asset files (under `webapp/static/`) mapped to app versions.
- `ASSETS_PER_APP_VERSION_PAD1.md`: same overview for the iPad 1 web-app (under `webapp/pad1/ipad-static/`).

## Runtime-only artefacts

All gitignored, created on first run:

- `icharguard.db` (+ `-wal` / `-shm`): SQLite database shared by the router and API server. Holds devices, sessions, bindings, calendars, manual events, media settings, AI albums, per-device weather config, charger readings. Migrations live in `src/db.py` (currently schema v7).
- `photos/{device_id}/`, `photos_with_ai/{device_id}/`, `photos_temp/`: uploaded media.
- `logs/{device_uuid}/client.log`: native-app telemetry (2.2.29+).
- `weather_icons/`: QWeather PNGs, populated by `scripts/fetch-weather-icons.py`.
- `webapp/`: iFramix webapp files, populated by `scripts/fetch-webapp-assets.py`, `scripts/fetch-pad1-webapp-assets.py` and `scripts/fetch-download-assets.py`.
- `server.crt` / `server.key`: local TLS cert/key.
