# Running iFramix Local as a Background Service on Debian

In this guide, you'll set up your server to correctly run this app as a background process ("service").

**Note:** If you use a Mac or Windows computer as the server, a guide will be made available soon. Stay tuned!

## Prerequisites

- The server needs to have a Debian-based Linux system. A Raspberry Pi will work.
- Python 3 should be installed
- The Mosquitto MQTT broker should be running (via Docker, or locally installed)
- DNS overrides should be in place on your router, or you're using a custom DNS server such as `dnsmasq`, AdGuard Home or Pi-Hole


## 1. Create systemd service files to run the app in the background.

These files make the app start / run in the background. Handy, so they won't stop when you quit the terminal.

### 1.1:  Router

Run this command to create a service file for the Router component.

in `WorkingDirectory`, Use the path where you've previously downloaded the project (`git clone`).

```bash
sudo tee /etc/systemd/system/iframix-local-router.service > /dev/null << 'EOF'
[Unit]
Description=iFramix Local - MQTT Router
After=network.target

# If not running Mosquitto via docker, place a '#' on the After line above this message, 
# and remove the '#' on the following 2 lines.
# After=network.target mosquitto.service
# Wants=mosquitto.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/iframix-local
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/iframix-local/venv/bin/python3 /opt/iframix-local/icharguard-router.py --headless
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

The `--headless` flag runs the router as the background service: it subscribes to MQTT, auto-discovers devices, responds to charger events and persists device state. To send commands, run the script without `--headless` — the interactive CLI reads device state from the shared `devices.json` and publishes MQTT commands without conflicting with the headless instance.

### 1.2: Backend Server

Perform a similar step to run the Backend API server in the background:

```bash
sudo tee /etc/systemd/system/iframix-local-api.service > /dev/null << 'EOF'
[Unit]
Description=iFramix Local - Backend API Server
After=network.target

# If not running Mosquitto via Docker, place a '#' on the After line above this message, 
# and remove the '#' on the following 2 lines.
# After=network.target mosquitto.service
# Wants=mosquitto.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/iframix-local
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/iframix-local/venv/bin/python3 /opt/iframix-local/icharguard-api.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

## 2. Enable and start the application

You'll need to run a few commands to register the new application files (services), 
to enable these at system startup, and to start the applications.

```bash
# Registers the new service files you've just created
sudo systemctl daemon-reload

# Enables the application to start at system startup (skip if you don't want this)
sudo systemctl enable iframix-local-router.service
sudo systemctl enable iframix-local-api.service

# Start the application.
sudo systemctl start iframix-local-router.service
sudo systemctl start iframix-local-api.service
```

## 3. Check if the application is running (via systemd)

Now that the service is started, verify if it is actually running:

```bash
# Check status
sudo systemctl status iframix-local-router.service
sudo systemctl status iframix-local-api.service

```

The commands above should output a green circle and indicate that both services are 'active' and 'enabled' at system startup.

## 4. How to start, stop and restart the application

Use the following commands to start, stop and re-start the application:

```bash
# Restart (e.g. after code changes, or new 'git pull')
sudo systemctl restart iframix-local-router.service
sudo systemctl restart iframix-local-api.service

# Stop the application.
sudo systemctl stop iframix-local-router.service
sudo systemctl stop iframix-local-api.service

# Start the application.
sudo systemctl start iframix-local-router.service
sudo systemctl start iframix-local-api.service

# Disable auto-start on boot.
sudo systemctl disable iframix-local-router.service
sudo systemctl disable iframix-local-api.service

# Enable auto-start on boot.
sudo systemctl enable iframix-local-router.service
sudo systemctl enable iframix-local-api.service
```


## 5. Viewing logs

You can view the logs via the `journalctl` command. The option `-f` outputs new log messages directly to your screen.

If you want to view older logs, omit the `-f` parameter, or add `-n <amount_of_lines` to view more log lines.

```bash
# View recent logs
sudo journalctl -u iframix-local-router.service -f
sudo journalctl -u iframix-local-api.service -f

# View recent logs (last 100 lines)
sudo journalctl -u iframix-local-router.service -f -n 100
sudo journalctl -u iframix-local-api.service -f -n 100

# View older logs
sudo journalctl -u iframix-local-router.service
sudo journalctl -u iframix-local-api.service
```

## 6. Verify Mosquitto is also running as a service (if not using Docker)

**If you are using Docker to run Mosquitto, skip this step.**

Mosquitto should already be enabled as a service. Verify with:

```bash
sudo systemctl status mosquitto.service
```

If not yet enabled:

```bash
sudo systemctl enable mosquitto.service
sudo systemctl start mosquitto.service
```

The `After=` and `Wants=` directives in the icharguard-router service should be un-commented (remove '#'). 
This ensures the router only starts up after Mosquitto has finished starting up.

## 7. Configuring logs (write logs to separate log files)

The router (and API server) log standard-out and standard-error by default. This log can be viewed using `journalctl -u iframix-local-router` or `journalctl -u iframix-local-api`.

If you would rather have the logs stored as separate files, pass these flags on `ExecStart` in the systemd service files:
(`/etc/system/system/iframix-local-api.service` and `/etc/systemd/system/iframix-local-router.service`)
```ini
ExecStart=/opt/iframix-local/venv/bin/python3 /opt/iframix-local/icharguard-router.py \
    --headless \
    --log-file /var/log/iframix-local/router.log \
    --error-log-file /var/log/iframix-local/router.err \
    --log-level INFO
```

Use `--log-level DEBUG` to additionally log every MQTT message in/out (high volume; intended for troubleshooting).

For the API server, the same flags apply, plus `--access-log-file /var/log/iframix-local/access.log` to split the per-request HTTP access log into its own file (analogous to nginx `access.log`).

Afterward, run `systemctl daemon-reload` followed by `systemctl restart iframix-local-api` and `systemctl restart iframix-local-router` to apply the changes you've just made.
