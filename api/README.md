# P15 Hub API

Python 3.12+; install `requirements.txt` and a TrueType font. Production image should install `fonts-dejavu-core`. `FONT_PATH` can override its location. API port 8000, one Uvicorn worker recommended for the small deployment; SQLite synchronizes independent connections with immediate transactions and WAL.

Required environment: separate random `ADMIN_TOKEN` and `AGENT_TOKEN`, each at least 24 characters. Optional: `AGENT_ID=esp32-01`, `AGENT_NAME=P15 · ESP32`, `DB_PATH=/data/p15.sqlite3`, `WEB_DIR=../web/dist`. Tokens are never returned by list endpoints. Agent tokens are stored as SHA-256 hashes. Initial agent token is synchronized from environment on startup, permitting deliberate rotation; dynamically registered agent tokens persist in SQLite.

Launch from project root:

```sh
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The web build is served by the same process. Studio endpoints require a user session; agent endpoints require the device bearer token. Bootstrap login is admin/admin and forces email, nickname and password setup. Registration defaults to disabled and is controlled by the administrator. Sessions use Secure/HttpOnly/SameSite cookies and CSRF protection; serve the application over HTTPS. ADMIN_TOKEN remains for maintenance access subject to MAINTENANCE_CIDRS. Public health, login and registration configuration endpoints do not grant access to studio data.

## Queue safety

A claim grants a 90-second lease. Repeating claim before print start returns the same job and token. A successful start consumes the lease exactly once; repeating start returns 409. An agent must not print without the first successful start response. After that boundary a timeout changes the job to `unknown`, never back to queued. Unknown jobs need physical inspection before the user submits a new job.

A lease that expires before start can safely return to queued with a new lease token. Starting with an old token fails. A valid lease can complete as `failed` or `unknown` before start to quarantine an ambiguous attempt, but never as `printed`. Terminal completion is idempotent only for the same terminal outcome and valid device/lease; a different result returns 409. A late result cannot silently rewrite a terminal `unknown` to `printed`.

Each admin submission requires an idempotency key. Reusing the same key and body returns existing jobs; reusing it with different content returns 409. Each requested copy has its own job ID. Cancellation is supported only while queued. A device gets no second job while it has a live printing job.

The API expires leases lazily during queue operations; no background scheduler is needed. Persist the whole `/data` directory, including SQLite WAL files while running. Use SQLite's backup API for an online backup, or stop the container before copying the database.

## Rendering

Text is laid out at 320 × 96 pixels with centered lines and 12-pixel horizontal/vertical safe margins. Automatic font size picks the largest 6–64 size that fits. Explicit sizes that do not fit return 422. There are at most four lines, 200 characters, and ten copies. The exact monochrome preview pixels are rotated clockwise into 96 × 320 pixels, MSB-first with black = 1; raw raster length is always 3840 bytes. This avoids client preview/print differences.

## Validation

```sh
pip install -r api/requirements-test.txt
python -m pytest -q api firmware/tools/test_provision.py
```

The suite covers atomic concurrent starts and claims, device isolation, request idempotency and copies, pre/post-start expiry, restart durability, valid completion states, authentication, cancellation, templates, label validation and pixel-exact preview/raster equivalence.

## Fonts

Label/preview/job/template bodies accept `font`: `sans` (default), `sans-bold`, `serif`, `mono`, `pixel`. SQLite adds font columns with default sans on upgrade, retaining records and rasters. Legacy Sans idempotency fingerprints remain compatible. Pixel font is an authored5×7 uppercase ASCII font; permitted explicit sizes are7,14,21,28,35,42,49,56,63, or0auto. Size21 USB-C example matches the original physical test SHA-256. Test suite now contains27tests.

## Text formatting and symbols

`Label`, preview, job and template requests now accept these optional fields:

- `align`: `left`, `center` (default), `right`.
- `bold`, `italic`, `underline`, `border`, `invert`: booleans, default false.
- `line_spacing`: 0–16, default 4.
- `letter_spacing`: 0–6, default 0.

Styles persist as `style_json` and are expanded into public job/template JSON; existing records default to the former centered layout. Default-field omission preserves existing idempotency fingerprints and original pixel-test raster. Formatting does not rewrite already queued rasters. TrueType uses installed DejaVu weight/slant variants. Curated monochrome symbols `☺ ☹ ♥ ★ ✓ ✕ ⚠ ⚡ → ← ↔ ↑ ↓` use authored bitmaps in every font, including pixel, rather than relying on platform emoji fonts. Common emoji aliases 🙂 😊 😀 🙁 ❤ ⭐ ✅ ❌ and presentation selectors immediately after supported symbols are normalized for monochrome rendering; original text remains stored. Other color/non-BMP or ZWJ compositions return 422. Pixel lowercase ASCII still uses uppercase shapes; diacritics require another font.

## Device telemetry and manual refresh

`POST /api/agent/telemetry` uses the device bearer token and accepts only the reporting device's data. All fields are optional: `firmware_version` (bridge), `wifi_rssi`, `uptime_s`, `free_heap`, `printer_connected`, `printer_checked`, `model`, `firmware` (printer), `serial`, `battery_percent` (0–100 or null), `printer_status`, `last_error`. Bounds, booleans, strings, status values and extra fields are validated. No unsupported battery percentage is inferred.

`GET /api/agents` includes `telemetry`, `telemetry_received_at`, `printer_checked_at` and `paused`. Bridge-only heartbeat reports preserve the prior printer identity and timestamps. `printer_checked=true` updates the checked timestamp and clears old battery/status when the new probe omits them, preventing stale measurements from appearing current. Previously observed model, firmware and serial survive unsuccessful probes; the UI must label their timestamps honestly.

Admin `POST /api/agents/{id}/refresh` sets a pending probe flag. An idle `POST /api/agent/claim` returns 204 with `X-Printer-Refresh: 1`; the flag remains until an actual `printer_checked=true` report. Jobs take priority, and active printing does not trigger a probe header.

Admin `POST /api/agents/{id}/pause` with `{ "paused": true }` prevents new claims for firmware maintenance. Existing leases may still start/complete so the operator can wait for in-flight jobs to finish before restarting hardware. Completion is always allowed. Unpause with false. This does not cancel or delete queued jobs.

Validation after this expansion: 111 tests passed, covering text styles, all curated symbols across fonts, exact original pixel hash, migrations/idempotency, telemetry isolation/validation, stale-value clearing, refresh and maintenance pause.

## QR and accounts

Labels accept `kind: text|qr` (default text). QR content is encoded into the same monochrome preview and print raster with an integer module scale and quiet zone. Overly dense content returns 422. User accounts use Argon2 password hashes, server-side sessions, forced bootstrap setup, login throttling and an administrator-only registration toggle. Shared printer workspace is intentional in this MVP.
