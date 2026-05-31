# Running Tests

The test suite verifies that the API server and MQTT router produce responses matching the [original cloud server specification](original-server-api-responses.md).

## Prerequisites

- Docker (for the Mosquitto test broker via [Testcontainers](https://testcontainers.com/))

## Setup

```bash
pip install -r requirements-test.txt
```

## Run

```bash
pytest
```

The tests automatically start a Mosquitto MQTT broker in Docker, spin up an isolated API server instance per test, and run the router as a subprocess. No manual broker setup is needed.

```bash
# Run with verbose output
pytest -v

# Run only API tests
pytest tests/api

# Run only router/MQTT tests
pytest tests/router

# Run a single feature's API tests
pytest tests/api/test_calendar.py

# Run a specific test class
pytest tests/api/test_auth.py::TestLogin -v
```

## What's Tested

- **Response format**: all endpoints return the `{code: 1, msg: "SUCCESS", data: ...}` envelope.
- **Login**: controller devices get `device: null`, display devices get a populated record.
- **Device management**: index, info, bind/unbind with correct field sets.
- **Settings**: screensaver, display, and address settings with MQTT notification side-effects.
- **Calendar**: link, list (with `linsence` typo preserved), and sync MQTT events.
- **Weather**: response format for configured devices, per-device isolation (two devices keep separate cities/units), empty `{}` response for unconfigured devices, unit preservation across address-only updates, the schema v7 `weather_template_id` column (round-trip through `values`, default 0 when omitted, preservation across city-only and address-only updates, propagation to the MQTT `ipad/device/setting/Weather` event), removal on `unbindUser`, and confirmation that the legacy global `weather_config` table is gone.
- **Media**: per-device photo listing, serving, upload (temp staging + setMedia classification), device isolation, per-photo display settings.
- **Download**: package info endpoint for the download page, privacy policy page.
- **Router**: charger `set_config`/`set_info` handling, `get_config` responses, charging history persistence, and auto-pairing.

Weather forecast and city search endpoints are not tested because they proxy to an external server.

## Continuous Integration

The full suite runs on every push to `main` and on every pull request via **GitHub Actions**. The workflow lives at [`.github/workflows/test.yml`](../.github/workflows/test.yml).

What the pipeline does:

1. Runs on the standard `ubuntu-latest` hosted runner, using the canonical `actions/checkout@v4` and `actions/setup-python@v5` actions.
2. Installs Python 3.13 via `setup-python`, with its built-in `cache: pip` (keyed by the hashes of `requirements.txt` + `requirements-test.txt`) so unchanged dependencies are not re-downloaded between runs.
3. Installs the Python dependencies from both requirements files.
4. Runs `pytest -v`.

No broker is installed or started by the workflow. GitHub's hosted runners ship with a Docker daemon, so the `mosquitto` fixture in `tests/conftest.py` starts the broker through Testcontainers exactly as it does locally.
