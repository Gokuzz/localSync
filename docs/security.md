# Security

This document separates the desired security model from what currently exists.

## Currently Implemented Security

Phase 5 has started replacing development-only namespaces with paired-device authentication:

- The backend generates a persistent self-signed local TLS identity under the configured data root.
- The canonical server fingerprint is `spki-sha256:<base64url>` over SubjectPublicKeyInfo.
- Pairing sessions are short-lived, one-time use, verifier-backed, and attempt-limited.
- Paired devices use server-generated device IDs and 256-bit opaque bearer credentials.
- SQLite stores only credential verifiers, not plaintext device credentials.
- `GET /api/v1/health` exposes only a minimal status response.
- Transfer endpoints require `Authorization: Bearer <device-credential>`.
- Authenticated principal identity, not client-supplied `device_id`, selects the device namespace.
- Upload-session status, append, and complete enforce owner-device access.
- Revoked credentials are rejected.
- Completed backup files and `StoredFile` records are not deleted by revocation.
- The local backend CLI can reactivate an existing revoked paired device by clearing `revoked_at`. This re-enables the same device credential and namespace for development validation; it does not transfer ownership or create a new trust relationship.
- fake_phone has pairing/authenticated backup commands for development testing and observes the server SPKI fingerprint before sending pairing codes.
- Android has a Keystore-backed credential storage boundary.
- Android pairing observes the presented TLS SPKI fingerprint before sending the pairing code, requires explicit user confirmation, then completes pairing over a pinned TLS client.
- Android normal authenticated traffic uses the stable logical TLS hostname `localsync.local`, maps it to the configured LAN locator through scoped OkHttp DNS, keeps hostname verification enabled, and attaches `Authorization` only on the pinned client path.
- Phase 5 real-device pinned-TLS validation has been completed for the local authenticated backup flow.
- `POST /api/v1/files/check` checks exact stored content by development namespace, size, and full SHA-256.
- `POST /api/v1/files` remains a complete non-resumable raw-body legacy development upload.
- `/api/v1/uploads` supports development-only resumable upload sessions with explicit offsets.
- Configuration uses environment variables and contains no committed secrets.
- Local filesystem storage utilities derive temporary and final directories from one configured data root.
- Storage path utilities reject traversal, absolute path injection, unexpected path separators, and paths escaping configured roots.
- Final path reservation rejects accidental overwrite.
- Partial files are separated under `.localsync-temp/`; finalized backup files live under `backups/`.
- Final files are created only after received size and full SHA-256 match declared metadata.
- Resumable chunks are written to partial files, flushed/fsynced once per accepted PUT request, and only then is the accepted offset committed to SQLite.
- Actual partial-file length is authoritative for resume. If the database claims bytes that are missing from the partial file, the session is marked failed rather than silently skipping bytes.
- Client filenames and device IDs are untrusted metadata. The server generates storage paths.
- Legacy development data may still contain old namespace strings. New authenticated transfers use server-generated paired-device IDs.
- Revoking device A and pairing the same physical phone again creates a separate device B with a new server-generated authenticated namespace. Existing backups remain associated with device A, and device B does not automatically inherit or claim device A's `StoredFile` records. This may cause the same media to upload again after revoke/re-pair, but it avoids unsafe ownership transfer.
- `upload_id` is an identifier only. Knowing or choosing an upload ID does not prove authorization.
- A simple free-space preflight guard exists, but it is not quota enforcement or storage reservation.
- Structured application errors avoid returning raw internal exceptions by default.
- The Android app reads accessible photo/video bytes through `ContentResolver`/MediaStore and streams them without decoding, resizing, recompressing, transcoding, or storing media bytes in Room.
- Android Room state is metadata only: media inventory, backup status, hashes, backend IDs, and server-controlled relative paths.
- Android source-media disappearance marks local inventory missing but does not call any backend deletion endpoint.
- Android debug builds still contain cleartext HTTP development configuration, but authenticated real-device flow must use HTTPS.
- Android local installation IDs such as `android-dev-<uuid>` are advisory client metadata, not authentication.

localSync still does not claim discovery security, internet exposure safety, quota enforcement, or tamper-proof endpoint identity. Bearer credentials remain replayable if stolen until revoked.

Phase 6 discovery is intentionally not an authentication mechanism. The backend advertises `_localsync._tcp.` with non-secret TXT metadata, including an advisory `spki-sha256:` hint. TXT records and service names are unauthenticated and spoofable. Android accepts a discovered locator only after the existing pinned TLS client verifies the actual persistent server SPKI identity; discovery never changes the stored pin, device credential, paired device ID, or revoked state. No bearer credential is attached to the discovery preflight.

Phase 5 intentionally does not merge device namespaces, reuse revoked device IDs, associate devices by filename, associate devices by Android local instance ID alone, or implement cross-device deduplication. A future design may explicitly separate authenticated paired-device identity, source/library identity, and stored content identity, or provide laptop-admin-approved credential rotation/re-authorization.

## Desired Security Model

- Only paired and authenticated devices may upload.
- Pairing credentials are short-lived during setup and protected after enrollment.
- Long-lived device secrets must not appear in logs.
- Upload endpoints validate authorization, size, offsets, filenames, paths, and content finalization state.
- Files are written to controlled storage locations only.
- Partial uploads are isolated from finalized backups.
- Corrupted or incomplete uploads fail closed.

## Threats and Required Mitigations

### Untrusted Device on Same Wi-Fi

Threat: another device discovers the desktop service and attempts upload or probing.

Required mitigation: expose only authenticated upload operations after pairing; keep health/discovery minimal.

### Unauthorized Upload

Threat: attacker fills disk or writes unwanted files.

Required mitigation: require device authorization, enforce quotas, validate transfer metadata, and reject unpaired clients.

### Stolen or Reused Pairing Token

Threat: pairing token is captured and reused.

Required mitigation: short token lifetime, one-time use, explicit confirmation, and device credential rotation strategy.

### Path Traversal and Malicious Filenames

Threat: client sends paths like `../` or reserved Windows names.

Required mitigation: treat client filenames as metadata, sanitize display names, generate server-controlled storage paths, and never join untrusted paths directly.

### Corrupted Upload

Threat: interrupted or modified bytes are finalized.

Current Phase 3 mitigation: verify expected size and full SHA-256 before finalization; invalid completed-session hash removes the partial file, marks the session failed, and creates no completed backup.

### Spoofed Device

Threat: attacker pretends to be a known device.

Required mitigation: authenticate requests with credentials bound to a paired device record.

### Accidental File Overwrite

Threat: two files resolve to the same destination name.

Required mitigation: use collision-resistant storage naming and metadata records rather than trusting original filenames as unique paths.

### Credentials in Logs

Threat: tokens are leaked through debug or access logs.

Required mitigation: redact authorization headers, tokens, pairing codes, and secrets.

### Excessive Disk Usage

Threat: very large or repeated uploads exhaust disk.

Required mitigation: quota checks, expected-size validation, partial cleanup policy, and clear error reporting.

### Denial Through Giant Uploads

Threat: client starts enormous transfers or many sessions.

Required mitigation: per-device limits, request size checks, session expiration, and streaming writes.

## Claims Not Yet Made

localSync does not claim quota enforcement, internet exposure safety, or tamper-proof endpoint identity.

Phase 5 transfer paths require paired-device bearer authentication and have completed local real-device pinned-TLS validation. localSync still does not claim production-ready internet exposure security.

Abandoned resumable partials are not automatically deleted in Phase 3. They may consume disk until an explicit future cleanup feature is added.
