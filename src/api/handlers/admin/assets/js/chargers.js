// Chargers view: the 10s tbody refresh (with change-only flashing),
// the header / sidebar counters, and the Power and Auto/Manual
// actions called from the server-rendered rows.

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
    const online = rows.filter(
        (r) => r.dataset.online === "true").length;
    const sub = document.getElementById("chargers-sub");
    if (sub) {
        sub.textContent = rows.length + " connected · " +
            charging + " charging";
    }
    // The sidebar "Chargers" badge mirrors the display-device counter:
    // a green dot + active (reported within 45 min) over total chargers.
    const count = document.getElementById("charger-count");
    if (count) {
        count.innerHTML = '<span class="dot online"></span>' +
            online + "/" + rows.length;
    }
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
