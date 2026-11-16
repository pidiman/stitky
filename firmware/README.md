# ESP32 P15 Wi-Fi bridge

PlatformIO Arduino firmware for the tested ESP32-D0WDQ6 / 4 MB board. Canonical label profile: 40 × 12 mm gap stock, 96 × 320 dot raster, supplied by the API. It never creates test jobs or prints at startup.

## Build and flash

```sh
pio run
pio run -t upload --upload-port /dev/cu.SLAB_USBtoUART
```

Platform `espressif32@6.12.0`, Arduino core 2.0.17, ArduinoJson 6.21.5. All API calls require HTTPS and the configured root CA. There is no insecure TLS mode. NTP synchronises the clock before TLS; allow outbound DNS, NTP, and HTTPS. No inbound connection to ESP32 is needed during normal use.

## API configuration via USB

Install Python `pyserial` locally. The masked tool neither prints nor saves passwords/tokens:

```sh
python3 tools/provision.py --api-url https://labels.example.com --ca certs/isrgrootx1.pem
```

Enter the device token from the server when asked. Optional `--token-file` reads an existing private local token file without putting its content on the command line. Optional `--wifi` asks for SSID and a hidden Wi-Fi password instead of using the portal. A `CONFIG` serial JSON line stores settings atomically in ESP32 NVS; serial replies never echo its contents. Fields: `api_url`, `agent_token`, `printer_mac`, `server_ca_pem`, optionally `ssid` and `password`. Omitted fields keep their stored values. `server_ca_pem` contains the root certificate in PEM, not a leaf certificate. Do not publish configuration JSON or take screenshots containing tokens.

The supplied public CA is not a secret; the server certificate must chain to it. Provisioning before public DNS/certificate setup is possible, but polling will fail until the endpoint is reachable with a valid certificate. API configuration may be saved before Wi-Fi setup.

## Captive Wi-Fi setup

On first boot without a stored Wi-Fi SSID, the board opens a protected WPA2 setup network. Its name (`P15-Setup-xxxx`) and unique random password are shown through the USB serial monitor at 115200 baud. Connect your phone/Mac to that network, then open **http://192.168.4.1** if the captive window does not appear automatically.

The form scans nearby Wi-Fi networks and preselects **MyWiFi**. Enter the 2.4 GHz network password locally in that form. Saving restarts the board and connects it to the selected network. The form never displays API credentials or the existing Wi-Fi password. The portal has a per-session CSRF token, is reachable only while the setup AP is open, and closes after 10 minutes. Hold **BOOT** (GPIO0) for 3 seconds *after the program has started*, or send serial `WIFI_SETUP`, to reopen it. Do not hold BOOT while resetting, which enters the hardware bootloader.

Serial `STATUS` reports configuration/Wi-Fi/pending state and free heap, without secrets. Wi-Fi/API credentials reside in standard ESP32 NVS; this MVP does not enable flash encryption. Reflashing only the app preserves settings and job recovery records. Erasing flash destroys those records and must not be used as a routine retry mechanism.

## Print recovery and queue semantics

The bridge polls every 10 seconds. It verifies raster dimensions, byte length and SHA-256, saves an unresolved job marker to NVS, and asks the API to start. It does not send any printer data unless start returns HTTP 200. TLS and HTTP objects are freed before BLE is initialised.

BLE uses the known printer MAC, FF00 service / FF02 transmit / FF01 responses / FF03 credits. Blocks contain at most 20 bytes, spaced at least 30 ms and gated by printer credits. It sends one L11 raster, one gap advance and one stop command. AA or exact `OK` is required for `printed`; a disconnect is never treated as success. Physical layout still needs visual acceptance.

The persistent marker prevents automatic reprinting after a reset or ambiguous network failure. Results are persisted before being reported; failed result reports are retried without retransmitting printer data. Any pending result blocks claiming another job. A server HTTP 409/404 on result reporting needs operator review; the firmware keeps the record instead of guessing whether it is safe to print. To retry a physical label, create an explicit new server job after reviewing the old job's status.

Captive Wi-Fi setup may be reopened to repair connectivity while a result is pending. API/token changes via USB are rejected until pending work is resolved, so a job cannot accidentally be reported to a different server.

## Verification limits

The code is built for the physical board profile. Wi-Fi association, HTTPS polling, repeated BLE/TLS memory recovery and queue-to-physical-print behaviour need on-device checks after provisioning. The earlier standalone BLE tests proved the P15 link and label protocol, but do not establish these new integration checks.

### USB provisioning diagnostics (1.0.1)

Startup prints `NVS OPEN config=1 jobs=1`; processing stops if either namespace fails to open. CONFIG rejection reports only a safe reason code, such as JSON parse error and byte count, invalid URL/token length/CA header, or NVS write counts/free entries. It does not print field contents. The UART receive buffer is 8192 bytes, and the provisioner sends 64-byte chunks with 10 ms pauses to avoid overrunning the default UART buffer while the captive portal is active.

## Single addressable RGB status LED (1.1.0)

Default: **one WS2812B/NeoPixel-compatible RGB pixel, GRB order, 800 kHz, DATA on GPIO18**, brightness limited to 32/255. Connect the module's **DIN** (not DOUT) to GPIO18, its 5V supply to 5V, and GND to the ESP32 common ground. A 330–470 Ω series DATA resistor is suitable; for reliable operation of a 5V pixel with a 3.3V ESP32 data signal, use a 74AHCT-family level shifter. This build assumes an RGB WS2812-compatible device; a different chipset or RGBW pixel needs the matching library configuration.

Compile-time settings in `platformio.ini`: `LED_PIN=18`, `LED_COUNT=1`, `LED_BRIGHTNESS=32`. The pinned driver is Adafruit NeoPixel 1.12.3. No extra FreeRTOS task is created. The main loop and its own waiting loops tick the effects. Third-party blocking Wi-Fi/TLS/BLE-scan calls can temporarily hold the current LED frame.

| LED | Meaning |
|---|---|
| Blue slow blink | Captive Wi-Fi setup portal |
| Yellow blink | Connecting Wi-Fi, waiting for time sync, or connecting to API |
| Dim steady green | Successful authenticated heartbeat / ready |
| Purple slow blink | Searching for / connecting to P15 |
| Purple steady briefly | BLE connected with printer credits |
| Cyan blink | Sending label / waiting for printer result |
| Green flashes for 1 second | Printer acknowledged the completed transfer |
| Red blink | Network/API/TLS, storage, BLE or uncertain print error |

Red error indication is latched until a successful authenticated queue heartbeat; no-ACK or disconnect is not shown as print success. Serial `LED_TEST` runs a 12-second visual sequence (blue, yellow, green, blinking purple, steady purple, cyan, red, flashing green), then restores the normal status. It creates no jobs and pauses queue polling during the LED sequence. Colors and electrical operation still require physical verification after wiring.

### Stable setup-network password

The setup AP password is generated once and cached in the separate NVS key `setup-pass`. Reopening USB, rebooting or reflashing only the application therefore keeps that password. It changes only when the NVS value is absent/invalid or deliberately erased. Existing API and Wi-Fi settings remain in the unchanged `settings` key. While the captive portal is active, serial `SETUP_INFO` reports its current SSID and AP password only; it does not expose the API token or target Wi-Fi password. When no portal is active it prints a status message instead.

### Captive mini-browser response fix (1.1.1)

The setup server now returns a complete HTML form with HTTP 200 for `/` and every other GET probe path, including common Android, Apple and Windows captive-detection requests. It no longer relies on an empty 302 redirect response. Responses use an explicit content length, `Cache-Control: no-store`, and `Connection: close`. The form submits to the absolute local URL `http://192.168.4.1/save` and keeps CSRF validation.

Wi-Fi discovery starts asynchronously when the portal opens. HTTP requests are served immediately using cached options, with MyWiFi always available and selected even while discovery is pending. Refresh updates the list; the rescan link starts another asynchronous scan. Safe USB diagnostics print only the request path and HTML byte count (`PORTAL GET ... HTML bytes=...`), never query parameters or form values. The host C++ renderer check is in `tools/test_portal_page.cpp`; physical captive-window behaviour still needs on-device verification.

### Corrected default SSID and Wi-Fi diagnostics (1.1.2)

The default SSID is **MyWiFi** (underscore). This corrects the setup form, its renderer tests, USB provisioning prompt and documentation. Saved settings are not overwritten by defaults. Safe Wi-Fi event diagnostics print disconnect reason number/name, association and assigned IP; `STATUS` includes the numeric Wi-Fi status and the saved SSID, without passwords or API tokens. The asynchronous scan behaviour remains unchanged from 1.1.1.


## Printer information and telemetry (1.2.1)

The bridge posts metadata to `POST /api/agent/telemetry` every 30 seconds: firmware version, Wi-Fi RSSI, uptime and free heap. These bridge-only reports set `printer_checked=false` and omit printer fields so an old printer reading is not falsely refreshed.

A printer probe runs once after boot when the queue is empty, and on a server `X-Printer-Refresh: 1` empty-claim response or local USB `PRINTER_INFO` request. Probes are limited to one per minute. Pending print outcomes are reported first; a probe is never run in a print session. BLE is disconnected before a subsequent HTTPS request, preserving memory on the original ESP32.

A probe sends only model `10 FF 20 F0`, firmware `10 FF 20 F1`, serial `10 FF 20 F2`, battery `10 FF 50 F1`, and status `10 FF 40`. It does not send wakeup, enable, print, feed or calibration commands. Replies are bounded to256 bytes and logged as `INFO RAW <name> sent=… bytes=… hex=…` for hardware validation. Query transmission waits at most1 second for a credit and each response up to3 seconds.


If the printer is off or does not answer information requests, the telemetry explicitly reports unavailable/unknown values and an explanatory error rather than a fictitious0% battery or ready state. Missing stable identity fields can be retained by the server, while a new checked report clears unavailable volatile battery/status values.

Parser host checks:

```sh
c++ -std=c++11 tools/test_printer_info.cpp -o /tmp/p15-info-test
/tmp/p15-info-test
```


Protocol cross-checks: local thermoprint `packages/core/src/printer.ts` reads the raw battery percentage from the second reply byte; https://raw.githubusercontent.com/0xMH/fichero-printer/main/docs/PROTOCOL.md describes the two-byte status/percentage framing. Parsing remains restricted to the frame actually observed on this P15.
