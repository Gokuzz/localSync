# Phase 3: Resumable Transfer Sessions

## Purpose / User Outcome

Add reliable resumable file transfer to localSync's generic development transfer protocol.

After Phase 3 implementation, a large file interrupted by Wi-Fi loss, client process exit, backend restart, laptop restart, HTTP timeout, or lost response should resume from previously accepted bytes instead of restarting from byte zero.

Phase 3 remains platform-neutral, sequential, local-network oriented, and unauthenticated development protocol work. It must be suitable for a future Android client without backend redesign, but it does not implement Android.

## Scope

Phase 3 includes:

- Persistent server-side `UploadSession` records.
- Resumable upload-session API under `/api/v1/uploads`.
- Strict append-by-offset raw-body upload requests.
- Authoritative next-offset reporting.
- DB/filesystem offset reconciliation after restart/crash.
- Idempotent completion and full-file SHA-256 verification.
- Fake-device CLI upgrade to use resumable upload sessions.
- Backend and fake-client tests for interruption, retry, restart, offset conflict, completion, and recovery.
- Live local Uvicorn demonstration of interrupted resume and lost-response retry.
- Documentation updates for protocol, architecture, security, testing, development, current state, repo map, and READMEs.
- ADR recommendation for durable resumable-transfer semantics.

## Out of Scope

Do not implement:

- Android app.
- MediaStore.
- WorkManager.
- React desktop UI.
- QR pairing.
- Production authentication.
- Authentication tokens.
- TLS certificate pinning.
- mDNS/Zeroconf discovery.
- Automatic backup scheduling.
- Manual Android document picker.
- Parallel file uploads.
- Multiple concurrent chunks.
- Adaptive chunk sizing.
- Bandwidth throttling.
- Cloud storage.
- External-drive replication.
- Image/video processing.
- Thumbnail generation.
- EXIF extraction.
- Album organization.
- Year/month organization.
- Automatic source deletion.
- Two-way sync.

Do not expand Phase 3 into cleanup services, quota systems, or production security.

## Current System Context

Phase 2 is complete.

Current backend:

- FastAPI app factory in `desktop/backend/app/main.py`.
- API module `desktop/backend/app/api/v1/files.py`.
- Existing endpoints:
  - `GET /api/v1/health`;
  - `POST /api/v1/files/check`;
  - `POST /api/v1/files`.
- `POST /api/v1/files` is a complete non-resumable raw-body upload using `Request.stream()`.
- File metadata is supplied through headers:
  - `X-localSync-Device-Id`;
  - `X-localSync-Filename`;
  - `X-localSync-Size`;
  - `X-localSync-Sha256`;
  - optional `X-localSync-Content-Type`.
- `stored_files` metadata table exists through Alembic `0002_stored_files`.
- Stored-file identity is `device_id + size + full SHA-256`.
- Finalized-file/metadata reconciliation exists when deterministic final bytes exist but DB metadata is absent.
- Storage roots:
  - `<data-root>/.localsync-temp`;
  - `<data-root>/backups`.
- Storage helpers generate safe server-controlled final keys under `<safe-device-id>/<safe-name>_<short-hash>.<ext>`.
- Current partial path helper uses `<upload-like-id>.partial`, but Phase 2 partials are not persisted as sessions.

Current fake client:

- Package under `tools/fake_phone/fake_phone`.
- Scans one source directory non-recursively.
- Computes SHA-256 incrementally.
- Uses synchronous `httpx`.
- Calls `/api/v1/files/check`.
- Uses non-resumable `/api/v1/files`.
- Processes files sequentially.

Current docs/security:

- `device_id` is a development namespace, not authentication.
- Upload endpoints are not production-secure.
- No pairing, tokens, discovery, Android, UI, or resumability exists yet.

## Assumptions

- SQLite remains the metadata store for Phase 3.
- Actual bytes remain normal filesystem files.
- One upload session owns one server-generated partial file.
- Upload IDs are server-generated UUID strings and are identifiers, not authentication credentials.
- The fake client should not need persistent local upload-id storage if `POST /api/v1/uploads` can recover a compatible active session by content identity.
- Transfer remains sequential. No concurrent file uploads or concurrent chunks.
- The client computes full SHA-256 before session creation.
- Server completion computes full SHA-256 by reading the finished partial file incrementally; the server does not persist Python `hashlib` state.
- Tests use generated data under temporary roots and temporary SQLite databases.

## Architecture / Approach

Add resumability by extending the current backend boundaries:

- New route module `app/api/v1/uploads.py`.
- New model `app/models/upload_session.py`.
- New repository `app/repositories/upload_sessions.py`.
- New service or extension of `FileTransferService` for session creation, status, append, offset reconciliation, and completion.
- Storage extensions for partial-file size checks, append-at-offset, flush/durability at request boundaries, and partial cleanup helpers.
- Fake-client transfer logic upgraded from single `/files` upload to upload-session loop.

Avoid a workflow engine. Persist only enough state to recover:

- expected content identity;
- original filename metadata;
- development device namespace;
- partial file key;
- currently known bytes received;
- status;
- link to completed stored file after success.

## Proposed Phase 3 Endpoints

Use `/api/v1/uploads` for resumable transfer sessions. This is generic and platform-neutral.

### `POST /api/v1/uploads`

Create or recover a resumable upload session.

Request:

```json
{
  "device_id": "fake-device-1",
  "filename": "video.bin",
  "expected_size": 5368709120,
  "expected_sha256": "<64 lowercase hex chars>",
  "content_type": "application/octet-stream"
}
```

Response when upload is needed:

```json
{
  "status": "receiving",
  "upload_id": "<server uuid>",
  "next_offset": 8388608,
  "expected_size": 5368709120,
  "chunk_size_hint": 4194304
}
```

Response when already completed:

```json
{
  "status": "already_stored",
  "stored_file_id": "<id>",
  "stored_path": "<relative key>"
}
```

Rules:

- Validate metadata exactly as Phase 2 does, with `expected_size` and `expected_sha256` names.
- Check completed stored content first using `device_id + expected_size + expected_sha256`, including existing finalized-file reconciliation.
- If content is completed, do not create a new session.
- If a compatible incomplete session exists for `device_id + expected_size + expected_sha256`, return it after offset reconciliation.
- If none exists, create a new receiving session and server-generated partial path.

Compatible active-session lookup:

- Match `device_id`, `expected_size`, `expected_sha256`, and non-terminal status.
- Filename/content type differences for the same expected bytes should not create duplicate partial uploads. Keep the earliest session metadata; optionally update display metadata only if there is a documented reason. Prefer not updating in Phase 3.
- This makes client restart natural without local upload-id persistence.

### `GET /api/v1/uploads/{upload_id}`

Return current state and authoritative next offset.

Response:

```json
{
  "status": "receiving",
  "upload_id": "<server uuid>",
  "next_offset": 8388608,
  "expected_size": 5368709120,
  "stored_file_id": null,
  "stored_path": null
}
```

Rules:

- Reconcile partial-file size before returning.
- If completed, return the stored file metadata.
- Do not expose absolute paths.

### `PUT /api/v1/uploads/{upload_id}`

Append raw bytes beginning at an explicitly declared offset.

Headers:

- `X-localSync-Offset`: non-negative integer byte offset.

Request body: raw bytes.

Success response:

```json
{
  "status": "receiving",
  "upload_id": "<server uuid>",
  "next_offset": 12582912
}
```

Offset mismatch response should use existing structured error conventions:

```json
{
  "error": {
    "code": "offset_mismatch",
    "message": "Upload offset does not match accepted bytes.",
    "details": {
      "expected_offset": 16777216
    }
  }
}
```

Status code: `409 Conflict`.

Rules:

- Server checks requested offset against authoritative partial-file length after reconciliation.
- If offset equals authoritative offset, append bytes.
- If offset is behind server, do not append again; return `offset_mismatch` with authoritative `expected_offset`.
- If offset is ahead of server, reject; do not create holes.
- Do not support random writes.
- Do not create chunk rows unless implementation proves a real need; Phase 3 uses append-style offset protocol.

### `POST /api/v1/uploads/{upload_id}/complete`

Verify and finalize a complete upload session.

Response after success or already completed:

```json
{
  "status": "completed",
  "upload_id": "<server uuid>",
  "stored_file_id": "<id>",
  "stored_path": "<relative key>"
}
```

Rules:

- Reconcile offset before completion.
- If current size is less than expected, return a structured error such as `upload_incomplete` with `next_offset`.
- If current size is greater than expected, mark failed or return `size_mismatch`; do not finalize.
- Compute full SHA-256 by reading partial file incrementally.
- If hash mismatches, do not finalize; mark failed only if that helps avoid repeated doomed completion attempts. Prefer `failed` for verified corrupt sessions.
- If hash matches, finalize through existing storage logic and persist/reconcile `StoredFile`.
- Mark `UploadSession` completed with `completed_file_id`.
- Repeated complete calls after success return the same completed result without duplicating final files or metadata.

## Backward Compatibility for `POST /api/v1/files`

Keep Phase 2 `POST /api/v1/files` during Phase 3.

Decision:

- Do not remove it or silently change its response contract.
- Mark it as legacy/non-resumable development upload in docs.
- Internally it may share validation, storage-key, and finalization helpers with the resumable service.
- Prefer future fake-client default behavior to use `/uploads`.
- Keep `/files/check` as a useful optimization/convenience endpoint. `POST /uploads` remains authoritative and must still check already-completed content and compatible active sessions.

Future migration:

- Once Android and resumable transfer are stable, a later explicit protocol revision can deprecate or remove non-resumable `/files`.

## UploadSession Data Model

Add `upload_sessions` through a new Alembic migration, likely `0003_upload_sessions.py`. Do not modify old migrations.

Minimal proposed fields:

- `id`: server-generated UUID string primary key. Needed for client requests and session lookup.
- `device_id`: development namespace. Needed for lookup and storage namespace; not authentication.
- `original_filename`: sanitized/display-safe metadata from the client. Needed for eventual final storage naming.
- `expected_size`: integer. Needed for offsets, completion, disk-space checks, and validation.
- `expected_sha256`: 64-character lowercase hex. Needed for identity and completion verification.
- `content_type`: nullable advisory metadata. Not trusted for paths or validity.
- `temp_relative_path`: server-controlled relative key under `.localsync-temp`, e.g. `<upload-id>.partial`. Avoid absolute host paths.
- `bytes_received`: integer last committed known accepted offset. Reconciled from actual partial-file length on load/status/create/append/complete.
- `status`: small string enum. Proposed persisted values: `receiving`, `completed`, `failed`.
- `completed_file_id`: nullable foreign key/reference to `stored_files.id`. Needed for idempotent completion/status after finalization.
- `created_at`: audit/debug timestamp.
- `updated_at`: needed to identify abandoned sessions and support future cleanup decisions.

Indexes/constraints:

- Primary key on `id`.
- Index on `(device_id, expected_size, expected_sha256, status)` or a smaller practical lookup index for compatible active sessions.
- Optional unique partial behavior is hard in SQLite for only active statuses; avoid over-complicated uniqueness. Application code can reuse an existing compatible active session and tolerate rare duplicates by returning one canonical session.

Do not add:

- Device table.
- Chunk table.
- Pairing/auth table.
- File bytes/BLOB columns.

## Session States

Persist only:

- `receiving`: session can accept appends and be completed.
- `completed`: final bytes and stored metadata exist or can be reconciled.
- `failed`: session cannot continue because verified bytes are corrupt or metadata is invalid for completion.

Do not persist transient `verifying` unless implementation needs crash recovery from a long-running verification step. In Phase 3, verification can be retried idempotently by calling complete again while status remains `receiving` until finalization succeeds.

Conceptual lifecycle:

```text
receiving -> completed
receiving -> failed
```

The broader conceptual states NEW/RECEIVING/READY_TO_COMPLETE/VERIFYING/COMPLETED can remain documentation concepts, but the database does not need all of them.

## Authoritative Offset Strategy

Use actual partial-file size as the authoritative accepted offset, reconciled into `upload_sessions.bytes_received`.

Reasoning:

- The only bytes that can be resumed from are bytes that actually exist in the partial file.
- Crash window A: chunk written, DB offset not updated. Partial file length may be greater than DB. Treat the actual file length as accepted, update DB on next session load/status/create/append/complete, and return that next offset.
- Crash window B: DB offset updated, partial data missing. Write ordering should prevent this by flushing/closing the file before DB update. If encountered, trust actual file length, lower DB `bytes_received` to file length, and return that next offset. Never skip missing bytes.
- If actual partial-file size exceeds `expected_size`, mark failed or return `size_mismatch`; do not finalize.

Implementation should centralize reconciliation:

```text
load session
resolve partial path
actual_size = partial_path.stat().st_size if exists else 0
if actual_size != bytes_received:
    bytes_received = actual_size
    updated_at = now
    commit
return actual_size as next_offset
```

If a receiving session has no partial file, treat next offset as 0 and recreate the empty partial only if safe, or mark failed if metadata says bytes were previously received and the file vanished. Prefer safe behavior:

- if DB says 0 and file missing: recreate empty partial;
- if DB says >0 and file missing: set offset to 0 only after returning a structured `partial_missing`/failed state would be too harsh? For backup integrity, do not pretend bytes exist. Prefer mark failed and require a new session, unless implementation can safely restart from zero under the same session. The plan should choose during implementation; default recommendation is mark failed to avoid ambiguous recovery.

## Chunk / Offset Semantics

Append-only protocol:

- Client sends bytes at explicit offset.
- Server accepts only if `offset == authoritative partial-file size`.
- Server appends exactly the request body.
- Server returns authoritative `next_offset`.

Lost response/retry:

- Client sends offset 8 MiB.
- Server appends to 16 MiB and commits.
- Response is lost.
- Client retries offset 8 MiB.
- Server sees authoritative offset 16 MiB, does not append, returns `409 offset_mismatch` with `expected_offset = 16 MiB`.
- Client seeks to 16 MiB and continues.

Future offset:

- Server has 8 MiB.
- Client sends offset 16 MiB.
- Server rejects with `409 offset_mismatch`, `expected_offset = 8 MiB`.
- No sparse/hole upload is created.

Chunk size:

- Fake client default chunk size: 8 MiB.
- Make it configurable with a CLI option such as `--chunk-size-mib`.
- Rationale: 8 MiB keeps memory bounded, avoids absurdly tiny requests, and limits retry cost. Tests should override to smaller chunks.
- Protocol does not require every client to use the same chunk size.
- Tests should use much smaller chunk sizes to exercise multi-chunk behavior without large fixtures.

## File Durability

Durability boundary should be at each `PUT /uploads/{upload_id}` request, not every network buffer.

Proposed sequence for an accepted append request:

1. Open partial file in append-binary mode.
2. Stream request body to file in bounded buffers.
3. Flush Python file object.
4. Optionally call `os.fsync(file.fileno())` before acknowledging the chunk.
5. Close file.
6. Re-stat actual file length.
7. Update `bytes_received` and `updated_at` in SQLite.
8. Commit DB transaction.
9. Return `next_offset`.

Recommendation:

- Use `flush()` and `os.fsync()` once per accepted append request in Phase 3 unless implementation/testing shows unacceptable cost.
- Do not fsync every internal network buffer.
- Document that this gives stronger acknowledged-chunk durability than buffered writes alone, but do not claim absolute power-loss durability for all hardware/filesystems.

If fsync is made configurable, default should favor safety over throughput for backup software.

## Hash Verification

Do not persist `hashlib` internal state.

At completion:

- Reconcile actual partial-file size.
- If size differs from expected, reject completion.
- Read the complete partial file incrementally.
- Compute full SHA-256.
- Compare with `expected_sha256`.
- Finalize only if both full size and full SHA-256 match.

Tradeoff:

- Completion reads the partial file once more from disk.
- This is acceptable for Phase 3 because it keeps the implementation portable, simple, and robust across restarts.

## Completion / Finalization Flow

For `POST /api/v1/uploads/{upload_id}/complete`:

1. Load session.
2. If completed, return existing stored file result.
3. If failed, return a structured error unless retry is explicitly supported.
4. Reconcile partial-file size.
5. If size is less than expected, return `upload_incomplete` with `next_offset`.
6. If size is greater than expected, return `size_mismatch` and mark failed.
7. Compute full SHA-256 incrementally.
8. If hash mismatch, return `hash_mismatch`; mark failed and keep or delete partial according to documented choice. Prefer keeping failed partial isolated for debugging only if documented; otherwise delete to save space. Implementation should choose explicitly.
9. Use existing stored-file reconciliation to detect already-finalized matching content.
10. If no final file exists, finalize partial into backup storage using server-generated deterministic storage key.
11. Create/reconcile `StoredFile` metadata.
12. Set upload session `status = completed`, `completed_file_id = stored_file.id`, `bytes_received = expected_size`.
13. Commit.
14. Return completed result.

Repeated complete:

- If session is completed and stored file exists, return completed result.
- If session is completed but stored metadata/file is inconsistent, use existing reconciliation where possible; otherwise return a structured consistency error.

## Filesystem / DB Crash Recovery

There is no distributed transaction across SQLite and the filesystem. Use deterministic recovery and idempotency.

Crash window A: chunk written, DB offset not updated.

- Actual partial file is longer than DB `bytes_received`.
- On next load/status/create/append/complete, stat the partial file and update DB to actual size.
- Return actual size as next offset.

Crash window B: DB offset updated, partial data missing.

- Write ordering should avoid this by fsync/close/stat before DB update.
- If encountered, trust actual file size. If file is shorter, lower DB offset to actual size and return that offset, unless partial file is missing after nonzero DB offset, in which case mark failed or require restart from zero under a new session.
- Never skip missing bytes.

Crash window C: full partial verified, process crashes before finalization.

- Session remains `receiving`.
- Complete can be called again. It re-verifies size/hash and finalizes.

Crash window D: file finalized, StoredFile insert fails.

- Reuse Phase 2 behavior: finalized bytes are durable backup data.
- Later matching create/check/complete verifies full SHA-256 and size of deterministic final file, recreates `StoredFile`, and proceeds.

Crash window E: StoredFile inserted, UploadSession completion status not committed.

- On repeated complete, stored-file lookup by `device_id + expected_size + expected_sha256` finds completed metadata and final bytes.
- Mark session completed and link `completed_file_id`.
- Return completed.

Crash window F: finalization succeeds, client response lost.

- Client calls complete again or POST /uploads again.
- Server returns completed/already stored without duplicating backup.

Backend restart:

- Sessions persist in SQLite.
- Partial files persist under `.localsync-temp`.
- `POST /uploads` or `GET /uploads/{id}` reconciles next offset from partial-file length.

## Client Restart Strategy

Prefer no fake-client local upload-id persistence in Phase 3.

Workflow after restart:

1. Scan source file.
2. Compute size and full SHA-256.
3. Call `/files/check`; skip if completed.
4. Call `POST /uploads` with metadata.
5. Backend returns existing compatible active session and authoritative `next_offset`.
6. Client seeks source file to `next_offset` and continues.

This protocol is natural for future Android because the client can derive identity from MediaStore/opened file bytes plus size/hash and recover server state without a local durable queue.

Race/ambiguity:

- Multiple active sessions for same identity are possible if two clients race.
- Application code should reuse one compatible session if found.
- If rare duplicates exist, complete should still be idempotent through `stored_files`; future cleanup can fail/cancel redundant sessions.

## Source Mutation Handling

The fake client computes full size and SHA-256 before session creation.

On resume:

- Recompute size and SHA-256 before calling `POST /uploads`.
- If size/hash differ from the original session metadata, `POST /uploads` will create/recover a different session or report already stored for different content.
- If the client reuses an upload ID directly, it should compare current source size/hash to session metadata from `GET /uploads/{id}` before sending.
- Completion verification remains authoritative and fails if uploaded bytes do not match expected full SHA-256.

Do not rely on timestamps as integrity proof. The fake client may use size/mtime only for a warning or optimization, not correctness.

## Abandoned Session Strategy

Record `updated_at` on upload sessions.

Do not implement aggressive automatic cleanup in Phase 3.

Reason:

- A large upload may be legitimately paused for a long time.
- Automatic deletion of partial bytes risks forcing retransmission and surprising users.

Phase 3 should provide enough data for future cleanup:

- status;
- updated_at;
- expected size;
- bytes received;
- temp relative path.

Disk-usage consequence:

- Abandoned partials can consume disk until a future explicit cleanup/retention feature is implemented.
- Document this in security/development docs.

Optional safe Phase 3 behavior:

- Expose status and leave manual deletion out of scope.
- Do not add delete/cancel endpoint unless implementation needs it for tests. Prefer deferring.

## Disk Space Strategy

Add a simple portable free-space check before creating or appending uploads if feasible.

Minimum Phase 3 behavior:

- On session creation, compare available space under `data_root` to remaining expected bytes, with a small safety margin if simple.
- On append, if available free space is clearly less than incoming request `Content-Length` when known, reject before writing.
- If `Content-Length` is absent, stream defensively and handle `OSError` with `storage_error`.

Do not implement per-device quotas or accounting infrastructure.

Return structured error such as `disk_space_insufficient` when rejecting obvious cases.

## Security Considerations

Phase 3 remains development-only network security.

Must document:

- `device_id` is a namespace, not authenticated identity.
- `upload_id` is an identifier, not an authorization credential.
- Anyone who can reach the backend can attempt development upload endpoints until pairing/authentication exists.
- No tokens, TLS pinning, mDNS discovery, or production encryption are implemented.
- Offset validation prevents accidental corruption but is not authorization.

Keep existing safeguards:

- no client-controlled server paths;
- safe metadata validation;
- partials isolated under `.localsync-temp`;
- finalization only after full size/hash verification;
- no file bytes in SQLite;
- no raw bytes or secrets in logs.

## Fake Client Workflow

Upgrade fake client to:

```text
scan source
compute size and SHA-256 incrementally
POST /api/v1/files/check
if exists: skip
POST /api/v1/uploads
if already_stored: skip
seek source to next_offset
while next_offset < size:
    read bounded chunk
    PUT /api/v1/uploads/{upload_id} with X-localSync-Offset
    if success: update next_offset
    if offset_mismatch: seek to expected_offset and continue
POST /api/v1/uploads/{upload_id}/complete
report success
```

CLI additions:

- `--chunk-size` default `4194304`.
- Keep existing `--server`, `--device-id`, `--source`.
- Sequential only.
- No persistent local queue in Phase 3.

Source files must never be modified or deleted.

## Dependency / Tooling Decisions

Prefer existing dependencies.

No planned new dependencies:

- Backend can use FastAPI, SQLAlchemy, Alembic, pytest, httpx, Ruff, standard library file APIs.
- Fake client can keep synchronous `httpx`.
- Do not add Redis, Celery, queues, resumable-upload libraries, aiofiles, cloud SDKs, or another database.
- Do not add async/concurrency optimization.

If implementation discovers a platform-specific file durability issue, document it before adding dependencies.

## Implementation Milestones

- [ ] Milestone 1: Finalize resumable protocol and persistence design.
  - Update `docs/protocol.md` with Phase 3 endpoint contract.
  - Decide exact error codes and response schemas.
  - Confirm ADR need; likely draft an ADR during implementation if semantics remain as planned.

- [ ] Milestone 2: Add `UploadSession` database model and Alembic migration.
  - Add SQLAlchemy model and repository.
  - Add migration `0003_upload_sessions`.
  - Add migration/repository tests.
  - Do not add Device, chunk, pairing, or auth tables.

- [ ] Milestone 3: Add storage primitives for resumable partials.
  - Partial size lookup.
  - Safe append at current end.
  - Flush/fsync/close at request boundary.
  - Partial missing handling.
  - Tests for partial path containment and durability-oriented write ordering where practical.

- [ ] Milestone 4: Implement session creation/recovery and status endpoint.
  - `POST /api/v1/uploads`.
  - `GET /api/v1/uploads/{upload_id}`.
  - Completed-content check.
  - Compatible incomplete-session recovery.
  - Offset reconciliation on load.

- [ ] Milestone 5: Implement strict offset-based streaming append.
  - `PUT /api/v1/uploads/{upload_id}`.
  - `X-localSync-Offset` validation.
  - Offset mismatch errors with authoritative `expected_offset`.
  - Lost-response retry and future-offset tests.

- [ ] Milestone 6: Implement DB/filesystem offset reconciliation.
  - Reconcile DB lower than partial-file length.
  - Reconcile DB higher than partial-file length.
  - Backend restart simulation.
  - Never skip missing bytes.

- [ ] Milestone 7: Implement idempotent completion and full-file verification.
  - `POST /api/v1/uploads/{upload_id}/complete`.
  - Full SHA-256 verification by reading partial file incrementally.
  - StoredFile/finalized-file reconciliation.
  - Idempotent repeated complete.

- [ ] Milestone 8: Upgrade fake client for resumable transfers.
  - Add resumable upload flow.
  - Add `--chunk-size`.
  - Handle offset mismatch by seeking to authoritative offset.
  - Keep sequential behavior.

- [ ] Milestone 9: Add interruption/retry/restart integration tests.
  - Client interruption/restart.
  - Backend restart.
  - Lost response retry.
  - Source mutation/hash mismatch.
  - Partial never finalized early.

- [ ] Milestone 10: Live interrupted-transfer demonstration.
  - Start real local Uvicorn backend.
  - Generate temporary file.
  - Transfer several chunks.
  - Interrupt client or backend.
  - Restart/recover.
  - Resume from non-zero offset.
  - Complete and verify SHA-256.
  - Demonstrate old-offset retry does not duplicate bytes.

- [ ] Milestone 11: Documentation and final validation.
  - Update docs and READMEs.
  - Run backend tests, fake-client tests, Ruff checks, Alembic upgrade/current, and live demo.
  - Update this ExecPlan Progress, Discoveries, Decision Log, and Final Results.
  - Move to completed only when all completion criteria are satisfied.

Each milestone should leave the repository valid and should not introduce later roadmap features.

## Files / Modules Expected to Change

Expected backend creates/updates:

- `desktop/backend/app/api/v1/uploads.py`
- `desktop/backend/app/api/v1/router.py`
- `desktop/backend/app/models/upload_session.py`
- `desktop/backend/app/models/__init__.py`
- `desktop/backend/app/repositories/upload_sessions.py`
- `desktop/backend/app/services/upload_sessions.py` or a focused extension of `file_transfers.py`
- `desktop/backend/app/services/file_transfers.py`
- `desktop/backend/app/storage/local_filesystem.py`
- `desktop/backend/migrations/versions/0003_upload_sessions.py`
- backend tests for upload sessions, offsets, append, completion, restart/recovery, and integration

Expected fake-client updates:

- `tools/fake_phone/fake_phone/client.py`
- `tools/fake_phone/fake_phone/cli.py`
- `tools/fake_phone/fake_phone/models.py`
- fake-client tests for resumable flow and offset mismatch handling

Expected docs updates:

- `docs/protocol.md`
- `docs/architecture.md` if implementation changes architecture materially
- `docs/security.md`
- `docs/testing.md`
- `docs/development.md`
- `docs/current-state.md`
- `docs/repo-map.md`
- `desktop/backend/README.md`
- `tools/fake_phone/README.md`
- this ExecPlan

Possible ADR:

- `docs/decisions/ADR-0004-resumable-transfer-sessions.md` if implementation confirms the planned durable choices.

## Testing and Validation

Required tests:

1. Normal multi-chunk upload.
2. Byte equality after completion.
3. Full SHA-256 equality.
4. Resume after fake-client interruption.
5. Resume after backend restart.
6. Exact `next_offset` reporting.
7. Duplicate/retried chunk after response loss.
8. Client sends offset behind server.
9. Client sends offset ahead of server.
10. Completion before all bytes arrive.
11. Complete hash mismatch.
12. Complete exact-size mismatch.
13. Repeated `/complete` call.
14. Repeated `POST /uploads` for same incomplete content.
15. Already-completed content does not create another session.
16. Temp file remains outside completed backup tree.
17. Partial data never becomes completed backup.
18. Filename collision handling remains safe.
19. Device namespaces remain isolated.
20. DB/file offset reconciliation.
21. Finalized-file/StoredFile reconciliation from Phase 2 still works.
22. Process/backend restart simulation where practical.
23. Source mutation between initial upload and resume fails integrity at completion.
24. Disk-space rejection where feasible with mockable disk usage.

All tests must use temporary data roots and isolated SQLite databases.

No large committed binary fixtures. Generate deterministic data in tests.

Expected validation commands:

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

Live demo must use generated temporary files and a real local Uvicorn backend.

## Live Demonstration Plan

Use a script or documented manual steps:

1. Generate a temporary binary file large enough to require several test chunks.
2. Start Uvicorn with a temporary `LOCALSYNC_DATA_ROOT` and SQLite database.
3. Run fake client with small `--chunk-size`, interrupt after at least one chunk, or simulate by stopping after a bounded chunk count if a test hook is added.
4. Restart fake client or backend.
5. Call `POST /uploads` again and confirm `next_offset > 0`.
6. Resume and complete.
7. Verify source SHA-256 equals destination SHA-256.
8. Simulate lost response by resending an already accepted old offset; confirm server returns authoritative next offset and file size does not grow incorrectly.

## Security Considerations

Phase 3 improves transfer reliability, not production network security.

Security docs must continue to state:

- no pairing;
- no authentication;
- no authorization;
- no TLS pinning;
- no mDNS discovery;
- `device_id` is not identity proof;
- `upload_id` is not an authorization credential.

Reliability/security boundaries:

- Incomplete partials stay under `.localsync-temp`.
- Completed backups only appear after full size and SHA-256 verification.
- Offset mismatch prevents accidental corruption.
- No file bytes are stored in SQLite.
- Logs should include transfer lifecycle, offsets, and failures but not raw bytes, complete request headers, secrets, or noisy per-buffer logs.

## Risks / Unknowns

- SQLite concurrency may require careful transaction boundaries even with sequential client behavior.
- Windows file locking can affect restart tests and cleanup.
- `os.fsync` per request may affect performance but is reasonable for backup correctness in Phase 3.
- Missing partial file with nonzero DB offset needs a conservative implementation choice; recommended default is fail the old session and let creation start a new session from zero.
- Duplicate active sessions can occur under races; app logic should reuse one but not overbuild locking.
- Abandoned partial files can consume disk until future cleanup.
- Disk free-space checks are inherently race-prone; they are safety hints, not guarantees.

## Architecture Review

1. Can an upload resume after fake-client restart?
   - Yes. The fake client recomputes size/SHA-256 and `POST /uploads` recovers a compatible active session with `next_offset`.

2. Can an upload resume after backend restart?
   - Yes. `UploadSession` persists in SQLite and partial bytes persist under `.localsync-temp`; status/create flows reconcile actual partial-file size.

3. What is authoritative if DB `bytes_received` differs from partial-file size?
   - Actual partial-file size is authoritative because those are the bytes that exist and can be resumed. DB is reconciled to the file length.

4. Can a repeated old-offset chunk duplicate data?
   - No. Server rejects offset behind authoritative size with `409 offset_mismatch` and returns expected offset without appending.

5. Can a future-offset chunk create a hole?
   - No. Server rejects offset ahead of authoritative size and never creates sparse logical content.

6. Can a completion request duplicate a finalized backup?
   - It should not. Completion checks session status and stored-file identity, reuses existing completed metadata/finalized bytes, and returns idempotently.

7. Can an incomplete partial ever appear under `backups/`?
   - No. Partials remain in `.localsync-temp`; finalization happens only after expected size and full SHA-256 verification.

8. Are acknowledged chunk bytes written durably enough for documented guarantees?
   - Plan recommends flush/fsync/close once per accepted append request before DB offset update and response. This is stronger than buffered writes but should not be documented as absolute power-loss durability.

9. How is full-file SHA-256 verified after a resumed upload?
   - Completion reads the whole partial file incrementally and compares against `expected_sha256`.

10. Are upload sessions persisted without storing file bytes in SQLite?
    - Yes. SQLite stores metadata, status, offset, and relative temp path only.

11. Can Android later use this protocol without redesign?
    - Yes. Android can compute size/SHA-256, create/recover upload sessions, seek/open source bytes, send append requests with offsets, and complete.

12. Have we accidentally introduced Phase 4+ concerns?
    - No. No Android, WorkManager, MediaStore, pairing, auth, discovery, UI, parallelism, or media parsing is planned.

13. How are existing Phase 2 `/files` semantics handled?
    - Keep `/files` as legacy non-resumable development upload. Do not delete it in Phase 3. Prefer fake client default to `/uploads`.

14. What happens to abandoned partial sessions?
    - They remain as resumable sessions with `updated_at`. Automatic cleanup is deferred to avoid deleting valid large transfer progress.

15. What disk-full behavior is required in Phase 3?
    - Add simple free-space checks for obvious insufficient space on create/append where feasible, handle write `OSError`, and defer quota/accounting.

## Documentation Impact

Expected updates during implementation:

- `docs/protocol.md`: actual `/api/v1/uploads` schemas, offset semantics, errors, completion semantics, and `/files` compatibility.
- `docs/architecture.md`: resumable session component and authoritative offset model if not already clear.
- `docs/security.md`: development-only upload sessions, `upload_id` not auth, disk/partial risks.
- `docs/testing.md`: resumable/restart/lost-response tests and live demo.
- `docs/development.md`: fake-client resumable command and validation.
- `docs/current-state.md`: Phase 3 complete status only after validation.
- `docs/repo-map.md`: upload session modules/migration/tests.
- `desktop/backend/README.md`: resumable endpoints and migration state.
- `tools/fake_phone/README.md`: resumable CLI behavior and `--chunk-size`.

ADR recommendation:

- Resumable transfer sessions and authoritative partial-file-size offset semantics are durable, cross-cutting protocol decisions that future Android/iOS/NAS clients will depend on.
- During Phase 3 implementation, create `ADR-0004-resumable-transfer-sessions.md` once implementation confirms this design.
- Do not create the ADR in this planning-only task.

## Progress

- 2026-08-16: Created Phase 3 ExecPlan after reading root/backend/tools agent instructions, current docs, ADRs, completed Phase 2 plan, and actual Phase 2 backend/fake-client implementation. No Phase 3 code implemented.
- 2026-08-16: Milestone 2 completed. Added `upload_sessions` model, repository, Alembic `0003_upload_sessions` migration, settings for maximum upload chunk size, and storage partial helpers. Updated migration test expectations. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed in `desktop/backend`.
- 2026-08-16: Milestones 3 through 7 completed. Added `/api/v1/uploads` create/status/append/complete endpoints, strict offset validation, Content-Length/request-size checks, fsync-before-DB-offset ordering, partial-file-size reconciliation, full-file SHA-256 completion verification, idempotent completion, and StoredFile/finalized-file reconciliation. Backend resumable tests passed.
- 2026-08-16: Milestone 8 completed. Upgraded `tools/fake_phone` to use resumable `/uploads` by default with sequential 8 MiB chunks and offset-mismatch recovery. Fake-client tests passed.
- 2026-08-16: Milestone 9 completed in automated coverage. Added tests for backend restart recovery, lost-response old-offset retry, source mutation/hash failure, missing partial handling, DB/file offset divergence, free-space rejection, and Phase 2 `/files` compatibility.

## Discoveries

- Phase 2 backend currently has `POST /api/v1/files/check` and non-resumable `POST /api/v1/files`.
- Phase 2 backend stores completed metadata in `stored_files` through migration `0002_stored_files`.
- Phase 2 service already has reusable metadata validation, final storage-key generation, `file_matches`, and finalized-file/metadata reconciliation behavior.
- Phase 2 fake client uses synchronous `httpx`, incremental hashing, and sequential file processing.
- Current storage has safe final/partial roots and can be extended for session-owned partial paths.
- Phase 3 user decisions set the fake-client default to 8 MiB and the server request limit to 16 MiB.
- Existing live fake-client integration now exercises the resumable `/uploads` protocol because the fake client defaults to resumable transfer.

## Decision Log

- Use `/api/v1/uploads` for resumable sessions.
- Keep `/api/v1/files` as legacy non-resumable development upload during Phase 3.
- Use actual partial-file size as authoritative offset and reconcile DB to it.
- Use append-only offset protocol; no chunk tables.
- Use full-file SHA-256 verification at completion by rereading the partial file.
- Prefer `POST /uploads` compatible-session recovery over fake-client local upload-id persistence.
- Persist only `receiving`, `completed`, and `failed` session statuses.
- Defer automatic abandoned-session cleanup.
- Recommend ADR-0004 during implementation for resumable-session/authoritative-offset semantics.
- Persisted upload session states are limited to `receiving`, `completed`, and `failed`.
- For DB/file offset anomalies where DB claims bytes that are missing from the partial file, mark the session failed rather than silently reconciling downward.
- Use `LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE` with a default 16 MiB server request limit.
- Use `--chunk-size-mib` in the fake client with a default 8 MiB chunk size.
- Create ADR-0004 because resumable sessions and authoritative partial-file offsets are durable protocol decisions.

## Completion Criteria

Phase 3 is complete when:

- `UploadSession` model, repository, and Alembic migration exist.
- `/api/v1/uploads`, `/api/v1/uploads/{upload_id}`, `/api/v1/uploads/{upload_id}` PUT append, and `/api/v1/uploads/{upload_id}/complete` exist and are documented.
- Existing `/api/v1/files/check` remains.
- Existing `/api/v1/files` is kept or explicitly documented as legacy non-resumable; it is not silently removed.
- Fake client resumes uploads through `/uploads`.
- Client restart and backend restart resume from nonzero offset.
- Lost-response retry does not duplicate bytes.
- Future-offset attempts cannot create holes.
- Completion is idempotent.
- Full SHA-256 and byte equality are verified after completion.
- Partial files never appear as completed backups.
- Tests cover required cases using temporary roots/databases.
- Live interrupted-transfer demo passes.
- Docs are updated.
- ADR is created if implementation confirms durable resumable semantics.
- Validation commands pass or limitations are documented.
- This ExecPlan is updated and moved to completed only if criteria are satisfied.

## Final Results

Completed on 2026-08-16.

Implemented:

- `upload_sessions` table through Alembic `0003_upload_sessions`.
- Persisted session states: `receiving`, `completed`, and `failed`.
- `POST /api/v1/uploads` session create/recovery.
- `GET /api/v1/uploads/{upload_id}` status with offset reconciliation.
- `PUT /api/v1/uploads/{upload_id}` raw-body append with `X-localSync-Offset`, required `Content-Length`, 16 MiB default request limit, and fsync-before-DB-offset ordering.
- `POST /api/v1/uploads/{upload_id}/complete` idempotent completion with full-file SHA-256 verification and safe finalization.
- Actual partial-file length is the authoritative accepted offset.
- DB/filesystem reconciliation:
  - DB behind filesystem reconciles upward;
  - missing partial with zero offset is recreated;
  - missing partial with nonzero offset fails the session;
  - DB ahead of filesystem fails the session;
  - finalized file/StoredFile recovery from Phase 2 is reused.
- Simple free-space preflight guard using the configured data filesystem.
- Fake-device client now uses resumable `/uploads` by default, with `--chunk-size-mib` defaulting to 8 MiB.
- Existing `/api/v1/files/check` and legacy non-resumable `POST /api/v1/files` remain.
- ADR-0004 documents resumable transfer sessions and authoritative partial-file offsets.

Validation:

- `desktop/backend`: `python -m pytest` passed with 79 tests. Uvicorn/websockets deprecation warnings appeared from installed dependencies during the live server integration test.
- `desktop/backend`: `python -m ruff check .` passed.
- `desktop/backend`: `python -m ruff format --check .` passed.
- `desktop/backend`: `python -m alembic upgrade head` passed through `0003_upload_sessions`.
- `desktop/backend`: `python -m alembic current` reported `0003_upload_sessions (head)`.
- `tools/fake_phone`: `python -m pytest` passed with 9 tests.
- `tools/fake_phone`: `python -m ruff check .` passed.
- `tools/fake_phone`: `python -m ruff format --check .` passed.
- Live Uvicorn/fake-client demonstration passed with generated temporary data:
  - one 1,000,000-byte chunk was accepted;
  - a repeated old-offset chunk returned the authoritative offset without duplicating bytes;
  - the fake client recovered the existing session and completed;
  - final size was 2,500,000 bytes;
  - source and destination SHA-256 matched.

Intentional limitations:

- Upload endpoints remain development-only and unauthenticated.
- `device_id` is not authentication.
- `upload_id` is not authorization.
- No automatic abandoned-session cleanup exists; partials can consume disk until future cleanup tooling.
- Free-space checking is a preflight guard, not quota reservation.
- Phase 2 `/files` remains non-resumable legacy behavior.
- No Android, MediaStore, WorkManager, React UI, pairing, tokens, TLS pinning, mDNS, parallel uploads, media parsing, thumbnails, EXIF, cloud, automatic deletion, or two-way sync was implemented.
