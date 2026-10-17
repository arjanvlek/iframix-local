## Compatibility of the local implementation per served webapp version

This section indicates which app variants work with the local implementation.

| iFramix Pro (web)app version | iOS Controller App | Android Controller App | iOS Display App | Android Display App   | Legacy iPad web-app | Ultra-Legacy iPad 1 web-app* |
|------------------------------|--------------------|------------------------|-----------------|-----------------------|---------------------|------------------------------|
| 2.3.8                        | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.3.5                        | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.3.4                        | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.3.3                        | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.3.1 / 2.3.2                | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.2.29                       | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.2.27                       | YES                | NO (rejects SSL cert)  | YES             | NO (rejects SSL cert) | YES                 | YES                          |
| 2.1.3                        | ?                  | ?                      | ?               | YES                   | NO (assets missing) | YES                          |

*The ultra-legacy iPad 1 web-app is not dependent on the main app version being served; its sources are stored separately under the `webapp/pad1` directory. 

OS Compatibility per app:

| App type                    | Supported OS version                                            |
|-----------------------------|-----------------------------------------------------------------|
| iOS Controller App          | iOS 14+, iPhone 6s+ / iPod Touch 7+                             |
| iOS Display App             | iOS 14+, iPhone 6s+ / iPod Touch 7+ / iPad Air 2+ / Mini 4+     |
| Legacy iPad Web-App         | iOS 9-13, iPad 2/3/4 / Air1 / Mini 1/2. No calendar support. *4 |
| Ultra-Legacy iPad 1 Web-App | iOS 5, iPad 1. Photos / Gallery Mode only.                      |
| Android Controller App      | Android 5.0+, Phones only                                       |
| Android Display App         | Android 5.0+, Phones and tables                                 |
| 

## Feature compatibility and MQTT Endpoints per served iFramix Pro webapp version

This section indicates which end-user features work with which served webapp version, and what the correct MQTT endpoints are for that version.

| (Web)App Version       | Photos | Gallery Mode | Flip Clock      | Weather Station | iCharGuard | Power Save Mode | Calendar | Playback Mode | Uses HTTPS? | App MQTT Address           | Charger MQTT Address |
|------------------------|--------|-------------|-----------------|-----------------|------------|-----------------|----------|---------------|-------------|----------------------------|----------------------|
| 2.3.8                  | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES           | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.3.5                  | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES           | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.3.4                  | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES           | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.3.3                  | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES           | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.3.1 / 2.3.2          | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | YES           | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.2.29                 | YES    | YES *1      | YES ( 5 styles) | YES (4 styles)  | YES        | YES             | YES *2   | NO            | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.2.27                 | YES    | YES *1      | YES ( 1 style)  | YES (1 style)   | YES        | YES             | YES *2   | NO            | YES         | wss://<host>:443/websocket | TCP <host>:1883      |
| 2.1.3                  | YES    | YES *1      | YES ( 1 style)  | YES (1 style)   | YES        | YES             | NO       | NO            | NO          | ws://<host>:8083/mqtt      | TCP <host>:1883      |
| Ultra-Legacy iPad 1 *3 | YES    | YES *1      | NO              | NO              | YES        | NO              | NO       | NO            | YES         | NOT USED                   | TCP <host>:1883      |

*1 Gallery Mode (called "Photos + AI" before app 2.3.4) works differently: It displays photo capture time, camera model and exposure (aperture and ISO)

*2 Calendar is only supported from within the native apps, not on the legacy iPad web-app. Online calendar functionality is limited.

*3 The ultra-legacy iPad 1 web-app only supports Photos and Gallery Mode.

*4 App 2.3.8 and newer is only compatible with iOS 14 and newer (was: iOS 12 and newer). This means iPads on iOS 11-13 now also load the legacy web-app. Not tested on such hardware.
