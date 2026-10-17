// Flip clock tab: time format + clock style (screensaver setting).

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
