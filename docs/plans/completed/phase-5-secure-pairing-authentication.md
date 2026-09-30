# Phase 5 Secure Pairing and Device Authentication

## Purpose / User Outcome

Replace development-only device namespaces with a real paired-device model.

After Phase 5 implementation, a user should be able to pair an Android installation with the laptop localSync backend, store durable device credentials, authenticate backup protocol requests, revoke a paired device, and have revoked or unpaired clients rejected.

Phase 5 must make the existing transfer APIs safer without changing the core backup semantics:

- completed backups are not deleted by revocation;
- media remains opaque bytes;
- resumable upload sessions remain platform-neutral;
- Android is the first real client, not the protocol definition.

## Scope

Phase 5 includes planning implementation for:

- persistent laptop/server identity for local trusted transport;
- short-lived one-time pairing sessions;
- durable paired-device credentials;
- authenticated-device principal resolution in the backend;
- authenticated coverage for existing file and upload APIs;
- upload-session ownership enforcement;
- revocation and local unpair behavior;
- fake-client pairing/auth support for repeatable non-Android testing;
- Android secure credential and server-identity storage;
- minimal Android pairing UI and authenticated OkHttp client behavior;
- security tests, integration tests, and real-device validation;
- documentation and ADRs for the security model.

## Out of Scope

Do not implement Phase 6 or later work:

- automatic Wi-Fi discovery;
- mDNS/NSD;
- WorkManager or automatic background backup;
- charging constraints or scheduling;
- React desktop UI;
- cloud identity, user accounts, OAuth, Firebase, or remote relay;
- arbitrary document transfer;
- laptop-to-phone transfer;
- QR-only UX if manual pairing is sufficient for Phase 5;
- production internet access;
- automatic backup deletion, pruning, or retention;
- media transcoding, thumbnails, EXIF extraction, or gallery polish.

Phase 5 should not redesign the resumable transfer protocol, chunking semantics, storage layout, or Android media pipeline except where authentication requires request changes.

## Current System Context

Repository state inspected before planning:

- Root and nested AGENTS instructions require platform-neutral protocol terminology, byte-preserving media transfer, no silent data loss, no cloud dependency, explicit validation, and ExecPlan maintenance.
- `docs/current-state.md` records Phase 4 complete. A real Android phone transferred photos to the laptop backend successfully. Real Android interrupted/resume validation is not yet recorded complete.
- ADR-0001 requires platform-neutral protocol/domain concepts.
- ADR-0002 requires one-way deletion-safe backup behavior.
- ADR-0003 requires opaque byte transfer, filesystem media storage, and SHA-256 integrity verification.
- ADR-0004 defines server-persisted resumable upload sessions, append-only offsets, authoritative partial-file length, and notes that current `device_id` and `upload_id` are identifiers, not authentication.
- Backend APIs currently expose:
  - `GET /api/v1/health`
  - `POST /api/v1/files/check`
  - `POST /api/v1/files`
  - `POST /api/v1/uploads`
  - `GET /api/v1/uploads/{upload_id}`
  - `PUT /api/v1/uploads/{upload_id}`
  - `POST /api/v1/uploads/{upload_id}/complete`
- Current backend request models trust client-supplied `device_id`:
  - `/files/check` request body includes `device_id`.
  - `/files` legacy upload uses `X-localSync-Device-Id`.
  - `/uploads` create request body includes `device_id`.
  - upload status, append, and complete identify sessions only by `upload_id`.
- Existing backend `stored_files.device_id` and `upload_sessions.device_id` are logical namespaces. They are not authenticated identities.
- Existing Android settings store a development server URL and editable `android-dev-<uuid>` device namespace in regular `SharedPreferences`.
- Existing Android network client uses OkHttp and sends `device_id` in JSON request bodies. It sends raw resumable PUT bodies with `X-localSync-Offset`.
- Existing fake client takes `--device-id` and uses the same unauthenticated resumable protocol.
- Existing desktop backend uses SQLite/Alembic, FastAPI, Pydantic, SQLAlchemy, and local filesystem storage. Alembic now resolves the database URL through application settings.
- Existing security docs explicitly state there is no pairing, no authentication, no production TLS, and device IDs are not identity proof.

## Assumptions

- Phase 5 may add small reputable cryptography support on the backend if required for persistent local TLS identity. Python's standard library does not provide a practical X.509 certificate generation API.
- The backend remains a local single-machine app with SQLite. No central auth service or cloud account exists.
- The desktop React UI does not exist yet, so laptop-side pairing and revocation can be implemented through local administrative CLI commands or loopback-only development/admin endpoints.
- Phase 6 discovery is not available. Pairing must work with a manually provided server address or an address embedded in a pairing artifact.
- The first Android pairing UX can be manual code entry if QR scanning/generation creates disproportionate dependency or implementation cost. The protocol should still be QR-compatible.
- Existing development data may contain namespace strings in `stored_files.device_id` and `upload_sessions.device_id`; Phase 5 should document migration behavior rather than silently corrupt or delete backups.

## Architecture / Approach

### Threat Model

Phase 5 addresses:

- another device on the same LAN calling upload/check/complete APIs;
- arbitrary clients choosing another `device_id`;
- unauthenticated access to upload sessions by guessing or learning `upload_id`;
- replay of expired or consumed pairing artifacts;
- brute force against human-entered pairing codes;
- revoked devices continuing to use transfer APIs;
- credentials being logged or returned by normal APIs;
- credentials stored as ordinary plaintext on Android;
- accidental treatment of development namespace values as authentication.

Phase 5 does not fully address:

- compromised laptop OS or Android OS;
- malware running as the local user reading localSync runtime data;
- denial of service from a LAN peer before rate limiting is reached;
- credential replay by an attacker who already stole a valid device credential;
- internet-exposed deployments;
- discovery spoofing, because discovery is Phase 6;
- complete traffic privacy until the local TLS implementation is actually validated.

### Selected Authentication Model

Use a paired-device model with server-generated device IDs and high-entropy opaque device credentials.

At pairing completion:

1. the backend creates a `PairedDevice` row with a server-generated stable device ID;
2. the backend generates a random long-term device credential using a cryptographically secure RNG;
3. the backend stores only a verifier/hash of that credential;
4. the plaintext credential is returned once to the client over the paired, pinned TLS connection;
5. future device requests authenticate with `Authorization: Bearer <credential>`;
6. the backend resolves the authenticated principal and uses that device ID for ownership and storage namespace decisions.

Why this model:

- simpler than asymmetric per-device signatures;
- platform-neutral for Android, fake clients, iOS, NAS, and desktop senders;
- immediate revocation is straightforward because every request can check the backend database;
- no stateless token validation or user account infrastructure is needed;
- long random credentials have enough entropy that a fast verifier hash is acceptable when plaintext tokens are never stored server-side.

### JWT Decision

Do not use JWT in Phase 5.

localSync has one local server, no distributed services, no cloud identity provider, and a strong need for immediate revocation. JWT would add signing-key lifecycle, expiration, and revocation complexity without solving a current problem. A random opaque credential checked against the local database is simpler and more controllable.

### Bearer Credential Verifier

Use a high-entropy random credential, not a human password.

The server should store a non-plaintext verifier, such as SHA-256 over a versioned credential string or HMAC-SHA256 using a server-side secret if the implementation introduces one cleanly. Verification must use constant-time comparison.

Do not use bcrypt/Argon2 merely by habit. Password hashing is designed for low-entropy human passwords; localSync device credentials should be generated with enough entropy to make offline guessing impractical. If implementation selects a keyed HMAC verifier, document key storage and rotation implications.

### Laptop Identity and Transport Security

Authentication credentials must not be sent as reusable bearer secrets over unrestricted cleartext HTTP.

Phase 5 should introduce a persistent local laptop/server TLS identity:

- generate a self-signed certificate and private key on first setup;
- store them under runtime localSync-managed data/config storage, not in the repository;
- reuse them across backend restarts;
- use restrictive filesystem permissions where the platform allows;
- expose a public fingerprint or public-key pin for pairing;
- never log private key material.

Android should pin the paired server identity rather than relying on public CA trust for private LAN IP addresses. Since DHCP can change the laptop IP, trusted identity must be separate from network address. Phase 6 discovery can later find a new address for the same pinned server identity.

Implementation should prefer pinning the server certificate or public key fingerprint with narrowly scoped OkHttp TLS configuration. It must not install a global trust-all `TrustManager`.

Potential backend dependency:

- `cryptography` for certificate/key generation and fingerprint handling.

Do not add full PKI frameworks or external CA dependencies.

### Pairing Model

Use short-lived one-time pairing sessions.

Recommended API shape:

- local/admin side:
  - `POST /api/v1/pairing-sessions`
  - creates a short-lived pairing session and returns data suitable for display as a manual code and future QR payload.
- device side:
  - `POST /api/v1/pairing-sessions/{pairing_id}/complete`
  - consumes the pairing artifact, registers the device, and returns the long-term device credential once.

Because desktop UI does not exist, `POST /api/v1/pairing-sessions` should be accessible only through a local administrative path. The implementation should choose one of:

- a backend CLI command that creates and prints the pairing artifact; or
- a loopback-only endpoint guarded by client host checks.

Do not expose arbitrary LAN pairing-session creation.

Pairing session properties:

- expires quickly, for example 5 to 10 minutes;
- one-time use;
- stores a verifier for the pairing secret/code, not plaintext;
- tracks failed attempts;
- rejects expired or consumed sessions;
- can be cleaned up after expiry/consumption;
- is not a long-term credential.

Manual pairing code:

- acceptable as the first Phase 5 UX if entropy and attempt limits are sufficient;
- should be generated with secure randomness;
- should be short enough to type but long enough to resist trivial LAN guessing during the expiry window.

QR strategy:

- design the pairing artifact as versioned data that can be encoded as QR later;
- do not require QR scanning in the first implementation if it adds a large dependency;
- do not embed filesystem paths or unnecessary data;
- include only fields required to contact and verify the server and consume the pairing session.

Conceptual QR/manual artifact fields:

- protocol marker and version, for example `localsync-pairing-v1`;
- server URL or host/port for the current manual setup;
- server identity fingerprint or public-key pin;
- `pairing_id`;
- pairing secret/code;
- expiry timestamp.

### Server Address During Pairing

Discovery remains out of scope.

During Phase 5:

- Android may still require a manually entered server address;
- the pairing artifact may include the current server address for convenience;
- identity pinning must allow the address to change later without requiring a new trusted identity.

The user-facing Android UI must label this as local/development setup until discovery and production UX exist.

### Backend Data Model

Add new tables using Alembic. Do not modify existing migrations.

#### `paired_devices`

Minimal proposed fields:

- `id`: server-generated opaque UUID or similar stable ID. This becomes the authenticated device namespace.
- `display_name`: user-visible name supplied during pairing or edited locally.
- `credential_hash`: verifier for the long-term credential, never plaintext.
- `platform`: optional advisory string such as `android` or `fake_client`; not authorization.
- `client_instance_id`: optional advisory Android/fake-client local installation ID; not authentication.
- `created_at`: auditing and display.
- `last_seen_at`: operational visibility and revocation UX.
- `revoked_at`: nullable; non-null means authentication must fail.

Do not create user/account/email/OAuth tables.

#### `pairing_sessions`

Minimal proposed fields:

- `id`: random/opaque identifier.
- `secret_verifier`: verifier for the pairing secret or code.
- `created_at`: lifecycle.
- `expires_at`: expiry enforcement.
- `consumed_at`: one-time-use enforcement.
- `attempt_count`: brute-force control.
- `max_attempts`: optional if configurable per session; otherwise a constant.

Do not store plaintext pairing secrets or long-term credentials.

### Existing Schema Migration

Existing `stored_files.device_id` and `upload_sessions.device_id` should become references to authenticated device IDs for newly paired clients.

Implementation must decide whether to:

- leave columns as strings for now and populate them with paired-device IDs; or
- add foreign keys to `paired_devices.id` where migration risk is acceptable.

Given existing development data may contain arbitrary namespace strings, the safest Phase 5 implementation may leave existing string columns unchanged and enforce identity in application code first. A later migration can add stricter referential constraints after data migration policy is clear.

### Authenticated Endpoint Policy

Endpoint classification:

- Public:
  - `GET /api/v1/health`, minimal response only.
- Local administrative:
  - create/list/revoke pairing or paired-device records if exposed over HTTP; otherwise CLI-only.
- Pairing-session scoped:
  - `POST /api/v1/pairing-sessions/{pairing_id}/complete`.
- Authenticated device:
  - `POST /api/v1/files/check`;
  - `POST /api/v1/files`;
  - `POST /api/v1/uploads`;
  - `GET /api/v1/uploads/{upload_id}`;
  - `PUT /api/v1/uploads/{upload_id}`;
  - `POST /api/v1/uploads/{upload_id}/complete`.

Do not leave the legacy non-resumable `/api/v1/files` path unauthenticated.

### Remove Trust in Client `device_id`

After pairing:

- the authenticated principal supplies device identity;
- client-supplied `device_id` is no longer identity proof;
- new authenticated request models should omit `device_id` where practical;
- if transitional models still include `device_id`, it must be ignored or required to match the authenticated principal;
- tests must prove a client cannot impersonate another device by sending a different `device_id`.

Backward compatibility:

- The API is still pre-production, but migration should be documented.
- Android and fake_phone should be upgraded to the authenticated protocol in Phase 5.
- A temporary explicit development fallback may be acceptable only if it is off by default, clearly named, documented as unsafe, and not used as a permanent test bypass.
- Tests should usually pair a device or create paired-device fixtures directly in isolated databases.

### Upload-Session Ownership

For upload session status, append, and complete:

- resolve authenticated device first;
- load the upload session;
- reject access unless `upload_session.device_id == authenticated_device.id`;
- do not accept request body or header `device_id` as authorization.

For file checking and storage:

- lookups are scoped to the authenticated device namespace unless future cross-device deduplication is explicitly designed.

Knowing an `upload_id` must not grant access.

### Revocation

Revocation should set `paired_devices.revoked_at`.

After revocation:

- all future authenticated requests with that credential fail;
- the device cannot access existing upload sessions;
- completed backup files remain;
- completed `stored_files` metadata remains;
- active partial upload sessions for that device should not continue.

Partial-session policy:

- Prefer marking active `receiving` sessions for the revoked device as `failed` or making them inaccessible through auth checks.
- Do not delete completed backups.
- Do not aggressively delete partial bytes unless a deliberate cleanup policy is implemented and documented.

Because desktop UI does not exist, revocation can be implemented as:

- a local backend CLI/admin command; or
- a loopback-only admin endpoint.

Do not build the React UI in Phase 5.

### Laptop Reset / Repairing

If the laptop TLS identity or backend data is lost:

- Android must reject a server presenting an unexpected identity at the same IP/URL;
- the app should surface a clear "server identity changed" or pairing-lost state;
- repairing should require explicit user action;
- local forget can remove Android credentials even if the server is unreachable.

Do not silently trust a new laptop identity because the address matches.

### Android Credential Storage

Current Android settings use regular `SharedPreferences` for non-secret development URL and namespace.

Phase 5 should add a separate credential storage boundary:

- store long-term device credential using Android Keystore-backed encryption;
- store pinned server certificate/public-key fingerprint and paired server metadata;
- keep Room for media inventory and backup state only;
- do not store credentials in Room;
- do not store long-term credentials as ordinary plaintext SharedPreferences;
- do not request invasive hardware identifiers.

Implementation option:

- use Android Keystore to create an app-local AES/GCM key and encrypt the bearer credential into private SharedPreferences.

Avoid adding Jetpack Security or other dependencies unless implementation shows direct Keystore usage is too error-prone for the current scope.

### Android UX

Minimal Phase 5 UI:

- Not paired state;
- server URL field may remain during transition;
- pairing code/session entry or scan placeholder depending on QR decision;
- Paired state showing server display name/fingerprint summary and device display name;
- Forget/Unpair action;
- clear error for revoked, invalid credential, expired pairing, or server identity mismatch.

Do not build discovery UI, polished account management, or background backup UX.

### Fake Client Migration

The fake client should keep testing the real security model.

Planned behavior:

- add a pairing command that consumes a pairing session and stores server URL, server fingerprint, device ID, and credential in a local fake-client config file;
- add authenticated backup command behavior using `Authorization: Bearer`;
- keep sequential resumable transfer semantics;
- warn that fake-client local config is a development credential store, not Android-grade secure storage.

Tests may use isolated helper functions to create paired devices directly in temporary databases, but the fake client should not rely on a permanent unauthenticated bypass.

## Proposed API Shape

Final names should be confirmed during implementation, but use `/api/v1/` and generic device terms.

### Pairing

`POST /api/v1/pairing-sessions`

Creates a short-lived pairing session. Local/admin only.

Conceptual response:

```json
{
  "pairing_id": "opaque-id",
  "pairing_code": "ABCD-EFGH-IJKL",
  "expires_at": "2026-08-22T12:34:56Z",
  "server_fingerprint": "sha256:...",
  "server_url": "https://192.168.1.10:8000",
  "artifact_version": 1
}
```

`POST /api/v1/pairing-sessions/{pairing_id}/complete`

Consumes a valid session and registers a device.

Conceptual request:

```json
{
  "pairing_code": "ABCD-EFGH-IJKL",
  "display_name": "Viraj Android",
  "platform": "android",
  "client_instance_id": "android-local-installation-id"
}
```

Conceptual response:

```json
{
  "device_id": "server-generated-device-id",
  "device_credential": "returned-once-high-entropy-secret",
  "server_fingerprint": "sha256:...",
  "server_display_name": "Viraj-PC"
}
```

Do not return credential hashes or pairing verifiers.

### Authenticated Transfer Requests

Use:

```http
Authorization: Bearer <device_credential>
```

For authenticated clients, the server should derive `device_id` from the credential.

Recommended Phase 5 request-model changes:

- `/files/check`: remove `device_id` from the required client body or ignore/match it if retained temporarily.
- `/files`: remove `X-localSync-Device-Id` requirement for authenticated clients.
- `/uploads`: remove `device_id` from the required client body or ignore/match it if retained temporarily.
- `/uploads/{upload_id}` operations: enforce upload ownership against authenticated principal.

Existing response bodies should avoid leaking absolute paths and must not include credentials.

### Revocation/Admin

Choose one implementation path:

- CLI/local command:
  - list paired devices;
  - revoke paired device by ID.
- Or loopback-only HTTP endpoints under `/api/v1/admin/paired-devices`.

Do not expose LAN-wide administrative revocation without authentication.

## Milestones

- [x] Milestone 1: Finalize threat model, credential model, TLS/server-identity design, and transitional API compatibility decisions. Update this ExecPlan if implementation discoveries materially change the design.
- [x] Milestone 2: Add persistent laptop/server identity generation and loading. Store certificate/key material only under runtime localSync data/config storage. Add tests for persistence across restart and fingerprint stability.
- [x] Milestone 3: Add `pairing_sessions` and `paired_devices` database models and Alembic migration. Include verifier fields, expiry/consumption fields, attempt counts, device revocation fields, and no plaintext credentials.
- [x] Milestone 4: Implement pairing-session creation and completion APIs or CLI/admin boundary. Enforce expiry, one-time use, wrong-code handling, and attempt limits.
- [x] Milestone 5: Implement backend credential verification and authenticated-device dependency. Add structured errors for missing, invalid, revoked, and insecure-transport credentials.
- [x] Milestone 6: Protect existing transfer routes. Replace trusted client `device_id` with authenticated principal. Keep health public. Keep pairing scoped separately.
- [x] Milestone 7: Enforce upload-session ownership for status, append, and complete. Add tests proving device A cannot access device B sessions.
- [x] Milestone 8: Implement revocation/local unpair backend behavior. Ensure completed backup data remains after revocation and revoked credentials fail.
- [x] Milestone 9: Upgrade fake_phone for pairing/authenticated transfer. Add development credential config handling without a permanent auth bypass.
- [x] Milestone 10: Add Android secure credential storage and pinned server identity storage. Keep Room metadata-only.
- [ ] Milestone 11: Add Android pairing UI/state and authenticated OkHttp client. Handle server identity mismatch, expired pairing, invalid credentials, revoked credentials, and local forget.
- [x] Milestone 12: Add security regression and integration tests across backend, fake client, and Android JVM tests.
- [ ] Milestone 13: Run real-device validation: pair, back up, reject unauthenticated/wrong credential, revoke, reject revoked device, pair again, verify backup data remains.
- [ ] Milestone 14: Update docs, add ADRs, run full validation, and move the ExecPlan to completed only when completion criteria are satisfied.

Each milestone should leave the repository in a valid state and must not introduce Phase 6 discovery or automatic backup behavior.

## Files / Modules Expected to Change

Expected backend files:

- `desktop/backend/app/core/config.py`
- `desktop/backend/app/core/errors.py`
- `desktop/backend/app/core/security.py` or a similarly scoped auth module
- `desktop/backend/app/api/deps.py`
- `desktop/backend/app/api/v1/router.py`
- `desktop/backend/app/api/v1/files.py`
- `desktop/backend/app/api/v1/uploads.py`
- new `desktop/backend/app/api/v1/pairing.py`
- optional local admin CLI module under `desktop/backend/app/cli/`
- `desktop/backend/app/models/paired_device.py`
- `desktop/backend/app/models/pairing_session.py`
- `desktop/backend/app/repositories/paired_devices.py`
- `desktop/backend/app/repositories/pairing_sessions.py`
- `desktop/backend/app/services/pairing.py`
- `desktop/backend/app/services/device_auth.py`
- `desktop/backend/app/services/upload_sessions.py`
- `desktop/backend/app/services/file_transfers.py`
- `desktop/backend/migrations/versions/*.py`
- backend tests under `desktop/backend/tests/`

Expected Android files:

- `android/app/src/main/java/dev/localsync/android/data/settings/SettingsStore.kt`
- new Android credential-store module under `data/security/` or `data/settings/`
- `android/app/src/main/java/dev/localsync/android/data/network/LocalSyncProtocolClient.kt`
- `android/app/src/main/java/dev/localsync/android/data/network/ProtocolModels.kt`
- `android/app/src/main/java/dev/localsync/android/data/repository/BackupRepository.kt`
- Compose UI/ViewModel files under `android/app/src/main/java/dev/localsync/android/ui/`
- Android tests under `android/app/src/test/`

Expected fake-client files:

- `tools/fake_phone/fake_phone/client.py`
- `tools/fake_phone/fake_phone/cli.py`
- new fake-client credential/config helper if needed
- fake-client tests

Expected docs:

- `docs/security.md`
- `docs/protocol.md`
- `docs/architecture.md`
- `docs/testing.md`
- `docs/development.md`
- `docs/current-state.md`
- `docs/repo-map.md`
- `docs/testing/android-real-device-validation.md`
- `desktop/backend/README.md`
- `android/README.md`
- `tools/fake_phone/README.md`
- ADR(s) under `docs/decisions/`

## Testing and Validation

### Backend Tests

Add tests for:

- pairing session creation;
- pairing session expiry;
- wrong pairing secret/code;
- attempt limit behavior;
- one-time session consumption;
- successful paired-device registration;
- no plaintext long-term credential storage;
- durable server identity across application restart;
- missing credentials rejected;
- invalid credentials rejected;
- revoked credentials rejected;
- credential material absent from normal API responses;
- health endpoint remains public with minimal response;
- authenticated `/files/check`;
- authenticated legacy `/files`;
- authenticated `/uploads` creation;
- authenticated upload status, append, and complete;
- client-supplied `device_id` cannot impersonate another device;
- device A cannot access device B upload session;
- completed backups remain after revocation;
- resumable/retry semantics still work under authentication;
- Alembic migration creates new auth tables in isolated temp databases.

### Android JVM/Instrumented Tests

Add tests for:

- Android credential encryption/decryption using testable Keystore abstraction or Robolectric-compatible boundary;
- paired server identity persistence;
- no credential storage in Room;
- authenticated request header injection;
- no credentials in logs or normal UI state;
- server identity mismatch handling;
- expired pairing and wrong-code errors;
- revoked credential response handling;
- local forget removes credential and paired identity;
- backup flow uses authenticated principal rather than editable development namespace;
- existing manual Backup Now flow still marks backed up only after server success.

### Fake Client Tests

Add tests for:

- pairing command consumes a pairing session;
- credential config is used for authenticated requests;
- missing config fails clearly;
- invalid/revoked credential fails clearly;
- authenticated resumable transfer still handles offset conflicts and completion.

### Real Device Validation

Use generated/non-personal media only.

Checklist:

1. Start backend with persistent data root and TLS identity.
2. Create pairing session from laptop.
3. Pair real Android device.
4. Confirm authenticated backup succeeds.
5. Confirm unauthenticated request fails.
6. Confirm wrong credential fails.
7. Revoke Android device.
8. Confirm subsequent Android backup fails.
9. Pair again.
10. Confirm backup succeeds again.
11. Confirm completed backup data from the revoked device was not deleted.
12. If TLS identity pinning is implemented, demonstrate Android rejects an unexpected server identity at the same URL/IP.

### Validation Commands

Run configured validation that exists after implementation:

Backend:

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic current
```

Fake client:

```powershell
cd tools/fake_phone
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Android:

```powershell
cd android
.\gradlew.bat assembleDebug
.\gradlew.bat test
.\gradlew.bat lint
```

Run instrumented tests and real-device validation when Android device/emulator infrastructure is available. If unavailable, report the environment limitation and leave real-device criteria open as appropriate.

## Security Considerations

### Credential Handling

- Never commit generated TLS keys, certificates, pairing secrets, or device credentials.
- Never log `Authorization` headers, device credentials, pairing secrets, private keys, or Android encrypted credential blobs.
- Server stores credential verifiers only.
- Android stores long-term credentials using Android Keystore-backed protection.
- Room remains media/backup metadata only.

### Pairing

- Pairing sessions expire.
- Pairing sessions are one-time use.
- Pairing secrets/codes are not long-term credentials.
- Pairing completion validates attempt count and expiry.
- Expired/consumed pairing sessions can be cleaned up safely.

### Transport

- Authenticated device APIs should require TLS in real use.
- Do not globally disable TLS validation.
- Do not implement Android trust-all certificate behavior.
- Pin the paired laptop identity so IP changes do not imply identity changes.
- Clearly document any development-only HTTP fallback if it exists, and keep it off for authenticated real-device flow.

### Authorization

- Authenticated principal determines device identity.
- `device_id` from request body or headers is not proof.
- Upload-session access requires owner-device match.
- Revocation rejects future requests.
- Completed backups are retained after revocation.

### Replay

TLS and credential secrecy protect normal API requests from passive LAN attackers. If a valid bearer credential is stolen, ordinary bearer requests can be replayed until revocation. Phase 5 does not implement per-request signatures, nonces, or proof-of-possession tokens. Existing upload offset semantics still prevent duplicated old-offset chunks from corrupting partial files.

## Risks / Unknowns

- Exact self-signed TLS integration with Uvicorn and Android pinned trust needs implementation validation.
- Android Keystore behavior differs across devices and API levels; tests should isolate logic and validate on a real device.
- Manual pairing code entropy and usability need a concrete choice during implementation.
- Loopback-only admin endpoints can be tricky when backend listens on `0.0.0.0`; a CLI may be safer for creating/revoking pairing sessions before desktop UI exists.
- Existing development data has arbitrary namespace strings. Foreign-key migration from `stored_files.device_id` to `paired_devices.id` may need a deliberate data migration policy later.
- QR scanning/generation may be deferred if dependency cost is too high for Phase 5.
- Certificate hostname validation for private LAN addresses requires careful OkHttp configuration. Pinning must be narrow and must not become trust-all TLS.

## Architecture Review Questions

1. What exact credential proves device identity?
   - A server-generated high-entropy opaque device credential presented as `Authorization: Bearer` after pairing.

2. Is that credential ever stored plaintext server-side?
   - No. The server stores only a verifier/hash and compares using constant-time comparison.

3. Where is it stored on Android?
   - In a dedicated credential store protected by Android Keystore-backed encryption, not Room and not ordinary plaintext preferences.

4. How does the phone verify laptop identity?
   - By pinning the server certificate or public-key fingerprint established during pairing.

5. Does laptop identity survive IP changes?
   - Yes. Identity is certificate/public-key based and persisted under runtime data/config storage; IP address is only a locator.

6. How does first-time trust bootstrap work?
   - The laptop creates a short-lived pairing artifact containing server address, server identity fingerprint, pairing ID, and pairing secret/code. Android connects to the server using the pinned fingerprint and consumes the one-time pairing session.

7. What exactly is inside the pairing artifact?
   - A version marker, server URL or address, server identity fingerprint/public-key pin, pairing ID, pairing secret/code, and expiry. No filesystem paths or long-term credentials.

8. How long does pairing remain valid?
   - Implementation should choose a short window, likely 5 to 10 minutes, and document the final value.

9. Can a pairing artifact be reused?
   - No. It expires and is consumed once.

10. Can device A access device B upload session?
    - No. Authenticated principal must match the upload session owner.

11. Can arbitrary `device_id` impersonation still occur?
    - No. Client-supplied `device_id` is no longer identity proof and is removed, ignored, or required to match the authenticated principal.

12. What happens after revocation?
    - The device credential fails authentication. Existing completed backups remain. Active sessions become inaccessible or failed according to documented implementation policy.

13. Are completed backups retained after revocation?
    - Yes. Revocation is an authorization change, not a deletion command.

14. What happens if laptop identity changes unexpectedly?
    - Android rejects the server and requires explicit repairing or local forget/re-pair.

15. Is transport encrypted?
    - Phase 5 should introduce local TLS for authenticated and pairing flows. Do not claim secure transport until implemented and validated.

16. If bearer tokens are used, what replay properties remain?
    - A stolen bearer credential can be replayed until revoked. Phase 5 relies on TLS, secret storage, and revocation; it does not add per-request nonces/signatures.

17. Why JWT or why not JWT?
    - Do not use JWT. localSync has no distributed verifier, no cloud auth, and needs immediate local revocation.

18. Does fake_phone still test the same security model?
    - Yes. It should pair and authenticate with the same bearer credential flow, using a development config file for stored credentials.

19. Can Phase 6 discovery change IP without changing trusted identity?
    - Yes. Discovery can later locate a network address for the same pinned server identity.

20. Are we accidentally implementing cloud/account architecture?
    - No. The plan uses local pairing, local TLS identity, and local device records only.

## Documentation Impact

Expected updates during implementation:

- `docs/protocol.md`: pairing APIs, authentication headers, endpoint auth policies, request-model transition away from trusted `device_id`, TLS identity expectations.
- `docs/security.md`: implemented security model, remaining limitations, credential storage, transport security, revocation, replay caveats.
- `docs/architecture.md`: paired-device/laptop-identity components and boundaries.
- `docs/testing.md`: security regression and real-device pairing validation.
- `docs/development.md`: backend HTTPS startup, pairing/revocation commands, fake-client auth flow, Android setup.
- `docs/current-state.md`: Phase 5 completion state and remaining security limitations.
- `docs/repo-map.md`: new backend/Android/fake-client auth modules.
- `docs/testing/android-real-device-validation.md`: update real-device validation to include pairing/auth checks.
- `desktop/backend/README.md`, `android/README.md`, `tools/fake_phone/README.md`.

## ADR Recommendations

Create ADRs during Phase 5 implementation once details are confirmed:

- `ADR-0005-paired-device-authentication.md`
  - opaque high-entropy device credentials;
  - server-side verifier storage;
  - no JWT;
  - authenticated principal replaces trusted `device_id`.
- `ADR-0006-local-tls-server-identity.md`
  - persistent laptop TLS identity;
  - self-signed certificate/public-key pinning;
  - pairing trust bootstrap;
  - IP/address separated from server identity.

If implementation chooses manual pairing first and defers QR scanning, that likely belongs in documentation rather than a separate ADR unless the QR deferral becomes a durable product decision.

## Progress

- 2026-08-22: Created Phase 5 ExecPlan after reading root, Android, and backend agent instructions; current state, architecture, protocol, security, testing, and development docs; ADR-0001 through ADR-0004; completed Phase 3 and Phase 4 plan excerpts; current backend file/upload APIs; current Android OkHttp client and settings store; and current fake-client device namespace handling. No Phase 5 code implemented.
- 2026-08-22: Milestones 1 through 7 partially implemented for the backend. Added persistent TLS identity generation, paired-device and pairing-session models/migration, pairing completion API, local admin CLI, bearer credential verification, protected transfer routes, and upload-session ownership checks. Affected backend tests passed: `python -m pytest tests/test_pairing_auth.py tests/test_file_check.py tests/test_file_upload.py tests/test_resumable_uploads.py`.
- 2026-08-22: Milestone 9 implemented. Updated fake_phone with `pair` and `backup` commands, local development credential config, pairing completion, and bearer-authenticated transfer requests. Validation passed: `python -m pytest` in `tools/fake_phone` and `python -m pytest tests/test_fake_client_integration.py` in `desktop/backend`.
- 2026-08-22: Milestones 10 and 11 partially implemented for Android. Added Android Keystore-backed credential storage boundary, paired credential state, bearer auth interceptor, pairing completion request/response handling, local forget behavior, minimal pairing UI fields, and tests for auth header injection and credential repository behavior. Validation passed: `.\gradlew.bat test`.
- 2026-08-22: Completed the remaining Android trust-ordering implementation. Added a pairing-only TLS certificate observation path that obtains and displays the canonical SPKI fingerprint before any pairing code is sent; pairing completion now requires explicit local confirmation and then uses a pinned TLS client. Added normal Android pinned TLS with request host `localsync.local`, scoped OkHttp DNS mapping to the mutable LAN locator, default hostname verification, and Authorization added only on that pinned path. Added JVM tests for pairing-code ordering, PIN_A/PIN_B mismatch rejection, bearer suppression on HTTP/unverified paths, and same identity at a changed locator. `.\gradlew.bat test` passed.
- 2026-08-22: Updated fake_phone with SPKI fingerprint observation and preflight pin checks before pairing-code or bearer transmission for real CLI use. The local config remains development-only plaintext credential storage. `python -m pytest` in `tools/fake_phone` passed with 13 tests.
- 2026-08-22: Checked for real-device validation access from this environment. `adb devices` returned an empty device list, so Phase 5 real Android pairing/auth/revocation validation could not be executed from this shell. The plan remains active.
- 2026-08-30: User manually validated the Phase 5 pairing flow on a real Android phone. Confirmed: Android connected to the localSync HTTPS backend, pairing ID/code entry was exercised, Android displayed/used the observed `spki-sha256:` server fingerprint, the fingerprint was manually compared against the laptop CLI fingerprint before confirmation, pairing completed successfully, and Android became paired with the laptop. Not confirmed by this report: authenticated Backup Now after pairing, unauthenticated request rejection, wrong bearer rejection, revocation, rejected backup after revocation, completed-backup retention after revocation, re-pair after revocation, unexpected TLS identity rejection, same trusted identity at a different LAN IP, or real-device interrupted upload/resume.
- 2026-08-30: User manually validated backend revocation enforcement on a real Android phone. After revoking the paired device, backend `POST /api/v1/files/check` returned repeated `401 Unauthorized`, confirming server-side revoked credential rejection. The Android client incorrectly treated the 401 as a per-item failure and continued checking remaining media, causing repeated `/files/check` requests. Fixed Android backup retry classification so 401 authentication/revocation failures, 403 authorization failures, and TLS identity failures are non-retryable for the current backup run. The first affected item is marked `REVOKED`, `AUTH_REQUIRED`, or `SERVER_IDENTITY_CHANGED`, and the backup run stops before checking subsequent media. Validation passed: `.\gradlew.bat test`, `.\gradlew.bat assembleDebug`, and `.\gradlew.bat lint`.
- 2026-08-30: User manually validated the rebuilt Android revocation behavior on a real phone. Confirmed: device revocation was performed, revoked credentials receive `401 Unauthorized`, Android stops the current Backup Now run after the first revoked-auth failure instead of checking remaining media, old completed backup files remain after revocation, the phone can be paired again, the new pairing receives a new server-generated device ID, and authenticated Backup Now succeeds after re-pair. The re-paired phone uploaded the same content again because `/files/check` is scoped by the newly authenticated device ID and does not claim backups associated with the revoked prior device ID. This is intentionally safe for Phase 5.
- 2026-08-30: Added local admin CLI command `python -m app.cli devices activate <device-id>` for Phase 5 validation. It clears `revoked_at` on an existing paired device so the same credential/namespace can be retested after revocation. This is intentionally CLI-only and does not merge namespaces, issue credentials, or claim backups from another paired device.
- 2026-08-30: User manually completed the remaining Phase 5 real-device validation. Confirmed: unauthenticated protected requests are rejected, wrong bearer credentials are rejected, Android rejects unexpected TLS/server identity, the same trusted server identity works after locator/IP changes, real Android interrupted upload resumes from a nonzero server offset and completes, and final source/destination SHA-256 values match.

## Discoveries

- Current backend transfer APIs still trust client-supplied `device_id`.
- Current Android stores development server URL and editable `device_id` in regular `SharedPreferences`; no credential storage exists yet.
- Current fake client uses `--device-id` and has no pairing/auth flow.
- Existing `stored_files.device_id` and `upload_sessions.device_id` are logical namespace strings; migration to authenticated device IDs must be deliberate.
- Real Android photo backup has been validated, but Android real-device interrupted/resume validation remains unrecorded.
- Backend implementation leaves existing `stored_files.device_id` and `upload_sessions.device_id` as strings and populates them with authenticated paired-device IDs for new transfers. Foreign keys are deferred to avoid corrupting old development data.
- fake_phone now uses the same pairing/authenticated transfer model as other clients for tests and development. Its local config is a development credential store, not equivalent to Android Keystore.
- Android normal backup requests now add bearer credentials through a scoped OkHttp interceptor when paired credentials are present.
- Android now separates current server locator from trusted server identity. Normal requests use `https://localsync.local:<port>` for TLS hostname verification and map `localsync.local` to the configured LAN host through a scoped OkHttp `Dns`.
- Android pairing now observes the presented certificate fingerprint before sending the pairing code. The pairing code is sent only after the observed fingerprint matches the laptop CLI fingerprint and the user explicitly confirms.
- fake_phone now observes the server SPKI fingerprint before sending the pairing code and preflights the stored fingerprint before bearer-authenticated transfer requests when using the real CLI path.
- Real-device backend revocation enforcement has been confirmed: revoked Android credentials receive `401 Unauthorized`.
- Android initially retried revoked `/files/check` failures across remaining media because the backup loop treated all per-item exceptions as retryable item failures. Android now stops the whole manual backup run on non-retryable auth/authorization/TLS identity failures.
- Revoking device A and pairing the same physical phone again creates device B. Existing backups remain associated with device A, and device B does not automatically inherit or claim device A's `StoredFile` namespace. The same media may therefore be uploaded again after revoke/re-pair. Phase 5 intentionally does not merge device namespaces, reuse revoked device IDs, associate devices by filename or Android local instance ID alone, let a new device claim another device's backups, or implement cross-device deduplication.
- For quick validation, CLI reactivation of a revoked paired device can restore the same device A credential/namespace by clearing `revoked_at`. This is separate from re-pairing and should not be treated as credential rotation.
- A future design may separate authenticated paired-device identity, source/library identity, and stored content identity, or add an explicit laptop-admin-approved credential rotation or re-authorization flow. That redesign is deferred.

## Decision Log

- Select high-entropy opaque bearer credentials for Phase 5 planning instead of JWT or asymmetric per-request signatures.
- Store only backend credential verifiers, not plaintext credentials.
- Require a persistent laptop/server TLS identity and Android identity pinning before treating bearer authentication as secure.
- Keep identity platform-neutral: `PairedDevice`, `PairingSession`, credential, server identity.
- Do not trust client-supplied `device_id` after pairing; authenticated principal owns transfer namespaces.
- Keep `GET /api/v1/health` public and minimal.
- Protect both resumable upload APIs and legacy `/api/v1/files`.
- Retain completed backups after revocation.
- Treat revoke/re-pair as a new authenticated device namespace. Do not automatically transfer stored-file ownership from the revoked device to the new paired device.
- Allow local CLI-only activation of an existing revoked paired device for validation and administrative recovery by clearing `revoked_at`; do not expose this as a LAN API in Phase 5.
- Plan manual pairing first, with a versioned artifact that can be encoded as QR later.
- Recommend ADRs for paired-device auth and local TLS trust bootstrap.
- Implemented the canonical server fingerprint as an SPKI SHA-256 base64url value prefixed with `spki-sha256:`.
- Implemented Android normal pinned TLS with the stable logical hostname `localsync.local`; the mutable LAN IP/host is only a locator.
- Kept permissive certificate observation isolated to the pre-secret pairing stage. It does not carry pairing codes, bearer credentials, or backup requests.

## Completion Criteria

Phase 5 is complete only when:

- persistent laptop/server identity exists and survives restart;
- pairing sessions are short-lived, one-time use, attempt-limited, and do not store plaintext secrets;
- paired devices are persisted with credential verifiers and revocation state;
- authenticated-device dependency exists and does not trust client-supplied `device_id`;
- all transfer endpoints except health/pairing/admin boundaries require authenticated device access;
- upload-session ownership is enforced;
- missing, invalid, and revoked credentials are rejected;
- fake_phone can pair/authenticate and still exercise resumable transfers;
- Android stores credentials with Android Keystore-backed protection and pins laptop identity;
- Android pairing/unpair UI and authenticated backup flow work;
- revocation does not delete completed backup data;
- security, protocol, testing, development, repo-map, README, and current-state docs are updated;
- ADRs are created for the durable auth and TLS identity decisions;
- backend, fake-client, Android build/test/lint, Alembic validation, and real-device validation have been run or environment limitations are explicitly recorded.

## Final Results

Phase 5 implementation and required validation are complete.

Implemented:

- persistent backend TLS identity generation using ECDSA P-256 self-signed certificate material under `<data-root>/security/`;
- canonical `spki-sha256:` server fingerprint;
- `paired_devices` and `pairing_sessions` migration `0004_pairing_and_devices`;
- 256-bit base64url bearer device credentials with SHA-256 verifier-only server storage;
- pairing completion endpoint and local CLI pairing-session creation/list/revoke commands;
- authenticated backend transfer endpoints and upload-session ownership checks;
- fake_phone pair/backup commands using bearer credentials;
- Android Keystore-backed credential storage boundary, paired credential state, auth header injection, pairing completion parsing, local forget, and minimal pairing UI;
- ADR-0005 and ADR-0006;
- docs updates for current security/protocol/development behavior.

Validation completed:

- `desktop/backend`: `python -m pytest` passed with 89 tests and 2 external deprecation warnings.
- `desktop/backend`: `python -m ruff check .` passed.
- `desktop/backend`: `python -m ruff format --check .` passed.
- `desktop/backend`: `python -m alembic upgrade head` ran migration to `0004_pairing_and_devices`.
- `desktop/backend`: `python -m alembic current` reported `0004_pairing_and_devices (head)`.
- `tools/fake_phone`: `python -m pytest` passed with 13 tests.
- `tools/fake_phone`: `python -m ruff check .` passed.
- `tools/fake_phone`: `python -m ruff format --check .` passed.
- `android`: `.\gradlew.bat assembleDebug` passed.
- `android`: `.\gradlew.bat test` passed.
- `android`: `.\gradlew.bat lint` passed.
- `android`: combined `.\gradlew.bat clean assembleDebug test lint` timed out in this environment, then the same validations were run successfully as separate commands. Prior runs had non-fatal warnings: Compose `TabRow` deprecation and one native symbol stripping warning for `libandroidx.graphics.path.so`.

Final real-device validation:

- Real-device Phase 5 pairing with pre-secret fingerprint verification has been confirmed on a real Android phone.
- Server-side revoked-device rejection has been confirmed on a real Android phone by backend `401 Unauthorized` responses after revocation.
- Android post-revocation handling has been confirmed on a real Android phone: the rebuilt client stops the current Backup Now run after the first revoked-auth failure instead of retrying across remaining media.
- Completed-backup retention after revocation, re-pair after revocation, and authenticated Backup Now after re-pair have been confirmed on a real Android phone.
- Unauthenticated protected request rejection and wrong-bearer rejection have been confirmed.
- Android rejection of an unexpected TLS/server identity has been confirmed.
- The same trusted server identity working after locator/IP change has been confirmed.
- Real Android interrupted upload resumed from a nonzero server offset, completed successfully, and final source/destination SHA-256 values matched.

Remaining limitations:

- Revoke/re-pair creates a new authenticated device namespace. Existing backups remain associated with the revoked prior device ID, so the same media may upload again after re-pair. Cross-device deduplication, namespace merge, and credential rotation/re-authorization remain future design work.
- Phase 6 discovery, automatic backup scheduling, QR pairing UX, and production internet exposure remain out of scope.
