// Weather tab: city search, units and weather-station style.

async function loadWeather(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    try {
        const data = await getJSON(
            "/api/ipad/device/setting/weather?id=" + deviceId);
        const cur = (data && data.data) || {};
        if (cur.city) {
            const cm = cur.cityMsg || {};
            state.weather = {
                cityId: cm.id || "",
                cityName: cur.city,
                lat: cm.lat || "",
                lon: cm.lon || "",
            };
            setCurrentCity(view, "Current: ", cur.city);
        }
        setSegValue($('[data-seg="unit"]', view), cur.unit || 1);
        // weather_template_id is 0-based (0..3) to match the iFramix
        // 2.2.29 webapp catalog. A saved 0 must stay 0.
        const styleId = (cur.weather_template_id != null)
            ? cur.weather_template_id : 0;
        setStyleGridValue($('[data-style-grid="weather"]', view), styleId);
    } catch {}
}

function setCurrentCity(view, prefix, city) {
    const el = $(".current-city", view);
    if (!el) return;
    el.innerHTML = '<span class="cc-ico">' + icon("cloud", 15) + "</span>";
    el.appendChild(document.createTextNode(prefix));
    const b = document.createElement("b");
    b.textContent = city;
    el.appendChild(b);
}

async function searchCity(view) {
    const kw = $(".city-query", view).value.trim();
    if (!kw) return;
    const list = $(".city-results", view);
    try {
        const data = await getJSON(
            "/api/ipad/address/city?keyword=" +
            encodeURIComponent(kw) + "&lang=en");
        list.innerHTML = "";
        const results = Array.isArray(data.data) ? data.data : [];
        if (!results.length) {
            toast("No cities found for “" + kw + "”", true);
            return;
        }
        const state = getState(view.dataset.deviceId);
        for (const city of results) {
            const opt = document.createElement("button");
            opt.type = "button";
            opt.className = "city-opt";
            const parts = [city.name];
            if (city.adm1 && city.adm1 !== city.name) parts.push(city.adm1);
            if (city.country) parts.push(city.country);
            const label = parts.filter(Boolean).join(", ");
            opt.innerHTML = icon("cloud", 14);
            opt.appendChild(document.createTextNode(" " + label));
            opt.addEventListener("click", () => {
                state.weather = {
                    cityId: city.city_id || city.id || "",
                    cityName: city.name || "",
                    lat: city.lat || "",
                    lon: city.lon || "",
                };
                setCurrentCity(view, "Selected: ", label);
                list.innerHTML = "";
            });
            list.appendChild(opt);
        }
    } catch (e) {
        toast("Search error: " + e, true);
    }
}

async function saveWeather(view) {
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    if (!state.weather.cityId) {
        toast("Search and select a city first", true);
        return;
    }
    const unit = parseInt(segValue($('[data-seg="unit"]', view)) || "1", 10);
    const styleId = styleGridValue($('[data-style-grid="weather"]', view));
    try {
        const data = await postJSON("/api/ipad/device/setting/weather", {
            id: parseInt(deviceId, 10),
            values: {
                city: state.weather.cityName,
                cityMsg: {
                    id: state.weather.cityId,
                    name: state.weather.cityName,
                    lat: state.weather.lat,
                    lon: state.weather.lon,
                },
                unit,
                weather_template_id: styleId == null ? 0 : styleId,
            },
        });
        if (data.code === 1) toast("Weather settings saved");
        else toast("Failed: " + (data.msg || "?"), true);
    } catch (e) {
        toast("Error: " + e, true);
    }
}
