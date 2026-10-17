// Photos tab: paginated gallery (All / Normal / Gallery Mode filter,
// sort, load more) and bulk delete.

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
                state.filter === "ai" ? "Gallery Mode " : "normal ") +
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
        badge.textContent = "Gallery Mode"
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
            view.dataset.aspect, displayTemplateType(view),
            m.template_id || 0, parseInt(m.template_type, 10) || 0);
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
