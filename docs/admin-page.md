# Admin Page

The API server includes a web-based admin page at `/admin` for controlling the chargers and display devices directly from a browser.

**This panel is a local-only addition. It is not part of the original iFramix Pro.**

The page has two sections:

## Chargers

Table with all your chargers, showing MAC, WiFi name, firmware, voltage, current, battery percentage, and three charging columns:

- **Charge command**: the desired on/off state last sent by the controller app or the admin page's Enable/Disable button.
- **Charger status**: the actual state. This is either the state the charger explicitly reports over MQTT, or, when firmware omits that field, inferred from the charger's measured current.
- **Mode**: each charger can be switched between **manual** (default) and **auto** mode.
  - In manual mode, the charger only reacts to the Enable/Disable buttons on the Admin panel. The controller app's requests update the stored desired state but do not drive the charger.
  - In auto mode, the Enable/Disable buttons are hidden and every request from the controller app is forwarded to the charger as an MQTT `charging_switch` command, which drives the charger to power on / off.
  - Switching a charger into auto also immediately pushes the current desired state (if any).

The chargers table refreshes in the background every 10 seconds.

## Display Devices

All your display devices, collapsed by default. Expanding a device reveals forms that allow you to configure your device:

- **Upload photos**: multi-file picker to upload photos. Below the picker, a thumbnail grid per type (normal / AI) shows what is currently stored for that device. To stay fast on devices with hundreds of photos, the grid loads photos in pages (24 at a time, newest first) behind a **Load more** button, and the thumbnails are downscaled and cached on the server, so a card opens quickly without downloading every full-resolution image. Clicking an AI thumbnail opens a template-picker modal where you can specify the style (template) for the photo. Each thumbnail has a checkbox in its corner: tick one or more photos and use the **Delete selected** button below that grid to remove them in bulk (after a confirmation prompt). Deletion uses the same flow as removing photos from the display app, so the display refreshes automatically.
- **Flip clock**: pick one of the 5 flip-clock styles iFramix Pro 2.2.29 introduced and the 12-hour / 24-hour format (the `time` field).
- **Weather**: search and specify your city, select between Imperial / Metric units and select one of the 4 weather-station styles iFramix Pro 2.2.29 introduced.
- **Calendars**: link an external calendar (Google / Outlook / iCloud iCal URL, or a manual iCal URL) or delete a previously synced one.
- **Delete display device**: When clicked, asks for confirmation. If you delete a device, all its associated data, including photos, will be deleted from the server.

## Unsupported features

Binding a charger to a display device is not supported. This can only be done from the iFramix app on a controller device.
The native controller app does that over Bluetooth, which would require your server to have a Bluetooth module and be nearby the charger unit. 
It would also have to prompt for the Wi-Fi credentials to send to the charger unit, which is a non-standard, undocumented feature.
