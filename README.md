# iFramix Local - Offline Controller for iFramix Pro and iCharGuard

Run your iFramix Pro picture frame and iCharGuard charger **without the Chinese cloud**. 
This project replaces the cloud server with one you run yourself at home, 
so your pictures stay in-house and devices keep working even if the manufacturer's servers go offline.

No firmware changes are needed. We simply tell your network "when devices ask for the cloud server, send them to my computer instead."

## Will this work for me?

Yes - if you are tech-savvy, use an iPad to display the pictures and use an iPhone or iPod touch to control the picture frame.

If you use an Android phone (e.g. Samsung) to control the picture frame, or an Android tablet to display the pictures,
this project unfortunately **does not (yet) work for you.** Stay tuned for future updates on Android support.

The project has been tested with iFramix Pro app version **2.2.29**. Download the latest version from the 
[App Store](https://apps.apple.com/us/app/iframix-pro/id6470332689) or install an older version from [Pgyer](https://pgyer.com/iframixPro).

See [COMPATIBILITY.md](COMPATIBILITY.md) for which features work with which app version.

## Important Disclaimer

> [!CAUTION]
> **This is NOT an official iFramix product.**
>
> **This project and the author are NOT affiliated with iFramix Pro and Chengdu Malong Technology Co., Ltd in ANY way.**
>
>  **The creator of this project is [Arjan Vlek](https://github.com/arjanvlek)**
> 
> **Use of this project is ENTIRELY AT YOUR OWN RISK. The creator is not responsible for any damage resulting from use of this project, including damage to your iCharGuard charger, wooden iFramix picture frame, the device you place inside the picture frame and the device you use to control your picture frame. Do NOT disassemble the charger module or the LED Strip of your picture frame because of the risk of electric shock!**.

## Important Security Notice

> [!CAUTION]
> This project is aimed to be run at a local computer or server at home. Since the login page does not validate your username and password, and photos can be downloaded from the admin page, you should NOT install this project on a public server, VPS or other cloud service.

## What you'll need

Before you start, make sure you have:

1. **A computer that stays always on** (Linux, macOS, or Windows). This will be your "server". It needs to be on the same Wi-Fi/network as your picture frame's charger and iPad.
2. **Python 3.9 or newer** installed. ([How to install Python](https://www.python.org/downloads/))
3. Preferably: **Docker Desktop** or **Docker Engine for Linux** installed. ([How to install Docker](https://www.docker.com/products/docker-desktop/)). An advanced guide [without Docker](docs/debian-mosquitto-dns-server-setup.md) is available.
4. **Your router's admin page and login**, so you can change DNS settings.
5. **About 30-60 minutes** of free time.

You should also be comfortable opening the Command Prompt (Terminal) and running commands. 
Don't worry, every command you need is written out below.

## Before you start: find your server's IP address

You'll need this in several steps. On the computer that will run the server:

- **macOS / Linux:** open a terminal and run `ifconfig` (or `ip addr` on Linux). Look for an address like `192.168.x.x`.
- **Windows:** open Command Prompt and run `ipconfig`. Look for "IPv4 Address".

Write this address down. We'll call it `<YOUR_SERVER_IP>` throughout this guide.

## Step-by-step setup

Follow the next steps in order to get the project set up.

### Step 1: Clone this Repository & Install Python dependencies

Go to a directory of your choice. On linux systems, preferably the `/opt` directory.
Remember this location.

Then, download the project to your server:

```bash
git clone https://github.com/arjanvlek/iframix-local.git
```

> [!NOTE]
> On Linux, the /opt directory may not be writable, resulting in a 'permission denied' error. If this happens, scroll down to '[Troubleshooting](#troubleshooting)' to see how to fix this.

Next, download the Python libraries the server needs.

```bash
pip install -r requirements.txt
```

Finally, open a terminal on your server machine and `cd` into the folder where you downloaded this project. 
Use this for the next steps.

### Step 2: Start the MQTT broker

MQTT is the messaging system the charger and app use to talk to the server. Docker will run it for us.

To start it, run:

```bash
docker compose up -d
```

You can check if it's running with `docker ps`. You should see an item named `mosquitto`.

> [!TIP]
> If Docker is not working, scroll down to [Troubleshooting](#troubleshooting) to fix the issue.

### Step 3: Download the webapp assets

The icons, HTML files, and scripts shown inside the iPad app are copyrighted by the original makers, so we cannot include them by default. 
These scripts download them for you from the original maker's server. Run them **one at a time**, in this order:

```bash
python3 scripts/fetch-webapp-assets.py
python3 scripts/fetch-pad1-webapp-assets.py
python3 scripts/fetch-download-assets.py
python3 scripts/fetch-weather-icons.py
./scripts/apply-local-index-html-patch.sh
```

### Step 4: Create a security certificate

The iFramix app only talks over HTTPS (secure connections), which needs a certificate. Since we're not a real cloud company, we'll make our own.

Copy and paste this whole command:

```bash
openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt \
    -days 365 -nodes -subj '/CN=ifp.ga.codethriving.com' \
    -addext 'subjectAltName=DNS:ifp.ga.codethriving.com,DNS:api.qiniu.com,DNS:upload-z2.qiniup.com,DNS:up-z2.qiniup.com,DNS:iframixcn.codethriving.com'
```

This creates two files: `server.crt` (the certificate) and `server.key` (the secret key). Keep them in the project folder.

### Step 5: Tell your iPad to trust the certificate

Because we made the certificate ourselves, the iPad doesn't trust it yet. We need to install it as a trusted certificate. 
Do this on every iPad or device that will run the iFramix app.

**5a.** On your server, start a small temporary web server so the iPad can download the certificate:

```bash
python3 -m http.server 8888
```

Leave this running until step 5e.

**5b.** On your iPad, open Safari and go to:

```
http://<YOUR_SERVER_IP>:8888
```

**5c.** Tap on `server.crt`. Safari will ask if you want to download a configuration profile. Tap **Allow**.

**5d.** Open the **Settings** app on your iPad. Near the top, you should see "Profile Downloaded". Tap it, then tap **Install** and enter your iPad passcode.

**5e.** Now go to **Settings → General → About → Certificate Trust Settings**. Find the new certificate and toggle it **on**. (Apple's guide: https://support.apple.com/en-us/102390 )

You can now stop the temporary web server in your terminal by pressing **Ctrl+C**.

### Step 6: Point cloud addresses to your server (DNS overrides)

This is the magic step. We tell your network "when something asks for the iFramix cloud, send them to my server instead."

Log in to your router (usually by visiting `http://192.168.1.1` or `http://192.168.0.1` in a browser) and find the DNS or "Local DNS" settings. 
Add an entry for **each** of these hostnames, all pointing to `<YOUR_SERVER_IP>`:

| Hostname                     | Why it's needed                                 |
|------------------------------|-------------------------------------------------|
| `ifp.ga.codethriving.com`    | Main app, MQTT broker, web-app, downloads       |
| `api.qiniu.com`              | Photo upload region lookup (older app versions) |
| `upload-z2.qiniup.com`       | Photo upload target (older app versions)        |
| `up-z2.qiniup.com`           | Photo upload target (older app versions)        |
| `iframixcn.codethriving.com` | Weather station icons                           |

> [!NOTE]
> If your router doesn't support custom DNS entries, you can run a local DNS server like Pi-hole or AdGuard Home instead.
> See the [advanced guides](docs/debian-mosquitto-dns-server-setup.md) how to set up one.

### Step 7: Start the charger router

This program listens for chargers and remembers their state.
To start it, run:

```bash
python3 icharguard-router.py --headless
```

Leave this terminal window open. If you want to control chargers directly from the terminal, run it without `--headless`. See [docs/router.md](docs/router.md) for details.

### Step 8: Start the API server

Open a **new terminal window** (keep the router from step 7 running), go to the directory where you've downloaded the project,
and start the API server:

```bash
sudo python3 icharguard-api.py
```

You'll need `sudo` and your password because the server uses port 443 (the standard HTTPS port).

If you don't want to use sudo, you can test on a different port without SSL:

```bash
python3 icharguard-api.py --port 8080 --no-ssl
```

See [docs/api-server.md](docs/api-server.md) for all options.

### Step 9: Open the admin page

In any browser on your network, go to:

```
https://<YOUR_SERVER_IP>/admin
```

You should see a page that shows 'Chargers' and 'Display Devices'. 
This is where you manage your chargers and picture frames. See [docs/admin-page.md](docs/admin-page.md) for what you can do here.

> [!NOTE]
> If it's not working, scroll down to [Troubleshooting](#troubleshooting) to find tips on what could be causing the issue.

### Step 10: Try the iFramix Pro app

Open the iFramix Pro app on your iPad. If everything is set up right, it will now talk to your server instead of the cloud.

**To log in, use any email and password you like** (anything that looks like a real email and is long enough will work). The server doesn't actually verify them.

To confirm it's working, log in with a non-existing email address and your own chosen password. 
Since the real app wouldn't accept this, you'll know the local one is working if you are able to log in.

You can also look at the terminal where the API server is running. You should see lots of incoming requests as the app loads.

If it's not working, scroll a bit down to view [Troubleshooting](#troubleshooting) steps.

### Step 11: Making the server setup permanent

Congratulations! The iFramix app is now working locally.

Now, let's make the setup permanent, so it won't stop working when you disconnect from your server.

To make the app run permanently, follow these guide in order to 'deploy' the app permanently to the server.

[Debian background service setup](docs/debian-background-service-setup.md):

## Troubleshooting

**The app shows a connection error.**
- Check that the DNS overrides in your router are correct and your iPad is using the router's DNS (try toggling Wi-Fi off and on).
- Make sure the certificate is fully trusted (Step 5e).
- Make sure both the router (Step 7) and API server (Step 8) are running.

**`git clone` says "permission denied"**
- On linux, you may not be allowed to write to the `/opt` directory. If this happens, clone the project in a different directory first,
then move it as administrator to `/opt`. Finally, make the moved project accessible to you.
  - `sudo mv /path/to/downloaded-iframix-local /opt` to move the project to `/opt`
  - `sudo chown -R <your_username>:<your_username> iframix-local` to make the moved project accessible to you.

**`sudo python3 icharguard-api.py` says "permission denied" or "port in use".**
- Another program may be using port 443, most likely a Web Server such as Apache or NGINX. 
- Try the non-SSL test command in Step 8 to confirm the server itself starts.
- Then, find out what program is running on your server. If you already have a Web Server running on port 443, you
may have to proxy this project through your Web Server (search for 'apache reverse proxy' or 'nginx reverse proxy' depending on which web server you use.)

**Docker says it can't start the container.**
- On Windows / macOS: Make sure Docker Desktop is running (look for the whale icon in your menu bar or system tray).
- On Linux, make sure `containerd` and `docker.service` are running. Run `docker ps` to test if Docker works.

## Documentation

### Setup and operation

- [Router](docs/router.md): headless/CLI modes, logging options, CLI commands.
- [Backend API Server](docs/api-server.md): options, certificate generation, ports.
- [Admin Page](docs/admin-page.md): browser-based control of chargers and display devices.
- [Debian background service setup](docs/debian-background-service-setup.md): running the application in the background on your server.
- [Debian Custom Mosquitto / DNS server setup](docs/debian-mosquitto-dns-server-setup.md): manual setup of Mosquitto (without Docker) and a custom dnsmasq DNS server.

### How things work under-the-hood

- [Architecture and MQTT message flow](docs/architecture.md): components, topics, and how they talk to each other.
- [Photos](docs/photos.md): local replacement for AI mode and cloud uploads, classification flow.
- [Weather](docs/weather.md): Open-Meteo adapter, per-device config, weather icons.
- [Project structure](docs/project-structure.md): full file layout and runtime artefacts.
- [Compatibility](COMPATIBILITY.md): which features work with which app version.
- [Assets per app version](ASSETS_PER_APP_VERSION.md): minified asset files mapped to app versions.
- [Assets per app version (iPad 1)](ASSETS_PER_APP_VERSION_PAD1.md): same overview for the iPad 1 web-app.

### Testing

- [Running tests](docs/testing.md): test suite setup, what is covered.

## Usage of Generative AI within this project

I believe in transparency when it comes to using Generative AI / LLM to develop software. 

**Has Generative AI been used within this project?**

Yes. Most of the source code and tests in this project have been generated using Claude Code, including parts of the documentation.

**Has the project and its code been manually validated / tested before releasing it?**

Yes. The code has been validated and I've manually tested everything with a real iFramix set and a Raspberry Pi server. 

I've also manually validated the documentation and adjusted it where needed.

## License

This project and the author are not affiliated with iFramix and Chengdu Malong Technology Co., Ltd in any way.

Usage is at your own risk.

All webapp assets, images and fonts remain under copyright of their respective authors.

The content of this repository is licensed under the MIT license.
