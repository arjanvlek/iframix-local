// Gallery Mode template picker modal: live preview + option list,
// saved via /api/ipad/media/update.

// Context for the photo currently being edited; cleared on close.
let _tplCtx = null;

function openTemplateModal(view, m) {
    const modal = document.getElementById("template-modal");
    if (!modal) return;
    // The catalog and the saved template_type follow the DISPLAY
    // orientation (see the catalog comment above). A template_id that
    // was stored for the other orientation is ignored by the display,
    // so it is not treated as the current selection either.
    // A clamped id (beyond the catalog) preselects the style the display
    // really shows; ``orig`` keeps the stored id so Apply is enabled and
    // one click normalises the row. Rows are never rewritten silently.
    const displayType = displayTemplateType(view);
    const aspect = view.dataset.aspect || "16x9";
    const storedType = parseInt(m.template_type, 10) || 0;
    const rawId = parseInt(m.template_id, 10) || 0;
    const effect = templateEffect(aspect, displayType, rawId, storedType);
    const storedId = effect.kind === "mismatch" ? 0 : rawId;
    const selId = effect.kind === "clamped" ? effect.shows : storedId;
    _tplCtx = {
        view,
        item: m,
        aspect,
        templateType: displayType,
        orig: storedId,
        sel: selId,
        legacy: legacy4x3Catalog(),
    };

    $(".modal-meta", modal).textContent = m.filename || "(unnamed)";
    const orient = displayType === 2 ? "portrait" : "landscape";
    const orientEl = $(".tpl-orient", modal);
    orientEl.innerHTML = icon(
        orient === "portrait" ? "smartphone" : "monitor", 13);
    orientEl.appendChild(document.createTextNode(orient + " display"));

    const frame = $(".display-frame", modal);
    frame.dataset.aspect = _tplCtx.aspect;
    frame.dataset.orientation = orient;

    const spec = _templatePickerSpec(_tplCtx.aspect, _tplCtx.templateType);
    let hint = spec.hint;
    if (effect.kind === "mismatch") {
        hint += " Saved for a " +
            (storedType === 2 ? "portrait" : "landscape") +
            " display, so this display ignores it and picks at random.";
    } else if (effect.kind === "clamped") {
        hint += " Saved style " + rawId + " is beyond this catalog; the " +
            "display shows style " + effect.shows + ". Apply to save that.";
    }
    $(".template-hint", modal).textContent = hint;

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
            (_tplCtx.aspect === "4x3"
                ? (_tplCtx.templateType === 2 ? " aspect-3x4" : " aspect-4x3")
                : "") + '">' +
            _templatePreviewSvg(_tplCtx.aspect, i, m.url, _tplCtx.templateType,
                                _tplCtx.legacy) +
            "</span>" +
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
        _tplCtx.aspect, _tplCtx.sel || 1, _tplCtx.item.url,
        _tplCtx.templateType, _tplCtx.legacy);
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
