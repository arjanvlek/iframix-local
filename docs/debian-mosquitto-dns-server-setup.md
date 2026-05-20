# Manual setup of Mosquitto and DNS server for iFramix Local

This guide explains how to setup a custom DNS server (dnsmasq) and install Mosquitto without using Docker.

This only works on Linux-based servers.

## Prerequisites

- Debian-based system with systemd
- Python 3 installed
- DNS overrides on the network router for `ifp.ga.codethriving.com`, `api.qiniu.com`, `upload-z2.qiniup.com`, `up-z2.qiniup.com` and `iframixcn.codethriving.com` 
(for the charger, which uses the router's DNS and cannot be configured to use a custom DNS server)

## 1. Install a custom DNS server (if your router doesn't support setting DNS records)

If your router doesn't have the ability to set DNS settings, 
the most reliable approach is to install `dnsmasq` on the server and point each iPad's DNS directly at it:

Install dnsmasq with `sudo apt install dnsmasq`.

Then, create the following config to redirect iFramix domain names to your server:

```bash
cat << 'EOF' | sudo tee /etc/dnsmasq.d/iframix-local.conf
address=/ifp.ga.codethriving.com/192.168.178.120
address=/api.qiniu.com/192.168.178.120
address=/upload-z2.qiniup.com/192.168.178.120
address=/up-z2.qiniup.com/192.168.178.120
address=/iframixcn.codethriving.com/192.168.178.120
EOF
```

Replace `192.168.178.120` with your server's IP. 

The Qiniu domains (`api.qiniu.com`, `upload-z2.qiniup.com`, `up-z2.qiniup.com`) are needed for photo uploads.
The `iframixcn.codethriving.com` domain is needed for the weather icons.

Then, restart dnsmasq with `sudo systemctl restart dnsmasq`

Then on each iPad, set the DNS server manually: **Settings > Wi-Fi > tap your network > Configure DNS > Manual**, and set it to your server's IP. 
Dnsmasq will answer with the local IP for all redirected domains and forward all other queries to the upstream DNS.

## 2. Install Mosquitto without Docker (with WebSocket support)

If not using Docker to run Mosquitto on your server, follow these steps to manually install it:

Install Mosquitto using `sudo apt install mosquitto`.

Then, create a custom config for iFramix Pro that enables it on port 1883 and 9001 (mqtt-over-websocket)

```bash
sudo tee -a /etc/mosquitto/conf.d/iframix-local.conf > /dev/null << 'EOF'

# MQTT over WebSocket for the iFramix (web)app
listener 9001
protocol websockets
EOF
```

Finally, restart Mosquitto to activate the new configuration.

```bash
sudo systemctl restart mosquitto
```

### 2.1. Verify if Mosquitto works

Run `systemctl status mosquitto` to verify if the service is "Active" (running) and "Enabled" (auto-starts at boot)
