// Calendars tab: link, list and delete external calendars.

const CAL_PROVIDERS = {
    google: {name: "Google Calendar", hue: 256},
    icloud: {name: "Apple iCloud", hue: 220},
    outlook: {name: "Outlook / Microsoft 365", hue: 240},
    manual: {name: "Other (ICS URL)", hue: 290},
};

async function loadCalendars(view) {
    const deviceId = view.dataset.deviceId;
    const list = $(".cal-list", view);
    if (!list) return;
    try {
        const data = await getJSON(
            "/api/calendar/index?device_id=" + deviceId);
        const items = (data && data.data && data.data.list) || [];
        list.innerHTML = "";
        const tabCount = $('.tab[data-tab="calendars"] .tcount', view);
        if (tabCount) tabCount.textContent = items.length || "";
        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "empty";
            empty.textContent = "No calendars linked yet.";
            list.appendChild(empty);
            return;
        }
        for (const cal of items) {
            const prov = CAL_PROVIDERS[cal.driver] ||
                {name: cal.driver || "Calendar", hue: 256};
            const item = document.createElement("div");
            item.className = "cal-item";

            const ico = document.createElement("div");
            ico.className = "cal-ico";
            ico.style.background = "oklch(0.55 0.15 " + prov.hue + ")";
            ico.innerHTML = icon("calendar", 17);
            item.appendChild(ico);

            const meta = document.createElement("div");
            meta.className = "cal-meta";
            const name = document.createElement("div");
            name.className = "cal-name";
            name.textContent = cal.name || "(no name)";
            const url = document.createElement("div");
            url.className = "cal-url";
            url.textContent = cal.url || "";
            meta.appendChild(name);
            meta.appendChild(url);
            item.appendChild(meta);

            const tag = document.createElement("span");
            tag.className = "tag";
            tag.textContent = prov.name;
            item.appendChild(tag);

            const del = document.createElement("button");
            del.type = "button";
            del.className = "icon-btn";
            del.style.width = "34px";
            del.style.height = "34px";
            del.title = "Remove";
            del.innerHTML = icon("trash", 15);
            del.style.color = "var(--danger-text)";
            del.addEventListener("click", () =>
                removeCalendar(view, cal.id));
            item.appendChild(del);

            list.appendChild(item);
        }
    } catch {}
}

async function addCalendar(view) {
    const deviceId = view.dataset.deviceId;
    const driver = $(".cal-driver", view).value;
    let name = $(".cal-name-input", view).value.trim();
    const url = $(".cal-url-input", view).value.trim();
    if (!url) { toast("Add a calendar URL first", true); return; }
    if (!name) {
        name = (CAL_PROVIDERS[driver] || {}).name ||
            driver.charAt(0).toUpperCase() + driver.slice(1);
    }
    try {
        const data = await postJSON("/api/calendar/external/link", {
            url,
            device_id: parseInt(deviceId, 10),
            name,
            driver,
        });
        if (data.code === 1) {
            toast("Calendar linked");
            $(".cal-name-input", view).value = "";
            $(".cal-url-input", view).value = "";
            loadCalendars(view);
        } else {
            toast("Failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Error: " + e, true);
    }
}

async function removeCalendar(view, calId) {
    try {
        const data = await postJSON("/api/calendar/delete", {id: calId});
        if (data.code === 1) {
            toast("Calendar removed");
            loadCalendars(view);
        } else {
            toast("Delete failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Delete error: " + e, true);
    }
}
