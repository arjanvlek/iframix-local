# MQTT Router

The router handles charger discovery, responds to charger events, and manages charger-to-device bindings.

```bash
# Headless mode (background service. Use this for production)
python3 icharguard-router.py --headless

# Interactive CLI (manually send commands and view charger status)
python3 icharguard-router.py
```

**Headless mode** subscribes to MQTT, auto-discovers chargers, responds to their `set_config` events with charging parameters, persists device state to `devices.json`, and stores charger voltage/current history from `set_info` events. Run as a systemd service for production (see [debian-background-service-setup.md](debian-background-service-setup.md)).

**Interactive CLI** allows you to manually view and control the chargers. It does not subscribe to MQTT, so it runs safely alongside the headless service.

## Logging options (apply to both modes)

| Flag               | Default | Description                                                                   |
|--------------------|---------|-------------------------------------------------------------------------------|
| `--log-file`       | stdout  | Write INFO/DEBUG output to this file instead of stdout                        |
| `--error-log-file` | stderr  | Write WARNING/ERROR output to this file instead of stderr                     |
| `--log-level`      | `INFO`  | Minimum level: `DEBUG`/`INFO`/`WARNING`/`ERROR`. `DEBUG` enables MQTT traffic |

```bash
# Quiet by default; bump to DEBUG to see every MQTT message in/out
python3 icharguard-router.py --headless --log-level DEBUG

# Persist logs to files (e.g. when not running under systemd / journald)
python3 icharguard-router.py --headless \
    --log-file /var/log/icharguard/router.log \
    --error-log-file /var/log/icharguard/router.err
```

## CLI commands

| Command              | Description                              |
|----------------------|------------------------------------------|
| `list`               | Show all discovered charger devices      |
| `on [target]`        | Enable charging (no battery limit)       |
| `off [target]`       | Disable charging                         |
| `limit <N> [target]` | Enable charging with battery limit at N% |
| `quit`               | Exit                                     |

Targets can be a device number from `list`, a partial match on UUID/MAC/WiFi name, or a full UUID. When only one device is connected, the target can be omitted.
