// Wires the tabs and forms of one server-rendered device view.

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
        const label = v === "ai" ? "Gallery Mode" : "Normal";
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
