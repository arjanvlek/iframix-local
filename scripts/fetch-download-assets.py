#!/usr/bin/env python3
"""Fetch the static iFramix Pro **download** webapp assets.

The download page (``/download`` on the API server) is a small Vite-built
Vue SPA that the cloud server uses to advertise the app store /
direct-download links. It is checked into ``webapp/download/`` so the
local API server can serve it. Unlike the controller webapps it is *not*
versioned — there is no ``MOST RECENT VERSION:`` to bump — so this script
simply overwrites whatever is currently in ``webapp/download/``.

What gets fetched:

  1. The main page (``GET /download/``) → ``webapp/download/index.html``.
  2. The privacy-policy page (``GET /download/xieyi/index.html``) →
     ``webapp/download/xieyi/index.html``. CLAUDE.md documents the page
     as part of the download webapp; it is fully self-contained today
     (inline CSS) but the script still scans it in case that changes.
  3. Every script / stylesheet / font / image referenced from those two
     pages.
  4. Recursively, every ``./<hash>.<ext>`` chunk reference inside the
     fetched JS / CSS bundles. References are resolved against the URL
     of the file being scanned (Vite emits relative paths from inside
     ``assets/``), and only resolved paths under ``/download/`` are
     accepted — anything else is treated as a false positive and skipped.

Reference discovery is regex-based and keys on quoted asset filenames
inside JS / CSS payloads. False positives surface as 404s in the final
report; they do not affect correctness.

Usage:
    python3 scripts/fetch-download-assets.py
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEBAPP_DIR = os.path.join(REPO_ROOT, "webapp")
DOWNLOAD_DIR = os.path.join(WEBAPP_DIR, "download")

# HTML entry points to fetch. URLs ending in ``/`` land as the
# directory's ``index.html`` (handled by ``url_to_local_path`` below).
ENTRY_PAGES: list[str] = [
    "/download/",
    "/download/xieyi/index.html",
]

# Regex for any quoted asset filename inside a JS / CSS payload. Vite
# emits content-hashed names like ``index-CzhP9uAk.js`` or
# ``top_bg_mobile_ratio-CgzZfA31.png``. We deliberately keep this loose
# and rely on the urljoin + ``/download/`` prefix check to filter false
# positives.
ASSET_REF_RE = re.compile(
    r"""["'`]"""
    r"""((?:\./|\.\./|/)?[A-Za-z0-9_@./\-]+"""
    r"""\.(?:js|css|woff2?|ttf|otf|png|jpe?g|svg|webp|gif|ico))"""
    r"""["'`]""",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# DNS — resolve via 8.8.8.8 and pin urllib's getaddrinfo to that IP.
# ---------------------------------------------------------------------------

def dns_a_lookup(host: str, dns_server: str = DNS_SERVER,
                 timeout: float = 10.0) -> str | None:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(host, "A")
    except dns.exception.DNSException:
        return None
    for record in answer:
        if record.address:
            return record.address
    return None


_PINNED_IPS: dict[str, str] = {}
_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, *args, **kwargs):
    ip = _PINNED_IPS.get(host)
    if ip is None:
        return _original_getaddrinfo(host, port, *args, **kwargs)
    port_int = port if isinstance(port, int) else (int(port) if port else 0)
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port_int))]


def install_pinned_resolver(host: str) -> str:
    ip = dns_a_lookup(host)
    if ip is None:
        raise SystemExit(
            f"could not resolve {host} via DNS {DNS_SERVER}")
    _PINNED_IPS[host] = ip
    socket.getaddrinfo = _patched_getaddrinfo
    return ip


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_get(url: str, *, max_attempts: int = 2) -> tuple[int | None, bytes | None, str | None]:
    last_err: str | None = None
    for _ in range(max_attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.status, resp.read(), None
        except urllib.error.HTTPError as exc:
            return exc.code, None, f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
    return None, None, last_err


# ---------------------------------------------------------------------------
# HTML parsing — same shape as the other fetch scripts; pulls every
# script/link/img URL out of the parsed tree (incl. nomodule + data-src).
# ---------------------------------------------------------------------------

class _AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "script":
            for key in ("src", "data-src"):
                val = d.get(key)
                if val:
                    self.found.append(val)
        elif tag == "link":
            href = d.get("href")
            if href:
                self.found.append(href)
        elif tag == "img":
            src = d.get("src")
            if src:
                self.found.append(src)


def parse_html_assets(html_bytes: bytes) -> list[str]:
    parser = _AssetCollector()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    seen: set[str] = set()
    out: list[str] = []
    for url in parser.found:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_to_download_path(ref: str, source_url: str) -> str | None:
    """Resolve ``ref`` against ``source_url`` to an absolute ``/download/...``
    path. Returns ``None`` for cross-origin, non-asset, or out-of-tree refs.
    """
    if not ref:
        return None
    low = ref.lower()
    if low.startswith(("data:", "javascript:", "mailto:", "blob:", "#")):
        return None
    abs_url = urljoin(source_url, ref)
    parsed = urlparse(abs_url)
    if parsed.netloc and parsed.netloc != UPSTREAM_HOST:
        return None
    path = parsed.path
    if not path.startswith("/download/"):
        return None
    return path


def url_to_local_path(url_path: str) -> str:
    """``/download/foo.js`` → ``webapp/download/foo.js``.

    URLs that end in ``/`` (the entry-page case, e.g. ``/download/``) are
    treated as a request for that directory's ``index.html``, so the body
    lands at ``webapp/download/index.html`` instead of clobbering the
    directory itself.

    Note ``url_path`` always starts with ``/download/`` (callers gate on
    that) so we never write outside ``webapp/``.
    """
    relative = url_path.lstrip("/")
    if relative == "" or relative.endswith("/"):
        relative += "index.html"
    return os.path.join(WEBAPP_DIR, *relative.split("/"))


def save_bytes(local_path: str, body: bytes) -> None:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    tmp = local_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, local_path)


def discover_referenced_paths(body: bytes, source_url: str) -> set[str]:
    """Scan a JS / CSS body for further ``/download/...`` references."""
    if not body:
        return set()
    text = body.decode("utf-8", errors="replace")
    paths: set[str] = set()
    for raw in ASSET_REF_RE.findall(text):
        resolved = resolve_to_download_path(raw, source_url)
        if resolved is not None:
            paths.add(resolved)
    return paths


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def fetch_and_save(url_path: str) -> tuple[bool, str]:
    """Fetch a ``/download/...`` URL path and write it under webapp/."""
    url = UPSTREAM_BASE + url_path
    status, body, err = http_get(url)
    if status == 200 and body is not None:
        save_bytes(url_to_local_path(url_path), body)
        return True, ""
    if err:
        return False, err
    return False, f"HTTP {status}"


def fetch_entry_page(url_path: str,
                     results: list[tuple[str, bool, str]]) -> bytes | None:
    """Fetch one HTML entry page. Returns the body on success."""
    url = UPSTREAM_BASE + url_path
    print(f"  GET {url}")
    status, body, err = http_get(url, max_attempts=2)
    if status != 200 or not body:
        msg = err or f"HTTP {status}"
        results.append((url_path, False, msg))
        print(f"    !! failed: {msg}")
        return None
    lowered = body[:512].lower()
    if b"<html" not in lowered and b"<!doctype html" not in lowered:
        results.append((url_path, False, "non-HTML body"))
        print("    !! upstream returned a non-HTML body")
        return None
    save_bytes(url_to_local_path(url_path), body)
    results.append((url_path, True, ""))
    print(f"    saved {len(body)} bytes")
    return body


def fetch_direct_refs(html_body: bytes,
                      source_url: str,
                      results: list[tuple[str, bool, str]]) -> set[str]:
    """Fetch each external resource referenced from one HTML page."""
    saved: set[str] = set()
    for raw in parse_html_assets(html_body):
        path = resolve_to_download_path(raw, source_url)
        if path is None:
            continue
        if path in saved:
            continue
        ok, reason = fetch_and_save(path)
        results.append((path, ok, reason))
        if ok:
            saved.add(path)
    return saved


def recurse_chunks(seed: set[str],
                   results: list[tuple[str, bool, str]]) -> set[str]:
    """Recursively fetch ``/download/...`` refs inside JS / CSS bundles."""
    visited: set[str] = set(seed)
    failed: set[str] = set()
    queue: list[str] = sorted(seed)
    iteration = 0
    while queue:
        iteration += 1
        next_queue: list[str] = []
        for path in queue:
            if not (path.endswith(".js") or path.endswith(".css")):
                continue
            local = url_to_local_path(path)
            if not os.path.isfile(local):
                continue
            with open(local, "rb") as f:
                body = f.read()
            source_url = UPSTREAM_BASE + path
            for ref in discover_referenced_paths(body, source_url):
                if ref in visited or ref in failed:
                    continue
                visited.add(ref)
                ok, reason = fetch_and_save(ref)
                results.append((ref, ok, reason))
                if ok:
                    next_queue.append(ref)
                else:
                    failed.add(ref)
        queue = next_queue
        if not next_queue:
            break
    return visited - failed, iteration


def print_report(results: list[tuple[str, bool, str]]) -> None:
    print("Fetch report")
    if not results:
        print("  (no files were attempted)")
        return
    rows = [(p.rsplit("/", 1)[1] or p.rstrip("/").rsplit("/", 1)[-1] or p,
             "YES" if ok else "NO",
             "" if ok else reason)
            for p, ok, reason in results]
    name_col = max(len("file name"), *(len(r[0]) for r in rows))
    succ_col = max(len("success"), 3)
    reason_col = max(len("failure reason"), *(len(r[2]) for r in rows))
    print(f"| {'file name':<{name_col}} | {'success':<{succ_col}} "
          f"| {'failure reason':<{reason_col}} |")
    print(f"|{'-' * (name_col + 2)}|{'-' * (succ_col + 2)}"
          f"|{'-' * (reason_col + 2)}|")
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
    argparse.ArgumentParser(
        description="Fetch the iFramix download webapp assets"
    ).parse_args(argv)

    if not os.path.isdir(WEBAPP_DIR):
        raise SystemExit(f"webapp directory not found: {WEBAPP_DIR}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ip = install_pinned_resolver(UPSTREAM_HOST)
    print(f"Resolved {UPSTREAM_HOST} via {DNS_SERVER} -> {ip}")
    print()

    results: list[tuple[str, bool, str]] = []
    all_seed: set[str] = set()
    for url_path in ENTRY_PAGES:
        print(f"Fetching entry page {url_path}")
        body = fetch_entry_page(url_path, results)
        if body is None:
            # The xieyi page is optional; the main /download/ page is
            # required for there to be anything to do. Either way, keep
            # going with whatever we already have.
            continue
        seed = fetch_direct_refs(body, UPSTREAM_BASE + url_path, results)
        all_seed |= seed
        print(f"  direct refs fetched: {len(seed)}")

    if not all_seed:
        raise SystemExit(
            "no asset references discovered from any entry page — aborting")

    print()
    print("Recursing chunk references")
    fetched, iterations = recurse_chunks(all_seed, results)
    print(f"  closure stable after {iterations} iteration(s); "
          f"{len(fetched)} files fetched in total")
    print()
    print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
