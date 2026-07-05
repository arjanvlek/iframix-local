# Admin Page

The API server includes a web-based admin page at `/admin` for controlling the chargers and display devices directly from a browser.

**This panel is a local-only addition. It is not part of the original iFramix Pro.**

The page is a master-detail layout: a sidebar on the left lists the **Chargers** view and all your **display devices**, and the panel on the right shows whichever one you selected. 

The device list is searchable and every device shows an online/offline dot (online = the device talked to the server within the last 5 minutes). 
The online indicators refresh in the background every 10 seconds like the chargers table. 
Clicking the **Live · 10s** pill in the top right pauses the background refresh (the green dot disappears and the labels switch to "Paused"); clicking it again resumes and immediately catches up. 
On phones and small windows, the sidebar collapses (as a "hamburger" menu).

## Chargers

Table with all your chargers. 
The leftmost column shows green when the charger is active (has reported in the last 45 minutes). 

Then it shows MAC, WiFi name, firmware, voltage, current, battery percentage, and two charging columns:

- **Charge cmd**: the desired on/off state last sent by the controller app.
- **Status**: the actual state. This is either the state the charger explicitly reports over MQTT, or, when firmware omits that field, inferred from the charger's measured current.

Each row also has:

- **Mode**: an Auto/Manual toggle per charger (default: manual).
  - In manual mode, the charger only reacts to the **Power on / Power off** button on the admin page. The controller app's requests update the stored desired state but do not drive the charger.
  - In auto mode, the Power button is disabled ("Controlled by app") and every request from the controller app is forwarded to the charger as an MQTT `charging_switch` command, which drives the charger to power on / off.
  - Switching a charger into auto also immediately pushes the current desired state (if any).
- **Power output**: a single button (manual mode only) that toggles the charger's power output. A "pending" badge appears in the Status column when the charger's reported status has not yet caught up with your last Power click.

The chargers table refreshes in the background every 10 seconds; a voltage/current cell flashes briefly only when its value changed since the previous refresh.

The **Chargers** item in the sidebar shows the active/total count (e.g. `3/5`).

## Display devices

Contains all your display devices.

Selecting a device in the sidebar opens its settings (six tabs):

- **Photos**: A gallery for all your photos with an **All / Normal / AI** filter. Choose the type of photos (Normal or AI), then drag photos onto the dropzone (or click it to browse). Uploads start immediately. The **Sort** dropdown offers **File name** (newest first), **Upload date** (newest file modification time first), and **Capture date (EXIF)** (newest EXIF capture date first, with photos that have no readable capture date sorted last).
- Clicking a normal photo opens a full-size preview
- Clicking an **AI** photo opens the **AI display template** picker — a modal with a large live preview that renders your actual photo in the selected layout, next to a named list of every template the display can render (10 styles on 4:3 displays, 5 on 16:9 displays for horizontal photos, 4 for vertical photos). 
- Each AI thumbnail shows a chip with its current template. 
- Every thumbnail has a check button in its corner: tick one or more photos and use **Delete selected** to remove them in bulk (after a confirmation prompt).
- **Flip clock**: pick the 12-hour / 24-hour format and one of the 5 flip-clock styles iFramix Pro 2.2.29 introduced.
- **Weather**: search and select your city, choose °C / °F, and pick one of the 4 weather-station styles iFramix Pro 2.2.29 introduced.
- **Calendars**: link an external calendar (Google / Apple iCloud / Outlook, or any iCal URL) or delete a previously linked one.
- **Playback**: configure the playback mode iFramix Pro 2.3.1 introduced, where the display automatically switches between modules (Photos, AI Photos, Flip Clock, Weather, Calendar). In **Random** mode, pick the switch interval (1–240 minutes) and toggle which modules join the rotation. In **Fixed** mode, pick a default module and optionally add daily time rules (start time, end time, module) that override it; rules repeat daily, must stay within one day, and cannot overlap. Existing rules can be edited and deleted. Changes are applied when you press **Save playback** — the display device is notified immediately over MQTT.
- **Remove**: deletes the display device after confirmation. If you delete a device, all its associated data, including photos, will be deleted from the server.

## Unsupported features

Binding a charger to a display device is not supported. This can only be done from the iFramix app on a controller device.
The native controller app does that over Bluetooth, which would require your server to have a Bluetooth module and be nearby the charger unit. 
It would also have to prompt for the Wi-Fi credentials to send to the charger unit, which is a non-standard, undocumented feature.
