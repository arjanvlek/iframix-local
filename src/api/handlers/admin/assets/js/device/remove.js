// Remove tab: delete the display device and all of its data.

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
