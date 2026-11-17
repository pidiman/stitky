# P15 Hub API

[Project](../README.md) · [Architecture](../docs/ARCHITECTURE.md) · [Deployment](../docs/DEPLOY.md)

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

Label/preview/job/template bodies accept `font`: `sans` (default), `sans-bold`, `serif`, `mono`, `pixel`. SQLite adds font columns with default sans on upgrade, retaining records and rasters. Legacy Sans idempotency fingerprints remain compatible. Pixel font is an authored5×7 uppercase ASCII font; permitted explicit sizes are7,14,21,28,35,42,49,56,63, or0auto. Size21 USB-C example matches the original physical test SHA-256. The pixel-font tests preserve the original raster.

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

The text-formatting and telemetry suite covers text styles, all curated symbols across fonts, exact original pixel hash, migrations/idempotency, telemetry isolation/validation, stale-value clearing, refresh and maintenance pause.

## QR and accounts

Labels accept `kind: text|qr` (default text). QR content is encoded into the same monochrome preview and print raster with an integer module scale and quiet zone. Overly dense content returns 422. User accounts use Argon2 password hashes, server-side sessions, forced bootstrap setup, login throttling and an administrator-only registration toggle. Shared printer workspace is intentional in this MVP.

## Endpoint map

Paths below describe the current implementation. Built-in OpenAPI/Swagger UI is disabled. Studio access means an authenticated, fully configured user session; mutating session requests need X-CSRF-Token.

| Method and path | Access | Purpose |
|---|---|---|
| GET /api/health | Public | API and database health |
| GET /api/auth/config | Public | Registration availability |
| POST /api/auth/login | Public | Login and issue session |
| GET /api/auth/me | Session | Current user and CSRF token |
| POST /api/auth/setup | Bootstrap session + CSRF | Mandatory first account setup |
| POST /api/auth/logout | Session + CSRF | Revoke current session |
| POST /api/auth/register | Public, only when enabled | Create ordinary user account |
| GET, PUT /api/auth/settings | Administrator | Read/change registration setting |
| POST /api/preview | Studio | Render monochrome PNG |
| GET, POST /api/jobs | Studio | List recent jobs / create jobs |
| POST /api/jobs/{id}/cancel | Studio | Cancel queued job |
| GET, POST /api/templates | Studio | List / save templates |
| DELETE /api/templates/{id} | Studio | Remove template |
| GET /api/agents | Studio | Devices and telemetry |
| POST /api/agents | Administrator | Create device and reveal token once |
| POST /api/agents/{id}/pause | Administrator | Pause/unpause future claims |
| POST /api/agents/{id}/refresh | Studio | Request printer information read |
| POST /api/agent/claim | Device bearer | Claim own next job or return 204 |
| POST /api/agent/jobs/{id}/start | Device bearer + lease | Authorize first physical attempt |
| POST /api/agent/jobs/{id}/complete | Device bearer + lease | Report terminal outcome |
| POST /api/agent/telemetry | Device bearer | Report bridge/printer data |

The separate maintenance bearer can access studio/administrator operations only subject to its configured network restriction. Do not embed it into browser storage or public examples.

Common responses: 401 unauthenticated; 403 unauthorized, unfinished setup or CSRF/origin rejection; 409 conflicting job state, duplicate account or idempotency conflict; 422 invalid content or schema; 429 login throttling. Inspect the response detail rather than retrying a physical print blindly.

## QR captions

`qr_caption` is optional and defaults to an empty string. For `kind: qr`, a nonempty caption places the complete QR in the left 96 × 96 region and text in the right 212 × 96 region starting at x=108. The QR keeps the same integer module scale and four-module quiet zone. Empty/whitespace-only captions retain the original centered QR layout.

Captions accept up to 120 characters and four lines; surrounding whitespace is trimmed. Font, font_size, align, bold, italic, underline and spacing apply to the caption. Border and inversion remain forbidden for QR. Overflow or unsupported characters return 422; a nonempty caption on a text-only label is rejected.

Captions persist in job/template style_json without a schema change. Existing records default to an empty caption, existing stored rasters stay unchanged and empty captions preserve legacy request fingerprints. Preview and print raster share identical pixels. Firmware changes are not required.

## Multi-printer profiles

GET /api/profiles lists the supported P15 and Brother profiles. Labels, templates and jobs accept profile_id (default p15_40x12), length_mm (20–200, default 50; continuous Brother only) and auto_cut (boolean, default true). Devices accept printer_model p15 or brother_ql810w at creation. Enqueue rejects a device/profile mismatch.

Brother jobs store native monochrome raster instructions with payload_format brother-raster-v1, raster_width 720 and native raster_height. Their claim returns size, sha256, payload_path, media_width_mm and media_length_mm instead of base64. GET /api/agent/jobs/{id}/payload requires the device bearer and X-Lease-Token and only returns a leased Brother payload. Existing P15 claim shape, rasters and fingerprints are preserved. New profile metadata uses style_json; geometry/format columns and printer_model are added with legacy defaults.

Telemetry accepts media_ready as a bounded printable string, clears stale media on a new unanswered printer probe, and never assumes an IPP job is physically verified. See [Brother operating notes](../docs/BROTHER.md).
