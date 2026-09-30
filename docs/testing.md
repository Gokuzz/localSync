# Testing Strategy

The desktop backend has a pytest suite. As more components are implemented, tests should prove backup safety, byte preservation, resumability, and security boundaries.

## Planned Coverage

- Backend unit tests.
- Protocol integration tests.
- Fake-device tests.
- Interrupted upload tests.
- Resume tests.
- Hash mismatch tests.
- Duplicate detection tests.
- Filename collision tests.
- Disk-full or disk-limit tests.
- Deletion-safety tests.
- Android tests.
- Desktop UI tests.

## Permanent Product Invariant Test

The suite must eventually include a deletion-safety test:

1. Back up source media.
2. Verify the laptop copy exists and matches expected bytes.
3. Delete source media.
4. Run synchronization again.
5. Verify the laptop copy still exists.

## Validation Expectations

Every implementation task should run relevant tests, formatting, linting, type checking, and build checks when available. If a tool does not exist yet or cannot be run, report that explicitly.

## Desktop Backend Tests

Current backend tests cover:

- package import;
- FastAPI application creation;
- `GET /api/v1/health`;
- configuration defaults and environment overrides;
- SQLite session creation against temporary databases;
- Alembic baseline migration against a temporary database;
- structured application error responses;
- logging configuration;
- storage root creation;
- temporary/final directory separation;
- traversal, absolute path, and separator rejection;
- unsafe filename sanitization;
- final path overwrite protection;
- partial-to-final storage move primitive.
- stored file migration and repository behavior;
- file check endpoint;
- raw streaming file upload endpoint;
- SHA-256 and size mismatch failures;
- duplicate transfer handling;
- filename collision safety;
- namespace isolation;
- filesystem/DB metadata recovery when finalized bytes exist without metadata;
- live fake-client to backend integration using temporary data.
- upload session creation and repeated recovery;
- normal multi-chunk resumable upload;
- exact `next_offset` reporting;
- old-offset lost-response retry behavior;
- future-offset rejection;
- incomplete completion behavior;
- completion hash mismatch and source mutation failure;
- idempotent repeated completion;
- backend restart resume from a persisted session and partial file;
- DB/filesystem offset reconciliation and anomaly failure;
- missing partial-file handling;
- server chunk-size limit and free-space rejection.
- persistent server TLS identity generation and fingerprint stability;
- pairing-session completion, expiry, one-time use, and attempt lock;
- credential verifier behavior without plaintext server-side credential storage;
- authenticated transfer endpoints;
- revoked credential rejection;
- upload-session ownership enforcement;
- completed backup retention after revocation;
- local backend CLI pairing-session creation.

Run from `desktop/backend`:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## Fake Device Tests

Run from `tools/fake_phone`:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Current fake-device tests cover directory scanning, incremental hashing, check-before-upload behavior, resumable upload calls, offset-mismatch recovery, pairing completion, credential config writing, bearer-authenticated transfer requests, CLI success, already-backed-up handling, and backend error reporting.

Phase 2 permanently establishes byte-preserving transfer tests for tiny deterministic fixtures: source SHA-256 equals destination SHA-256, and direct bytes match.

Phase 3 adds permanent resumability tests: interrupted or retried transfers must not duplicate accepted bytes, incomplete partials must stay out of `backups`, and completed destination bytes must match source bytes exactly.

## Android Tests

Run from `android`:

```powershell
.\gradlew.bat test
.\gradlew.bat lint
.\gradlew.bat assembleDebug
```

Current Android JVM tests cover:

- Android 10-12, Android 13, and Android 14+ media permission mapping.
- Unknown, denied, partial, and full access states.
- Incremental SHA-256 helpers and bounded limited-stream behavior.
- Request-body streaming failure when a source ends before the declared chunk length.
- OkHttp protocol parsing for `/files/check` and structured offset-mismatch errors.
- Authenticated request header injection.
- Pre-secret pairing fingerprint observation and local confirmation gating.
- Pinned TLS success for the canonical `spki-sha256:` server identity.
- Pinned TLS rejection before request delivery when the server identity changes.
- Same pinned server identity succeeding at a different LAN locator.
- Bearer credentials not being attached for HTTP/unverified connections.
- Pairing completion response parsing.
- Manual Backup Now repository behavior for already-backed-up skip, offset-conflict recovery, backend-completion authority, and source-disappearance deletion safety.
- Backup requiring paired credentials.
- Paired credential save and local forget behavior.
- DNS-SD advertisement metadata, configured-port propagation, lifecycle registration/unregistration, and no-secret TXT records.
- Android discovery candidate filtering, supported protocol handling, scoped locator updates after pinned TLS, wrong-identity rejection, duplicate-safe ephemeral state, and multicast-lock policy.

Instrumented tests and real MediaStore/device validation should run when an Android emulator or physical device is available:

```powershell
.\gradlew.bat connectedDebugAndroidTest
```

Phase 4 real Android phone validation was later performed outside the Codex environment. Android photo backup to the laptop backend succeeded and completed files appeared under the configured backend backup root.

Phase 5 real-device pairing was manually validated on a real Android phone: the app connected to the HTTPS backend, displayed/used the observed `spki-sha256:` server fingerprint, the fingerprint was manually verified against the laptop CLI value before pairing confirmation, and pairing completed successfully. Revocation was also manually validated: after revocation, the backend rejected the Android credential with `401 Unauthorized` on `POST /api/v1/files/check`; the rebuilt Android client stopped the Backup Now run after the first revoked-auth failure; completed backup files remained; the phone was paired again with a new server-generated device ID; and authenticated Backup Now after re-pair succeeded.

Current Phase 5 limitation: revoke/re-pair creates a new authenticated device namespace. Existing backups remain associated with the revoked prior device ID, so `/files/check` for the new paired device does not recognize them and the same media may upload again. This is intentionally safe for Phase 5. Do not treat filename, Android local instance ID, or a new pairing as authority to claim another device namespace; cross-device deduplication or admin-approved credential rotation is future design work.

The remaining Phase 5 real-device checks were later completed: unauthenticated protected requests were rejected, wrong bearer credentials were rejected, Android rejected an unexpected TLS/server identity, the same trusted server identity worked after the locator/IP changed, a real Android interrupted upload resumed from a nonzero server offset and completed successfully, and final source/destination SHA-256 values matched.

Manual real-device validation steps for the current Phase 4 app are documented in [android-real-device-validation.md](testing/android-real-device-validation.md).

Phase 6 real-device discovery validation is separate: it must confirm same-LAN discovery, pinned verification before locator replacement, a changed locator with the same certificate, unavailable-advertisement fallback to the manual locator, and rejection of a spoofed or wrong-identity candidate. No discovery result should trigger Backup Now.

The current Phase 6 implementation checkpoint is automated-test complete but real-device validation pending. Use the detailed procedure in [android-real-device-validation.md](testing/android-real-device-validation.md), record only observed outcomes, and keep the Phase 6 ExecPlan active until its required real-device criteria are satisfied.
