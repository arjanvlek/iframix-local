// iFramix Admin — master-detail UI (Claude Design handoff implementation).
//
// The page is server-rendered (sidebar rows, charger table rows and one
// hidden .view per display device); this script wires navigation, the
// 10s charger refresh, and the per-device settings forms to the same
// REST endpoints the native controller app uses.
//
// The script is split into the files under assets/js/, which
// page_template.py concatenates (in _SCRIPT_FILES order) into one
// inline <script>. This file holds the shared helpers (DOM lookup,
// JSON fetch, inline icons, toasts, segmented controls / style grids).
// It is loaded first, so it also carries the "use strict" directive for
// the whole script.

"use strict";

/* ===================== tiny helpers ===================== */

function $(sel, root) { return (root || document).querySelector(sel); }
function $all(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
}

async function postJSON(url, body) {
    const r = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
    });
    return r.json();
}

async function getJSON(url) {
    const r = await fetch(url);
    return r.json();
}

/* ---- inline icons (subset of the design icon set) ---- */
function icon(name, size) {
    const paths = {
        check: '<polyline points="20 6 9 17 4 12"/>',
        trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
        x: '<path d="M18 6 6 18M6 6l12 12"/>',
        image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
        cloud: '<path d="M17.5 19a4.5 4.5 0 0 0 .5-9 6 6 0 0 0-11.6-1.5A4 4 0 0 0 6 19h11.5Z"/>',
        calendar: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
        monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
        smartphone: '<rect x="6.5" y="2" width="11" height="20" rx="2.5"/><path d="M11 18h2"/>',
        alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
    };
    const s = size || 16;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" ' +
        'fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round">' +
        (paths[name] || "") + "</svg>";
}

/* ---- toast ---- */
function toast(msg, isError) {
    const wrap = document.getElementById("toast-wrap");
    if (!wrap) return;
    const t = document.createElement("div");
    t.className = "toast" + (isError ? " error" : "");
    t.innerHTML = '<span class="ti">' +
        icon(isError ? "alert" : "check") + "</span>";
    const span = document.createElement("span");
    span.textContent = msg;
    t.appendChild(span);
    wrap.appendChild(t);
    setTimeout(() => t.remove(), 2400);
}

/* ---- segmented controls / style grids ---- */
function wireSeg(seg, onChange) {
    if (!seg) return;
    $all("button", seg).forEach((btn) => {
        btn.addEventListener("click", () => {
            $all("button", seg).forEach(
                (b) => b.setAttribute("aria-pressed", "false"));
            btn.setAttribute("aria-pressed", "true");
            if (onChange) onChange(btn.dataset.value);
        });
    });
}
function setSegValue(seg, value) {
    if (!seg) return;
    $all("button", seg).forEach((b) => b.setAttribute(
        "aria-pressed", b.dataset.value === String(value) ? "true" : "false"));
}
function segValue(seg) {
    const b = seg && $('button[aria-pressed="true"]', seg);
    return b ? b.dataset.value : null;
}

function wireStyleGrid(grid) {
    if (!grid) return;
    $all(".style-tile", grid).forEach((tile) => {
        tile.addEventListener("click", () => {
            $all(".style-tile", grid).forEach(
                (t) => t.setAttribute("aria-pressed", "false"));
            tile.setAttribute("aria-pressed", "true");
        });
    });
}
function setStyleGridValue(grid, value) {
    if (!grid) return;
    $all(".style-tile", grid).forEach((t) => t.setAttribute(
        "aria-pressed", t.dataset.value === String(value) ? "true" : "false"));
}
function styleGridValue(grid) {
    const t = grid && $('.style-tile[aria-pressed="true"]', grid);
    return t ? parseInt(t.dataset.value, 10) : null;
}
