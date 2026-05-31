// Background refresh of the chargers table.  Replaces the previous
// full-page reload so any open settings card keeps its state.
async function refreshChargers() {
    try {
        const r = await fetch("/admin/chargers");
        const rowsHtml = await r.text();
        const tbody = document.getElementById("chargers-tbody");
        if (tbody) tbody.innerHTML = rowsHtml;
    } catch {}
}

// Charger toggle (existing behavior)
async function toggle(uuid, on) {
    const statusEl = document.getElementById("status");
    statusEl.textContent = `${on ? "Enabling" : "Disabling"} charging...`;
    statusEl.className = "status";
    try {
        const r = await fetch("/admin/toggle", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uuid, charging_on: on}),
        });
        const data = await r.json();
        if (data.code === 1) {
            statusEl.textContent =
                `Command sent: charging ${on ? "enabled" : "disabled"}`;
            statusEl.className = "status ok";
            refreshChargers();
        } else {
            statusEl.textContent = `Error: ${data.msg || "unknown"}`;
            statusEl.className = "status error";
        }
    } catch (err) {
        statusEl.textContent = `Request failed: ${err}`;
        statusEl.className = "status error";
    }
}

// Charger mode switch (auto <-> manual)
async function setMode(uuid, mode) {
    const statusEl = document.getElementById("status");
    statusEl.textContent = `Switching charger to ${mode} mode...`;
    statusEl.className = "status";
    try {
        const r = await fetch("/admin/set-mode", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({uuid, mode}),
        });
        const data = await r.json();
        if (data.code === 1) {
            statusEl.textContent = `Charger switched to ${mode} mode`;
            statusEl.className = "status ok";
            refreshChargers();
        } else {
            statusEl.textContent = `Error: ${data.msg || "unknown"}`;
            statusEl.className = "status error";
        }
    } catch (err) {
        statusEl.textContent = `Request failed: ${err}`;
        statusEl.className = "status error";
    }
}

// --- Display-device settings ---

function setStatus(card, form, msg, cls) {
    const el = card.querySelector(`.subform[data-form="${form}"] .status`);
    if (el) {
        el.textContent = msg;
        el.className = `status ${cls || ""}`;
    }
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

// Flip clock (screensaver)
async function loadClock(card) {
    const deviceId = card.dataset.deviceId;
    try {
        const data = await getJSON(
            `/api/ipad/device/setting/screensaver?id=${deviceId}`);
        const cur = (data && data.data) || {};
        const no = (cur.no != null) ? parseInt(cur.no, 10) : 1;
        const time = (cur.time != null) ? parseInt(cur.time, 10) : 1;
        const styleRadio = card.querySelector(
            `.subform[data-form="clock"] input[name="clock-style-${deviceId}"]` +
            `[value="${no}"]`);
        if (styleRadio) styleRadio.checked = true;
        const fmtRadio = card.querySelector(
            `.subform[data-form="clock"] input[name="clock-${deviceId}"]` +
            `[value="${time}"]`);
        if (fmtRadio) fmtRadio.checked = true;
    } catch {}
}

async function saveClock(card) {
    const deviceId = card.dataset.deviceId;
    const styleChecked = card.querySelector(
        `.subform[data-form="clock"] input[name="clock-style-${deviceId}"]:checked`);
    const formatChecked = card.querySelector(
        `.subform[data-form="clock"] input[name="clock-${deviceId}"]:checked`);
    if (!styleChecked) {
        setStatus(card, "clock", "Pick a flip-clock style (1-5)", "error");
        return;
    }
    if (!formatChecked) {
        setStatus(card, "clock", "Select 12h or 24h", "error");
        return;
    }
    setStatus(card, "clock", "Saving...", "");
    try {
        const data = await postJSON("/api/ipad/device/setting/screensaver", {
            id: parseInt(deviceId, 10),
            values: {
                no: parseInt(styleChecked.value, 10),
                time: parseInt(formatChecked.value, 10),
            },
        });
        if (data.code === 1) setStatus(card, "clock", "Saved", "ok");
        else setStatus(card, "clock", `Failed: ${data.msg || "?"}`, "error");
    } catch (e) {
        setStatus(card, "clock", `Error: ${e}`, "error");
    }
}

// Weather
async function loadWeather(card) {
    const deviceId = card.dataset.deviceId;
    try {
        const data = await getJSON(
            `/api/ipad/device/setting/weather?id=${deviceId}`);
        const cur = (data && data.data) || {};
        const sub = card.querySelector('.subform[data-form="weather"]');
        if (!sub) return;
        if (cur.city) {
            sub.querySelector(".current-city").textContent =
                `Current: ${cur.city}`;
            const cm = cur.cityMsg || {};
            card.dataset.cityId = cm.id || "";
            card.dataset.cityName = cur.city;
            card.dataset.cityLat = cm.lat || "";
            card.dataset.cityLon = cm.lon || "";
        }
        const unit = cur.unit || 1;
        const unitRadio = sub.querySelector(
            `input[type="radio"][name="unit-${card.dataset.deviceId}"]` +
            `[value="${unit}"]`);
        if (unitRadio) unitRadio.checked = true;
        // weather_template_id is 0-based (0..3) to match the iFramix
        // 2.2.29 webapp catalog. Use ?? so a saved 0 stays 0 instead of
        // falling back to "no row" semantics.
        const styleId = (cur.weather_template_id != null)
            ? cur.weather_template_id : 0;
        const styleRadio = sub.querySelector(
            `input[type="radio"][name="weather-style-${card.dataset.deviceId}"]` +
            `[value="${styleId}"]`);
        if (styleRadio) styleRadio.checked = true;
    } catch {}
}

async function searchCity(card) {
    const sub = card.querySelector('.subform[data-form="weather"]');
    const kw = sub.querySelector("input.city-query").value.trim();
    if (!kw) return;
    setStatus(card, "weather", "Searching...", "");
    try {
        const data = await getJSON(
            `/api/ipad/address/city?keyword=${encodeURIComponent(kw)}&lang=en`);
        const list = sub.querySelector(".city-results");
        list.innerHTML = "";
        const results = Array.isArray(data.data) ? data.data : [];
        if (!results.length) {
            setStatus(card, "weather", "No results", "error");
            return;
        }
        for (const city of results) {
            const opt = document.createElement("div");
            opt.className = "city-opt";
            const parts = [city.name];
            if (city.adm1 && city.adm1 !== city.name) parts.push(city.adm1);
            if (city.country) parts.push(city.country);
            opt.textContent = parts.filter(Boolean).join(", ");
            opt.addEventListener("click", () => {
                card.dataset.cityId = city.city_id || city.id || "";
                card.dataset.cityName = city.name || "";
                card.dataset.cityLat = city.lat || "";
                card.dataset.cityLon = city.lon || "";
                sub.querySelector(".current-city").textContent =
                    `Selected: ${opt.textContent}`;
                list.innerHTML = "";
            });
            list.appendChild(opt);
        }
        setStatus(card, "weather", `${results.length} result(s)`, "ok");
    } catch (e) {
        setStatus(card, "weather", `Search error: ${e}`, "error");
    }
}

async function saveWeather(card) {
    const deviceId = card.dataset.deviceId;
    const sub = card.querySelector('.subform[data-form="weather"]');
    const cityId = card.dataset.cityId || "";
    const cityName = card.dataset.cityName || "";
    if (!cityId) {
        setStatus(card, "weather",
            "Search and select a city first", "error");
        return;
    }
    const unitChecked = sub.querySelector(
        `input[type="radio"][name="unit-${deviceId}"]:checked`);
    const unit = unitChecked ? parseInt(unitChecked.value, 10) : 1;
    const styleChecked = sub.querySelector(
        `input[type="radio"][name="weather-style-${deviceId}"]:checked`);
    const weatherTemplateId = styleChecked
        ? parseInt(styleChecked.value, 10) : 0;
    setStatus(card, "weather", "Saving...", "");
    try {
        const data = await postJSON("/api/ipad/device/setting/weather", {
            id: parseInt(deviceId, 10),
            values: {
                city: cityName,
                cityMsg: {
                    id: cityId,
                    name: cityName,
                    lat: card.dataset.cityLat || "",
                    lon: card.dataset.cityLon || "",
                },
                unit,
                weather_template_id: weatherTemplateId,
            },
        });
        if (data.code === 1) setStatus(card, "weather", "Saved", "ok");
        else setStatus(card, "weather", `Failed: ${data.msg || "?"}`, "error");
    } catch (e) {
        setStatus(card, "weather", `Error: ${e}`, "error");
    }
}

// Calendar
async function loadCalendars(card) {
    const deviceId = card.dataset.deviceId;
    try {
        const data = await getJSON(
            `/api/calendar/index?device_id=${deviceId}`);
        const list = card.querySelector(
            '.subform[data-form="calendar"] .cal-list');
        if (!list) return;
        list.innerHTML = "";
        const items = (data && data.data && data.data.list) || [];
        if (!items.length) {
            const empty = document.createElement("li");
            empty.className = "empty";
            empty.textContent = "No calendars linked";
            list.appendChild(empty);
            return;
        }
        for (const cal of items) {
            const li = document.createElement("li");
            const meta = document.createElement("div");
            meta.textContent =
                `${cal.name || "(no name)"} — ${cal.driver || ""}`;
            const del = document.createElement("button");
            del.className = "btn off tiny";
            del.textContent = "Delete";
            del.addEventListener("click", () => deleteCalendar(card, cal.id));
            li.appendChild(meta);
            li.appendChild(del);
            list.appendChild(li);
        }
    } catch {}
}

async function linkCalendar(card) {
    const deviceId = card.dataset.deviceId;
    const sub = card.querySelector('.subform[data-form="calendar"]');
    const driver = sub.querySelector("select.cal-driver").value;
    let name = sub.querySelector("input.cal-name").value.trim();
    const url = sub.querySelector("input.cal-url").value.trim();
    if (!url) {
        setStatus(card, "calendar", "URL is required", "error");
        return;
    }
    if (!name) name = driver.charAt(0).toUpperCase() + driver.slice(1);
    setStatus(card, "calendar", "Linking...", "");
    try {
        const data = await postJSON("/api/calendar/external/link", {
            url,
            device_id: parseInt(deviceId, 10),
            name,
            driver,
        });
        if (data.code === 1) {
            setStatus(card, "calendar", "Linked", "ok");
            sub.querySelector("input.cal-url").value = "";
            sub.querySelector("input.cal-name").value = "";
            loadCalendars(card);
        } else {
            setStatus(card, "calendar",
                `Failed: ${data.msg || "?"}`, "error");
        }
    } catch (e) {
        setStatus(card, "calendar", `Error: ${e}`, "error");
    }
}

async function deleteCalendar(card, calId) {
    try {
        const data = await postJSON("/api/calendar/delete", {id: calId});
        if (data.code === 1) {
            setStatus(card, "calendar", "Deleted", "ok");
            loadCalendars(card);
        } else {
            setStatus(card, "calendar",
                `Delete failed: ${data.msg || "?"}`, "error");
        }
    } catch (e) {
        setStatus(card, "calendar", `Delete error: ${e}`, "error");
    }
}

// Photo listing (per type), paginated. Photos are fetched a page at a
// time from the lightweight /admin/photos endpoint and rendered as
// lazy-loading thumbnails (served downscaled + long-cached from
// /admin/thumb), so opening a card with hundreds of photos no longer
// downloads every full-resolution image up front. For AI photos the
// thumbnail is clickable and opens the template-picker modal.
const PHOTO_PAGE_SIZE = 24;

function loadPhotos(card) {
    const deviceId = card.dataset.deviceId;
    for (const type of ["normal", "ai"]) {
        const grid = card.querySelector(
            `.photo-grid[data-photo-type="${type}"]`);
        const count = card.querySelector(
            `.ps-count[data-photo-type="${type}"]`);
        if (!grid) continue;
        // Fresh load: page 1, replacing whatever was there.
        loadPhotoPage(deviceId, type, grid, count, 1, false);
    }
}

async function loadPhotoPage(deviceId, type, grid, count, page, append) {
    try {
        const data = await getJSON(
            `/admin/photos?device_id=${deviceId}&type=${type}` +
            `&page=${page}&page_size=${PHOTO_PAGE_SIZE}`);
        const d = (data && data.data) || {};
        const items = d.list || [];
        const total = d.total || 0;
        if (!append) grid.innerHTML = "";
        for (const m of items) {
            grid.appendChild(buildThumb(type, m));
        }
        grid.dataset.page = page;
        grid.dataset.total = total;
        if (count) count.textContent = total;
        updateLoadMore(grid, deviceId, type, count, total);
        updateDeleteButton(grid);
    } catch {}
}

function buildThumb(type, m) {
    const el = document.createElement("div");
    el.className = `photo-thumb${type === "ai" ? " ai" : ""}`;
    el.title = `${m.filename || ""} (id ${m.id})`;
    // Every thumbnail carries its media id so a bulk delMedia can
    // collect the checked ones regardless of normal/AI type.
    el.dataset.mediaId = m.id;

    const img = document.createElement("img");
    img.className = "thumb-img";
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = m.filename || "";
    img.src = m.thumb_url;
    el.appendChild(img);

    if (type === "ai") {
        // The modal preview uses the full-resolution image; the grid tile
        // uses the cheap thumbnail above.
        el.dataset.url = m.url;
        el.dataset.filename = m.filename || "";
        el.dataset.templateId = m.template_id || 0;
        el.dataset.templateType = m.template_type || 1;
        el.dataset.display = m.display || "";
        el.addEventListener("click", () => openTemplateModal(el));
    }
    // Selection checkbox for bulk delete. stopPropagation keeps a click on
    // the checkbox from also opening the AI template modal.
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "photo-select";
    cb.title = "Select for deletion";
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
        el.classList.toggle("selected", cb.checked);
        updateDeleteButton(el.closest(".photo-grid"));
    });
    el.appendChild(cb);
    return el;
}

// Render (or clear) the "Load more" control beneath a grid based on how
// many of the total photos are currently loaded.
function updateLoadMore(grid, deviceId, type, count, total) {
    const section = grid.closest(".photo-section");
    if (!section) return;
    const more = section.querySelector(
        `.photo-more[data-photo-type="${type}"]`);
    if (!more) return;
    const loaded = grid.querySelectorAll(".photo-thumb").length;
    more.innerHTML = "";
    if (loaded < total) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn neutral tiny load-more-btn";
        btn.textContent = `Load more (${loaded} of ${total})`;
        btn.addEventListener("click", () => {
            const next = (parseInt(grid.dataset.page, 10) || 1) + 1;
            btn.disabled = true;
            btn.textContent = "Loading...";
            loadPhotoPage(deviceId, type, grid, count, next, true);
        });
        more.appendChild(btn);
    } else if (total > PHOTO_PAGE_SIZE) {
        const note = document.createElement("span");
        note.className = "photo-more-note";
        note.textContent = `All ${total} shown`;
        more.appendChild(note);
    }
}

// Reflect the number of checked thumbnails on the section's
// "Delete selected (N)" button and enable/disable it accordingly.
function updateDeleteButton(grid) {
    const section = grid.closest(".photo-section");
    if (!section) return;
    const btn = section.querySelector(".photo-del-btn");
    if (!btn) return;
    const n = grid.querySelectorAll("input.photo-select:checked").length;
    btn.disabled = n === 0;
    btn.textContent = `Delete selected (${n})`;
}

// Bulk-delete the checked photos of one type via the same delMedia
// endpoint / MQTT event the display app uses when removing photos.
async function deleteSelectedPhotos(card, type) {
    const deviceId = card.dataset.deviceId;
    const grid = card.querySelector(
        `.photo-grid[data-photo-type="${type}"]`);
    if (!grid) return;
    const ids = Array.from(
        grid.querySelectorAll("input.photo-select:checked"))
        .map((cb) => cb.closest(".photo-thumb").dataset.mediaId)
        .filter(Boolean);
    if (!ids.length) return;
    if (!confirm(
        `Delete ${ids.length} ${type} photo(s)? This cannot be undone.`)) {
        return;
    }
    setStatus(card, "upload", `Deleting ${ids.length} photo(s)...`, "");
    try {
        const data = await postJSON("/api/ipad/media/delMedia", {
            id: ids,
            device_id: parseInt(deviceId, 10),
        });
        if (data.code === 1) {
            setStatus(card, "upload",
                `Deleted ${ids.length} photo(s)`, "ok");
            // delMedia removes files in a background thread, so give it a
            // moment before re-reading the (now shorter) list.
            setTimeout(() => loadPhotos(card), 500);
        } else {
            setStatus(card, "upload",
                `Delete failed: ${data.msg || "?"}`, "error");
        }
    } catch (e) {
        setStatus(card, "upload", `Delete error: ${e}`, "error");
    }
}

// --- Template-picker modal ---
//
// Stores the photo currently being edited so the Save button knows which
// /api/ipad/media/update payload to post. Cleared on close.
let _templateModalCtx = null;

// Maps the display device's aspect plus the photo's saved orientation
// to (button count, hint text). The catalog sizes match the iPad
// webapp's catalogs at runtime so any pick the admin makes is a value
// the iPad can actually render:
//   * 4:3 displays use the inline-injected 10-template ``pq``/``mq``
//     catalogs regardless of orientation, so we always show 10.
//   * 16:9 displays use static CSS classes ``mcol_1..5`` (horizontal,
//     5 templates) or ``mrow_1..4`` (vertical, 4 templates).
// Returns an SVG markup for a template preview button. The SVG mimics
// the actual layout the iPad webapp will render when this template_id
// is saved on the matching aspect ratio. ``preview-text-bg`` rects pick
// up a blue tint when the button is selected (see the
// ``.template-btn.selected svg .preview-text-bg`` CSS rule).
//
// Colors:
//   * #9e9e9e — image area
//   * #e0e0e0 — text panel background (gets tinted on selection)
//   * #888    — title/desc lines
//   * #cfcfcf — overlay box background on dark image
function _templatePreviewSvg(aspect, id) {
    const bg = (color) => `<rect width="100" height="60" fill="${color}"/>`;
    const img = (x, y, w, h) =>
        `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#9e9e9e"/>`;
    const panel = (x, y, w, h, cls) =>
        `<rect class="${cls}" x="${x}" y="${y}" width="${w}" height="${h}" fill="#e0e0e0"/>`;
    const box = (x, y, w, h, fill) =>
        `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${fill}" stroke="#bbb" stroke-width="0.5"/>`;
    const lines = (cx, y, w, count, color = "#888") => {
        let s = "";
        for (let i = 0; i < count; i++) {
            const lw = w * (1 - i * 0.18);
            s += `<rect x="${cx - lw / 2}" y="${y + i * 5}" width="${lw}" height="2" rx="1" fill="${color}"/>`;
        }
        return s;
    };
    const svg = (body) =>
        `<svg viewBox="0 0 100 60" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;

    if (aspect === "4x3") {
        // Mirror the 10 entries in the webapp's ``pq`` catalog.
        switch (id) {
            case 1: // Left Bookend: 25% sidebar left, 75% image right, gradient text-box at bottom
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 25, 60, "preview-text-bg")
                    + img(25, 0, 75, 60)
                    + '<rect x="25" y="44" width="75" height="16" fill="rgba(0,0,0,0.45)"/>'
                    + lines(62, 50, 40, 2, "#fff")
                    + lines(8, 28, 14, 2, "#999")
                );
            case 2: // Split Canvas: 40% text left, 60% image right
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 40, 60, "preview-text-bg")
                    + img(40, 0, 60, 60)
                    + lines(20, 28, 26, 2, "#888")
                );
            case 3: // Corner Cut: full-width image with diagonal clip + text bottom
                return svg(
                    bg("#f5f5f5")
                    + '<polygon points="0,0 100,0 100,30 0,40" fill="#9e9e9e"/>'
                    + lines(50, 47, 50, 2, "#888")
                );
            case 4: // Asymmetric Base: image 72%, text bar bottom
                return svg(
                    bg("#f5f5f5")
                    + img(0, 0, 100, 43)
                    + lines(30, 50, 30, 2, "#888")
                    + lines(70, 50, 24, 2, "#888")
                );
            case 5: // Cross Boundary: image 75% top + cross block
                return svg(
                    bg("#f5f5f5")
                    + img(0, 0, 100, 45)
                    + '<rect x="55" y="32" width="35" height="18" fill="#5a5a5a"/>'
                    + lines(20, 53, 22, 1, "#888")
                );
            case 6: // Dark Card: full image + dark text card
                return svg(
                    bg("#9e9e9e")
                    + '<rect x="20" y="38" width="60" height="14" rx="2" fill="#333"/>'
                    + lines(50, 42, 36, 2, "#cfcfcf")
                );
            case 7: // Side Arch: 38% text left, 62% image right with arch
                return svg(
                    bg("#f5f5f5")
                    + panel(0, 0, 38, 60, "preview-text-bg")
                    + '<path d="M 38,0 L 100,0 L 100,60 L 38,60 Q 18,30 38,0 Z" fill="#9e9e9e"/>'
                    + lines(19, 28, 22, 2, "#888")
                );
            case 8: // Legacy Top Cover: image top 75%, text strip bottom centered
                return svg(
                    bg("#f5f5f5")
                    + img(0, 0, 100, 45)
                    + lines(50, 51, 50, 2, "#888")
                );
            case 9: // Legacy Bottom Left: image top 75%, text bottom-left
                return svg(
                    bg("#f5f5f5")
                    + img(0, 0, 100, 45)
                    + lines(20, 51, 28, 2, "#888")
                );
            case 10: // Legacy Side Ribbon: image left 75%, text right ribbon
                return svg(
                    bg("#f5f5f5")
                    + img(0, 0, 75, 60)
                    + panel(75, 0, 25, 60, "preview-text-bg")
                    + lines(87, 18, 16, 4, "#888")
                );
        }
    }

    // 16:9 catalog. mcol_1..5 (horizontal) and mrow_1..4 (vertical) end
    // up with the same visual split logic per the override block in
    // webapp/index.html: split layout for 1/2, full-image overlay for
    // 3/4/5. mrow has 4 entries; we reuse the first four designs.
    switch (id) {
        case 1: // mcol_1: image left half, text right half
            return svg(
                bg("#f5f5f5")
                + panel(50, 0, 50, 60, "preview-text-bg")
                + img(0, 0, 50, 60)
                + lines(75, 26, 28, 2, "#888")
            );
        case 2: // mcol_2: image right half, text left half
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 50, 60, "preview-text-bg")
                + img(50, 0, 50, 60)
                + lines(25, 26, 28, 2, "#888")
            );
        case 3: // mcol_3: full image + text overlay top-left (with our override)
            return svg(
                bg("#9e9e9e")
                + box(6, 8, 36, 18, "#e8e8e8")
                + lines(24, 13, 24, 2, "#666")
            );
        case 4: // mcol_4: full image + text overlay bottom-right (with our override)
            return svg(
                bg("#9e9e9e")
                + box(58, 34, 36, 18, "#e8e8e8")
                + lines(76, 39, 24, 2, "#666")
            );
        case 5: // mcol_5: full image + small text overlay bottom-left (translucent)
            return svg(
                bg("#9e9e9e")
                + box(6, 38, 32, 14, "rgba(255,255,255,0.85)")
                + lines(22, 41, 20, 2, "#666")
            );
    }
    // Fallback for unexpected ids: just label them numerically.
    return svg(
        bg("#f5f5f5")
        + `<text x="50" y="36" font-family="sans-serif" font-size="20" text-anchor="middle" fill="#888">${id}</text>`
    );
}

function _templatePickerSpec(aspect, templateType) {
    if (aspect === "4x3") {
        return {
            count: 10,
            hint: `Image has a ${templateType === 2 ? "vertical" : "horizontal"}` +
                ` layout. Ten styles available for 4:3 displays.`,
        };
    }
    if (templateType === 2) {
        return {
            count: 4,
            hint: "Image has a vertical layout. Four styles available for 16:9 displays.",
        };
    }
    return {
        count: 5,
        hint: "Image has a horizontal layout. Five styles available for 16:9 displays.",
    };
}

function openTemplateModal(thumb) {
    const modal = document.getElementById("template-modal");
    if (!modal) return;
    const card = thumb.closest(".card");
    _templateModalCtx = {
        card,
        thumb,
        mediaId: thumb.dataset.mediaId,
        url: thumb.dataset.url,
        filename: thumb.dataset.filename,
        display: thumb.dataset.display || "",
        templateId: parseInt(thumb.dataset.templateId, 10) || 0,
        templateType: parseInt(thumb.dataset.templateType, 10) || 1,
        aspect: (card && card.dataset.aspect) || "16x9",
    };

    modal.querySelector(".modal-preview").style.backgroundImage =
        `url("${_templateModalCtx.url.replace(/"/g, "%22")}")`;
    modal.querySelector(".modal-meta").textContent =
        `${_templateModalCtx.filename || "(unnamed)"}  ·  id ${_templateModalCtx.mediaId}`;

    const spec = _templatePickerSpec(
        _templateModalCtx.aspect, _templateModalCtx.templateType);
    const grid = modal.querySelector(".template-grid");
    // Grid is always 5 columns; for 4:3 (10 templates) the second row
    // wraps automatically. The buttons keep a 16:9 aspect ratio so
    // every preview reads the same regardless of how many there are.
    grid.innerHTML = "";
    for (let i = 1; i <= spec.count; i++) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "template-btn";
        btn.dataset.templateId = i;
        btn.title = `Style ${i}`;
        btn.innerHTML = _templatePreviewSvg(_templateModalCtx.aspect, i);
        if (i === _templateModalCtx.templateId) btn.classList.add("selected");
        btn.addEventListener("click", (e) => {
            for (const b of grid.querySelectorAll(".template-btn")) {
                b.classList.remove("selected");
            }
            e.currentTarget.classList.add("selected");
            _templateModalCtx.templateId =
                parseInt(e.currentTarget.dataset.templateId, 10);
        });
        grid.appendChild(btn);
    }

    const hintEl = modal.querySelector(".template-hint");
    if (hintEl) hintEl.textContent = spec.hint;

    modal.querySelector(".modal .status").textContent = "";
    modal.querySelector(".modal .status").className = "status";
    modal.classList.add("open");
}

function closeTemplateModal() {
    const modal = document.getElementById("template-modal");
    if (modal) modal.classList.remove("open");
    _templateModalCtx = null;
}

async function saveTemplateModal() {
    if (!_templateModalCtx) return;
    const modal = document.getElementById("template-modal");
    const statusEl = modal.querySelector(".modal .status");
    if (!_templateModalCtx.templateId || _templateModalCtx.templateId < 1) {
        statusEl.textContent = "Pick a style first";
        statusEl.className = "status error";
        return;
    }
    statusEl.textContent = "Saving...";
    statusEl.className = "status";
    // Preserve any positionX/Y the iPad already saved; the picker only
    // changes the layout. ``display`` is a JSON string when present.
    const display = _templateModalCtx.display || "";
    try {
        const data = await postJSON("/api/ipad/media/update", {
            id: _templateModalCtx.mediaId,
            display,
            template_id: _templateModalCtx.templateId,
            template_type: _templateModalCtx.templateType,
        });
        if (data.code !== 1) {
            statusEl.textContent = `Failed: ${data.msg || "?"}`;
            statusEl.className = "status error";
            return;
        }
        // Reflect the new value on the thumbnail so a follow-up open
        // shows the new selection without a fresh mediaList round-trip.
        if (_templateModalCtx.thumb) {
            _templateModalCtx.thumb.dataset.templateId =
                _templateModalCtx.templateId;
            _templateModalCtx.thumb.dataset.templateType =
                _templateModalCtx.templateType;
        }
        statusEl.textContent = "Saved";
        statusEl.className = "status ok";
        setTimeout(closeTemplateModal, 600);
    } catch (e) {
        statusEl.textContent = `Error: ${e}`;
        statusEl.className = "status error";
    }
}

// Photo upload
async function uploadPhotos(card) {
    const deviceId = card.dataset.deviceId;
    const sub = card.querySelector('.subform[data-form="upload"]');
    const input = sub.querySelector('input[type="file"]');
    if (!input.files.length) {
        setStatus(card, "upload", "No files selected", "error");
        return;
    }
    const files = Array.from(input.files);
    const typeRadio = sub.querySelector(
        'input[type="radio"][name^="upload-type-"]:checked');
    const uploadType = typeRadio ? typeRadio.value : "normal";

    // Upload sequentially (one file at a time) to avoid overwhelming the
    // server when many photos are selected. Mirrors how the native app
    // uploads photos one by one.
    const assetIds = [];
    try {
        for (const [idx, file] of files.entries()) {
            setStatus(card, "upload",
                `Uploading ${idx + 1}/${files.length} as ${uploadType}...`, "");
            const fd = new FormData();
            fd.append("file", file);
            fd.append("key", file.name);
            const suffix = (file.name.split(".").pop() || "jpg").toLowerCase();
            fd.append("x:suffix", suffix);
            const r = await fetch("/api/user/asset/upload",
                {method: "POST", body: fd});
            const data = await r.json();
            if (data && data.code === 1 && data.data && data.data.id) {
                assetIds.push(data.data.id);
            } else {
                throw new Error(`upload rejected for ${file.name}`);
            }
        }
        const data = await postJSON("/api/ipad/media/setMedia", {
            device_id: parseInt(deviceId, 10),
            asset_ids: assetIds,
            type: uploadType,
        });
        if (data.code === 1) {
            setStatus(card, "upload",
                `Uploaded ${assetIds.length} photo(s)`, "ok");
            input.value = "";
            loadPhotos(card);
        } else {
            setStatus(card, "upload",
                `setMedia failed: ${data.msg || "?"}`, "error");
        }
    } catch (e) {
        setStatus(card, "upload", `Upload failed: ${e}`, "error");
    }
}

// Wire up after DOM is ready
// Wire up after DOM is ready
document.querySelectorAll(".card").forEach(function(card) {
    var head = card.querySelector(".card-head");
    head.addEventListener("click", function() {
        card.classList.toggle("open");
        if (card.classList.contains("open") && !card.dataset.loaded) {
            card.dataset.loaded = "1";
            loadClock(card);
            loadWeather(card);
            loadCalendars(card);
            loadPhotos(card);
        }
    });

    var uploadBtn = card.querySelector(
      '.subform[data-form="upload"] .upload-btn');
    if (uploadBtn) uploadBtn.addEventListener(
      "click", function() { uploadPhotos(card); });

    var clockBtn = card.querySelector(
      '.subform[data-form="clock"] .save-btn');
    if (clockBtn) clockBtn.addEventListener(
      "click", function() { saveClock(card); });

    var weatherSearchBtn = card.querySelector(
      '.subform[data-form="weather"] .search-btn');
    if (weatherSearchBtn) weatherSearchBtn.addEventListener(
      "click", function() { searchCity(card); });

    var weatherSaveBtn = card.querySelector(
      '.subform[data-form="weather"] .save-btn');
    if (weatherSaveBtn) weatherSaveBtn.addEventListener(
      "click", function() { saveWeather(card); });

    var calBtn = card.querySelector(
      '.subform[data-form="calendar"] .link-btn');
    if (calBtn) calBtn.addEventListener(
      "click", function() { linkCalendar(card); });

    var delBtn = card.querySelector(
      '.subform[data-form="delete"] .delete-btn');
    if (delBtn) delBtn.addEventListener(
      "click", function() { deleteDevice(card); });

    card.querySelectorAll('.photo-del-btn').forEach(function(btn) {
        btn.addEventListener("click", function() {
            deleteSelectedPhotos(card, btn.dataset.photoType);
        });
    });
});

function deleteDevice(card) {
    var deviceId = card.dataset.deviceId;
    var name = (card.querySelector(".card-head .name") || {}).textContent ||
      ("Device " + deviceId);
    if (!confirm(
      "Delete \"" + name + "\" and all its data?\n\n" +
      "This removes the session, charger binding, calendars, AI " +
      "album config, photo settings, and the photos/, " +
      "photos_with_ai/ and logs/ directories. It cannot be undone."
    )) {
        return;
    }
    setStatus(card, "delete", "Deleting...", "");
    postJSON("/api/ipad/device/unbindUser", {id: parseInt(deviceId, 10)})
      .then(function(data) {
          if (data.code === 1) {
              setStatus(card, "delete", "Deleted", "ok");
              card.parentNode.removeChild(card);
          } else {
              setStatus(card, "delete",
                "Failed: " + (data.msg || "?"), "error");
          }
      })
      .catch(function(e) {
          setStatus(card, "delete", "Error: " + e, "error");
      });
}

// Wire up the template-picker modal once the DOM is ready.
(() => {
    const modal = document.getElementById("template-modal");
    if (!modal) return;
    modal.querySelector(".close").addEventListener(
        "click", closeTemplateModal);
    modal.querySelector(".cancel-btn").addEventListener(
        "click", closeTemplateModal);
    modal.querySelector(".save-template-btn").addEventListener(
        "click", saveTemplateModal);
    // Click on the dim backdrop (but not the modal itself) closes it.
    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeTemplateModal();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal.classList.contains("open")) {
            closeTemplateModal();
        }
    });
})();

// Background-refresh the chargers table every 10s.  Runs regardless of
// whether a settings card is open — only the table body is replaced, so
// open cards and their in-flight forms are preserved.
setInterval(refreshChargers, 10000);
