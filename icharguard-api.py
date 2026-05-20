#!/usr/bin/env python3
"""
iCharGuard API Server

Simulates the cloud HTTPS API endpoints used by the iFramix controller apps
and serves the legacy iFramix webapp for old iPads.

Captures battery percentage reports and stores them in devices.json so the
router script can display battery levels alongside voltage/current.

Usage:
    # Generate a self-signed certificate first (once):
    openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt \
        -days 365 -nodes -subj '/CN=ifp.ga.codethriving.com' \
        -addext 'subjectAltName=DNS:ifp.ga.codethriving.com'

    # Run (requires root for port 443):
    sudo python3 icharguard-api.py

    # Or on a custom port without SSL (for testing):
    python3 icharguard-api.py --port 8080 --no-ssl
"""

import os
import sys

# Ensure the project root is on sys.path so src.api is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api import config  # noqa: E402
from src.api.handler import APIHandler, main  # noqa: E402
from src.api.persistence import load_devices  # noqa: E402
from src.api.utils import build_id_map  # noqa: E402

if __name__ == "__main__":
    main()
