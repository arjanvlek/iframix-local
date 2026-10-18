#!/usr/bin/env bash
# Re-apply the local patches to webapp/index.html after a fresh pull from the
# cloud server. Four patches are applied:
#
# 1. local-iframix-patch — the cloud-built webapp/index.html branches on
#    window.location.hostname and routes any non-prod/non-test host to a
#    hardcoded "iframixtest.codethriving.com" URL. That breaks when serving
#    locally (wrong API + MQTT host, wrong scheme under --no-ssl). This patch
#    rewrites that `else` branch to derive the values from window.location so
#    the same bundle works on any host/port and automatically tracks --no-ssl
#    via the page's own protocol.
# 2. iframix-mcol-overrides — fixes the Gallery Mode mcol_*/mrow_* template
#    layouts on non-4:3 displays.
# 3. iframix-flipclock-flexfix — fixes the flip clock on iOS 9/10 Safari.
# 4. iframix-home-legacyfix — fixes the 2.3.8 home-screen tiles on iOS 9/10
#    Safari.
#
# Patches 2-4 are <style> blocks (with their explanatory comment) stored in
# scripts/index-html-patches/<id>.html and inserted, in that order, right
# before </head>.
#
# Idempotent: each patch is detected by its marker (the comment marker for
# patch 1, the <style id="..."> for patches 2-4) and skipped when already
# present. A file that already carries all four patches is left untouched.
# Before the first change, the unpatched file is copied to <target>.orig.
#
# Usage:
#   scripts/apply-local-index-html-patch.sh                  # default: webapp/index.html
#   scripts/apply-local-index-html-patch.sh path/to/index.html

set -euo pipefail

target="${1:-webapp/index.html}"
snippet_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/index-html-patches"

if [[ ! -f "$target" ]]; then
    echo "error: $target not found" >&2
    exit 1
fi

python3 - "$target" "$snippet_dir" <<'PY'
import os
import re
import shutil
import sys

path, snippet_dir = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    src = f.read()
new = src

# --- Patch 1: local-iframix-patch -------------------------------------------

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

if "local-iframix-patch" in new:
    print("already applied: local-iframix-patch")
else:
    new, count = pattern.subn(replacement, new, count=1)
    if count != 1:
        print("error: fallback else-branch not found — bundle format changed?", file=sys.stderr)
        sys.exit(2)
    print("applied: local-iframix-patch")

# --- Patches 2-4: <style> blocks before </head> -----------------------------

style_ids = [
    "iframix-mcol-overrides",
    "iframix-flipclock-flexfix",
    "iframix-home-legacyfix",
]

def find_block(text, style_id):
    """Return the start of the block for style_id (its leading comment, if
    any), or None when the <style> is not present."""
    style = re.search(r'^[ \t]*<style\s+id="%s"' % re.escape(style_id), text, re.MULTILINE)
    if style is None:
        return None
    comment = None
    for comment in re.finditer(r"^[ \t]*<!--.*?-->[ \t]*\n", text[:style.start()], re.MULTILINE | re.DOTALL):
        pass
    if comment is not None and comment.end() == style.start():
        return comment.start()
    return style.start()

# Separate the local blocks from the bundle's own <head> content with a blank
# line, but only when none of them is present yet (a partially patched file
# already has that separator).
separator_needed = all(find_block(new, sid) is None for sid in style_ids)

for i, style_id in enumerate(style_ids):
    if find_block(new, style_id) is not None:
        print(f"already applied: {style_id}")
        continue
    with open(os.path.join(snippet_dir, style_id + ".html"), "r", encoding="utf-8") as f:
        snippet = f.read()
    # Keep the canonical order: insert before the first later block that is
    # already present, otherwise right before </head>.
    later = [find_block(new, sid) for sid in style_ids[i + 1:]]
    later = [pos for pos in later if pos is not None]
    if later:
        pos = min(later)
    else:
        head_end = re.search(r"^</head>", new, re.MULTILINE)
        if head_end is None:
            print("error: </head> not found at the start of a line — bundle format changed?", file=sys.stderr)
            sys.exit(2)
        pos = head_end.start()
    if separator_needed:
        snippet = "\n" + snippet
        separator_needed = False
    new = new[:pos] + snippet + new[pos:]
    print(f"applied: {style_id}")

if new == src:
    print(f"already patched: {path}")
    sys.exit(0)

shutil.copyfile(path, path + ".orig")
with open(path, "w", encoding="utf-8") as f:
    f.write(new)

print(f"patched: {path} (original saved as {path}.orig)")
PY
