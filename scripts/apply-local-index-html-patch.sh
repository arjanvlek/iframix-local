#!/usr/bin/env bash
# Re-apply the local fallback patch to webapp/index.html after a fresh pull
# from the cloud server.
#
# The cloud-built webapp/index.html branches on window.location.hostname and
# routes any non-prod/non-test host to a hardcoded "iframixtest.codethriving.com"
# URL. That breaks when serving locally (wrong API + MQTT host, wrong scheme
# under --no-ssl). This script rewrites that `else` branch to derive the
# values from window.location so the same bundle works on any host/port and
# automatically tracks --no-ssl via the page's own protocol.
#
# Idempotent: detects an already-patched file via the marker comment and
# exits with status 0 without touching anything.
#
# Usage:
#   scripts/apply-local-index-html-patch.sh                  # default: webapp/index.html
#   scripts/apply-local-index-html-patch.sh path/to/index.html

set -euo pipefail

target="${1:-webapp/index.html}"

if [[ ! -f "$target" ]]; then
    echo "error: $target not found" >&2
    exit 1
fi

if grep -q 'local-iframix-patch' "$target"; then
    echo "already patched: $target"
    exit 0
fi

cp "$target" "$target.orig"

python3 - "$target" <<'PY'
import re
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# Match the cloud bundle's fallback `else { ... }` block — the one that sets
# the four window.* config fields plus debug + mqttMaxCount on the
# non-prod/non-test branch. The cloud bundle ships this with
# baseUrl = '//iframixtest.codethriving.com', but a user may also have
# hand-edited it to localhost; the regex tolerates both by anchoring on the
# four window.* assignments rather than the URLs.
pattern = re.compile(
    r"\}\s*else\s*\{\s*"
    r"window\.isHttps\s*=\s*[^;]+;\s*"
    r"window\.debug\s*=\s*[^;]+;\s*"
    r"window\.baseUrl\s*=\s*[^;]+;\s*"
    r"window\.mqttAddr\s*=\s*[^;]+;\s*"
    r"window\.appAddr\s*=\s*[^;]+;\s*"
    r"window\.mqttMaxCount\s*=\s*[^;]+;\s*"
    r"\}"
)

replacement = (
    "} else {\n"
    "            // local-iframix-patch: derive config from window.location so the\n"
    "            // same bundle works on any host/port and under --no-ssl. See\n"
    "            // scripts/apply-local-index-html-patch.sh.\n"
    "            window.isHttps = window.location.protocol === 'https:';\n"
    "            window.baseUrl = window.location.protocol + '//' + window.location.host;\n"
    "            window.mqttAddr = window.location.host;\n"
    "            window.debug = true;\n"
    "            window.appAddr = 'https://www.pgyer.com/iframixPro';\n"
    "            window.mqttMaxCount = 33;\n"
    "        }"
)

new, count = pattern.subn(replacement, src, count=1)
if count != 1:
    print("error: fallback else-branch not found — bundle format changed?", file=sys.stderr)
    sys.exit(2)

with open(path, "w", encoding="utf-8") as f:
    f.write(new)

print(f"patched: {path}")
PY
