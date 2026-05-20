#!/usr/bin/env python3
"""Download the QWeather S1 icon set into the local ``weather_icons/`` dir.

The bundled webapp hardcodes weather icon URLs to
``http://iframixcn.codethriving.com/weather_icons/{code}.png``. To serve them
locally (after a DNS override that points that hostname at this server), the
local ``weather_icons/`` directory must contain the same set of PNGs. The icon
images are copyrighted by QWeather and intentionally not committed to the
repo, so each user has to pull them themselves with this script.

Usage:
    python3 scripts/fetch-weather-icons.py [--dest weather_icons]
                                           [--base-url URL]
                                           [--force]

By default the script:
  - resolves ``iframixcn.codethriving.com`` by querying DNS server 8.8.8.8
    directly (bypassing any local DNS override that points the hostname at
    this very server) so it can pull from the real upstream even on the box
    that hosts the local replacement
  - writes to ``weather_icons/`` next to this script
  - skips icon codes that already exist on disk (use ``--force`` to refetch)
  - tolerates 404s for individual codes and reports them in the summary

The code list below covers every code referenced by ``src/api/open_meteo.py``
plus the full QWeather S1 catalog (day + night variants) so admin-uploaded
photos or future code-table edits do not silently fall back to a missing
icon.
"""

import argparse
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

try:
    import dns.exception
    import dns.resolver
except ImportError as _exc:
    raise SystemExit(
        "dnspython is required for this script. "
        "Install it with: pip install -r requirements.txt"
    ) from _exc

# DNS server queried directly when resolving the upstream host. Bypassing
# the system resolver matters on the box that hosts this project: its
# /etc/hosts or local dnsmasq points the upstream name back at itself, so
# the system resolver would return 127.0.0.1 instead of the real CDN.
DNS_SERVER = "8.8.8.8"

# Default upstream host. Resolved manually so a local DNS override doesn't
# bend the request back at the local server.
DEFAULT_HOST = "iframixcn.codethriving.com"
DEFAULT_BASE_URL = f"http://{DEFAULT_HOST}/weather_icons"

# Full QWeather icon catalog, per
# https://dev.qweather.com/en/docs/resource/icons/ (70 codes total). Day
# variants live in 1xx/3xx/4xx/5xx, night variants in 15x/35x/45x, moon
# phases in 80x, and 9xx covers extreme temperature / "unknown". Listing
# each code explicitly (instead of brute-forcing 100..999) keeps the script
# polite to the upstream server and makes it auditable against the docs.
ICON_CODES = [
    # --- Sun / cloud (day): 5 codes ---
    "100",  # Sunny
    "101",  # Cloudy
    "102",  # Few Clouds
    "103",  # Partly Cloudy
    "104",  # Overcast
    # --- Sun / cloud (night): 4 codes ---
    "150",  # Clear
    "151",  # Cloudy
    "152",  # Few Clouds
    "153",  # Partly Cloudy
    # --- Rain / thunderstorm (day & night where noted): 19 codes ---
    "300",  # Shower Rain (day)
    "301",  # Heavy Shower Rain (day)
    "302",  # Thundershower
    "303",  # Heavy Thunderstorm
    "304",  # Hail
    "305",  # Light Rain
    "306",  # Moderate Rain
    "307",  # Heavy Rain
    "308",  # Extreme Rain
    "309",  # Drizzle Rain
    "310",  # Rainstorm
    "311",  # Heavy Rainstorm
    "312",  # Severe Rainstorm
    "313",  # Freezing Rain
    "314",  # Light to Moderate Rain
    "315",  # Moderate to Heavy Rain
    "316",  # Heavy Rain to Rainstorm
    "317",  # Rainstorm to Heavy Rainstorm
    "318",  # Heavy to Severe Rainstorm
    # --- Rain (night only): 2 codes ---
    "350",  # Shower Rain
    "351",  # Heavy Shower Rain
    # --- Rain (generic): 1 code ---
    "399",  # Rain
    # --- Snow / sleet (day & night where noted): 11 codes ---
    "400",  # Light Snow
    "401",  # Moderate Snow
    "402",  # Heavy Snow
    "403",  # Snowstorm
    "404",  # Sleet
    "405",  # Rain and Snow
    "406",  # Shower Rain and Snow (day)
    "407",  # Snow Flurry (day)
    "408",  # Light to Moderate Snow
    "409",  # Moderate to Heavy Snow
    "410",  # Heavy Snow to Snowstorm
    # --- Snow (night only): 2 codes ---
    "456",  # Shower Rain and Snow
    "457",  # Snow Flurry
    # --- Snow (generic): 1 code ---
    "499",  # Snow
    # --- Fog / dust / haze: 14 codes ---
    "500",  # Mist
    "501",  # Fog
    "502",  # Haze
    "503",  # Sand
    "504",  # Dust
    "507",  # Duststorm
    "508",  # Sandstorm
    "509",  # Dense Fog
    "510",  # Strong Fog
    "511",  # Moderate Haze
    "512",  # Heavy Haze
    "513",  # Severe Haze
    "514",  # Heavy Fog
    "515",  # Extra Heavy Fog
    # --- Moon phases (lunar): 8 codes ---
    "800",  # New Moon
    "801",  # Waxing Crescent (N) / Waning Crescent (S)
    "802",  # First Quarter (N) / Last Quarter (S)
    "803",  # Waxing Gibbous (N) / Waning Gibbous (S)
    "804",  # Full Moon
    "805",  # Waning Gibbous (N) / Waxing Gibbous (S)
    "806",  # Last Quarter (N) / First Quarter (S)
    "807",  # Waning Crescent (N) / Waxing Crescent (S)
    # --- Temperature / unknown: 3 codes ---
    "900",  # Hot
    "901",  # Cold
    "999",  # Unknown (fallback used by src/api/open_meteo.py)
]


def resolve_host(host, dns_server=DNS_SERVER, timeout=10.0):
    """Resolve ``host`` by querying ``dns_server`` directly via dnspython.

    Bypasses ``/etc/resolv.conf`` and any local dnsmasq / /etc/hosts entry
    that would point the name back at this box. Returns ``None`` and logs
    to stderr on any DNS error.
    """
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(host, "A")
    except dns.exception.DNSException as exc:
        print(
            f"error: DNS query to {dns_server} for {host} failed: {exc}",
            file=sys.stderr)
        return None
    for record in answer:
        if record.address:
            return record.address
    print(
        f"error: DNS server {dns_server} returned no A record for {host}",
        file=sys.stderr)
    return None


def build_opener_with_pinned_host(host):
    """Return ``(opener, ip)`` that routes ``host`` requests to a fixed IP.

    Implemented by replacing the URL host with the resolved IP and sending
    the original hostname in the ``Host`` header. This sidesteps any local
    DNS override that might point the hostname at this very server.
    """
    ip = resolve_host(host)
    if ip is None:
        return None, None
    return urllib.request.build_opener(), ip


def rewrite_url_with_ip(url, host, ip):
    """Return ``url`` with its hostname replaced by ``ip``."""
    parsed = urlparse(url)
    netloc = parsed.netloc
    if parsed.port:
        netloc = f"{ip}:{parsed.port}"
    else:
        netloc = ip
    return parsed._replace(netloc=netloc).geturl()


def fetch_one(opener, url, host, ip, dest_path):
    """Fetch one icon. Returns ``"fetched"``, ``"skipped"`` or ``"missing"``."""
    direct_url = rewrite_url_with_ip(url, host, ip) if ip else url
    req = urllib.request.Request(direct_url, headers={"Host": host})
    try:
        with opener.open(req, timeout=15) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "missing"
        print(f"warn: {url} -> HTTP {exc.code}", file=sys.stderr)
        return "missing"
    except urllib.error.URLError as exc:
        print(f"warn: {url} -> {exc}", file=sys.stderr)
        return "missing"
    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, dest_path)
    return "fetched"


def main():
    parser = argparse.ArgumentParser(
        description="Pull QWeather S1 icons into weather_icons/")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dest = os.path.join(
        os.path.dirname(script_dir), "weather_icons")
    parser.add_argument(
        "--dest", default=default_dest,
        help=f"Destination directory (default: {default_dest})")
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=f"Upstream icon base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument(
        "--force", action="store_true",
        help="Refetch icons that already exist on disk")
    args = parser.parse_args()

    os.makedirs(args.dest, exist_ok=True)

    parsed = urlparse(args.base_url)
    host = parsed.hostname
    if host is None:
        print(f"error: cannot parse host from {args.base_url}", file=sys.stderr)
        return 1

    opener, ip = build_opener_with_pinned_host(host)
    if opener is None:
        return 1
    if ip != host:
        print(f"Resolved {host} -> {ip}")

    fetched = skipped = missing = 0
    for code in ICON_CODES:
        name = f"{code}.png"
        dest_path = os.path.join(args.dest, name)
        if os.path.isfile(dest_path) and not args.force:
            skipped += 1
            continue
        url = f"{args.base_url.rstrip('/')}/{name}"
        result = fetch_one(opener, url, host, ip, dest_path)
        if result == "fetched":
            fetched += 1
            print(f"  fetched {name}")
        elif result == "missing":
            missing += 1

    print()
    print(
        f"Done. fetched={fetched} skipped={skipped} missing={missing} "
        f"total={len(ICON_CODES)}")
    print(f"Stored in {args.dest}")
    if missing:
        print(
            "(missing codes are codes the upstream server doesn't ship — "
            "this is normal for a few of them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
