# Backend API Server

The Backend API server implements the cloud REST API endpoints used by both the native iFramix apps and the legacy webapp.

It also serves three static frontends:

- **`/`**: the main web-app (`webapp/`), used by the native iFramix apps on display devices and via Safari on legacy iPads with iOS 9+.
- **`/pad1`**: the iPad 1 web-app (`webapp/pad1/`), for iPads with iOS < 9. The main web-app redirects there automatically.
- **`/download`**: the app download/install page (`webapp/download/`).

## Generate a self-signed certificate (once)

```bash
openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt \
    -days 365 -nodes -subj '/CN=ifp.ga.codethriving.com' \
    -addext 'subjectAltName=DNS:ifp.ga.codethriving.com,DNS:api.qiniu.com,DNS:upload-z2.qiniup.com,DNS:up-z2.qiniup.com,DNS:iframixcn.codethriving.com'
```

## Run

```bash
# Run (requires root for port 443)
sudo python3 icharguard-api.py

# Or on a custom port without SSL (for testing)
python3 icharguard-api.py --port 8080 --no-ssl
```

## Options

| Flag                  | Default      | Description                                                                 |
|-----------------------|--------------|-----------------------------------------------------------------------------|
| `--port`              | 443          | Port to listen on                                                           |
| `--no-ssl`            |              | Disable HTTPS (plain HTTP)                                                  |
| `--cert`              | `server.crt` | Path to SSL certificate                                                     |
| `--key`               | `server.key` | Path to SSL private key                                                     |
| `--mosquitto-ws-port` | 9001         | Mosquitto WebSocket listener port                                           |
| `--log-file`          | stdout       | Write INFO/DEBUG output to this file                                        |
| `--error-log-file`    | stderr       | Write WARNING/ERROR output to this file                                     |
| `--log-level`         | `INFO`       | `DEBUG`/`INFO`/`WARNING`/`ERROR` (DEBUG enables MQTT traffic)               |
| `--access-log-file`   | stdout       | Write per-request HTTP access log to this file (separate from `--log-file`) |

For production deployment, see [debian-background-service-setup.md](debian-background-service-setup.md).
