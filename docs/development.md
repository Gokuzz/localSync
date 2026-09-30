# Development

This repository has a desktop backend, fake-device transfer foundation, Android manual media-backup client, Phase 5 pairing/authentication, and Phase 6 foreground local-network discovery. Additional tooling will be added as production hardening and frontend components are introduced.

## Expected Workflow

- Read root and scoped `AGENTS.md` files before meaningful implementation.
- Use an ExecPlan for complex, security-sensitive, cross-platform, or multi-step work.
- Keep changes scoped to the task.
- Update docs when implementation changes architecture, protocol, security, storage semantics, public APIs, platform behavior, or developer workflow.
- Run relevant tests, formatters, linters, type checks, and builds once they exist.

## Dependency Policy

Prefer simple, testable abstractions and platform capabilities. Add production dependencies only when they materially reduce risk or complexity, and document why they are needed.

## Data Safety

Treat backup behavior as safety-critical. Incomplete, corrupted, or unverified uploads must not be represented as successful backups.

## Desktop Backend

Setup:

```powershell
cd desktop/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run:

```powershell
cd desktop/backend
python -m uvicorn app.main:app --reload
```

Validate:

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic current
```

The backend uses `pyproject.toml`, standard `venv`, and `pip`. Production and development dependencies are separated with the `dev` extra.

Useful backend environment variables:

- `LOCALSYNC_ENV`: `development`, `test`, or `production`; defaults to `development`.
- `LOCALSYNC_DATA_ROOT`: localSync data root; defaults to `data`.
- `LOCALSYNC_DATABASE_URL`: optional SQLAlchemy database URL; defaults to SQLite at `<data-root>/localsync.db`.
- `LOCALSYNC_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; defaults to `INFO`.
- `LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE`: maximum resumable PUT request size in bytes; defaults to `16777216`.
- `LOCALSYNC_SERVER_PORT`: HTTPS port advertised through DNS-SD; defaults to `8000` and must match the Uvicorn port.
- `LOCALSYNC_DISCOVERY_ENABLED`: enables the backend `_localsync._tcp.` advertisement; defaults to `true`.
- `LOCALSYNC_DISCOVERY_INSTANCE_NAME`: optional human-readable DNS-SD service instance name.

Alembic resolves its runtime database URL through the same application settings as FastAPI. If `LOCALSYNC_DATA_ROOT` or `LOCALSYNC_DATABASE_URL` is set, run `python -m alembic upgrade head` in the same shell before starting Uvicorn so migrations apply to the same SQLite database the app will use.

Phase 5 generates persistent local TLS identity files under `<data-root>/security/`. Generated certificate/key files are runtime data and must not be committed.

Create a pairing session after migrations:

```powershell
cd desktop/backend
python -m app.cli pairing create --server-url https://<laptop-lan-ip>:8000
```

List, revoke, and reactivate paired devices:

```powershell
python -m app.cli devices list
python -m app.cli devices revoke <device-id>
python -m app.cli devices activate <device-id>
```

`devices activate` is a local Phase 5 validation/admin helper. It clears `revoked_at` for the same paired device credential and namespace. It does not create a new credential, merge namespaces, or make one paired device inherit another device's stored-file records.

Run the authenticated backend over HTTPS with the generated identity:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile <data-root>\security\server-cert.pem --ssl-keyfile <data-root>\security\server-key.pem
```

Authenticated real-device flows must use HTTPS. Tests may use ASGI/TestClient without TLS when `LOCALSYNC_ENV=test`.

Phase 6 advertises the configured HTTPS port over mDNS UDP 5353 using `_localsync._tcp.`. The backend uses the declared `zeroconf>=0.132` dependency; the current repository environment resolves it to `0.151.3`. Zeroconf runs on its own internal loop so synchronous registration does not block FastAPI startup. On Windows, allow the configured HTTPS TCP port and UDP 5353 on the Private network profile only if the firewall prompts or local policy blocks discovery; do not disable the firewall globally. Some guest/corporate Wi-Fi networks block multicast or isolate clients. Android keeps the manual HTTPS locator fallback, and the fallback still uses the Phase 5 pinned server identity.

## Fake Device Client

Setup:

```powershell
cd tools/fake_phone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Pair and run against a local backend:

```powershell
cd tools/fake_phone
python -m fake_phone pair --server https://127.0.0.1:8000 --pairing-id <pairing-id> --pairing-code <pairing-code> --server-fingerprint <fingerprint> --config .\fake-device.json
python -m fake_phone backup --config .\fake-device.json --source ./sample-media --chunk-size-mib 8
```

Validate:

```powershell
cd tools/fake_phone
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

The fake client is a development utility. Its local config stores a bearer credential in a plain JSON file and is not Android-grade secure storage. It observes the server SPKI fingerprint before sending the pairing code and preflights the stored fingerprint before bearer-authenticated backup requests.

## Android Client

Toolchain selected in Phase 4:

- Gradle wrapper 9.6.1.
- Android Gradle Plugin 9.3.0.
- Kotlin/Compose compiler plugin 2.3.10.
- KSP 2.3.10.
- Compose BOM 2026.06.00.
- `minSdk = 29`, `compileSdk = 36`, `targetSdk = 36`.

Build and validate:

```powershell
cd android
.\gradlew.bat assembleDebug
.\gradlew.bat test
.\gradlew.bat lint
```

Run Gradle validations sequentially on Windows. Parallel Gradle invocations can contend over Kotlin incremental compilation caches.

Run instrumented tests only when an emulator or device is attached:

```powershell
cd android
.\gradlew.bat connectedDebugAndroidTest
```

For local backend testing, start the desktop backend over HTTPS and enter its LAN locator URL in the Android app's Developer Settings screen. A physical phone normally needs the laptop LAN address, not `127.0.0.1`; the Android emulator usually reaches the host at `https://10.0.2.2:8000`.

Phase 5 Android builds store paired credentials through an Android Keystore-backed credential boundary. Pairing first observes the presented SPKI fingerprint without sending the pairing code, requires explicit user confirmation, then submits the pairing code over a pinned TLS client. Normal backup traffic uses `localsync.local` for hostname verification and a scoped OkHttp DNS mapping to the current LAN locator before adding `Authorization: Bearer`. Phase 6 adds foreground `Find Laptop` discovery through platform `NsdManager`; it verifies the existing pin before updating the locator and does not start backups automatically.

The Android app currently targets SDK 36 and uses `CHANGE_WIFI_MULTICAST_STATE` only for a scoped multicast lock on platform combinations that need it during active discovery. When the project later targets Android 17/API 37, revisit `ACCESS_LOCAL_NETWORK` and newer system-mediated NSD picker APIs.
