// Page bootstrap: global listeners, the 10s background refresh and
// the initial (deep-linked) view. Loaded last.

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
