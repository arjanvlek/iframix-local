// Playback tab (app 2.3.1+): random / fixed playback mode.

//
// Mirrors the native app's Playback Settings screen: random mode
// (switch interval + per-module inclusion toggles) or fixed mode
// (default module + daily time rules). The API stores and broadcasts
// the whole settings document on every save, so all edits here are
// local until "Save playback" posts the assembled document.

const PLAYBACK_MODULE_NAMES = {
    album: "Photos",
    album_ai: "Gallery Mode",
    screensaver: "Flip Clock",
    weather: "Weather",
    calendar: "Calendar",
};

async function loadPlayback(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    let cur = {};
    try {
        const data = await getJSON(
            "/api/ipad/device/setting/playback?id=" + deviceId);
        // An unconfigured device gets an empty array back (matching
        // the cloud server); treat it the same as an empty object.
        if (data && data.data && !Array.isArray(data.data)) {
            cur = data.data;
        }
    } catch {}
    const random = cur.random || {};
    const fixed = cur.fixed || {};

    state.playback.rules = (fixed.rules || []).map((r) => ({
        startTime: r.startTime, endTime: r.endTime, module: r.module}));
    state.playback.editIndex = null;
    state.playback.isPlaying = !!cur.isPlaying;
    state.playback.currentModule = cur.currentModule || "";

    setSegValue($('[data-seg="playback-mode"]', view),
        cur.mode === "fixed" ? "fixed" : "random");
    $(".playback-interval", view).value =
        random.intervalMinutes != null ? random.intervalMinutes : 15;
    const excluded = random.excludedModules || [];
    $all(".module-row", view).forEach((row) => {
        $("input", row).checked =
            excluded.indexOf(row.dataset.module) === -1;
    });
    $(".playback-default", view).value = fixed.defaultModule || "";

    renderPlaybackMode(view);
    renderPlaybackModuleCount(view);
    renderPlaybackRules(view);
}

function renderPlaybackMode(view) {
    const mode = segValue($('[data-seg="playback-mode"]', view));
    $(".playback-random", view).hidden = mode === "fixed";
    $(".playback-fixed", view).hidden = mode !== "fixed";
}

function renderPlaybackModuleCount(view) {
    const total = $all(".module-row", view).length;
    const on = $all(".module-row input:checked", view).length;
    const label = $(".module-count", view);
    if (label) label.textContent = "(" + on + " / " + total + " enabled)";
}

function renderPlaybackRules(view) {
    const state = getState(view.dataset.deviceId);
    const list = $(".rule-list", view);
    if (!list) return;
    list.innerHTML = "";

    let emptyNote = $(".rule-empty", view);
    if (!state.playback.rules.length) {
        if (!emptyNote) {
            emptyNote = document.createElement("div");
            emptyNote.className = "rule-empty";
            emptyNote.textContent = "No time rules yet. The default " +
                "module will be used all day.";
            list.parentNode.insertBefore(emptyNote, list);
        }
        emptyNote.hidden = false;
        return;
    }
    if (emptyNote) emptyNote.hidden = true;

    state.playback.rules.forEach((rule, i) => {
        const item = document.createElement("div");
        item.className = "rule-item" +
            (state.playback.editIndex === i ? " editing" : "");

        const time = document.createElement("span");
        time.className = "rule-time";
        time.textContent = rule.startTime + " – " + rule.endTime;
        item.appendChild(time);

        const name = document.createElement("span");
        name.className = "rule-module-name";
        name.textContent =
            PLAYBACK_MODULE_NAMES[rule.module] || rule.module;
        item.appendChild(name);

        const actions = document.createElement("div");
        actions.className = "rule-actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "btn sm";
        edit.textContent = "Edit";
        edit.addEventListener("click", () => startRuleEdit(view, i));
        actions.appendChild(edit);
        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn sm ghost-danger";
        del.innerHTML = icon("trash", 13);
        del.title = "Delete rule";
        del.addEventListener("click", () => {
            state.playback.rules.splice(i, 1);
            if (state.playback.editIndex === i) resetRuleForm(view);
            else if (state.playback.editIndex > i) {
                state.playback.editIndex--;
            }
            renderPlaybackRules(view);
        });
        actions.appendChild(del);
        item.appendChild(actions);

        list.appendChild(item);
    });
}

function startRuleEdit(view, index) {
    const state = getState(view.dataset.deviceId);
    const rule = state.playback.rules[index];
    if (!rule) return;
    state.playback.editIndex = index;
    $(".rule-start", view).value = rule.startTime;
    $(".rule-end", view).value = rule.endTime;
    $(".rule-module", view).value = rule.module;
    $(".rule-add-label", view).textContent = "Update rule";
    $(".rule-cancel-btn", view).hidden = false;
    renderPlaybackRules(view);
}

function resetRuleForm(view) {
    const state = getState(view.dataset.deviceId);
    state.playback.editIndex = null;
    $(".rule-start", view).value = "";
    $(".rule-end", view).value = "";
    $(".rule-module", view).selectedIndex = 0;
    $(".rule-add-label", view).textContent = "Add rule";
    $(".rule-cancel-btn", view).hidden = true;
}

// Rules repeat daily and may not overlap (same constraints the native
// app enforces). Start must come before end within the same day.
function submitRule(view) {
    const state = getState(view.dataset.deviceId);
    const start = $(".rule-start", view).value;
    const end = $(".rule-end", view).value;
    const module = $(".rule-module", view).value;
    if (!start || !end) {
        toast("Pick a start and end time first", true);
        return;
    }
    if (start >= end) {
        toast("End time must be after start time (rules stay within " +
            "one day)", true);
        return;
    }
    if (!module) {
        toast("Pick a module for this rule", true);
        return;
    }
    const overlap = state.playback.rules.some((r, i) =>
        i !== state.playback.editIndex &&
        start < r.endTime && r.startTime < end);
    if (overlap) {
        toast("Time rules cannot overlap an existing rule", true);
        return;
    }
    const rule = {startTime: start, endTime: end, module};
    if (state.playback.editIndex !== null) {
        state.playback.rules[state.playback.editIndex] = rule;
    } else {
        state.playback.rules.push(rule);
    }
    state.playback.rules.sort(
        (a, b) => a.startTime < b.startTime ? -1 : 1);
    resetRuleForm(view);
    renderPlaybackRules(view);
}

async function savePlayback(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    const mode = segValue($('[data-seg="playback-mode"]', view)) ||
        "random";

    const interval = parseInt($(".playback-interval", view).value, 10);
    if (!(interval >= 1 && interval <= 240)) {
        toast("Switch interval must be between 1 and 240 minutes", true);
        return;
    }
    const excluded = $all(".module-row", view)
        .filter((row) => !$("input", row).checked)
        .map((row) => row.dataset.module);
    if (mode === "random" &&
            excluded.length === $all(".module-row", view).length) {
        toast("Enable at least one module for random playback", true);
        return;
    }
    const defaultModule = $(".playback-default", view).value;
    if (mode === "fixed" && !defaultModule &&
            !state.playback.rules.length) {
        toast("Pick a default module or add a time rule first", true);
        return;
    }

    try {
        const data = await postJSON("/api/ipad/device/setting/playback", {
            id: parseInt(deviceId, 10),
            values: {
                mode,
                random: {
                    intervalMinutes: interval,
                    excludedModules: excluded,
                },
                fixed: {
                    defaultModule,
                    rules: state.playback.rules,
                },
                isPlaying: state.playback.isPlaying,
                currentModule: state.playback.currentModule,
            },
        });
        if (data.code === 1) toast("Playback settings saved");
        else toast("Failed: " + (data.msg || "?"), true);
    } catch (e) {
        toast("Error: " + e, true);
    }
}
