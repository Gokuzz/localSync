# Desktop Backend

Python/FastAPI backend foundation for localSync desktop backup receiving.

Phase 5 implements application bootstrap, configuration, SQLite/Alembic migration infrastructure, safe local filesystem storage primitives, structured application errors, logging setup, paired-device authentication, pairing-session completion, local admin CLI, protected file check/upload endpoints, resumable upload-session endpoints, and tests. Phase 6 adds a lifecycle-managed DNS-SD/mDNS advertisement for locator discovery.

It does not implement automatic media backup, manual Android document transfer, desktop UI, or cloud functionality.

## Setup

```powershell
cd desktop/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

```powershell
cd desktop/backend
python -m uvicorn app.main:app --reload
```

Authenticated real-device flows should run over HTTPS with the generated local TLS identity:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile data\security\server-cert.pem --ssl-keyfile data\security\server-key.pem
```

Health endpoint:

```text
GET /api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

Authenticated transfer endpoints:

```text
POST /api/v1/files/check
POST /api/v1/files
POST /api/v1/uploads
GET /api/v1/uploads/{upload_id}
PUT /api/v1/uploads/{upload_id}
POST /api/v1/uploads/{upload_id}/complete
```

Normal device requests use `Authorization: Bearer <device-credential>`.

Create pairing sessions and manage paired devices locally:

```powershell
python -m app.cli pairing create --server-url https://<laptop-lan-ip>:8000
python -m app.cli devices list
python -m app.cli devices revoke <device-id>
python -m app.cli devices activate <device-id>
```

`devices activate` clears `revoked_at` for an existing paired device so Phase 5 validation can quickly retest the same credential. It does not merge device namespaces, issue a new credential, or claim backups from another paired device.

`POST /api/v1/files` uses a raw streaming request body. Metadata is supplied through headers:

- `X-localSync-Filename`
- `X-localSync-Size`
- `X-localSync-Sha256`
- optional `X-localSync-Content-Type`

Authenticated principal identity selects the device namespace. Client-supplied `device_id` is not authorization proof.

`POST /api/v1/files` is legacy and non-resumable. New development clients should prefer `/api/v1/uploads`.

Resumable uploads use raw PUT request bodies with `X-localSync-Offset` and `Content-Length`. The backend accepts only the authoritative partial-file offset, flushes/fsyncs accepted chunks before committing the new offset, and verifies full SHA-256 before finalizing.

## Validate

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic current
```

## Configuration

Configuration is loaded from environment variables.

- `LOCALSYNC_ENV`: `development`, `test`, or `production`; defaults to `development`.
- `LOCALSYNC_DATA_ROOT`: localSync data root; defaults to `data`.
- `LOCALSYNC_DATABASE_URL`: optional SQLAlchemy database URL; defaults to SQLite at `<data-root>/localsync.db`.
- `LOCALSYNC_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; defaults to `INFO`.
- `LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE`: maximum resumable PUT request size in bytes; defaults to `16777216`.
- `LOCALSYNC_SERVER_PORT`: configured HTTPS port and DNS-SD advertised port; defaults to `8000`.
- `LOCALSYNC_DISCOVERY_ENABLED`: enables `_localsync._tcp.` advertisement; defaults to `true`.
- `LOCALSYNC_DISCOVERY_INSTANCE_NAME`: optional DNS-SD display name.

Alembic uses the same application configuration. For example, this migrates and runs against `data-real-device/localsync.db`:

```powershell
$env:LOCALSYNC_DATA_ROOT = "data-real-device"
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

If `LOCALSYNC_DATABASE_URL` is set, both Alembic and FastAPI use that explicit database URL.

Phase 6 discovery uses `zeroconf` (resolved as `0.151.3` in the current repository environment) to advertise `protocol=1`, `tls=required`, `host=localsync.local`, and the advisory canonical `spki-sha256:` fingerprint. It never advertises credentials or pairing secrets. Allow UDP 5353 and the configured HTTPS TCP port on the Windows Private profile only when required by local firewall policy; mDNS may be unavailable on isolated or multicast-blocked networks.

The storage layout derives temporary and final roots from the data root:

```text
<data-root>/
    .localsync-temp/
    backups/
```

Tests override roots and databases with temporary paths.

## Database

Alembic is configured with:

- `0001_baseline`
- `0002_stored_files`
- `0003_upload_sessions`
- `0004_pairing_and_devices`

`stored_files` stores completed transfer metadata. `upload_sessions` stores resumable transfer metadata, offsets, and relative partial paths. `paired_devices` and `pairing_sessions` store authentication metadata and verifiers only. Actual file bytes remain normal filesystem files under the configured data root.
