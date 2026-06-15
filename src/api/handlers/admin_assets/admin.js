// iFramix Admin — master-detail UI (Claude Design handoff implementation).
//
// The page is server-rendered (sidebar rows, charger table rows and one
// hidden .view per display device); this script wires navigation, the
// 10s charger refresh, and the per-device settings forms to the same
// REST endpoints the native controller app uses.

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

/* ===================== view switching ===================== */

function showView(key) {
    let target = document.getElementById("view-" + key);
    if (!target) { key = "chargers"; target = $("#view-chargers"); }

    $all(".view").forEach((v) => v.classList.toggle("active", v === target));
    $all(".nav-item, .device-row").forEach((b) =>
        b.classList.toggle("active", b.dataset.view === key));

    const title = document.getElementById("topbar-title");
    if (key === "chargers") {
        title.textContent = "Chargers";
    } else {
        title.innerHTML = '<span class="crumb">Devices&nbsp;/&nbsp;</span>';
        title.appendChild(
            document.createTextNode(target.dataset.name || ""));
    }

    if (target.classList.contains("device-view") && !target.dataset.loaded) {
        target.dataset.loaded = "1";
        initDevice(target);
    }
    closeDrawer();
    history.replaceState(null, "", "#" + key);
}

/* ---- mobile drawer ---- */
function openDrawer() {
    $("#sidebar").classList.add("open");
    $("#drawer-scrim").hidden = false;
}
function closeDrawer() {
    $("#sidebar").classList.remove("open");
    $("#drawer-scrim").hidden = true;
}

/* ---- sidebar search ---- */
function filterDevices(query) {
    const q = query.trim().toLowerCase();
    let any = false;
    $all("#device-list .device-row").forEach((row) => {
        const hit = !q ||
            (row.dataset.search || "").indexOf(q) !== -1;
        row.hidden = !hit;
        if (hit) any = true;
    });
    const noMatch = $("#device-list .no-match");
    if (noMatch) noMatch.hidden = any || !$("#device-list .device-row");
}

/* ===================== chargers ===================== */

async function refreshChargers() {
    try {
        const r = await fetch("/admin/chargers");
        const rowsHtml = await r.text();
        const tbody = document.getElementById("chargers-tbody");
        if (!tbody) { return; }

        // Change-only flash: snapshot the currently displayed voltage /
        // current per charger before swapping the tbody, then re-apply the
        // .flash animation class only to cells whose value actually changed.
        // (The server no longer bakes in .flash, so steady values stay
        // calm and new rows / the initial render never flash.)
        const prev = {};
        $all("tr[data-uuid]", tbody).forEach((tr) => {
            const v = $(".cell-voltage", tr);
            const c = $(".cell-current", tr);
            prev[tr.dataset.uuid] = {
                voltage: v ? v.textContent.trim() : null,
                current: c ? c.textContent.trim() : null,
            };
        });

        tbody.innerHTML = rowsHtml;

        $all("tr[data-uuid]", tbody).forEach((tr) => {
            const old = prev[tr.dataset.uuid];
            if (!old) { return; }
            const v = $(".cell-voltage", tr);
            const c = $(".cell-current", tr);
            if (v && old.voltage !== null &&
                    v.textContent.trim() !== old.voltage) {
                v.classList.add("flash");
            }
            if (c && old.current !== null &&
                    c.textContent.trim() !== old.current) {
                c.classList.add("flash");
            }
        });

        updateChargersSub();
    } catch {}
}

function updateChargersSub() {
    const rows = $all("#chargers-tbody tr[data-uuid]");
    const charging = rows.filter(
        (r) => r.dataset.status === "on").length;
    const sub = document.getElementById("chargers-sub");
    if (sub) {
        sub.textContent = rows.length + " connected · " +
            charging + " charging";
    }
    const count = document.getElementById("charger-count");
    if (count) count.textContent = rows.length;
}

/* ---- live refresh toggle ---- */
// Clicking the topbar "Live · 10s" pill pauses/resumes the 10s
// background refresh (chargers table + device presence). Paused state:
// the pulsing green dot disappears and every "live" label flips to a
// paused wording (pill, sidebar foot).
let liveRefresh = true;

function setLiveRefresh(on) {
    liveRefresh = on;
    const pill = document.getElementById("live-toggle");
    if (pill) {
        pill.classList.toggle("paused", !on);
        pill.title = on
            ? "Click to pause the 10s background refresh"
            : "Click to resume the 10s background refresh";
        const label = $(".rtext", pill);
        if (label) label.textContent = on ? "Live · 10s" : "Paused";
    }
    const foot = document.getElementById("sidebar-foot");
    if (foot) {
        const dot = $(".dot", foot);
        if (dot) dot.className = "dot " + (on ? "online" : "offline");
        const text = $(".foot-text", foot);
        if (text) {
            text.textContent = on
                ? "Telemetry auto-refreshes every 10s"
                : "Auto-refresh paused";
        }
    }
    if (on) {
        // catch up immediately rather than waiting for the next tick
        refreshChargers();
        refreshDeviceStatus();
    }
}

// Background refresh of the display-device presence indicators: the
// sidebar online dots, the "N/M" online counter, and each detail
// view's Online/Offline chip + "seen ..." tag. Polled on the same 10s
// cadence as the chargers table; only existing DOM nodes are updated
// (a newly logged-in device still requires a page reload to appear).
async function refreshDeviceStatus() {
    try {
        const resp = await getJSON("/admin/devices");
        const d = (resp && resp.data) || {};
        const counter = $(".nav-label .online-count");
        if (counter) {
            counter.innerHTML = '<span class="dot online"></span>' +
                (d.online || 0) + "/" + (d.total || 0);
        }
        (d.devices || []).forEach((dev) => {
            const cls = dev.online ? "online" : "offline";
            const label = dev.online ? "Online" : "Offline";

            const row = $('.device-row[data-view="device-' + dev.id +
                '"] .dot');
            if (row) {
                row.className = "dot " + cls;
                row.title = label;
            }

            const view = document.getElementById("view-device-" + dev.id);
            if (!view) return;
            const chip = $(".presence-chip", view);
            if (chip) {
                chip.className = "chip presence-chip " + cls;
                chip.innerHTML = '<span class="dot ' + cls + '"></span>' +
                    label;
            }
            const seen = $(".seen-tag", view);
            if (seen) seen.textContent = "seen " + dev.seen;
        });
    } catch {}
}

// Called from the server-rendered Power on/off buttons.
async function toggle(uuid, on) {
    try {
        const data = await postJSON("/admin/toggle",
            {uuid, charging_on: on});
        if (data.code === 1) {
            toast("Power output turned " + (on ? "on" : "off"));
            refreshChargers();
        } else {
            toast("Error: " + (data.msg || "unknown"), true);
        }
    } catch (err) {
        toast("Request failed: " + err, true);
    }
}

// Called from the server-rendered Auto/Manual segmented control.
async function setMode(uuid, mode) {
    try {
        const data = await postJSON("/admin/set-mode", {uuid, mode});
        if (data.code === 1) {
            toast("Mode set to " + (mode === "auto" ? "Auto" : "Manual"));
            refreshChargers();
        } else {
            toast("Error: " + (data.msg || "unknown"), true);
        }
    } catch (err) {
        toast("Request failed: " + err, true);
    }
}

/* ===================== per-device state ===================== */

const PHOTO_PAGE_SIZE = 24;
const deviceState = {};

function getState(deviceId) {
    if (!deviceState[deviceId]) {
        deviceState[deviceId] = {
            kind: "normal",
            filter: "all",
            sort: "default",
            selected: new Set(),
            photos: {
                normal: {items: [], total: 0, page: 0},
                ai: {items: [], total: 0, page: 0},
            },
            weather: {cityId: "", cityName: "", lat: "", lon: ""},
            playback: {rules: [], editIndex: null,
                       isPlaying: false, currentModule: ""},
        };
    }
    return deviceState[deviceId];
}

function initDevice(view) {
    loadPhotos(view);
    loadClock(view);
    loadWeather(view);
    loadPlayback(view);
    loadCalendars(view);
}

/* ===================== photos ===================== */

function loadPhotos(view) {
    const state = getState(view.dataset.deviceId);
    state.selected.clear();
    ["normal", "ai"].forEach((type) => {
        state.photos[type] = {items: [], total: 0, page: 0};
        loadPhotoPage(view, type, 1);
    });
}

async function loadPhotoPage(view, type, page) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    try {
        const data = await getJSON(
            "/admin/photos?device_id=" + deviceId + "&type=" + type +
            "&page=" + page + "&page_size=" + PHOTO_PAGE_SIZE +
            "&sort=" + state.sort);
        const d = (data && data.data) || {};
        const slot = state.photos[type];
        if (page === 1) slot.items = [];
        slot.items = slot.items.concat(d.list || []);
        slot.total = d.total || 0;
        slot.page = page;
        renderGallery(view);
    } catch {}
}

function renderGallery(view) {
    const state = getState(view.dataset.deviceId);
    const grid = $(".grid-photos", view);
    if (!grid) return;

    const n = state.photos.normal;
    const a = state.photos.ai;
    let shown;
    if (state.filter === "normal") shown = n.items.map(
        (m) => ({m, type: "normal"}));
    else if (state.filter === "ai") shown = a.items.map(
        (m) => ({m, type: "ai"}));
    else shown = n.items.map((m) => ({m, type: "normal"}))
        .concat(a.items.map((m) => ({m, type: "ai"})));

    grid.innerHTML = "";
    shown.forEach(({m, type}) => grid.appendChild(photoNode(view, m, type)));

    // filter counts
    const counts = {normal: n.total, ai: a.total, all: n.total + a.total};
    $all(".fcount", view).forEach((el) => {
        el.textContent = counts[el.dataset.fcount];
    });
    const tabCount = $('.tab[data-tab="photos"] .tcount', view);
    if (tabCount) tabCount.textContent = counts.all || "";

    // empty state
    const empty = $(".photos-empty", view);
    if (empty) {
        empty.hidden = shown.length > 0;
        empty.textContent = "No " +
            (state.filter === "all" ? "" :
                state.filter === "ai" ? "AI " : "normal ") +
            "photos yet — drop some above to get started.";
    }

    renderLoadMore(view);
    updateDeleteButton(view);
}

function photoNode(view, m, type) {
    const state = getState(view.dataset.deviceId);
    const el = document.createElement("div");
    el.className = "photo" +
        (state.selected.has(String(m.id)) ? " selected" : "");
    el.title = (m.filename || "") +
        (type === "ai" ? " · click to set display template"
                       : " · click to preview");
    el.dataset.mediaId = m.id;

    const img = document.createElement("img");
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = m.filename || "";
    img.src = m.thumb_url;
    el.appendChild(img);

    if (type === 'ai') {
        const badge = document.createElement("span");
        badge.className = "ph-badge ai";
        badge.textContent = "AI"
        el.appendChild(badge);
    }

    const check = document.createElement("button");
    check.type = "button";
    check.className = "ph-check";
    check.title = "Select for deletion";
    check.innerHTML = icon("check", 13);
    check.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = String(m.id);
        if (state.selected.has(id)) state.selected.delete(id);
        else state.selected.add(id);
        el.classList.toggle("selected", state.selected.has(id));
        updateDeleteButton(view);
    });
    el.appendChild(check);

    if (type === "ai") {
        const chip = document.createElement("span");
        chip.className = "ph-tpl";
        chip.innerHTML = icon("image", 12);
        const label = document.createElement("span");
        label.textContent = templateChipName(
            view.dataset.aspect, m.template_type || 1, m.template_id || 0);
        chip.appendChild(label);
        el.appendChild(chip);
        el.addEventListener("click", () => openTemplateModal(view, m));
    } else {
        el.addEventListener("click", () => openLightbox(m.url));
    }
    return el;
}

function renderLoadMore(view) {
    const state = getState(view.dataset.deviceId);
    const more = $(".photo-more", view);
    if (!more) return;
    const types = state.filter === "all"
        ? ["normal", "ai"] : [state.filter];
    const loaded = types.reduce(
        (s, t) => s + state.photos[t].items.length, 0);
    const total = types.reduce((s, t) => s + state.photos[t].total, 0);
    more.innerHTML = "";
    if (loaded < total) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn sm load-more-btn";
        btn.textContent =
            "Load more (" + loaded + " of " + total + ")";
        btn.addEventListener("click", () => {
            btn.disabled = true;
            btn.textContent = "Loading…";
            types.forEach((t) => {
                const slot = state.photos[t];
                if (slot.items.length < slot.total) {
                    loadPhotoPage(view, t, slot.page + 1);
                }
            });
        });
        more.appendChild(btn);
    } else if (total > PHOTO_PAGE_SIZE) {
        const note = document.createElement("span");
        note.className = "photo-more-note";
        note.textContent = "All " + total + " shown";
        more.appendChild(note);
    }
}

function updateDeleteButton(view) {
    const state = getState(view.dataset.deviceId);
    const btn = $(".delete-selected", view);
    if (!btn) return;
    const nSel = state.selected.size;
    btn.hidden = nSel === 0;
    $(".del-count", btn).textContent = nSel;
}

// Bulk-delete the checked photos via the same delMedia endpoint /
// `ipad/media/delete` MQTT event the display app uses.
async function deleteSelectedPhotos(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    const ids = Array.from(state.selected);
    if (!ids.length) return;
    if (!confirm("Delete " + ids.length +
            " photo(s)? This cannot be undone.")) {
        return;
    }
    try {
        const data = await postJSON("/api/ipad/media/delMedia", {
            id: ids,
            device_id: parseInt(deviceId, 10),
        });
        if (data.code === 1) {
            toast(ids.length + " photo" +
                (ids.length > 1 ? "s" : "") + " deleted");
            // delMedia removes files in a background thread, so give it
            // a moment before re-reading the (now shorter) list.
            setTimeout(() => loadPhotos(view), 600);
        } else {
            toast("Delete failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Delete error: " + e, true);
    }
}

/* ---- upload (dropzone) ---- */

async function handleFiles(view, fileList) {
    const files = Array.from(fileList || []).filter(
        (f) => /^image\//.test(f.type) || /\.(jpe?g|png|gif|webp|heic)$/i
            .test(f.name));
    if (!files.length) return;
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    const kind = state.kind;
    const dz = $(".dropzone", view);
    const title = $(".dz-title", view);
    const origTitle = title.textContent;
    dz.classList.add("busy");

    // Upload sequentially (one file at a time) to avoid overwhelming the
    // server when many photos are selected. Mirrors how the native app
    // uploads photos one by one.
    const assetIds = [];
    try {
        for (const [idx, file] of files.entries()) {
            title.textContent = "Uploading " + (idx + 1) + "/" +
                files.length + "…";
            const fd = new FormData();
            fd.append("file", file);
            fd.append("key", file.name);
            const suffix =
                (file.name.split(".").pop() || "jpg").toLowerCase();
            fd.append("x:suffix", suffix);
            const r = await fetch("/api/user/asset/upload",
                {method: "POST", body: fd});
            const data = await r.json();
            if (data && data.code === 1 && data.data && data.data.id) {
                assetIds.push(data.data.id);
            } else {
                throw new Error("upload rejected for " + file.name);
            }
        }
        const data = await postJSON("/api/ipad/media/setMedia", {
            device_id: parseInt(deviceId, 10),
            asset_ids: assetIds,
            type: kind,
        });
        if (data.code === 1) {
            toast(assetIds.length +
                (kind === "ai" ? " AI image" : " photo") +
                (assetIds.length > 1 ? "s" : "") + " added");
            loadPhotos(view);
        } else {
            toast("setMedia failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Upload failed: " + e, true);
    } finally {
        dz.classList.remove("busy");
        title.textContent = origTitle;
    }
}

/* ===================== flip clock ===================== */

async function loadClock(view) {
    const deviceId = view.dataset.deviceId;
    try {
        const data = await getJSON(
            "/api/ipad/device/setting/screensaver?id=" + deviceId);
        const cur = (data && data.data) || {};
        const no = (cur.no != null) ? parseInt(cur.no, 10) : 1;
        const time = (cur.time != null) ? parseInt(cur.time, 10) : 1;
        setSegValue($('[data-seg="clock-format"]', view), time);
        setStyleGridValue($('[data-style-grid="clock"]', view), no);
    } catch {}
}

async function saveClock(view) {
    const deviceId = view.dataset.deviceId;
    const time = segValue($('[data-seg="clock-format"]', view));
    const no = styleGridValue($('[data-style-grid="clock"]', view));
    if (!time) { toast("Select 12-hour or 24-hour first", true); return; }
    if (!no) { toast("Pick a clock style first", true); return; }
    try {
        const data = await postJSON("/api/ipad/device/setting/screensaver", {
            id: parseInt(deviceId, 10),
            values: {no, time: parseInt(time, 10)},
        });
        if (data.code === 1) toast("Clock settings saved");
        else toast("Failed: " + (data.msg || "?"), true);
    } catch (e) {
        toast("Error: " + e, true);
    }
}

/* ===================== weather ===================== */

async function loadWeather(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    try {
        const data = await getJSON(
            "/api/ipad/device/setting/weather?id=" + deviceId);
        const cur = (data && data.data) || {};
        if (cur.city) {
            const cm = cur.cityMsg || {};
            state.weather = {
                cityId: cm.id || "",
                cityName: cur.city,
                lat: cm.lat || "",
                lon: cm.lon || "",
            };
            setCurrentCity(view, "Current: ", cur.city);
        }
        setSegValue($('[data-seg="unit"]', view), cur.unit || 1);
        // weather_template_id is 0-based (0..3) to match the iFramix
        // 2.2.29 webapp catalog. A saved 0 must stay 0.
        const styleId = (cur.weather_template_id != null)
            ? cur.weather_template_id : 0;
        setStyleGridValue($('[data-style-grid="weather"]', view), styleId);
    } catch {}
}

function setCurrentCity(view, prefix, city) {
    const el = $(".current-city", view);
    if (!el) return;
    el.innerHTML = '<span class="cc-ico">' + icon("cloud", 15) + "</span>";
    el.appendChild(document.createTextNode(prefix));
    const b = document.createElement("b");
    b.textContent = city;
    el.appendChild(b);
}

async function searchCity(view) {
    const kw = $(".city-query", view).value.trim();
    if (!kw) return;
    const list = $(".city-results", view);
    try {
        const data = await getJSON(
            "/api/ipad/address/city?keyword=" +
            encodeURIComponent(kw) + "&lang=en");
        list.innerHTML = "";
        const results = Array.isArray(data.data) ? data.data : [];
        if (!results.length) {
            toast("No cities found for “" + kw + "”", true);
            return;
        }
        const state = getState(view.dataset.deviceId);
        for (const city of results) {
            const opt = document.createElement("button");
            opt.type = "button";
            opt.className = "city-opt";
            const parts = [city.name];
            if (city.adm1 && city.adm1 !== city.name) parts.push(city.adm1);
            if (city.country) parts.push(city.country);
            const label = parts.filter(Boolean).join(", ");
            opt.innerHTML = icon("cloud", 14);
            opt.appendChild(document.createTextNode(" " + label));
            opt.addEventListener("click", () => {
                state.weather = {
                    cityId: city.city_id || city.id || "",
                    cityName: city.name || "",
                    lat: city.lat || "",
                    lon: city.lon || "",
                };
                setCurrentCity(view, "Selected: ", label);
                list.innerHTML = "";
            });
            list.appendChild(opt);
        }
    } catch (e) {
        toast("Search error: " + e, true);
    }
}

async function saveWeather(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    if (!state.weather.cityId) {
        toast("Search and select a city first", true);
        return;
    }
    const unit = parseInt(segValue($('[data-seg="unit"]', view)) || "1", 10);
    const styleId = styleGridValue($('[data-style-grid="weather"]', view));
    try {
        const data = await postJSON("/api/ipad/device/setting/weather", {
            id: parseInt(deviceId, 10),
            values: {
                city: state.weather.cityName,
                cityMsg: {
                    id: state.weather.cityId,
                    name: state.weather.cityName,
                    lat: state.weather.lat,
                    lon: state.weather.lon,
                },
                unit,
                weather_template_id: styleId == null ? 0 : styleId,
            },
        });
        if (data.code === 1) toast("Weather settings saved");
        else toast("Failed: " + (data.msg || "?"), true);
    } catch (e) {
        toast("Error: " + e, true);
    }
}

/* ===================== playback (app 2.3.1+) ===================== */
//
// Mirrors the native app's Playback Settings screen: random mode
// (switch interval + per-module inclusion toggles) or fixed mode
// (default module + daily time rules). The API stores and broadcasts
// the whole settings document on every save, so all edits here are
// local until "Save playback" posts the assembled document.

const PLAYBACK_MODULE_NAMES = {
    album: "Photos",
    album_ai: "AI Photos",
    screensaver: "Flip Clock",
    weather: "Weather",
    calendar: "Calendar",
};

async function loadPlayback(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    let cur = {};
    try {
        const data = await getJSON(
            "/api/ipad/device/setting/playback?id=" + deviceId);
        // An unconfigured device gets an empty array back (matching
        // the cloud server); treat it the same as an empty object.
        if (data && data.data && !Array.isArray(data.data)) {
            cur = data.data;
        }
    } catch {}
    const random = cur.random || {};
    const fixed = cur.fixed || {};

    state.playback.rules = (fixed.rules || []).map((r) => ({
        startTime: r.startTime, endTime: r.endTime, module: r.module}));
    state.playback.editIndex = null;
    state.playback.isPlaying = !!cur.isPlaying;
    state.playback.currentModule = cur.currentModule || "";

    setSegValue($('[data-seg="playback-mode"]', view),
        cur.mode === "fixed" ? "fixed" : "random");
    $(".playback-interval", view).value =
        random.intervalMinutes != null ? random.intervalMinutes : 15;
    const excluded = random.excludedModules || [];
    $all(".module-row", view).forEach((row) => {
        $("input", row).checked =
            excluded.indexOf(row.dataset.module) === -1;
    });
    $(".playback-default", view).value = fixed.defaultModule || "";

    renderPlaybackMode(view);
    renderPlaybackModuleCount(view);
    renderPlaybackRules(view);
}

function renderPlaybackMode(view) {
    const mode = segValue($('[data-seg="playback-mode"]', view));
    $(".playback-random", view).hidden = mode === "fixed";
    $(".playback-fixed", view).hidden = mode !== "fixed";
}

function renderPlaybackModuleCount(view) {
    const total = $all(".module-row", view).length;
    const on = $all(".module-row input:checked", view).length;
    const label = $(".module-count", view);
    if (label) label.textContent = "(" + on + " / " + total + " enabled)";
}

function renderPlaybackRules(view) {
    const state = getState(view.dataset.deviceId);
    const list = $(".rule-list", view);
    if (!list) return;
    list.innerHTML = "";

    let emptyNote = $(".rule-empty", view);
    if (!state.playback.rules.length) {
        if (!emptyNote) {
            emptyNote = document.createElement("div");
            emptyNote.className = "rule-empty";
            emptyNote.textContent = "No time rules yet. The default " +
                "module will be used all day.";
            list.parentNode.insertBefore(emptyNote, list);
        }
        emptyNote.hidden = false;
        return;
    }
    if (emptyNote) emptyNote.hidden = true;

    state.playback.rules.forEach((rule, i) => {
        const item = document.createElement("div");
        item.className = "rule-item" +
            (state.playback.editIndex === i ? " editing" : "");

        const time = document.createElement("span");
        time.className = "rule-time";
        time.textContent = rule.startTime + " – " + rule.endTime;
        item.appendChild(time);

        const name = document.createElement("span");
        name.className = "rule-module-name";
        name.textContent =
            PLAYBACK_MODULE_NAMES[rule.module] || rule.module;
        item.appendChild(name);

        const actions = document.createElement("div");
        actions.className = "rule-actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "btn sm";
        edit.textContent = "Edit";
        edit.addEventListener("click", () => startRuleEdit(view, i));
        actions.appendChild(edit);
        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn sm ghost-danger";
        del.innerHTML = icon("trash", 13);
        del.title = "Delete rule";
        del.addEventListener("click", () => {
            state.playback.rules.splice(i, 1);
            if (state.playback.editIndex === i) resetRuleForm(view);
            else if (state.playback.editIndex > i) {
                state.playback.editIndex--;
            }
            renderPlaybackRules(view);
        });
        actions.appendChild(del);
        item.appendChild(actions);

        list.appendChild(item);
    });
}

function startRuleEdit(view, index) {
    const state = getState(view.dataset.deviceId);
    const rule = state.playback.rules[index];
    if (!rule) return;
    state.playback.editIndex = index;
    $(".rule-start", view).value = rule.startTime;
    $(".rule-end", view).value = rule.endTime;
    $(".rule-module", view).value = rule.module;
    $(".rule-add-label", view).textContent = "Update rule";
    $(".rule-cancel-btn", view).hidden = false;
    renderPlaybackRules(view);
}

function resetRuleForm(view) {
    const state = getState(view.dataset.deviceId);
    state.playback.editIndex = null;
    $(".rule-start", view).value = "";
    $(".rule-end", view).value = "";
    $(".rule-module", view).selectedIndex = 0;
    $(".rule-add-label", view).textContent = "Add rule";
    $(".rule-cancel-btn", view).hidden = true;
}

// Rules repeat daily and may not overlap (same constraints the native
// app enforces). Start must come before end within the same day.
function submitRule(view) {
    const state = getState(view.dataset.deviceId);
    const start = $(".rule-start", view).value;
    const end = $(".rule-end", view).value;
    const module = $(".rule-module", view).value;
    if (!start || !end) {
        toast("Pick a start and end time first", true);
        return;
    }
    if (start >= end) {
        toast("End time must be after start time (rules stay within " +
            "one day)", true);
        return;
    }
    if (!module) {
        toast("Pick a module for this rule", true);
        return;
    }
    const overlap = state.playback.rules.some((r, i) =>
        i !== state.playback.editIndex &&
        start < r.endTime && r.startTime < end);
    if (overlap) {
        toast("Time rules cannot overlap an existing rule", true);
        return;
    }
    const rule = {startTime: start, endTime: end, module};
    if (state.playback.editIndex !== null) {
        state.playback.rules[state.playback.editIndex] = rule;
    } else {
        state.playback.rules.push(rule);
    }
    state.playback.rules.sort(
        (a, b) => a.startTime < b.startTime ? -1 : 1);
    resetRuleForm(view);
    renderPlaybackRules(view);
}

async function savePlayback(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    const mode = segValue($('[data-seg="playback-mode"]', view)) ||
        "random";

    const interval = parseInt($(".playback-interval", view).value, 10);
    if (!(interval >= 1 && interval <= 240)) {
        toast("Switch interval must be between 1 and 240 minutes", true);
        return;
    }
    const excluded = $all(".module-row", view)
        .filter((row) => !$("input", row).checked)
        .map((row) => row.dataset.module);
    if (mode === "random" &&
            excluded.length === $all(".module-row", view).length) {
        toast("Enable at least one module for random playback", true);
        return;
    }
    const defaultModule = $(".playback-default", view).value;
    if (mode === "fixed" && !defaultModule &&
            !state.playback.rules.length) {
        toast("Pick a default module or add a time rule first", true);
        return;
    }

    try {
        const data = await postJSON("/api/ipad/device/setting/playback", {
            id: parseInt(deviceId, 10),
            values: {
                mode,
                random: {
                    intervalMinutes: interval,
                    excludedModules: excluded,
                },
                fixed: {
                    defaultModule,
                    rules: state.playback.rules,
                },
                isPlaying: state.playback.isPlaying,
                currentModule: state.playback.currentModule,
            },
        });
        if (data.code === 1) toast("Playback settings saved");
        else toast("Failed: " + (data.msg || "?"), true);
    } catch (e) {
        toast("Error: " + e, true);
    }
}

/* ===================== calendars ===================== */

const CAL_PROVIDERS = {
    google: {name: "Google Calendar", hue: 256},
    icloud: {name: "Apple iCloud", hue: 220},
    outlook: {name: "Outlook / Microsoft 365", hue: 240},
    manual: {name: "Other (ICS URL)", hue: 290},
};

async function loadCalendars(view) {
    const deviceId = view.dataset.deviceId;
    const list = $(".cal-list", view);
    if (!list) return;
    try {
        const data = await getJSON(
            "/api/calendar/index?device_id=" + deviceId);
        const items = (data && data.data && data.data.list) || [];
        list.innerHTML = "";
        const tabCount = $('.tab[data-tab="calendars"] .tcount', view);
        if (tabCount) tabCount.textContent = items.length || "";
        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "empty";
            empty.textContent = "No calendars linked yet.";
            list.appendChild(empty);
            return;
        }
        for (const cal of items) {
            const prov = CAL_PROVIDERS[cal.driver] ||
                {name: cal.driver || "Calendar", hue: 256};
            const item = document.createElement("div");
            item.className = "cal-item";

            const ico = document.createElement("div");
            ico.className = "cal-ico";
            ico.style.background = "oklch(0.55 0.15 " + prov.hue + ")";
            ico.innerHTML = icon("calendar", 17);
            item.appendChild(ico);

            const meta = document.createElement("div");
            meta.className = "cal-meta";
            const name = document.createElement("div");
            name.className = "cal-name";
            name.textContent = cal.name || "(no name)";
            const url = document.createElement("div");
            url.className = "cal-url";
            url.textContent = cal.url || "";
            meta.appendChild(name);
            meta.appendChild(url);
            item.appendChild(meta);

            const tag = document.createElement("span");
            tag.className = "tag";
            tag.textContent = prov.name;
            item.appendChild(tag);

            const del = document.createElement("button");
            del.type = "button";
            del.className = "icon-btn";
            del.style.width = "34px";
            del.style.height = "34px";
            del.title = "Remove";
            del.innerHTML = icon("trash", 15);
            del.style.color = "var(--danger-text)";
            del.addEventListener("click", () =>
                removeCalendar(view, cal.id));
            item.appendChild(del);

            list.appendChild(item);
        }
    } catch {}
}

async function addCalendar(view) {
    const deviceId = view.dataset.deviceId;
    const driver = $(".cal-driver", view).value;
    let name = $(".cal-name-input", view).value.trim();
    const url = $(".cal-url-input", view).value.trim();
    if (!url) { toast("Add a calendar URL first", true); return; }
    if (!name) {
        name = (CAL_PROVIDERS[driver] || {}).name ||
            driver.charAt(0).toUpperCase() + driver.slice(1);
    }
    try {
        const data = await postJSON("/api/calendar/external/link", {
            url,
            device_id: parseInt(deviceId, 10),
            name,
            driver,
        });
        if (data.code === 1) {
            toast("Calendar linked");
            $(".cal-name-input", view).value = "";
            $(".cal-url-input", view).value = "";
            loadCalendars(view);
        } else {
            toast("Failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Error: " + e, true);
    }
}

async function removeCalendar(view, calId) {
    try {
        const data = await postJSON("/api/calendar/delete", {id: calId});
        if (data.code === 1) {
            toast("Calendar removed");
            loadCalendars(view);
        } else {
            toast("Delete failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Delete error: " + e, true);
    }
}

/* ===================== remove device ===================== */

async function deleteDevice(view) {
    const deviceId = view.dataset.deviceId;
    try {
        const data = await postJSON("/api/ipad/device/unbindUser",
            {id: parseInt(deviceId, 10)});
        if (data.code === 1) {
            toast("Display device removed");
            const row = $('.device-row[data-view="device-' + deviceId +
                '"]');
            if (row) row.remove();
            view.remove();
            showView("chargers");
        } else {
            toast("Failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Error: " + e, true);
    }
}

/* ===================== lightbox (normal photos) ===================== */

function openLightbox(url) {
    const lb = document.getElementById("lightbox");
    $("img", lb).src = url;
    lb.classList.add("open");
}
function closeLightbox() {
    const lb = document.getElementById("lightbox");
    lb.classList.remove("open");
    $("img", lb).src = "";
}

/* ===================== AI template modal ===================== */
//
// The modal keeps the design's layout (large live preview left, named
// option list right) but the catalog is the real aspect-aware one: the
// iPad webapp renders 10 templates on 4:3 displays (its inline
// ``pq``/``mq`` catalogs) and the static ``mcol_1..5`` (horizontal) /
// ``mrow_1..4`` (vertical) classes on 16:9 — so every option offered
// here is a value the display can actually render.

const TPL_META_4X3 = [
    {name: "Left bookend", desc: "Sidebar left, photo right with caption strip"},
    {name: "Split canvas", desc: "Caption panel left, photo right"},
    {name: "Corner cut", desc: "Photo with a diagonal caption area below"},
    {name: "Asymmetric base", desc: "Photo on top, captions below"},
    {name: "Cross boundary", desc: "Photo with an overlapping block"},
    {name: "Dark card", desc: "Full photo with a dark caption card"},
    {name: "Side arch", desc: "Caption left, photo right behind an arch"},
    {name: "Top cover", desc: "Photo on top, centered caption below"},
    {name: "Bottom left", desc: "Photo on top, caption bottom-left"},
    {name: "Side ribbon", desc: "Photo left, caption ribbon right"},
];
const TPL_META_16X9_H = [
    {name: "Photo left", desc: "Photo on the left, caption panel right"},
    {name: "Photo right", desc: "Photo on the right, caption panel left"},
    {name: "Overlay top-left", desc: "Full photo, caption card top-left"},
    {name: "Overlay bottom-right", desc: "Full photo, caption card bottom-right"},
    {name: "Overlay bottom-left", desc: "Full photo, translucent caption bottom-left"},
];
// mrow_1..4 (vertical photos on 16:9) reuse the first four designs.
const TPL_META_16X9_V = TPL_META_16X9_H.slice(0, 4);

function templateCatalog(aspect, templateType) {
    if (aspect === "4x3") return TPL_META_4X3;
    return templateType === 2 ? TPL_META_16X9_V : TPL_META_16X9_H;
}

function templateChipName(aspect, templateType, id) {
    const cat = templateCatalog(aspect, templateType);
    if (id >= 1 && id <= cat.length) return cat[id - 1].name;
    return id ? "Style " + id : "Auto";
}

function _templatePickerSpec(aspect, templateType) {
    if (aspect === "4x3") {
        return {
            count: 10,
            hint: "Photo has a " +
                (templateType === 2 ? "vertical" : "horizontal") +
                " layout · ten templates suit 4:3 displays.",
        };
    }
    if (templateType === 2) {
        return {
            count: 4,
            hint: "Photo has a vertical layout · " +
                "four templates suit 16:9 displays.",
        };
    }
    return {
        count: 5,
        hint: "Photo has a horizontal layout · " +
            "five templates suit 16:9 displays.",
    };
}

// Renders an SVG preview of the layout the iPad webapp shows for this
// template_id on the given display aspect. When ``photoUrl`` is given,
// the photo itself is composited into the image areas (cover-cropped),
// so the modal preview is a true "how it will look" rendering;
// otherwise the image areas are plain grey. ``preview-text-bg`` rects
// pick up an accent tint when the parent option is selected.
let _svgUid = 0;
function _templatePreviewSvg(aspect, id, photoUrl) {
    const W = aspect === "4x3" ? 120 : 160;
    const H = 90;
    // Layouts are authored on the original 100x60 grid; map into the
    // aspect-correct viewBox so embedded photos keep their proportions.
    const fx = (v) => +(v / 100 * W).toFixed(2);
    const fy = (v) => +(v / 60 * H).toFixed(2);
    const esc = (u) => String(u || "")
        .replace(/&/g, "&amp;").replace(/"/g, "&quot;")
        .replace(/</g, "%3C").replace(/>/g, "%3E");
    const defs = [];

    const photo = (x, y, w, h, clip) => {
        const attrs = 'x="' + fx(x) + '" y="' + fy(y) + '" width="' +
            fx(w) + '" height="' + fy(h) + '"' +
            (clip ? ' clip-path="url(#' + clip + ')"' : "");
        if (photoUrl) {
            return '<image href="' + esc(photoUrl) + '" ' + attrs +
                ' preserveAspectRatio="xMidYMid slice"/>';
        }
        return '<rect ' + attrs + ' fill="#9e9e9e"/>';
    };
    const clipPoly = (points) => {
        const cid = "tplclip" + (++_svgUid);
        const pts = points.map(
            ([x, y]) => fx(x) + "," + fy(y)).join(" ");
        defs.push('<clipPath id="' + cid + '"><polygon points="' +
            pts + '"/></clipPath>');
        return cid;
    };
    const clipPath = (d) => {
        const cid = "tplclip" + (++_svgUid);
        defs.push('<clipPath id="' + cid + '"><path d="' + d +
            '"/></clipPath>');
        return cid;
    };
    const bg = (color) => '<rect width="' + W + '" height="' + H +
        '" fill="' + color + '"/>';
    const fullPhoto = () => photo(0, 0, 100, 60);
    const panel = (x, y, w, h) =>
        '<rect class="preview-text-bg" x="' + fx(x) + '" y="' + fy(y) +
        '" width="' + fx(w) + '" height="' + fy(h) + '" fill="#e0e0e0"/>';
    const box = (x, y, w, h, fill) =>
        '<rect x="' + fx(x) + '" y="' + fy(y) + '" width="' + fx(w) +
        '" height="' + fy(h) + '" rx="3" fill="' + fill +
        '" stroke="#bbb" stroke-width="0.5"/>';
    const lines = (cx, y, w, count, color) => {
        let s = "";
        for (let i = 0; i < count; i++) {
            const lw = w * (1 - i * 0.18);
            s += '<rect x="' + fx(cx - lw / 2) + '" y="' + fy(y + i * 5) +
                '" width="' + fx(lw) + '" height="' + fy(2) +
                '" rx="1" fill="' + (color || "#888") + '"/>';
        }
        return s;
    };
    const svg = (body) =>
        '<svg viewBox="0 0 ' + W + " " + H +
        '" xmlns="http://www.w3.org/2000/svg">' +
        (defs.length ? "<defs>" + defs.join("") + "</defs>" : "") +
        body + "</svg>";

    if (aspect === "4x3") {
        // Mirror the 10 entries in the webapp's ``pq``/``mq`` catalogs.
        switch (id) {
            case 1: // Left bookend
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 25, 60)
                    + photo(25, 0, 75, 60)
                    + '<rect x="' + fx(25) + '" y="' + fy(44) +
                      '" width="' + fx(75) + '" height="' + fy(16) +
                      '" fill="rgba(0,0,0,0.45)"/>'
                    + lines(62, 50, 40, 2, "#fff")
                    + lines(8, 28, 14, 2, "#999")
                );
            case 2: // Split canvas
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 40, 60)
                    + photo(40, 0, 60, 60)
                    + lines(20, 28, 26, 2)
                );
            case 3: { // Corner cut
                const cid = clipPoly(
                    [[0, 0], [100, 0], [100, 30], [0, 40]]);
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 100, 40, cid)
                    + lines(50, 47, 50, 2)
                );
            }
            case 4: // Asymmetric base
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 100, 43)
                    + lines(30, 50, 30, 2)
                    + lines(70, 50, 24, 2)
                );
            case 5: // Cross boundary
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 100, 45)
                    + '<rect x="' + fx(55) + '" y="' + fy(32) +
                      '" width="' + fx(35) + '" height="' + fy(18) +
                      '" fill="#5a5a5a"/>'
                    + lines(20, 53, 22, 1)
                );
            case 6: // Dark card
                return svg(
                    (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                    + '<rect x="' + fx(20) + '" y="' + fy(38) +
                      '" width="' + fx(60) + '" height="' + fy(14) +
                      '" rx="2" fill="#333"/>'
                    + lines(50, 42, 36, 2, "#cfcfcf")
                );
            case 7: { // Side arch
                const d = "M " + fx(38) + "," + fy(0) +
                    " L " + fx(100) + "," + fy(0) +
                    " L " + fx(100) + "," + fy(60) +
                    " L " + fx(38) + "," + fy(60) +
                    " Q " + fx(18) + "," + fy(30) +
                    " " + fx(38) + "," + fy(0) + " Z";
                const cid = clipPath(d);
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 38, 60)
                    + photo(18, 0, 82, 60, cid)
                    + lines(13, 28, 18, 2)
                );
            }
            case 8: // Top cover
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 100, 45)
                    + lines(50, 51, 50, 2)
                );
            case 9: // Bottom left
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 100, 45)
                    + lines(20, 51, 28, 2)
                );
            case 10: // Side ribbon
                return svg(
                    bg("#f5f5f5")
                    + photo(0, 0, 75, 60)
                    + panel(75, 0, 25, 60)
                    + lines(87, 18, 16, 4)
                );
        }
    }

    // 16:9 catalog. mcol_1..5 (horizontal) and mrow_1..4 (vertical) per
    // the override block in webapp/index.html: split layout for 1/2,
    // full-photo overlay for 3/4/5.
    switch (id) {
        case 1: // photo left half, text right half
            return svg(
                bg("#f5f5f5")
                + panel(50, 0, 50, 60)
                + photo(0, 0, 50, 60)
                + lines(75, 26, 28, 2)
            );
        case 2: // photo right half, text left half
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 50, 60)
                + photo(50, 0, 50, 60)
                + lines(25, 26, 28, 2)
            );
        case 3: // full photo + caption card top-left
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(6, 8, 36, 18, "#e8e8e8")
                + lines(24, 13, 24, 2, "#666")
            );
        case 4: // full photo + caption card bottom-right
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(58, 34, 36, 18, "#e8e8e8")
                + lines(76, 39, 24, 2, "#666")
            );
        case 5: // full photo + translucent caption bottom-left
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(6, 38, 32, 14, "rgba(255,255,255,0.85)")
                + lines(22, 41, 20, 2, "#666")
            );
    }
    // Fallback for unexpected ids: label them numerically.
    return svg(
        bg("#f5f5f5")
        + '<text x="' + (W / 2) + '" y="' + (H / 2 + 6) +
        '" font-family="sans-serif" font-size="20" ' +
        'text-anchor="middle" fill="#888">' + id + "</text>"
    );
}

// Context for the photo currently being edited; cleared on close.
let _tplCtx = null;

function openTemplateModal(view, m) {
    const modal = document.getElementById("template-modal");
    if (!modal) return;
    _tplCtx = {
        view,
        item: m,
        aspect: view.dataset.aspect || "16x9",
        templateType: parseInt(m.template_type, 10) || 1,
        orig: parseInt(m.template_id, 10) || 0,
        sel: parseInt(m.template_id, 10) || 0,
    };

    $(".modal-meta", modal).textContent = m.filename || "(unnamed)";
    const orient = _tplCtx.templateType === 2 ? "vertical" : "horizontal";
    const orientEl = $(".tpl-orient", modal);
    orientEl.innerHTML = icon(
        orient === "vertical" ? "smartphone" : "monitor", 13);
    orientEl.appendChild(document.createTextNode(orient));

    const frame = $(".display-frame", modal);
    frame.dataset.aspect = _tplCtx.aspect;

    const spec = _templatePickerSpec(_tplCtx.aspect, _tplCtx.templateType);
    $(".template-hint", modal).textContent = spec.hint;

    const cat = templateCatalog(_tplCtx.aspect, _tplCtx.templateType);
    const grid = $(".template-grid", modal);
    grid.innerHTML = "";
    for (let i = 1; i <= spec.count; i++) {
        const meta = cat[i - 1] || {name: "Style " + i, desc: ""};
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tpl-opt template-btn" +
            (i === _tplCtx.sel ? " active" : "");
        btn.dataset.templateId = i;
        btn.innerHTML =
            '<span class="tpl-thumb' +
            (_tplCtx.aspect === "4x3" ? " aspect-4x3" : "") + '">' +
            _templatePreviewSvg(_tplCtx.aspect, i, m.url) + "</span>" +
            '<span class="tpl-opt-meta">' +
            '<span class="tpl-opt-name"></span>' +
            '<span class="tpl-opt-desc"></span></span>' +
            '<span class="tpl-radio">' + icon("check", 13) + "</span>";
        $(".tpl-opt-name", btn).textContent = meta.name;
        $(".tpl-opt-desc", btn).textContent = meta.desc;
        btn.addEventListener("click", () => {
            _tplCtx.sel = i;
            $all(".tpl-opt", grid).forEach(
                (b) => b.classList.toggle("active", b === btn));
            updateTemplatePreview();
        });
        grid.appendChild(btn);
    }

    updateTemplatePreview();
    modal.classList.add("open");
}

function updateTemplatePreview() {
    if (!_tplCtx) return;
    const modal = document.getElementById("template-modal");
    const frame = $(".display-frame", modal);
    frame.innerHTML = _templatePreviewSvg(
        _tplCtx.aspect, _tplCtx.sel || 1, _tplCtx.item.url);
    const save = $(".save-template-btn", modal);
    save.disabled = !_tplCtx.sel || _tplCtx.sel === _tplCtx.orig;
}

function closeTemplateModal() {
    const modal = document.getElementById("template-modal");
    if (modal) modal.classList.remove("open");
    _tplCtx = null;
}

async function saveTemplateModal() {
    if (!_tplCtx || !_tplCtx.sel) return;
    const ctx = _tplCtx;
    try {
        // Preserve any positionX/Y the iPad already saved; the picker
        // only changes the layout. ``display`` is a JSON string.
        const data = await postJSON("/api/ipad/media/update", {
            id: ctx.item.id,
            display: ctx.item.display || "",
            template_id: ctx.sel,
            template_type: ctx.templateType,
        });
        if (data.code !== 1) {
            toast("Failed: " + (data.msg || "?"), true);
            return;
        }
        ctx.item.template_id = ctx.sel;
        ctx.item.template_type = ctx.templateType;
        toast("Template set to “" + templateChipName(
            ctx.aspect, ctx.templateType, ctx.sel) + "”");
        renderGallery(ctx.view);
        closeTemplateModal();
    } catch (e) {
        toast("Error: " + e, true);
    }
}

/* ===================== wiring ===================== */

function wireDeviceView(view) {
    const state = getState(view.dataset.deviceId);

    // tabs
    $all(".tab", view).forEach((tab) => {
        tab.addEventListener("click", () => {
            $all(".tab", view).forEach(
                (t) => t.classList.toggle("active", t === tab));
            $all(".tab-panel", view).forEach((p) => p.classList.toggle(
                "active", p.dataset.panel === tab.dataset.tab));
        });
    });

    // photos: upload kind
    wireSeg($('[data-seg="upload-kind"]', view), (v) => {
        state.kind = v;
        const label = v === "ai" ? "AI" : "Normal";
        $all(".kind-label", view).forEach(
            (el) => { el.textContent = label; });
    });

    // photos: dropzone
    const dz = $(".dropzone", view);
    const fileInput = $('input[type="file"]', dz);
    dz.addEventListener("click", () => fileInput.click());
    dz.addEventListener("dragover", (e) => {
        e.preventDefault();
        dz.classList.add("drag");
    });
    dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
    dz.addEventListener("drop", (e) => {
        e.preventDefault();
        dz.classList.remove("drag");
        handleFiles(view, e.dataTransfer.files);
    });
    fileInput.addEventListener("change", (e) => {
        handleFiles(view, e.target.files);
        e.target.value = "";
    });

    // photos: filter + sort + delete
    wireSeg($('[data-seg="filter"]', view), (v) => {
        state.filter = v;
        renderGallery(view);
    });
    $(".photo-sort", view).addEventListener("change", (e) => {
        state.sort = e.target.value;
        loadPhotos(view);
    });
    $(".delete-selected", view).addEventListener(
        "click", () => deleteSelectedPhotos(view));

    // clock
    wireSeg($('[data-seg="clock-format"]', view));
    wireStyleGrid($('[data-style-grid="clock"]', view));
    $(".clock-save", view).addEventListener(
        "click", () => saveClock(view));

    // weather
    wireSeg($('[data-seg="unit"]', view));
    wireStyleGrid($('[data-style-grid="weather"]', view));
    $(".city-search-btn", view).addEventListener(
        "click", () => searchCity(view));
    $(".city-query", view).addEventListener("keydown", (e) => {
        if (e.key === "Enter") searchCity(view);
    });
    $(".weather-save", view).addEventListener(
        "click", () => saveWeather(view));

    // playback
    wireSeg($('[data-seg="playback-mode"]', view),
        () => renderPlaybackMode(view));
    $all(".module-row input", view).forEach((box) => {
        box.addEventListener(
            "change", () => renderPlaybackModuleCount(view));
    });
    $(".rule-add-btn", view).addEventListener(
        "click", () => submitRule(view));
    $(".rule-cancel-btn", view).addEventListener("click", () => {
        resetRuleForm(view);
        renderPlaybackRules(view);
    });
    $(".playback-save", view).addEventListener(
        "click", () => savePlayback(view));

    // calendars
    $(".cal-add-btn", view).addEventListener(
        "click", () => addCalendar(view));
    $(".cal-url-input", view).addEventListener("keydown", (e) => {
        if (e.key === "Enter") addCalendar(view);
    });

    // remove device (inline confirm step, as designed)
    const removeBtn = $(".delete-device-btn", view);
    const confirmRow = $(".confirm-row", view);
    removeBtn.addEventListener("click", () => {
        removeBtn.hidden = true;
        confirmRow.hidden = false;
    });
    $(".confirm-cancel", view).addEventListener("click", () => {
        confirmRow.hidden = true;
        removeBtn.hidden = false;
    });
    $(".confirm-yes", view).addEventListener(
        "click", () => deleteDevice(view));
}

(function init() {
    // sidebar navigation
    $all(".nav-item, .device-row").forEach((btn) => {
        btn.addEventListener("click", () => showView(btn.dataset.view));
    });
    $("#device-search").addEventListener(
        "input", (e) => filterDevices(e.target.value));

    // mobile drawer
    $("#drawer-open").addEventListener("click", openDrawer);
    $("#drawer-scrim").addEventListener("click", closeDrawer);

    // device views
    $all(".device-view").forEach(wireDeviceView);

    // lightbox
    const lb = document.getElementById("lightbox");
    lb.addEventListener("click", closeLightbox);
    $(".lb-close", lb).addEventListener("click", closeLightbox);

    // template modal
    const modal = document.getElementById("template-modal");
    $(".close", modal).addEventListener("click", closeTemplateModal);
    $(".cancel-btn", modal).addEventListener("click", closeTemplateModal);
    $(".save-template-btn", modal).addEventListener(
        "click", saveTemplateModal);
    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeTemplateModal();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (modal.classList.contains("open")) closeTemplateModal();
        else if (lb.classList.contains("open")) closeLightbox();
    });

    // 10s background refresh: charger rows (tbody swap) + display-device
    // presence indicators. Only those nodes are touched, so any open
    // device view and in-flight form keep their state. The topbar pill
    // toggles the whole refresh on/off.
    updateChargersSub();
    setInterval(() => {
        if (!liveRefresh) return;
        refreshChargers();
        refreshDeviceStatus();
    }, 10000);
    const liveToggle = document.getElementById("live-toggle");
    if (liveToggle) {
        liveToggle.addEventListener("click",
            () => setLiveRefresh(!liveRefresh));
    }

    // initial view: deep-link via #device-<id>, else chargers
    const hash = (location.hash || "").replace(/^#/, "");
    showView(hash && document.getElementById("view-" + hash)
        ? hash : "chargers");
    window.addEventListener("hashchange", () => {
        const h = (location.hash || "").replace(/^#/, "");
        if (h && document.getElementById("view-" + h)) showView(h);
    });
})();
