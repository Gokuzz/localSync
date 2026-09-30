# Phase 2: Generic Fake-Device Client and Initial Transfer Protocol

## Purpose / User Outcome

Establish the first real end-to-end local transfer path between a generic fake device client and the localSync desktop backend.

At completion of Phase 2 implementation, a developer should be able to:

1. create tiny deterministic source files in a fake-device directory;
2. start the desktop backend;
3. run a command-line fake device client;
4. have the client scan files, compute size and SHA-256, check whether each file is already stored, stream missing file bytes to the backend, and report success/failure;
5. verify completed backup files are byte-identical to source files;
6. rerun the client without creating unnecessary duplicates;
7. transfer same-name different-content files without overwriting existing backups.

This phase proves the minimum useful transfer protocol. It deliberately does not implement resumable/chunked upload sessions, secure pairing, production authentication, Android behavior, or UI.

## Scope

Phase 2 includes planning for:

- Generic fake-device CLI under `tools/fake_phone/`.
- Platform-neutral fake-device terminology in code: `DeviceClient`, `TransferClient`, `FileCandidate`, `MediaItem` only where appropriate.
- Incremental SHA-256 hashing on the client and server.
- Initial `/api/v1/` transfer API.
- Duplicate/existence handling based primarily on `sha256 + size`.
- Single-request streaming upload from client to backend.
- Backend streaming write to temporary storage without loading full files into memory.
- Server-side expected-size and SHA-256 verification before finalization.
- Finalization through the Phase 1 storage boundary.
- Minimal persisted completed-file metadata if justified.
- Filename/path safety, collision safety, and non-overwrite behavior.
- Backend and fake-client tests using temporary roots/databases and tiny deterministic fixtures.
- Documentation updates that reflect the implemented protocol and its security limitations.

## Out of Scope

Do not implement or plan as part of Phase 2:

- Android app.
- MediaStore.
- WorkManager.
- React UI.
- Automatic backup scheduling.
- Local-network discovery.
- mDNS/Zeroconf.
- QR pairing.
- Production authentication.
- Authentication tokens.
- TLS pinning.
- Resumable uploads.
- Chunk upload sessions.
- Upload-session status endpoints.
- Parallel uploads.
- Upload pools.
- Bandwidth control.
- Video/image parsing.
- Thumbnails.
- EXIF processing.
- Manual Android document picker.
- Cloud services.
- Installer/system tray behavior.

Interrupted Phase 2 transfers may restart from zero. Phase 3 will add resumability.

## Current System Context

Phase 1 is complete.

Current backend capabilities:

- `desktop/backend/pyproject.toml` defines the Python package and dependencies.
- FastAPI app factory exists in `desktop/backend/app/main.py`.
- The only API path is `GET /api/v1/health`.
- Settings live in `app/core/config.py` and currently include environment, data root, optional database URL, and log level.
- SQLAlchemy setup exists in `app/db/session.py`.
- Alembic exists with empty `0001_baseline`.
- No domain tables, repositories, upload routes, pairing, authentication, discovery, transfer behavior, Android code, or UI exist.
- Storage foundation exists in `app/storage/`:
  - `LocalFilesystemStorage` derives `temp_root = <data-root>/.localsync-temp` and `backup_root = <data-root>/backups`;
  - `partial_path(session_id)` returns `<temp-root>/<session-id>.partial`;
  - `final_path(storage_key)` currently accepts a single safe path component;
  - `reserve_final_path(storage_key)` prevents overwrite;
  - `finalize_partial(partial_path, storage_key)` renames a partial file into final backup storage;
  - `sanitize_filename()` removes unsafe characters and handles reserved names;
  - `resolve_contained_path()` rejects absolute paths, traversal, and separators.

Current docs:

- `docs/protocol.md` describes future upload-session endpoints, but they are not implemented.
- `docs/security.md` clearly says there is no pairing/authenticated transfer.
- ADR-0001 requires platform-neutral protocol/domain language.
- ADR-0002 requires one-way deletion-safe backup semantics.
- ADR-0003 requires byte-preserving media transfer and SHA-256 integrity verification.

## Assumptions

- Phase 2 remains a development/test protocol foundation, not production-ready device trust.
- `tools/fake_phone/` remains the directory name to avoid churn, but Python package names, classes, API fields, and docs should use generic device/client language.
- The fake client can be synchronous and sequential.
- The fake client can use `httpx`, already present as a backend dev dependency, rather than adding `requests` or `aiohttp`.
- Tiny deterministic test fixtures are sufficient; fixtures do not need to be valid JPEG/video files because Phase 2 treats files as opaque bytes.
- The backend may add one minimal completed-file metadata table because successful transfer and duplicate detection now require durable state.
- The backend should not add persistent `UploadSession` yet because Phase 2 uses a single non-resumable upload request.
- A development-only `device_id` is acceptable for namespacing and testing but must not be described as authentication.

## Architecture / Approach

Use the existing backend boundaries and add only what Phase 2 behavior needs:

- API route module for files/transfers under `/api/v1/`.
- Pydantic request/response schemas at API boundary.
- A small application service to coordinate check/upload behavior, storage, hashing, and persistence.
- A minimal SQLAlchemy model/repository for completed stored files only if implementation confirms durable duplicate detection requires it.
- Storage enhancements to produce server-controlled final storage keys and allow nested safe namespaces generated by server code, not client paths.
- Fake client code under `tools/fake_phone/` that scans local files, hashes incrementally, calls the check endpoint, and streams uploads sequentially.

Do not create broad interfaces for every class. The filesystem storage boundary and repository boundary are justified; generic base service/repository classes are not.

## Proposed Phase 2 API

Use `/api/v1/files` rather than `/api/v1/media` or `/api/v1/upload-sessions`.

Rationale:

- Phase 2 transfers generic opaque files from a fake device. They may simulate future media but should not imply Android MediaStore or media-only behavior.
- `upload-sessions` implies resumability/session lifecycle, which belongs to Phase 3.
- `files` is platform-neutral and simple enough for Android to implement later without backend redesign.

### `POST /api/v1/files/check`

Purpose: determine whether the backend already has an exact file for a development device namespace.

Request concept:

```json
{
  "device_id": "fake-device-1",
  "filename": "normal.jpg",
  "size": 123,
  "sha256": "<64 lowercase hex chars>"
}
```

Response concept when already stored:

```json
{
  "status": "already_stored",
  "stored_file_id": "<opaque id>",
  "stored_path": "<safe relative storage key>"
}
```

Response concept when upload is needed:

```json
{
  "status": "upload_required"
}
```

Do not treat filename alone as identity. The check uses `device_id + size + sha256` for Phase 2. A future global deduplication policy can be evaluated separately.

### `POST /api/v1/files`

Purpose: stream a complete file in a single request.

Metadata is supplied as headers plus a raw binary body. The server streams `request.stream()` to disk and must not call `await request.body()` or accept file bytes as `bytes`.

Request metadata concept:

- `X-localSync-Device-Id`
- `X-localSync-Filename`
- `X-localSync-Size`
- `X-localSync-Sha256`
- optional `X-localSync-Content-Type`, treated as metadata only

Response concept for new successful storage:

```json
{
  "status": "stored",
  "stored_file_id": "<opaque id>",
  "stored_path": "<safe relative storage key>"
}
```

Response concept for idempotent duplicate:

```json
{
  "status": "already_stored",
  "stored_file_id": "<opaque id>",
  "stored_path": "<safe relative storage key>"
}
```

Duplicate behavior can be returned from both check and upload. Upload should recheck before writing so a client that skips or races the check does not create unnecessary duplicates.

## Duplicate / Existence Decision

Implement an explicit check endpoint and duplicate handling during upload.

Tradeoff:

- Check endpoint gives the fake client a clear protocol step and avoids sending bytes for known files.
- Upload-side deduplication is still required for correctness because clients can be retried, stale, or skip the check.
- This is slightly more API than upload-only deduplication, but it matches the intended future client workflow without creating upload sessions.

Phase 2 should not implement complicated global deduplication. Use exact-match lookup by `device_id + size + sha256`; filename is stored as metadata and used for readable storage names, not identity.

## Proposed Data Model

Add one minimal completed-file metadata table, likely named `stored_files`.

Justification:

- Duplicate/existence checks must survive backend restarts.
- The backend needs to know which final filesystem path corresponds to a verified file.
- Successful transfer needs an explicit metadata record separate from temporary files.

Do not add `Device` or `UploadSession` tables in Phase 2. `device_id` is a development namespace string, not a trusted device record.

Proposed fields:

- `id`: opaque server-generated UUID string. Needed for API responses and stable internal identity.
- `device_id`: development-only namespace supplied by client. Needed to isolate fake devices and avoid cross-device collisions.
- `original_filename`: sanitized/display-safe metadata derived from client filename. Needed for human-readable context; not used as a filesystem path.
- `size`: integer expected/verified byte count. Needed for integrity and duplicate lookup.
- `sha256`: lowercase 64-character hex digest. Needed for byte identity and duplicate lookup.
- `stored_path`: server-controlled relative storage key under `backups/`. Needed to locate the finalized file without storing absolute user paths in API responses.
- `content_type`: nullable metadata only if implementation can obtain it without trusting it for behavior.
- `created_at`: timestamp for audit/debugging.

Indexes/constraints:

- Unique constraint on `(device_id, size, sha256)` for idempotent exact duplicate detection.
- Unique constraint on `stored_path` to prevent two records pointing to one final file.

Actual bytes remain normal filesystem files. No BLOB columns.

Alembic migration:

- Add `0002_stored_files.py` after `0001_baseline`.
- Tests must apply migrations to a temporary SQLite database.

## Storage / Destination Strategy

Use a deterministic, non-destructive, generic destination layout:

```text
<data-root>/
    .localsync-temp/
        <transfer-id>.partial
    backups/
        <safe-device-id>/
            <safe-filename-stem>_<short-sha256><extension>
```

Example:

```text
backups/fake-device-1/IMG_0001_a1b2c3d4e5f6.jpg
```

Rationale:

- Device namespace prevents accidental collisions across development clients.
- Short hash in final filename lets same-name different-content files coexist.
- Full SHA-256 remains in the database; short hash is only for readable collision-resistant naming.
- No Photos/Videos/year/month organization is introduced before real media metadata exists.

The storage key must be generated by backend code from sanitized components. The client must never provide a final path or storage key.

Phase 1 `resolve_contained_path()` currently accepts only one path component. Phase 2 should extend storage safely for server-generated relative storage keys with multiple components, while preserving rejection of absolute paths, traversal, and unexpected separators from untrusted inputs.

## Upload / Finalization Flow

Chosen Phase 2 flow:

1. API validates required metadata shape: `device_id`, `filename`, `size`, `sha256`.
2. Service normalizes and validates device namespace and filename as metadata, not paths.
3. Service checks `stored_files` for `(device_id, size, sha256)`.
4. If found and final file still exists, return `already_stored`.
5. If metadata exists but file is missing, treat as consistency damage and return a structured error; do not silently claim success.
6. Generate a unique temporary transfer id and write request body to `<data-root>/.localsync-temp/<transfer-id>.partial` using streaming copy.
7. While streaming, count bytes and compute SHA-256 incrementally.
8. If byte count differs from declared size or hash differs from declared SHA-256, delete the partial file immediately and return structured failure.
9. Generate server-controlled final storage key using safe device id, sanitized original filename, and short SHA-256.
10. Reserve final path; if an exact final path conflict exists but content is not recorded as duplicate, generate a deterministic tie-breaker or return conflict rather than overwrite.
11. Atomically rename partial file into final backup storage through the storage boundary.
12. Insert `stored_files` metadata record.
13. Return `stored`.

Invalid temporary files should be deleted immediately. This is safer and simpler than retaining untrusted/corrupted data for diagnostics. Diagnostics should rely on structured logs and errors, not preserved invalid payloads.

## Filesystem / Database Consistency Strategy

There is no distributed transaction across SQLite and the filesystem.

Chosen Phase 2 ordering:

1. stream to partial file;
2. verify size/hash;
3. finalize filesystem file by same-root rename;
4. insert completed metadata record;
5. if metadata insert fails, keep the finalized file as durable backup bytes and return/report a database error. Later matching requests must reconcile metadata by verifying the existing finalized file.

Why this order:

- It never records a successful backup before bytes are verified and finalized.
- It avoids a database record pointing at a partial file.
- If DB insert fails after finalization, the worst case is an orphan finalized file, not a false successful record. Phase 2 treats filesystem bytes as durable and database metadata as recoverable catalog state for this specific failure window.

Known limitation:

- A crash after filesystem finalization but before DB insert can leave an orphan completed file not discoverable by database duplicate checks until the same expected content is checked/uploaded again. Phase 2 must reconcile this case by verifying full SHA-256 and size of the deterministic final file, recreating the metadata record, and returning success/already stored.

Alternative rejected:

- Insert pending state before finalization and update after finalization. This resembles upload sessions and recovery state, which belongs with resumable Phase 3 work.

## Filename and Path Safety

Rules:

- Client filename is metadata only.
- Client cannot choose final filesystem path.
- Reject or sanitize malicious filenames before any storage key generation.
- Reject absolute path injection, `../`, `..\\`, path separators, and names that collapse to empty.
- Preserve original filename only as safe metadata, not as authority.
- Never overwrite an existing completed backup file.

Required test names:

- `../secret.txt`
- `..\\secret.txt`
- `C:\\secret.txt`
- `/foo/bar.jpg`
- `normal.jpg`
- same-name different hashes

## Collision Behavior

Filename equality does not mean content equality.

Phase 2 storage key should include a short SHA-256 suffix:

```text
<safe-filename-stem>_<first-12-sha256><extension>
```

Examples:

- `IMG_0001_a1b2c3d4e5f6.jpg`
- `IMG_0001_987654321abc.jpg`

Same device, same filename, different content must create distinct final files. Same device, same size, same full SHA-256 must return `already_stored` and not create a duplicate.

If a short-hash filename collision somehow occurs, do not overwrite. Either append an opaque deterministic suffix derived from the full hash/record id or return `storage_conflict`. Prefer a deterministic extended-hash fallback before failing.

## Fake Device Client Design

Location:

```text
tools/fake_phone/
    README.md
    pyproject.toml or package metadata if needed
    fake_phone/
        __init__.py
        __main__.py
        cli.py
        client.py
        scanner.py
        hashing.py
        models.py
    tests/
        ...
```

Keep `tools/fake_phone/` as the directory name. Renaming it provides little value and would churn docs; code and docs should clarify it is a generic fake device.

CLI syntax:

```powershell
cd tools/fake_phone
python -m fake_phone --server http://127.0.0.1:8000 --device-id fake-device-1 --source ./sample-media
```

Behavior:

- Recursively or non-recursively scan a configured source directory. Prefer non-recursive for Phase 2 unless recursive scanning is needed by tests.
- Ignore directories.
- For each file, compute size from filesystem metadata and SHA-256 incrementally using fixed-size reads.
- Call `POST /api/v1/files/check`.
- If upload required, stream the file to `POST /api/v1/files`.
- Print concise per-file result: stored, already stored, failed.
- Exit nonzero if any file fails.

Use `argparse` rather than a CLI framework. Use synchronous `httpx.Client` and file iterators/generators for streaming. Do not add `requests` or `aiohttp`.

## Streaming Requirements

Client:

- Hash with incremental reads, for example 1 MiB chunks.
- Upload with a file object or generator so file bytes are not loaded into memory.

Server:

- Use a FastAPI/Starlette approach that streams request data.
- Do not use `await file.read()` without a bounded size; avoid patterns that load the entire file.
- Prefer iterating `request.stream()` for a raw binary body if multipart upload cannot be proven to stream safely.
- Compute hash and byte count during write.
- Use standard-library file I/O with bounded buffers.

Implementation must document the selected approach in the plan's Discoveries section.

## Error Semantics

Use structured `AppError` responses.

Planned error cases:

- `metadata_required`: missing required metadata.
- `metadata_invalid`: invalid size, SHA-256, device id, filename, or content type.
- `filename_invalid`: filename cannot be sanitized safely.
- `size_mismatch`: actual bytes do not match declared size.
- `hash_mismatch`: actual SHA-256 does not match declared SHA-256.
- `already_stored`: represented as a successful status, not an error.
- `storage_conflict`: destination collision that cannot be resolved safely.
- `storage_error`: filesystem failure.
- `database_error`: persistence failure.
- `client_disconnected`: interrupted upload or request stream failure where detectable.

Interrupted upload/server shutdown behavior:

- Phase 2 does not resume.
- Partial files must remain isolated under `.localsync-temp` or be deleted safely.
- No completed metadata record should be created.
- Backend should remain usable after the failure.

## Observability

Log enough to understand:

- transfer started;
- transfer skipped as duplicate;
- transfer verification failed;
- transfer finalized;
- database consistency cleanup attempted/failed.

Do not log raw file contents, request bodies, future secrets, or per-buffer transfer logs. Log hashes only sparingly, preferably truncated or in debug logs, because full hashes are identifiers.

## Dependency / Tooling Decisions

Backend:

- Existing dependencies are sufficient: FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, httpx, Ruff.
- If implementation chooses FastAPI multipart `UploadFile`, `python-multipart` may be required. Avoid adding it unless multipart is chosen and streaming behavior is confirmed.
- Prefer raw binary body + metadata headers to avoid adding `python-multipart` if it keeps streaming simple and explicit.

Fake client:

- Use `httpx`, already present in backend dev dependencies. If the fake client gets its own `pyproject.toml`, depend on `httpx` there.
- Use standard library `argparse`, `hashlib`, `pathlib`, and `mimetypes`.
- Do not add Requests, aiohttp, Typer, Click, rich, or async frameworks in Phase 2.

Testing:

- Keep using pytest and httpx/TestClient.
- Do not add media-processing libraries.

## Implementation Milestones

- [ ] Milestone 1: Finalize protocol details in docs and tests-first API shape.
  - Confirm raw streaming request body vs multipart after a brief FastAPI/Starlette implementation check.
  - Update `docs/protocol.md` with Phase 2 endpoint contract before or alongside implementation.
  - Keep repository valid; no fake-client behavior yet.

- [ ] Milestone 2: Add completed-file persistence.
  - Add `stored_files` SQLAlchemy model, repository, and Alembic migration.
  - Add migration tests and repository tests with temporary SQLite databases.
  - Do not add Device or UploadSession tables.

- [ ] Milestone 3: Extend storage foundation safely.
  - Add server-generated storage-key helpers for device namespace and hash-suffixed filename.
  - Preserve traversal/absolute/separator protection.
  - Add tests for malicious names, same-name different hashes, and final path non-overwrite.

- [ ] Milestone 4: Implement backend check endpoint.
  - Add `POST /api/v1/files/check`.
  - Lookup by `device_id + size + sha256`.
  - Return `upload_required` or `already_stored`.
  - Add API tests.

- [ ] Milestone 5: Implement backend single-request streaming upload.
  - Add `POST /api/v1/files`.
  - Stream request bytes to partial storage.
  - Compute size/hash during write.
  - Verify, finalize, persist metadata, and return structured status.
  - Delete invalid partial files on verification failure.
  - Add success, duplicate, mismatch, collision, traversal, and failure tests.

- [ ] Milestone 6: Implement generic fake-device CLI.
  - Add package under `tools/fake_phone/`.
  - Scan source directory, hash files incrementally, check backend, stream uploads sequentially, report results.
  - Add fake-client unit tests with tiny deterministic files.

- [ ] Milestone 7: End-to-end integration tests.
  - Exercise fake client against in-process or local test backend using temporary data root/database.
  - Validate source bytes equal destination bytes.
  - Validate rerun duplicate behavior and same-name different-content behavior.

- [ ] Milestone 8: Documentation and final validation.
  - Update docs listed below.
  - Run all configured backend and fake-client tests, Ruff checks, migration validation, and manual/direct transfer smoke test.
  - Update this ExecPlan Progress, Discoveries, Decision Log, and Final Results.
  - Move plan to completed only if all completion criteria are met.

Each milestone should leave tests runnable and should not introduce Phase 3 resumability or production security.

## Files / Modules Expected to Change

Expected backend creates/updates:

- `desktop/backend/app/api/v1/files.py`
- `desktop/backend/app/api/v1/router.py`
- `desktop/backend/app/api/v1/schemas.py` or endpoint-local schemas
- `desktop/backend/app/models/stored_file.py`
- `desktop/backend/app/repositories/stored_files.py`
- `desktop/backend/app/services/file_transfers.py`
- `desktop/backend/app/storage/local_filesystem.py`
- `desktop/backend/app/storage/names.py`
- `desktop/backend/app/storage/paths.py`
- `desktop/backend/migrations/versions/0002_stored_files.py`
- `desktop/backend/tests/test_file_check.py`
- `desktop/backend/tests/test_file_upload.py`
- `desktop/backend/tests/test_stored_files_repository.py`
- `desktop/backend/tests/test_storage_paths.py`

Expected fake-client creates/updates:

- `tools/fake_phone/README.md`
- `tools/fake_phone/pyproject.toml` if a separate installable package is useful
- `tools/fake_phone/fake_phone/__init__.py`
- `tools/fake_phone/fake_phone/__main__.py`
- `tools/fake_phone/fake_phone/cli.py`
- `tools/fake_phone/fake_phone/client.py`
- `tools/fake_phone/fake_phone/scanner.py`
- `tools/fake_phone/fake_phone/hashing.py`
- `tools/fake_phone/fake_phone/models.py`
- `tools/fake_phone/tests/**`

Expected docs updates:

- `docs/protocol.md`
- `docs/security.md`
- `docs/testing.md`
- `docs/development.md`
- `docs/current-state.md`
- `docs/repo-map.md`
- `desktop/backend/README.md`
- `tools/fake_phone/README.md`
- this ExecPlan

Possible ADR:

- Only create an ADR if Phase 2 settles a durable cross-cutting transfer contract that is expected to constrain Android and future clients. Ordinary endpoint naming or model implementation details do not need an ADR.

## Testing and Validation

Tests must use temporary data roots and isolated temporary SQLite databases. They must never write to real backup data.

Required backend tests:

- successful transfer creates completed destination;
- source SHA-256 equals destination SHA-256;
- source bytes equal destination bytes for tiny deterministic fixture;
- source file remains unchanged;
- duplicate upload same exact file does not create unnecessary duplicate;
- filename collision same name/different hash does not overwrite;
- hash mismatch fails and no completed backup file exists;
- size mismatch fails and no completed backup file exists;
- interrupted/failed upload leaves no completed backup file where practical;
- malicious filenames fail safely or sanitize safely without path escape:
  - `../secret.txt`;
  - `..\\secret.txt`;
  - `C:\\secret.txt`;
  - `/foo/bar.jpg`;
  - `normal.jpg`;
- multiple development device namespaces do not unintentionally collide;
- Alembic migration applies to temporary SQLite;
- database records do not store file bytes.

Required fake-client tests:

- scanner identifies files and ignores directories;
- hasher computes SHA-256 incrementally;
- client sends check request before upload;
- client streams file body without reading all bytes into memory;
- CLI exits zero when all files are stored/already stored;
- CLI exits nonzero on failed transfer.

Required integration test:

- Create tiny deterministic files in a temp fake source directory.
- Run fake client against a test backend configured with temp data root/database.
- Verify completed destination exists and bytes match.
- Run fake client again and verify duplicate status/no unnecessary duplicate.
- Transfer same-name different-content files and verify original is not overwritten.

Validation commands expected after implementation:

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic current
```

If fake client has its own project:

```powershell
cd tools/fake_phone
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Manual smoke test:

```powershell
cd desktop/backend
python -m uvicorn app.main:app --reload
```

In another shell:

```powershell
cd tools/fake_phone
python -m fake_phone --server http://127.0.0.1:8000 --device-id fake-device-1 --source ./sample-media
```

Use tiny generated files only.

## Security Considerations

Phase 2 remains development-only for transfer security.

Implemented security groundwork should include:

- no client-controlled server paths;
- metadata validation;
- safe filename handling;
- path traversal and absolute path rejection;
- server-controlled storage keys;
- no overwrite of completed backups;
- no completed file before size/hash verification;
- no DB metadata record before finalized bytes exist;
- no file contents in logs;
- clear structured errors.

Security limitations that must be documented:

- `device_id` is a development namespace, not authentication.
- Any client that can reach the backend can call Phase 2 upload endpoints unless later protected.
- No pairing, tokens, TLS pinning, encrypted local transport, or authorization exists.
- No quota enforcement unless explicitly added as a small safety check during implementation.
- A crash between filesystem finalization and DB insert can leave an orphan finalized file until a later matching request reconciles metadata.

Do not present Phase 2 as production-secure transfer.

## Risks / Unknowns

- FastAPI multipart upload behavior may not meet streaming requirements without `python-multipart`; raw request streaming may be cleaner.
- SQLite/file consistency cannot be atomic across filesystem and DB.
- Development-only upload endpoints are intentionally unauthenticated and must not be mistaken for production endpoints.
- Storage path helpers need careful extension from single-component keys to server-generated nested keys.
- Short SHA-256 suffix collisions are unlikely but must not cause overwrite.
- Integration testing the CLI against an in-process backend may require careful server/test fixture design.
- If fake client has a separate `pyproject.toml`, dependency duplication with backend dev dependencies should stay minimal and documented.

## Architecture Review

1. Does the protocol remain independent of Android?
   - Yes. Planned endpoints use generic file/device terminology. No Android routes, MediaStore IDs, or Android-specific domain types are planned.

2. Are we accidentally implementing resumability early?
   - No. Phase 2 uses a single streaming request. It may use temporary files and hashes, but it does not create upload sessions, offsets, chunks, or resume endpoints.

3. Can the server process a multi-GB file without loading it entirely into memory?
   - The plan requires server-side streaming and incremental hashing. Implementation must avoid unbounded `read()` calls and record the chosen FastAPI/Starlette streaming method.

4. Can incomplete data ever appear inside completed backup storage?
   - It should not. Bytes first land in `.localsync-temp`; only verified bytes are renamed into `backups/`. Tests must assert failed uploads do not appear under completed storage.

5. Is filename/path handling safe?
   - The client filename is metadata only. Final storage keys are server-generated from sanitized components. Traversal, absolute paths, and separators from untrusted input must be rejected or neutralized.

6. Can duplicate uploads be handled idempotently?
   - Yes. Check and upload both use `device_id + size + sha256`; duplicate upload returns `already_stored` rather than creating another file.

7. Can same-name different-content files coexist safely?
   - Yes. Final names include a short SHA-256 suffix, and full SHA-256 is stored in metadata. Existing files must never be overwritten.

8. Is filesystem/database consistency behavior explicitly understood?
   - Yes. The chosen order favors never recording success before verified finalization. The known orphan-file crash window is documented.

9. Are tests isolated from real data?
   - Yes. All backend and client tests must use temporary data roots, fake source directories, and temporary SQLite databases.

10. Can Android later implement the same client protocol without backend redesign?
    - Yes. Android can scan MediaStore, compute size/SHA-256 incrementally, call the same generic `/api/v1/files/check` and `/api/v1/files` endpoints, and stream file bytes.

## Documentation Impact

During implementation update:

- `docs/protocol.md`: record actual Phase 2 endpoints, request/response schemas, duplicate behavior, and that upload sessions remain future Phase 3.
- `docs/security.md`: add currently implemented Phase 2 safeguards and explicitly state `device_id` is not authentication.
- `docs/testing.md`: add transfer/fake-client/integration tests and byte-preservation invariant coverage.
- `docs/development.md`: add fake-client setup/run/test commands.
- `docs/current-state.md`: mark Phase 2 complete only after validation.
- `docs/repo-map.md`: add fake-client package and backend transfer modules.
- `desktop/backend/README.md`: add transfer API/dev-only warnings and validation commands.
- `tools/fake_phone/README.md`: add generic fake-device CLI usage.

Evaluate ADR need after implementation. A durable API choice may warrant an ADR if it constrains future Android/iOS clients; ordinary implementation details do not.

## Progress

- 2026-08-15: Created Phase 2 ExecPlan after reading root/tools/backend agent instructions, Phase 1 current docs, architecture/protocol/security/testing/development docs, ADRs, completed Phase 1 plan, and actual backend implementation. No Phase 2 code implemented.
- 2026-08-15: Milestone 1 completed. Locked Phase 2 upload transport to raw streaming request body with metadata headers and updated protocol docs. Updated consistency strategy so finalized filesystem bytes are durable and DB metadata is recoverable.
- 2026-08-15: Milestone 2 completed. Added `stored_files` model, repository, and Alembic `0002_stored_files` migration. No Device, UploadSession, chunk, pairing, or auth tables were added. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed.
- 2026-08-15: Milestone 3 completed. Extended storage helpers for server-generated nested storage keys, device namespace validation, hash-suffixed filenames, traversal rejection, and same-name/different-hash key separation. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed.
- 2026-08-15: Milestone 4 completed. Added `POST /api/v1/files/check`, service/repository integration, and metadata reconciliation when deterministic finalized bytes exist without DB metadata. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed.
- 2026-08-15: Milestone 5 completed. Added raw-body `POST /api/v1/files` upload using `Request.stream()`, incremental server SHA-256/size validation, temp cleanup on validation failure, non-overwrite finalization, duplicate handling, and filesystem-first metadata recovery tests. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed.
- 2026-08-15: Milestone 6 completed. Added generic fake-device CLI under `tools/fake_phone` using argparse, synchronous httpx, sequential check-before-upload behavior, incremental hashing, streamed file upload, and tests. `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` passed in `tools/fake_phone`.
- 2026-08-15: Milestone 7 completed. Added live Uvicorn integration test exercising fake client, successful transfer, duplicate skip, and same-name different-content preservation against temporary backend data. Backend validation passed with 57 tests.
- 2026-08-15: Milestone 8 completed. Updated protocol, security, testing, development, repo map, current-state, backend README, fake-client README, and this plan. Final validation and manual demo passed.

## Discoveries

- Phase 1 backend exposes only `/api/v1/health`.
- Phase 1 Alembic baseline has no domain tables.
- Phase 1 storage keys currently accept only one path component, so Phase 2 needs a carefully tested server-generated nested storage-key helper for `<device>/<filename_hash.ext>`.
- Existing storage roots already support same-root temp/final layout under `LOCALSYNC_DATA_ROOT`.
- `httpx` is already available as a backend dev dependency and is a reasonable fake-client HTTP dependency.
- Phase 2 upload will use `Request.stream()` with metadata headers, avoiding multipart and `python-multipart`.
- Server upload processing writes each chunk yielded by `Request.stream()` to a `.partial` file while updating SHA-256 and byte count; it does not call `request.body()` or accept file bytes as a `bytes` parameter.
- Live integration tests start a temporary Uvicorn server on localhost and use the actual fake-client CLI against generated sample files.
- Manual demo on generated temp files showed first upload stored one file, second run skipped exact duplicate without increasing completed file count, and same-name different-content transfer produced a second completed file while preserving the first.

## Decision Log

- Keep `tools/fake_phone/` directory name; use generic client/device terminology inside code and docs.
- Use explicit `POST /api/v1/files/check` plus upload-side duplicate detection.
- Use `POST /api/v1/files` for a single streaming upload request instead of upload sessions.
- Add only a `stored_files` table in Phase 2 if persistence is implemented; do not add Device or UploadSession tables.
- Use `device_id` only as a development namespace, not authentication.
- Use server-generated storage keys under `backups/<safe-device-id>/`.
- Include short SHA-256 suffix in final filenames to allow same-name different-content coexistence.
- Delete invalid temporary files immediately on verification failure.
- Prefer raw request streaming unless multipart streaming is proven safe and worth the dependency.
- Preserve finalized backup files if metadata persistence fails; reconcile missing metadata on later matching checks/uploads by verifying full SHA-256 and size.
- Do not create a Phase 2 ADR; the implementation follows the approved protocol plan and existing media-integrity/platform-neutrality ADRs without adding a new cross-cutting decision.

## Completion Criteria

Phase 2 is complete when:

- Backend has documented `/api/v1/files/check` and `/api/v1/files` endpoints.
- Fake-device CLI can scan a source directory, hash files incrementally, check backend state, stream uploads, and report results.
- Successful transfers preserve bytes exactly.
- Duplicate exact files do not create unnecessary duplicates.
- Same-name different-content files do not overwrite existing backups.
- Failed hash/size/interrupted uploads do not create completed backup files or success metadata.
- Completed-file metadata, if implemented, is managed through Alembic and stores no file bytes.
- Tests cover success, duplicate, collision, mismatch, path traversal, device namespace, and fake-client behavior using temp roots/databases.
- Docs are updated to reflect actual API, development workflow, tests, and security limitations.
- Validation commands pass or any environment limitations are explicitly documented.
- This ExecPlan is updated with progress, discoveries, decision log, and final results.
- The plan is moved to `docs/plans/completed/` only if all completion criteria are genuinely satisfied.

## Final Results

Completed on 2026-08-15.

Implemented:

- `POST /api/v1/files/check` exact-content check.
- `POST /api/v1/files` complete non-resumable raw-body streaming upload.
- Header metadata validation for development device namespace, filename, declared size, declared SHA-256, and optional advisory content type.
- Incremental server-side SHA-256 and byte counting while streaming request chunks into `.localsync-temp`.
- Verification before finalization into `backups`.
- Deterministic server-generated storage keys under `backups/<device-id>/`.
- Same-name different-content coexistence using hash-suffixed filenames.
- Duplicate exact-content handling by `device_id + size + full SHA-256`.
- `stored_files` table through Alembic `0002_stored_files`.
- Filesystem/DB recovery for finalized bytes missing metadata: later matching check/upload verifies full SHA-256 and size, recreates metadata, and returns success.
- Generic fake-device CLI under `tools/fake_phone`.
- Backend, fake-client, and live local integration tests.

Validation:

- `desktop/backend`: `python -m pytest` passed with 57 tests. Uvicorn/websockets deprecation warnings appeared from installed dependencies during the live server integration test.
- `desktop/backend`: `python -m ruff check .` passed.
- `desktop/backend`: `python -m ruff format --check .` passed.
- `desktop/backend`: `python -m alembic upgrade head` passed through `0002_stored_files`.
- `desktop/backend`: `python -m alembic current` reported `0002_stored_files (head)`.
- `tools/fake_phone`: `python -m pytest` passed with 8 tests.
- `tools/fake_phone`: `python -m ruff check .` passed.
- `tools/fake_phone`: `python -m ruff format --check .` passed.
- Source search found no Android/Windows-specific protocol/domain type names and no upload-session, offset, resume, mDNS, WorkManager, MediaStore, or React implementation.
- Manual demo with generated temp files passed:
  - first fake-client run uploaded `IMG_0001.bin`;
  - second run reported already backed up and completed file count stayed at 1;
  - same filename with different bytes uploaded safely and completed file count became 2;
  - source/destination hash preservation was true;
  - both expected byte contents were present.

Intentional limitations:

- Phase 2 upload is not resumable. Interrupted transfers restart from byte zero.
- `device_id` is only a development namespace, not authentication.
- Upload endpoints are not production-secure until pairing/authentication exists.
- No quota enforcement, TLS pinning, mDNS discovery, Android behavior, UI, media parsing, thumbnails, EXIF, or cloud behavior was implemented.
- A crash after filesystem finalization but before DB insert can leave an orphan finalized file until the same expected content is checked or uploaded again.
