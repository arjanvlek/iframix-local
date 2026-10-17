// Sidebar navigation: view switching, the mobile drawer and the
// client-side device search.

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
