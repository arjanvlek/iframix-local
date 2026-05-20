#!/usr/bin/env python3
"""Fetch static iFramix Pro webapp assets for a new app version.

Automates the procedure documented in
``.claude/skills/fetch-webapp-assets/SKILL.md``:

  1. Rename the currently-served ``webapp/index.html`` and
     ``webapp/static/js/app.js`` to ``index-<PREV>.html`` /
     ``app-<PREV>.js`` (preserving the older version alongside the new
     one). Skipped when the markdown sentinel is ``<NONE_YET>`` or when
     the source files are missing, so a fresh checkout with no
     ``webapp/`` contents works as a first-time run.
  2. Fetch the new ``index.html`` from ``https://ifp.ga.codethriving.com``
     using DNS server 8.8.8.8 (so a local DNS override that already points
     the hostname at this server is bypassed).
  3. Fetch every external resource referenced from ``index.html``
     (scripts, stylesheets, fonts, images). Including ``<script nomodule>``
     entries used by the legacy iPad webapp. Sanity-check that the fetched
     set contains an ``app.js`` and at least one ``entry-*.js``.
  4. Recursively scan the fetched JS / CSS bundles for further references
     to ``/static/...`` chunks, CSS, fonts and images. Fetch each new one
     and repeat until the dependency closure is stable (or only files that
     the upstream serves a 4xx/5xx for remain).
  5. Update ``ASSETS_PER_APP_VERSION.md`` — bump ``MOST RECENT VERSION:``
     and insert a new ``## App version <ARG>`` section with tables for
     ``assets`` / ``css`` / ``fonts`` / ``images`` / ``js``. Files already
     listed under an earlier version are marked ``Shared with <prev>``.
     If ran for the first time, ``ASSETS_PER_APP_VERSION.md`` is created
     from the template ``.ASSETS_PER_APP_VERSION.md``.
  6. Print a final table of every fetched URL with its success state and,
     when failed, the reason.

Usage:
    python3 scripts/fetch-webapp-assets.py <new-app-version>

The script uses ``dnspython`` (declared in ``requirements.txt``) to resolve
``ifp.ga.codethriving.com`` against ``8.8.8.8`` directly, then installs a
tiny ``getaddrinfo`` override so HTTPS requests connect to that IP while
SNI and the ``Host`` header keep the original hostname (so the TLS cert
and any vhost routing on the upstream still match).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse

try:
    import dns.exception
    import dns.resolver
except ImportError as _exc:
    raise SystemExit(
        "dnspython is required for this script. "
        "Install it with: pip install -r requirements.txt"
    ) from _exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UPSTREAM_HOST = "ifp.ga.codethriving.com"
UPSTREAM_BASE = f"https://{UPSTREAM_HOST}"
DNS_SERVER = "8.8.8.8"
USER_AGENT = "iframix-local/1.0"
REQUEST_TIMEOUT = 30

# Sentinel that marks a fresh ASSETS_PER_APP_VERSION.md before any
# version has been fetched. Step 1 is also skipped when the actual
# source files don't exist yet (first-time run on an empty webapp/).
NONE_YET_SENTINEL = "<NONE_YET>"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEBAPP_DIR = os.path.join(REPO_ROOT, "webapp")
ASSETS_MD = os.path.join(REPO_ROOT, "ASSETS_PER_APP_VERSION.md")
ASSETS_MD_TEMPLATE = os.path.join(REPO_ROOT, ".ASSETS_PER_APP_VERSION.md")

# Subdirectories under webapp/static/ that we recognise. Anything else
# discovered via the regex below is still fetched, but only these get a
# table in ASSETS_PER_APP_VERSION.md (matching the existing layout).
ASSET_SUBDIRS = ("assets", "css", "fonts", "images", "js")

# Heuristic that catches the typical Vite-built reference shapes:
#   "./chunk-abc123.js"               — sibling-relative (most chunks)
#   "../assets/abc.css"               — parent-then-dir (chunks → CSS)
#   "/static/fonts/inter-400.woff2"   — absolute (font preloads, etc.)
#   "./static/js/app.js?v=…"          — relative from /, with query suffix
# Discovered refs are resolved via urljoin against the URL of the file
# being scanned (so ./ and ../ resolve correctly) and then filtered to
# paths under /static/.
ASSET_PATH_RE = re.compile(
    r"""(?:"""
    r"""\.\.?/[A-Za-z0-9_@./\-]+"""             # ./foo, ../bar/baz
    r"""|/?static/(?:assets|css|fonts|images|js)/[A-Za-z0-9_@\-.]+?"""
    r""")"""
    r"""\.(?:js|css|woff2?|ttf|otf|png|jpe?g|svg|webp|gif|ico)\b""",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# DNS helpers — query 8.8.8.8 directly, then pin connections to that IP.
# ---------------------------------------------------------------------------

def dns_a_lookup(host: str, dns_server: str = DNS_SERVER,
                 timeout: float = 10.0) -> str | None:
    """Return one A-record IP for ``host`` from ``dns_server``.

    Uses ``dnspython`` configured to ignore ``/etc/resolv.conf`` and ask
    the given server directly. Returns ``None`` if no A record came back
    or the query failed for any other reason (caller logs and exits).
    """
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(host, "A")
    except dns.exception.DNSException:
        return None
    for record in answer:
        ip = record.address
        if ip:
            return ip
    return None


_PINNED_IPS: dict[str, str] = {}
_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, *args, **kwargs):
    ip = _PINNED_IPS.get(host)
    if ip is None:
        return _original_getaddrinfo(host, port, *args, **kwargs)
    # Return a single resolved address pointing at the pinned IP. urllib
    # passes the *original* hostname to ``ssl.wrap_socket`` for SNI and
    # cert verification, so the TLS handshake against the upstream still
    # works even though the socket is connected to ``ip``.
    port_int = port if isinstance(port, int) else (int(port) if port else 0)
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port_int))]


def install_pinned_resolver(host: str) -> str:
    """Resolve ``host`` via DNS 8.8.8.8 and pin all later sockets to it."""
    ip = dns_a_lookup(host)
    if ip is None:
        raise SystemExit(
            f"could not resolve {host} via DNS {DNS_SERVER} "
            "(network blocked or DNS server unreachable)")
    _PINNED_IPS[host] = ip
    socket.getaddrinfo = _patched_getaddrinfo
    return ip


# ---------------------------------------------------------------------------
# HTTP fetch with one automatic retry on transport errors.
# ---------------------------------------------------------------------------

def http_get(url: str, *, max_attempts: int = 2) -> tuple[int | None, bytes | None, str | None]:
    """Return ``(status, body, error)``.

    - On success: ``(200, body, None)`` (or whatever 2xx code we got).
    - On HTTP error (404, 500, ...): ``(code, None, "HTTP <code>")``.
    - On transport error: ``(None, None, <stringified-error>)`` after
      ``max_attempts`` tries.
    """
    last_err: str | None = None
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.status, resp.read(), None
        except urllib.error.HTTPError as exc:
            return exc.code, None, f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
    return None, None, last_err


# ---------------------------------------------------------------------------
# HTML parsing — collect every external resource referenced from index.html.
# ---------------------------------------------------------------------------

class _AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []
        self._script_depth = 0
        self.inline_script_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "script":
            src = d.get("src")
            if src:
                self.found.append(src)
            # vite-legacy-entry exposes its real URL on ``data-src`` and
            # runs ``System.import()`` against it at runtime; if we only
            # read ``src`` we miss the legacy entry chunk.
            data_src = d.get("data-src")
            if data_src:
                self.found.append(data_src)
            if not src:
                # Inline <script> body — record it so we can grep it for
                # asset paths injected at runtime (e.g. the bundle does
                # ``document.write('<script src="./static/js/app.js?v=' +
                # ts + '">')`` to load app.js, so the path never appears
                # in a parseable attribute).
                self._script_depth += 1
        elif tag == "link" and d.get("href"):
            # Pick up stylesheets, modulepreload, preload (fonts), icons.
            self.found.append(d["href"])
        elif tag == "img" and d.get("src"):
            self.found.append(d["src"])

    def handle_endtag(self, tag):
        if tag == "script" and self._script_depth > 0:
            self._script_depth -= 1

    def handle_data(self, data):
        if self._script_depth > 0:
            self.inline_script_text.append(data)


def parse_html_assets(html_bytes: bytes, base_url: str) -> list[str]:
    """Return every absolute asset path referenced from ``html_bytes``.

    Resolves direct src/href/data-src attribute values against
    ``base_url`` via ``normalise_path`` and additionally scans the body
    of every inline ``<script>`` so that runtime-injected refs (e.g.
    ``document.write('<script src="./static/js/app.js?v="...)``) get
    picked up too.
    """
    parser = _AssetCollector()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    seen: set[str] = set()
    out: list[str] = []
    for raw in parser.found:
        path = normalise_path(raw, base_url)
        if path is None or path in seen:
            continue
        seen.add(path)
        out.append(path)
    inline_text = "".join(parser.inline_script_text).encode("utf-8")
    for path in discover_referenced_paths(inline_text, base_url):
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def normalise_path(url_or_path: str, base_url: str) -> str | None:
    """Resolve a script/link/href value to an absolute ``/static/...`` path.

    Returns ``None`` if the value points outside this server (different
    host) or isn't a static asset (data:, javascript:, mailto:, ...).
    """
    if not url_or_path:
        return None
    lowered = url_or_path.lower()
    if lowered.startswith(("data:", "javascript:", "mailto:", "blob:", "#")):
        return None
    abs_url = urljoin(base_url, url_or_path)
    parsed = urlparse(abs_url)
    if parsed.netloc and parsed.netloc != UPSTREAM_HOST:
        return None
    return parsed.path  # always starts with '/'


def url_to_local_path(url_path: str) -> str:
    """Map ``/static/foo/bar.js`` to ``webapp/static/foo/bar.js``."""
    relative = url_path.lstrip("/")
    return os.path.join(WEBAPP_DIR, *relative.split("/"))


def save_bytes(local_path: str, body: bytes) -> None:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    tmp = local_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, local_path)


# ---------------------------------------------------------------------------
# Chunk discovery — scan a JS/CSS body for further /static/... references.
# ---------------------------------------------------------------------------

def discover_referenced_paths(body: bytes, source_url: str) -> set[str]:
    """Scan ``body`` for asset refs and resolve them against ``source_url``.

    Two conventions are at play in Vite-built Vue bundles, and they
    differ in how a leading ``./`` resolves:

    - Chunk references (``./chunk-X.js``, ``../assets/Y.css``) are
      relative to the URL of the chunk that contains them. urljoin
      against ``source_url`` handles those.
    - Image references baked in from Vue templates ("./static/images/
      no_mqtt.png") are written from the project root in source and
      resolved by Vue's runtime as document-root relative — the
      leading ``./`` is stripped, not interpreted as the chunk's own
      directory. urljoin would turn them into ``/static/js/static/
      images/...`` and 404. Detect that shape by sniffing for ``./
      static/`` (or bare ``static/``) and normalise directly.

    Only resolved paths under ``/static/`` are returned; anything else
    is treated as a false-positive substring match.
    """
    if not body:
        return set()
    text = body.decode("utf-8", errors="replace")
    paths: set[str] = set()
    for match in ASSET_PATH_RE.findall(text):
        if match.startswith("./static/"):
            path = match[1:]
        elif match.startswith("static/"):
            path = "/" + match
        else:
            abs_url = urljoin(source_url, match)
            parsed = urlparse(abs_url)
            if parsed.netloc and parsed.netloc != UPSTREAM_HOST:
                continue
            path = parsed.path
        if path.startswith("/static/"):
            paths.add(path)
    return paths


# ---------------------------------------------------------------------------
# ASSETS_PER_APP_VERSION.md helpers
# ---------------------------------------------------------------------------

PREV_VERSION_RE = re.compile(r"^MOST RECENT VERSION:\s*(\S+)\s*$", re.MULTILINE)
VERSION_HEADER_RE = re.compile(r"^## App version (\S+)\s*$", re.MULTILINE)


def find_previous_version() -> str:
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    m = PREV_VERSION_RE.search(content)
    if not m:
        raise SystemExit(
            "could not find 'MOST RECENT VERSION:' line in "
            "ASSETS_PER_APP_VERSION.md")
    return m.group(1)


def collect_files_per_existing_version() -> dict[str, str]:
    """Map filename -> earliest app version section that lists it.

    Used to populate ``Shared with X.Y.Z`` remarks in the new table.
    """
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    sections: list[tuple[str, int]] = [
        (m.group(1), m.start()) for m in VERSION_HEADER_RE.finditer(content)]
    # Each section ends where the next one starts (or at EOF).
    bounds: list[tuple[str, int, int]] = []
    for i, (ver, start) in enumerate(sections):
        end = sections[i + 1][1] if i + 1 < len(sections) else len(content)
        bounds.append((ver, start, end))
    table_row_re = re.compile(r"\|\s*\[([^\]]+)\]\(")
    out: dict[str, str] = {}
    for ver, start, end in bounds:
        for name in table_row_re.findall(content[start:end]):
            # Keep the *first* version that owned the file — that's the
            # right value for "Shared with ..." on a newer build.
            out.setdefault(name, ver)
    return out


def render_table(rows: list[tuple[str, str, str]]) -> str:
    """Render a ``| name | link | remark |`` markdown table.

    ``rows`` is ``(display_name, link_target, remark)``. Widths are
    auto-padded so it lines up visually with the existing tables.
    """
    if not rows:
        return ""
    name_col = max(len(f"[{n}]({l})") for n, l, _ in rows)
    name_col = max(name_col, len("Asset file"))
    remark_col = max((len(r) for _, _, r in rows), default=0)
    remark_col = max(remark_col, len("Remarks"))
    out: list[str] = []
    out.append(f"| {'Asset file':<{name_col}} | {'Remarks':<{remark_col}} |")
    out.append(f"|{'-' * (name_col + 2)}|{'-' * (remark_col + 2)}|")
    for n, l, r in rows:
        link = f"[{n}]({l})"
        out.append(f"| {link:<{name_col}} | {r:<{remark_col}} |")
    return "\n".join(out)


def build_new_version_section(new_version: str,
                              fetched_paths: list[str],
                              prior_owner: dict[str, str]) -> str:
    """Produce the markdown for the new ``## App version <X>`` section."""
    by_subdir: dict[str, list[str]] = {sd: [] for sd in ASSET_SUBDIRS}
    for path in fetched_paths:
        parts = path.lstrip("/").split("/")
        if len(parts) >= 3 and parts[0] == "static" and parts[1] in ASSET_SUBDIRS:
            by_subdir[parts[1]].append(path)

    lines: list[str] = []
    lines.append(f"## App version {new_version}")
    lines.append("")
    lines.append(
        "Files that are content-hashed per build. The `-legacy` suffix on "
        "JS chunks marks the")
    lines.append(
        "ES5-compiled bundle served to older browsers (notably iPad iOS 9) "
        "via the module /")
    lines.append("nomodule split that Vite's legacy plugin emits.")
    lines.append("")

    for subdir in ASSET_SUBDIRS:
        items = by_subdir.get(subdir) or []
        if not items:
            continue
        rows: list[tuple[str, str, str]] = []
        for path in sorted(set(items)):
            name = path.rsplit("/", 1)[1]
            link = "webapp" + path
            remarks: list[str] = []
            if name == "app.js":
                remarks.append("main bundle")
            elif name.startswith("entry-") and name.endswith("-legacy.js"):
                remarks.append("ES5 entry (legacy)")
            elif name.startswith("entry-"):
                remarks.append("modern entry")
            elif name.startswith("chunk-") and name.endswith("-legacy.js"):
                remarks.append("ES5 build (legacy)")
            prev = prior_owner.get(name)
            if prev and prev != new_version:
                remarks.append(f"Shared with {prev}")
            rows.append((name, link, ". ".join(remarks)))
        lines.append(f"### `{subdir}`")
        lines.append("")
        lines.append(render_table(rows))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def update_assets_md(new_version: str, fetched_paths: list[str]) -> None:
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    prior_owner = collect_files_per_existing_version()
    # 1) Bump MOST RECENT VERSION line.
    new_content, count = PREV_VERSION_RE.subn(
        f"MOST RECENT VERSION: {new_version}", content, count=1)
    if count == 0:
        raise SystemExit("could not find 'MOST RECENT VERSION:' line to update")
    # 2) Insert new section just before the first existing version header.
    m = VERSION_HEADER_RE.search(new_content)
    if not m:
        # No prior version sections — append at end.
        insert_at = len(new_content)
    else:
        insert_at = m.start()
    section_md = build_new_version_section(
        new_version, fetched_paths, prior_owner)
    # Ensure a blank line separates the new section from neighbours.
    sep_before = "" if new_content[:insert_at].endswith("\n\n") else "\n"
    sep_after = "\n" if not section_md.endswith("\n\n") else ""
    new_content = (
        new_content[:insert_at]
        + sep_before + section_md + sep_after
        + new_content[insert_at:]
    )
    with open(ASSETS_MD, "w", encoding="utf-8") as f:
        f.write(new_content)


# ---------------------------------------------------------------------------
# Step orchestration
# ---------------------------------------------------------------------------

def step1_rename_previous(previous_version: str) -> None:
    print(f"[1/6] Renaming current files to suffix '-{previous_version}'")
    if previous_version == NONE_YET_SENTINEL:
        print("  MOST RECENT VERSION is <NONE_YET> — nothing to rename, "
              "skipping (first-time run)")
        return
    targets = [
        ("index.html",
         os.path.join(WEBAPP_DIR, "index.html"),
         os.path.join(WEBAPP_DIR, f"index-{previous_version}.html")),
        ("static/js/app.js",
         os.path.join(WEBAPP_DIR, "static", "js", "app.js"),
         os.path.join(WEBAPP_DIR, "static", "js",
                      f"app-{previous_version}.js")),
    ]
    present = [(label, src, dst) for label, src, dst in targets
               if os.path.isfile(src)]
    if not present:
        # Empty webapp/ — there's nothing of the previous version to
        # preserve. Treat as a clean first-time run and just download.
        print("  no existing files to rename — treating as first-time run")
        return
    # Refuse to overwrite an existing renamed target up-front, before
    # any os.rename touches the tree.
    for label, _src, dst in present:
        if os.path.exists(dst):
            raise SystemExit(
                f"refusing to overwrite existing {dst}; "
                "delete or move it first")
    for label, src, dst in targets:
        if not os.path.isfile(src):
            print(f"  {label}: missing, skipping")
            continue
        os.rename(src, dst)
        if not os.path.isfile(dst) or os.path.exists(src):
            raise SystemExit(f"{label} rename failed sanity check")
        print(f"  {label} -> {os.path.relpath(dst, REPO_ROOT)}")


def step2_fetch_index() -> bytes:
    print(f"[2/6] Fetching {UPSTREAM_BASE}/  (DNS via {DNS_SERVER})")
    status, body, err = http_get(UPSTREAM_BASE + "/", max_attempts=2)
    if status != 200 or not body:
        raise SystemExit(
            f"failed to fetch index.html (status={status}, error={err})")
    lowered = body[:512].lower()
    if b"<html" not in lowered and b"<!doctype html" not in lowered:
        raise SystemExit("upstream returned a non-HTML body for /")
    save_bytes(os.path.join(WEBAPP_DIR, "index.html"), body)
    print(f"  saved {len(body)} bytes to webapp/index.html")
    return body


def step3_fetch_html_assets(html_body: bytes,
                            results: list[tuple[str, bool, str]]
                            ) -> set[str]:
    """Fetch each external resource referenced from index.html.

    Returns the set of absolute ``/static/...`` paths that were saved
    locally, so step 4 can scan them recursively.
    """
    print("[3/6] Fetching assets referenced from index.html")
    paths = parse_html_assets(html_body, UPSTREAM_BASE + "/")
    saved: set[str] = set()
    for path in paths:
        ok, reason = fetch_and_save(path)
        results.append((path, ok, reason))
        if ok:
            saved.add(path)
    # Validate that the index.html closure contains an app.js and
    # at least one entry-*.js.
    names = {p.rsplit("/", 1)[1] for p in saved}
    if "app.js" not in names:
        raise SystemExit(
            "step 3 sanity check failed: no 'app.js' among fetched assets")
    if not any(n.startswith("entry-") and n.endswith(".js") for n in names):
        raise SystemExit(
            "step 3 sanity check failed: no 'entry-*.js' among fetched assets")
    print(f"  fetched {sum(1 for _, ok, _ in results if ok)}/{len(results)} "
          "direct references")
    return saved


def step4_fetch_chunks(seed_paths: set[str],
                       results: list[tuple[str, bool, str]]) -> set[str]:
    """Recursively fetch ``/static/...`` references found inside JS / CSS."""
    print("[4/6] Recursively fetching chunk references")
    visited: set[str] = set(seed_paths)
    queue: list[str] = sorted(seed_paths)
    # Tracks paths we've already tried that 404'd, so we don't refetch them.
    failed: set[str] = set()
    iteration = 0
    while queue:
        iteration += 1
        next_queue: list[str] = []
        # Only scan JS and CSS bodies — fonts/images don't reference others.
        for path in queue:
            local = url_to_local_path(path)
            if not (path.endswith(".js") or path.endswith(".css")):
                continue
            if not os.path.isfile(local):
                continue
            with open(local, "rb") as f:
                body = f.read()
            source_url = UPSTREAM_BASE + path
            for referenced in discover_referenced_paths(body, source_url):
                if referenced in visited or referenced in failed:
                    continue
                visited.add(referenced)
                ok, reason = fetch_and_save(referenced)
                results.append((referenced, ok, reason))
                if ok:
                    next_queue.append(referenced)
                else:
                    failed.add(referenced)
        queue = next_queue
        if not next_queue:
            break
    print(f"  closure stable after {iteration} iteration(s); "
          f"{len(visited - failed)} files fetched, {len(failed)} failed")
    return visited - failed


def fetch_and_save(url_path: str) -> tuple[bool, str]:
    """Fetch one ``/static/...`` path and write it to the webapp tree."""
    url = UPSTREAM_BASE + url_path
    status, body, err = http_get(url)
    if status == 200 and body is not None:
        save_bytes(url_to_local_path(url_path), body)
        return True, ""
    if err:
        return False, err
    return False, f"HTTP {status}"


def step5_update_markdown(new_version: str,
                          fetched_paths: Iterable[str]) -> None:
    print(f"[5/6] Updating {os.path.relpath(ASSETS_MD, REPO_ROOT)}")
    update_assets_md(new_version, sorted(set(fetched_paths)))
    print("  done")


def step6_print_report(results: list[tuple[str, bool, str]]) -> None:
    print("[6/6] Fetch report")
    rows: list[tuple[str, str, str]] = []
    for path, ok, reason in results:
        name = path.rsplit("/", 1)[1] if "/" in path else path
        rows.append((name, "YES" if ok else "NO", "" if ok else reason))
    if not rows:
        print("  (no files were attempted)")
        return
    name_col = max(len("file name"), *(len(r[0]) for r in rows))
    succ_col = max(len("success"), 3)
    reason_col = max(len("failure reason"), *(len(r[2]) for r in rows))
    sep = (f"|{'-' * (name_col + 2)}|{'-' * (succ_col + 2)}"
           f"|{'-' * (reason_col + 2)}|")
    print(f"| {'file name':<{name_col}} | {'success':<{succ_col}} "
          f"| {'failure reason':<{reason_col}} |")
    print(sep)
    for name, ok, reason in rows:
        print(f"| {name:<{name_col}} | {ok:<{succ_col}} "
              f"| {reason:<{reason_col}} |")
    failed = [r for r in results if not r[1]]
    print()
    print(f"Summary: {len(results) - len(failed)} ok, {len(failed)} failed, "
          f"{len(results)} total.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch static iFramix webapp assets for a new app version")
    parser.add_argument(
        "version",
        help="Version number of the new app build, e.g. '2.3.0'")
    parser.add_argument(
        "--skip-rename", action="store_true",
        help=("Skip step 1 (useful if the rename was already done by hand "
              "and the run aborted later)."))
    parser.add_argument(
        "--skip-md", action="store_true",
        help="Skip step 5 (don't touch ASSETS_PER_APP_VERSION.md).")
    args = parser.parse_args(argv)

    new_version = args.version.strip()
    if not new_version:
        parser.error("version argument cannot be empty")

    if not os.path.isdir(WEBAPP_DIR):
        raise SystemExit(f"webapp directory not found: {WEBAPP_DIR}")
    if not os.path.isfile(ASSETS_MD):
        if not os.path.isfile(ASSETS_MD_TEMPLATE):
          raise SystemExit(f"missing {ASSETS_MD_TEMPLATE}")
        print(f"Creating {ASSETS_MD} from template file {ASSETS_MD_TEMPLATE}")
        shutil.copyfile(ASSETS_MD_TEMPLATE, ASSETS_MD)

    previous_version = find_previous_version()
    if previous_version == new_version:
        raise SystemExit(
            f"MOST RECENT VERSION is already {new_version} — nothing to do. "
            "Edit ASSETS_PER_APP_VERSION.md if you really meant to refetch.")
    print(f"Previous version: {previous_version}")
    print(f"New version:      {new_version}")

    ip = install_pinned_resolver(UPSTREAM_HOST)
    print(f"Resolved {UPSTREAM_HOST} via {DNS_SERVER} -> {ip}")
    print()

    if not args.skip_rename:
        step1_rename_previous(previous_version)
    else:
        print("[1/6] (skipped --skip-rename)")

    html_body = step2_fetch_index()
    results: list[tuple[str, bool, str]] = []
    seed = step3_fetch_html_assets(html_body, results)
    fetched = step4_fetch_chunks(seed, results)

    if not args.skip_md:
        step5_update_markdown(new_version, fetched)
    else:
        print("[5/6] (skipped --skip-md)")

    step6_print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
