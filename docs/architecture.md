# Architecture

## How it works

The iCharGuard charger communicates via MQTT v3.1.1 with static shared credentials and JSON payloads. This project intercepts that communication locally:

1. **DNS override** redirects charger traffic to your local server.
2. **Mosquitto MQTT broker** handles charger connections on port 1883 and app connections on port 9001.
3. **MQTT Router** responds to charger events and manages device state.
4. **Backend API Server** provides the REST API that the iFramix apps expect, serves the legacy webapp, and proxies MQTT-over-WebSocket.
5. **(Legacy) Web-App**: the display app for iPads on iOS 9+, based on original minified assets. Served by the Backend API Server at `/`.
6. **iPad 1 Web-App**: a separate, older-era web-app for iPads on iOS < 9. The main web-app automatically redirects these devices to `/pad1`. Served by the Backend API Server.
7. **Admin page** offers a browser-based administration solution in addition to the iFramix Pro controller app. Not available in the original product.

## MQTT Message Flow

All communication between components goes through the Mosquitto MQTT broker. There are two distinct topic namespaces:

- **`/mqtt/...`**: charger protocol topics (used by charger firmware, cannot be changed).
- **`/s2c/...`**: device notification topics (used by the webapp and native apps).

```
                         Mosquitto Broker
                        (port 1883 / 9001)
                               |
        ┌──────────────────────┼──────────────────────┐
        |                      |                      |
    CHARGER                  ROUTER                WEBAPP/APP
  (iCharGuard)          (headless mode)         (display device)

─── Charger announces itself ──────────────────────────────────

  Charger ──── /mqtt/cts/message ────> Router
               {event: "set_config",     │
                data: {uuid, mac, ...}}  │
                                         │
  Charger <── /mqtt/s2c/{charger} ─────  │  (get_config response)
                                         │
  Webapp  <──── /s2c/{device} ─────────  │  (bind notification)

─── Controller app changes settings ───────────────────────────

  Controller ──── POST /api/... ────> API Server
                                         │
  Webapp  <──── /s2c/{device} ─────────  │  (setting/media/calendar event)

─── CLI or Admin Page sends charging command ──────────────────

  CLI  ──── /mqtt/s2c/{charger} ────> Charger  (charging_switch)
```

### Topics Reference

| Topic                      | Direction                | Purpose                                                       |
|----------------------------|--------------------------|---------------------------------------------------------------|
| `/mqtt/cts/message`        | Charger -> Router        | Charger status events (`set_info`, `set_config`)              |
| `/mqtt/s2c/{charger_uuid}` | Router/CLI -> Charger    | Charger commands (`get_config`, `charging_switch`)            |
| `/s2c/{device_uuid}`       | API/Router -> Webapp/App | Device notifications (settings, media, calendar, bind/unbind) |

The webapp subscribes to `/s2c/{device_uuid}` via MQTT-over-WebSocket.

- For app versions 2.2.x and newer, this is on the URL `wss://<host>:443/websocket`, proxied to Mosquitto port 9001.
- For app versions 2.1.x and older, this is on the URL `ws://<host>:8083/mqtt`, also proxied to Mosquitto port 9001.
  - For this, you need to start 2 instances with the `--no-ssl` and `--webapp-version 2.1.3` arguments:
    - One with `--port 80`, which handles all traffic for the main app, except MQTT.
    - One with `--port 8083`, which only handles MQTT traffic.

The router subscribes to `#` (all topics) to log and process all traffic.
