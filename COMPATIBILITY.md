## Compatibility of the local implementation per served webapp version

This section indicates which app variants work with the local implementation.

| iFramix Pro (web)app version | iOS Controller App | Android Controller App | iOS Display App | Android Display App   | Legacy iPad web-app | Ultra-Legacy iPad 1 web-app* |
|------------------------------|--------------------|------------------------|-----------------|-----------------------|---------------------|------------------------------|
| 2.3.1 / 2.3.2                | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.2.29                       | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.2.27                       | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.1.3                        | ?                  | ?                      | ?               | YES                   | NO (assets missing) | YES                          |

*The ultra-legacy iPad 1 web-app is not dependent on the main app version being served; its sources are stored separately under the `webapp/pad1` directory. 

OS Compatibility per app:

| App type                    | Supported OS version                                        |
|-----------------------------|-------------------------------------------------------------|
| iOS Controller App          | iOS 12+, iPhone 5s+ / iPod Touch 6+                         |
| iOS Display App             | iOS 12+, iPhone 5s+ / iPod Touch 6+ / iPad Air 1+ / Mini 2+ |
| Legacy iPad Web-App         | iOS 9 + iOS 10, iPad 2/3/4/Mini 1. No calendar support.     |
| Ultra-Legacy iPad 1 Web-App | iOS 5, iPad 1. Photos / Photos + AI only.                   |
| Android Controller App      | Android 5.0+, Phones only                                   |
| Android Display App         | Android 5.0+, Phones and tables                             |
| 

## Feature compatibility and MQTT Endpoints per served iFramix Pro webapp version

This section indicates which end-user features work with which served webapp version, and what the correct MQTT endpoints are for that version.

| (Web)App Version       | Photos | Photos + AI | Flip Clock      | Weather Station | iCharGuard | Power Save Mode | Calendar | Playback Mode | Uses HTTPS? | App MQTT Address           | Charger MQTT Address |
|------------------------|--------|-------------|-----------------|-----------------|------------|-----------------|----------|---------------|-------------|----------------------------|----------------------|
| 2.3.1 / 2.3.2          | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES *4        | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.2.29                 | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | NO            | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.2.27                 | YES    | YES *1      | YES ( 1 style)  | YES (1 style)   | YES        | YES             | YES *2   | NO            | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.1.3                  | YES    | YES *1      | YES ( 1 style)  | YES (1 style)   | YES        | YES             | NO       | NO            | NO          | ws://<host>:8083/mqtt      | TCP <host>:1883      |
| Ultra-Legacy iPad 1 *3 | YES    | YES *1      | NO              | NO              | YES        | NO              | NO       | NO            | YES         | NOT USED                   | TCP <host>:1883      |

*1 Photos + AI works differently: It displays photo capture time, camera model and exposure (aperture and ISO)

*2 Calendar is only supported from within the native apps, not on the legacy iPad web-app. Online calendar functionality is limited.

*3 The ultra-legacy iPad 1 web-app only supports Photos and Photos + AI mode.

*4 Playback mode (introduced in app 2.3.1) automatically switches the display between modules — either a random module on a configurable 1–240 minute interval, or a fixed default module with daily time-rule overrides. Configurable from the native controller app and the local admin panel (`/admin`).
