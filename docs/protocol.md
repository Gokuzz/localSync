# Protocol

This is the protocol contract design. Phase 5 adds paired-device authentication over the existing generic file transfer and resumable upload foundation. Phase 6 adds a DNS-SD locator advertisement without changing transfer endpoints.

### Local Network Discovery

The backend advertises `_localsync._tcp.` over DNS-SD/mDNS when discovery is enabled. The advertised port is the configured HTTPS listener port. TXT fields are:

- `protocol=1`
- `tls=required`
- `host=localsync.local`
- `spki=spki-sha256:<base64url-sha256-SPKI>`

The `spki` value is an advisory candidate filter only. TXT records, service names, and resolved addresses are untrusted. An already-paired client must use the Phase 5 pinned TLS identity check before accepting a locator or sending an authenticated request. Discovery never changes the trusted identity and does not trigger Backup Now.

The protocol is platform-neutral and versioned under `/api/v1/`. It uses generic Device, Client, UploadSession, MediaItem, Transfer, and Backup terminology.

## Principles

- Local-network first.
- Authenticated devices only after pairing.
- Resumable uploads for large files.
- Idempotent operations where practical.
- Temporary upload state must not appear as completed backup state.
- Photos and videos may be automatic backup content. Documents and arbitrary files are manual transfer content in V1.

## Endpoint Concepts

### Authenticated Requests

Normal device requests use:

```http
Authorization: Bearer <device-credential>
```

The authenticated principal supplies device identity. Client-supplied `device_id` values and `X-localSync-Device-Id` are no longer authorization proof.

`GET /api/v1/health` remains public. Pairing completion is scoped to a valid pairing session. Pairing-session creation, device listing, and revocation are local CLI operations in Phase 5.

### Health

- `GET /api/v1/health`
- Returns service availability and protocol version.

### File Check

- `POST /api/v1/files/check`
- Development-only exact-content check for a generic device namespace.

Request body:

```json
{
  "filename": "normal.jpg",
  "size": 123,
  "sha256": "<64 lowercase hex chars>"
}
```

Response when exact content is already stored:

```json
{
  "exists": true,
  "stored_file_id": "<opaque id>",
  "stored_path": "<server-controlled relative storage key>"
}
```

Response when upload is required:

```json
{
  "exists": false
}
```

Identity is authenticated device namespace plus size and full SHA-256. Filename, extension, MIME type, and short hashes are not proof of identity.

### Phase 2 Legacy File Upload

- `POST /api/v1/files`
- Development-only complete non-resumable file upload.

Phase 2 uses a raw streaming request body for file bytes. Metadata is supplied through headers:

- `X-localSync-Filename`
- `X-localSync-Size`
- `X-localSync-Sha256`
- optional `X-localSync-Content-Type`

The server streams bytes incrementally into `.localsync-temp`, computes SHA-256 while writing, verifies declared size and full SHA-256, then finalizes into `backups` only after validation succeeds.

The client never supplies a server destination path. Completed paths are server-controlled and relative to backup storage.

This endpoint remains for legacy development compatibility. New resumable-capable clients should prefer `/api/v1/uploads`.

Interrupted `/api/v1/files` transfers are not resumable. A later attempt restarts from byte zero.

### Phase 3 Resumable Upload Sessions

Phase 3 adds generic upload sessions under `/api/v1/uploads`.

`POST /api/v1/uploads` creates or recovers a resumable upload session. The request body contains metadata only:

```json
{
  "filename": "video.bin",
  "expected_size": 12345,
  "expected_sha256": "<64 lowercase hex chars>",
  "content_type": "application/octet-stream"
}
```

If the exact content is already completed for the device namespace, the server returns:

```json
{
  "status": "already_stored",
  "stored_file_id": "<opaque id>",
  "stored_path": "<server-controlled relative storage key>"
}
```

If upload is needed, the server returns:

```json
{
  "status": "receiving",
  "upload_id": "<server uuid>",
  "next_offset": 0,
  "expected_size": 12345,
  "chunk_size_hint": 8388608
}
```

Repeated creation for the same authenticated device, filename, expected size, and expected SHA-256 recovers the existing session instead of requiring the client to persist upload IDs locally.

`GET /api/v1/uploads/{upload_id}` returns session state and the authoritative `next_offset`. The server reconciles the session against actual partial-file length before responding.

`PUT /api/v1/uploads/{upload_id}` appends raw request-body bytes. Required headers:

- `X-localSync-Offset`: non-negative integer byte offset.
- `Content-Length`: required declared chunk size.

The server accepts only `X-localSync-Offset == actual partial-file length`. On success it writes the streamed request body into `.localsync-temp`, flushes and fsyncs once for the request, persists the new offset, and returns the next offset.

If the offset is behind or ahead, the server does not append bytes and returns a structured `409 offset_mismatch` error with `details.expected_offset`.

The default fake-client chunk size is 8 MiB. The default server maximum accepted chunk request is 16 MiB through `LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE`. The protocol does not require every client to use the same chunk size.

`POST /api/v1/uploads/{upload_id}/complete` completes an upload idempotently. The server reconciles offset, requires the partial length to equal `expected_size`, rereads the full partial file incrementally, verifies the full SHA-256, finalizes into `backups`, persists or reconciles `stored_files` metadata, and marks the session `completed`.

If completion is called before all bytes arrive, the server returns `409 upload_incomplete` with `details.next_offset`. If full SHA-256 mismatches, the session is marked `failed`, the invalid partial is removed, and no completed backup appears.

Persisted upload-session states are `receiving`, `completed`, and `failed`.

`upload_id` is an identifier, not an authorization credential. The authenticated device must own the upload session.

### Pairing

- CLI: `python -m app.cli pairing create`
- Device API: `POST /api/v1/pairing-sessions/{pairing_id}/complete`

Pairing sessions are short-lived, one-time use, and attempt-limited. Pairing completion validates the pairing code, creates a paired-device record, returns the plaintext device credential once, and stores only a credential verifier. Pairing-session creation and revocation are local CLI operations in Phase 5, not LAN-accessible admin APIs.

### Device Authentication

Authenticated requests identify a paired device using a high-entropy opaque bearer credential. Credentials must not appear in logs.

Revocation sets `revoked_at` and rejects subsequent requests. Completed backup files remain.

### Existence Check

- Future: `POST /api/v1/media/check` or an evolved generic check endpoint.
- Client asks whether candidate media already exists or has an active upload session.

Conceptual request fields:

- `device_id`
- `client_media_id`
- `media_kind`
- `expected_size`
- optional `sha256`
- optional source timestamps

Conceptual response fields:

- `known`
- `backup_id`
- `upload_session_id`
- `next_offset`
- `status`

### Future Authenticated Upload Session Evolution

Future production revisions may evolve the development `/api/v1/uploads` contract with pairing/authentication, transfer kind, idempotency keys, and retention policy.

Conceptual request fields:

- `transfer_kind`: `automatic_media_backup` or `manual_file_transfer`
- `source_item_id`
- `filename`
- `content_type`
- `expected_size`
- optional `sha256`
- optional idempotency key

Conceptual response fields:

- `upload_session_id`
- `next_offset`
- `chunk_size_hint`
- `expires_at`
- `status`

### Future Authenticated Upload Session Status

Future production revisions may extend `GET /api/v1/uploads/{upload_id}` with authenticated device context, transfer kind, and additional lifecycle metadata.

### Future Upload Chunk Extensions

Future production revisions may extend `PUT /api/v1/uploads/{upload_id}` with authenticated device context.

Required concepts:

- `offset`
- `content_length`
- bytes in request body
- authenticated device identity

The Phase 3 receiver validates that the offset matches actual partial-file length. A repeated old-offset request is rejected with the authoritative next offset so clients can recover safely.

### Future Complete Upload Extensions

Future production revisions may extend `POST /api/v1/uploads/{upload_id}/complete` with authenticated device context and transfer-kind-specific metadata.

### Manual Transfers

Manual transfers use the same upload-session mechanics with `transfer_kind = manual_file_transfer`. They are initiated by explicit user selection and must not become automatic arbitrary-file scanning.

## IDs

IDs should be opaque strings in API contracts. Do not encode platform identity in ID names or formats.

## Error Semantics

Use structured errors with stable machine-readable codes and human-readable messages. Important error categories include authentication failure, authorization failure, invalid offset, size mismatch, hash mismatch, disk limit exceeded, unsupported media kind, expired session, and conflict.

## Retry and Idempotency

Session creation should support idempotency keys to avoid duplicate sessions after network retries. Chunk upload should tolerate retry of already accepted bytes when safely verifiable. Completion should be idempotent after successful finalization.

## Unresolved Areas

- Pairing UX and cryptographic details.
- Exact authentication token format and rotation.
- Final request/response schemas.
- Disk quota policy.
- Whether chunks require per-chunk hashes in addition to whole-file SHA-256.
