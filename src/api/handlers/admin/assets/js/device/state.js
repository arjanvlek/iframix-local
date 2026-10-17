// Per-device client state and the initial load of every tab.

const PHOTO_PAGE_SIZE = 24;
const deviceState = {};

function getState(deviceId) {
    if (!deviceState[deviceId]) {
        deviceState[deviceId] = {
            kind: "normal",
            filter: "all",
            sort: "default",
            selected: new Set(),
            photos: {
                normal: {items: [], total: 0, page: 0},
                ai: {items: [], total: 0, page: 0},
            },
            weather: {cityId: "", cityName: "", lat: "", lon: ""},
            playback: {rules: [], editIndex: null,
                       isPlaying: false, currentModule: ""},
        };
    }
    return deviceState[deviceId];
}

function initDevice(view) {
    loadPhotos(view);
    loadClock(view);
    loadWeather(view);
    loadPlayback(view);
    loadCalendars(view);
}
