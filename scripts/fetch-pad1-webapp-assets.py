#!/usr/bin/env python3
"""Fetch static iFramix Pro **iPad 1** webapp assets for a new app version.

Mirror of ``scripts/fetch-webapp-assets.py`` but for the legacy iPad 1
webapp that lives under ``webapp/pad1/`` (served at ``/pad1`` by the API
server). Implements the 6-step procedure from
``.claude/skills/fetch-pad1-webapp-assets/SKILL.md``:

  1. Rename the current ``webapp/pad1/index.html`` to
     ``index-<PREV>.html``. Skipped when the markdown sentinel is
     ``<NONE_YET>`` or when ``webapp/pad1/index.html`` does not exist,
     so a fresh checkout with no ``webapp/pad1/`` contents works as a
     first-time run.
  2. Fetch ``https://ifp.ga.codethriving.com/pad1`` via DNS 8.8.8.8 and
     save as ``webapp/pad1/index.html``.
  3. Fetch every external script / stylesheet / font / image referenced
     from index.html (including ``<script nomodule>`` entries). Sanity-
     check that an ``entry*.js`` made it in.
  4. Recursively scan fetched JS / CSS for further references under
     ``ipad-static/`` and fetch them until the closure is stable.
  5. Update ``ASSETS_PER_APP_VERSION_PAD1.md`` — bump ``MOST RECENT
     VERSION:`` and insert a new ``## App version <ARG>`` section with
     tables for ``assets (CSS)`` / ``assets (images)`` / ``js``,
     matching the existing layout.
     If ran for the first time, ``ASSETS_PER_APP_VERSION_PAD1.md``
     is created from the template ``.ASSETS_PER_APP_VERSION_PAD1.md``.
  6. Print a per-file success / failure report.

Usage:
    python3 scripts/fetch-pad1-webapp-assets.py <new-app-version>
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
INDEX_URL = f"{UPSTREAM_BASE}/pad1"
DNS_SERVER = "8.8.8.8"
USER_AGENT = "iframix-local/1.0"
REQUEST_TIMEOUT = 30

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEBAPP_DIR = os.path.join(REPO_ROOT, "webapp")
PAD1_DIR = os.path.join(WEBAPP_DIR, "pad1")
ASSETS_MD = os.path.join(REPO_ROOT, "ASSETS_PER_APP_VERSION_PAD1.md")
ASSETS_MD_TEMPLATE = os.path.join(REPO_ROOT, ".ASSETS_PER_APP_VERSION_PAD1.md")

# Sentinel that marks a fresh markdown file before any version has been
# fetched. Step 1 (rename existing index.html) is skipped in that case.
NONE_YET_SENTINEL = "<NONE_YET>"

# Subdirectories under webapp/pad1/ipad-static/ that we recognise.
ASSET_SUBDIRS = ("assets", "js")

# Heuristic that catches the typical Vite reference shapes:
#   "./chunk1e367b6f.js"              — sibling-relative (most chunks)
#   "../assets/b984b25f.css"          — parent-then-dir (chunks → CSS)
#   "/pad1/ipad-static/js/entry…js"   — absolute (from index.html)
#   "/ipad-static/…"                  — absolute, /pad1 prefix elided
# Discovered refs are resolved via urljoin against the URL of the file
# being scanned and then filtered to paths under /pad1/ipad-static/
# (with the /pad1 prefix re-attached when the chunk omits it).
ASSET_PATH_RE = re.compile(
    r"""(?:"""
    r"""\.\.?/[A-Za-z0-9_@./\-]+"""             # ./foo, ../bar/baz
    r"""|/?(?:pad1/)?ipad-static/(?:assets|js)/[A-Za-z0-9_@\-.]+?"""
    r""")"""
    r"""\.(?:js|css|woff2?|ttf|otf|png|jpe?g|svg|webp|gif|ico)\b""",
    re.IGNORECASE,
)

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".ico")


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
# HTML parsing
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
            # vite-legacy-entry sticks the real URL on data-src and runs
            # System.import() against it at runtime.
            data_src = d.get("data-src")
            if data_src:
                self.found.append(data_src)
            if not src:
                # Inline <script> — record the body so we can grep it
                # for asset paths injected at runtime.
                self._script_depth += 1
        elif tag == "link" and d.get("href"):
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
    """Return every absolute ``/pad1/...`` asset path referenced from the
    page — direct attribute refs and asset paths inside inline scripts.
    """
    parser = _AssetCollector()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    seen: set[str] = set()
    out: list[str] = []
    for raw in parser.found:
        path = normalise_to_pad1_path(raw, base_url)
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

def normalise_to_pad1_path(url_or_path: str, base_url: str) -> str | None:
    """Resolve a script/link value to an absolute ``/pad1/...`` path.

    Returns ``None`` for cross-origin URLs or non-asset schemes.
    """
    if not url_or_path:
        return None
    low = url_or_path.lower()
    if low.startswith(("data:", "javascript:", "mailto:", "blob:", "#")):
        return None
    abs_url = urljoin(base_url, url_or_path)
    parsed = urlparse(abs_url)
    if parsed.netloc and parsed.netloc != UPSTREAM_HOST:
        return None
    path = parsed.path
    if not path.startswith("/pad1/"):
        # Some chunk references omit the /pad1 prefix; reattach it.
        if path.startswith("/ipad-static/"):
            path = "/pad1" + path
        else:
            return None
    return path


def url_to_local_path(url_path: str) -> str:
    """``/pad1/ipad-static/foo.js`` → ``webapp/pad1/ipad-static/foo.js``."""
    relative = url_path.lstrip("/")
    return os.path.join(WEBAPP_DIR, *relative.split("/"))


def save_bytes(local_path: str, body: bytes) -> None:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    tmp = local_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, local_path)


def discover_referenced_paths(body: bytes, source_url: str) -> set[str]:
    """Scan ``body`` for asset refs and resolve them against ``source_url``.

    Two conventions co-exist in Vite-built Vue bundles (same as the
    main webapp — see scripts/fetch-webapp-assets.py for the long
    explanation):

    - Chunk refs like ``./chunkXXX.js`` / ``../assets/X.css`` resolve
      against the URL of the chunk that contains them (urljoin).
    - Image refs baked in from Vue templates ("./pad1/ipad-static/
      images/foo.png" or "./ipad-static/...") are document-root
      relative, so the leading ``./`` is stripped instead of being
      interpreted as the chunk's own directory.

    Only paths under ``/pad1/ipad-static/`` are returned — chunks that
    omit the ``/pad1`` prefix get it re-attached.
    """
    if not body:
        return set()
    text = body.decode("utf-8", errors="replace")
    paths: set[str] = set()
    for match in ASSET_PATH_RE.findall(text):
        if match.startswith("./pad1/ipad-static/"):
            path = match[1:]
        elif match.startswith("./ipad-static/"):
            path = "/pad1" + match[1:]
        elif match.startswith("pad1/ipad-static/"):
            path = "/" + match
        elif match.startswith("ipad-static/"):
            path = "/pad1/" + match
        else:
            abs_url = urljoin(source_url, match)
            parsed = urlparse(abs_url)
            if parsed.netloc and parsed.netloc != UPSTREAM_HOST:
                continue
            path = parsed.path
            if path.startswith("/ipad-static/"):
                path = "/pad1" + path
        if path.startswith("/pad1/ipad-static/"):
            paths.add(path)
    return paths


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

PREV_VERSION_RE = re.compile(r"^MOST RECENT VERSION:\s*(\S+)\s*$", re.MULTILINE)
VERSION_HEADER_RE = re.compile(r"^## App version (\S+)\s*$", re.MULTILINE)


def find_previous_version() -> str:
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    m = PREV_VERSION_RE.search(content)
    if not m:
        raise SystemExit(
            f"could not find 'MOST RECENT VERSION:' line in "
            f"{os.path.basename(ASSETS_MD)}")
    return m.group(1)


def collect_files_per_existing_version() -> dict[str, str]:
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    sections = [(m.group(1), m.start())
                for m in VERSION_HEADER_RE.finditer(content)]
    bounds = []
    for i, (ver, start) in enumerate(sections):
        end = sections[i + 1][1] if i + 1 < len(sections) else len(content)
        bounds.append((ver, start, end))
    table_row_re = re.compile(r"\|\s*\[([^\]]+)\]\(")
    out: dict[str, str] = {}
    for ver, start, end in bounds:
        for name in table_row_re.findall(content[start:end]):
            out.setdefault(name, ver)
    return out


def render_table(rows: list[tuple[str, str, str]]) -> str:
    if not rows:
        return ""
    name_col = max(len(f"[{n}]({l})") for n, l, _ in rows)
    name_col = max(name_col, len("Asset file"))
    remark_col = max((len(r) for _, _, r in rows), default=0)
    remark_col = max(remark_col, len("Remarks"))
    lines: list[str] = []
    lines.append(f"| {'Asset file':<{name_col}} | {'Remarks':<{remark_col}} |")
    lines.append(f"|{'-' * (name_col + 2)}|{'-' * (remark_col + 2)}|")
    for n, l, r in rows:
        link = f"[{n}]({l})"
        lines.append(f"| {link:<{name_col}} | {r:<{remark_col}} |")
    return "\n".join(lines)


def _js_remark(name: str) -> str:
    if name.startswith("entry") and name.endswith("-legacy.js"):
        return "Legacy (ES5) entry"
    if name.startswith("entry") and name.endswith(".js"):
        return "ES module entry"
    if name.startswith("chunk") and name.endswith("-legacy.js"):
        return "JS chunk (legacy ES5)"
    if name.startswith("chunk") and name.endswith(".js"):
        return "JS chunk (modern)"
    return ""


def build_new_version_section(new_version: str,
                              fetched_paths: list[str],
                              prior_owner: dict[str, str]) -> str:
    css_rows: list[tuple[str, str, str]] = []
    img_rows: list[tuple[str, str, str]] = []
    js_rows: list[tuple[str, str, str]] = []
    for path in sorted(set(fetched_paths)):
        parts = path.lstrip("/").split("/")
        if len(parts) < 4 or parts[0] != "pad1" or parts[1] != "ipad-static":
            continue
        subdir = parts[2]
        name = parts[-1]
        link = "webapp" + path
        prev = prior_owner.get(name)
        shared = f"Shared with {prev}" if prev and prev != new_version else ""
        if subdir == "assets":
            if name.lower().endswith(".css"):
                remark = "Main stylesheet" if name == "b984b25f.css" else "CSS chunk"
                if shared:
                    remark = f"{remark}. {shared}" if remark else shared
                css_rows.append((name, link, remark))
            elif name.lower().endswith(IMAGE_EXTS):
                ext = name.rsplit(".", 1)[-1].upper()
                remark = f"{ext} image asset"
                if shared:
                    remark = f"{remark}. {shared}"
                img_rows.append((name, link, remark))
            else:
                # Fonts or anything else lands as a generic asset row.
                remark = "Asset"
                if shared:
                    remark = f"{remark}. {shared}"
                img_rows.append((name, link, remark))
        elif subdir == "js":
            remark = _js_remark(name)
            if shared:
                remark = f"{remark}. {shared}" if remark else shared
            js_rows.append((name, link, remark))

    out: list[str] = []
    out.append(f"## App version {new_version}")
    out.append("")
    out.append(
        "Files that are content-hashed per build. The `-legacy` suffix on "
        "JS chunks marks the")
    out.append(
        "ES5-compiled bundle served via Vite's SystemJS legacy plugin.")
    out.append("")
    if css_rows:
        out.append("### `assets` (CSS)")
        out.append("")
        out.append(render_table(css_rows))
        out.append("")
    if img_rows:
        out.append("### `assets` (images)")
        out.append("")
        out.append(render_table(img_rows))
        out.append("")
    if js_rows:
        out.append("### `js`")
        out.append("")
        out.append(render_table(js_rows))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def update_assets_md(new_version: str, fetched_paths: list[str]) -> None:
    with open(ASSETS_MD, encoding="utf-8") as f:
        content = f.read()
    prior_owner = collect_files_per_existing_version()
    new_content, count = PREV_VERSION_RE.subn(
        f"MOST RECENT VERSION: {new_version}", content, count=1)
    if count == 0:
        raise SystemExit("could not find 'MOST RECENT VERSION:' to update")
    m = VERSION_HEADER_RE.search(new_content)
    insert_at = m.start() if m else len(new_content)
    section_md = build_new_version_section(
        new_version, fetched_paths, prior_owner)
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
# Steps
# ---------------------------------------------------------------------------

def step1_rename_previous(previous_version: str) -> None:
    print(f"[1/6] Renaming current pad1/index.html to suffix "
          f"'-{previous_version}'")
    if previous_version == NONE_YET_SENTINEL:
        print("  MOST RECENT VERSION is <NONE_YET> — nothing to rename, "
              "skipping (first-time run)")
        return
    src = os.path.join(PAD1_DIR, "index.html")
    dst = os.path.join(PAD1_DIR, f"index-{previous_version}.html")
    if not os.path.isfile(src):
        # Empty webapp/pad1/ — there's nothing of the previous version
        # to preserve. Treat as a clean first-time run.
        print("  no existing pad1/index.html to rename — treating as "
              "first-time run")
        return
    if os.path.exists(dst):
        raise SystemExit(f"refusing to overwrite existing {dst}")
    os.rename(src, dst)
    if not os.path.isfile(dst) or os.path.exists(src):
        raise SystemExit("rename sanity check failed")
    print(f"  pad1/index.html -> {os.path.relpath(dst, REPO_ROOT)}")


def step2_fetch_index() -> bytes:
    print(f"[2/6] Fetching {INDEX_URL}  (DNS via {DNS_SERVER})")
    status, body, err = http_get(INDEX_URL, max_attempts=2)
    if status != 200 or not body:
        raise SystemExit(
            f"failed to fetch pad1 index.html (status={status}, error={err})")
    lowered = body[:512].lower()
    if b"<html" not in lowered and b"<!doctype html" not in lowered:
        raise SystemExit("upstream returned a non-HTML body for /pad1")
    save_bytes(os.path.join(PAD1_DIR, "index.html"), body)
    print(f"  saved {len(body)} bytes to webapp/pad1/index.html")
    return body


def step3_fetch_html_assets(html_body: bytes,
                            results: list[tuple[str, bool, str]]
                            ) -> set[str]:
    print("[3/6] Fetching assets referenced from pad1/index.html")
    base = INDEX_URL + ("" if INDEX_URL.endswith("/") else "/")
    paths = parse_html_assets(html_body, base)
    saved: set[str] = set()
    for path in paths:
        ok, reason = fetch_and_save(path)
        results.append((path, ok, reason))
        if ok:
            saved.add(path)
    names = {p.rsplit("/", 1)[1] for p in saved}
    if not any(n.startswith("entry") and n.endswith(".js") for n in names):
        raise SystemExit(
            "step 3 sanity check failed: no 'entry*.js' among fetched assets")
    print(f"  fetched {sum(1 for _, ok, _ in results if ok)}/{len(results)} "
          "direct references")
    return saved


def step4_fetch_chunks(seed: set[str],
                       results: list[tuple[str, bool, str]]) -> set[str]:
    print("[4/6] Recursively fetching chunk references")
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
    print(f"  closure stable after {iteration} iteration(s); "
          f"{len(visited - failed)} files fetched, {len(failed)} failed")
    return visited - failed


def fetch_and_save(url_path: str) -> tuple[bool, str]:
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
    if not results:
        print("  (no files were attempted)")
        return
    rows = [(p.rsplit("/", 1)[1] if "/" in p else p,
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
    parser = argparse.ArgumentParser(
        description="Fetch static iFramix iPad 1 webapp assets for a new "
                    "app version")
    parser.add_argument("version", help="New app version, e.g. '2.3.0'")
    parser.add_argument(
        "--skip-rename", action="store_true",
        help="Skip step 1 (useful after a half-failed run).")
    parser.add_argument(
        "--skip-md", action="store_true",
        help="Skip step 5 (don't touch ASSETS_PER_APP_VERSION_PAD1.md).")
    args = parser.parse_args(argv)

    new_version = args.version.strip()
    if not new_version:
        parser.error("version cannot be empty")

    if not os.path.isdir(PAD1_DIR):
        raise SystemExit(f"missing {PAD1_DIR}")
    if not os.path.isfile(ASSETS_MD):
        if not os.path.isfile(ASSETS_MD_TEMPLATE):
            raise SystemExit(f"missing {ASSETS_MD_TEMPLATE}")
        print(f"Creating {ASSETS_MD} from template file {ASSETS_MD_TEMPLATE}")
        shutil.copyfile(ASSETS_MD_TEMPLATE, ASSETS_MD)

    previous_version = find_previous_version()
    if previous_version == new_version:
        raise SystemExit(
            f"MOST RECENT VERSION is already {new_version} — nothing to do.")
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
