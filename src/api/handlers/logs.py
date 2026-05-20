"""Client log collection handler (iFramix Pro app 2.2.29+)."""

import json
import logging
import os
import re
import time

from src.api import config

logger = logging.getLogger(__name__)


_UUID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class LogsMixin:

    def handle_log_create(self, body):
        """Append a client-side log entry to ``logs/{device_uuid}/client.log``.

        iFramix Pro app 2.2.29 introduced a client telemetry endpoint that
        posts JSON diagnostics from the app. We persist one timestamped
        line per log entry, per device, so the payloads can be inspected
        offline.
        """
        device_uuid = self.headers.get("XX-Device-Uuid") or "unknown"
        if not _UUID_RE.match(device_uuid):
            device_uuid = "unknown"

        device_dir = os.path.join(config.LOGS_DIR, device_uuid)
        os.makedirs(device_dir, exist_ok=True)
        log_path = os.path.join(device_dir, "client.log")

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} {payload}\n")

        logger.info(
            "[LOG] device=%s type=%s", device_uuid, body.get("type", "?"))
        self.respond_success(True)
