// The topbar "Live · 10s" pause toggle and the background refresh
// of the display-device presence indicators.

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
