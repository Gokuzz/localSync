# Phase 1: Desktop Backend Foundations

## Purpose / User Outcome

Establish a clean, testable desktop backend foundation for localSync. After Phase 1, the repository should have a runnable Python backend skeleton with configuration, database migration infrastructure, storage safety primitives, API conventions, structured errors, logging conventions, and pytest coverage.

This phase does not deliver media backup to users yet. It prepares the backend so later phases can implement upload sessions, resumable transfer, secure pairing, and fake-device integration without reshaping the project.

## Scope

Phase 1 includes:

- Python backend project metadata and minimal developer tooling.
- FastAPI application bootstrap.
- Versioned API route structure under `/api/v1/`.
- `GET /api/v1/health`.
- Externalized configuration for environment, database path/URL, backup root, temporary upload root, and logging level.
- SQLAlchemy + SQLite setup.
- Alembic initialization and an initial migration for only currently justified metadata tables.
- A small persistence layer for records needed by the architecture foundation.
- Filesystem storage component for safe path handling, partial/final directory separation, and atomic finalization primitives.
- Structured application/API error conventions.
- Logging configuration that avoids secrets and large file contents.
- pytest infrastructure and focused tests.
- Backend README/development documentation updates.

## Out of Scope

Do not implement:

- Android application.
- React desktop UI.
- Fake phone/client implementation.
- Automatic media scanning.
- WorkManager.
- MediaStore integration.
- QR pairing.
- Authentication tokens.
- Cryptographic pairing.
- TLS certificate pinning.
- mDNS / Zeroconf device discovery.
- Chunked uploads.
- Resumable uploads.
- Actual photo/video transfer.
- Manual arbitrary-file transfer.
- SHA-256 transfer verification workflow.
- Windows installer.
- System tray behavior.
- Startup-with-Windows behavior.
- Cloud functionality.

Phase 1 may leave names, fields, and extension points that account for future upload/session work, but must not implement those behaviors.

## Current System Context

The repository is in Phase 0.

- Root agent instructions and docs exist.
- `desktop/backend/` contains only `AGENTS.md` and `README.md`.
- No Python package, dependency metadata, tests, migrations, API code, or database exists.
- The product invariant is one-way backup: source deletion must never automatically delete laptop backup files.
- Media/files must remain normal filesystem files, not database BLOBs.
- Incomplete uploads must never appear as successful backups.
- Protocol/domain terminology must remain platform-neutral.

Relevant docs:

- `AGENTS.md`: repository invariants and validation expectations.
- `desktop/AGENTS.md`: desktop scope and platform-neutral terminology.
- `desktop/backend/AGENTS.md`: backend boundaries, streaming, database, storage, security, and testing expectations.
- `docs/architecture.md`: conceptual components and storage model.
- `docs/protocol.md`: future `/api/v1/` protocol concepts.
- `docs/security.md`: desired security vs currently implemented security.
- `docs/testing.md`: planned tests and deletion-safety invariant.
- `docs/development.md`: workflow and dependency policy.
- `docs/roadmap.md`: Phase 1 is desktop backend foundations.
- ADR-0001: platform-neutral domain/protocol model.
- ADR-0002: one-way deletion-safe backup semantics.
- ADR-0003: byte-preserving media integrity and filesystem storage.

## Assumptions

- The backend package will live entirely under `desktop/backend/`.
- V1 runs on Windows, but code should use Python `pathlib` and explicit storage adapters so domain and API names do not depend on Windows.
- SQLite is sufficient for local metadata in Phase 1.
- The initial database schema should include only tables useful for backend foundations and future transfer work: devices, upload sessions, and backup records/stored files. If implementation discovers a table has no immediate reason to exist, defer it.
- Authentication and pairing are not implemented in Phase 1, so any upload-like endpoints must remain absent.
- The health endpoint may expose non-sensitive service metadata such as service name, status, and API version.
- Tests must use temporary directories and temporary SQLite databases.

## Architecture / Approach

Use a small layered structure that creates real boundaries without abstracting every class.

- API routes handle HTTP details, Pydantic schemas, dependency wiring, and error translation.
- Application services contain business coordination when behavior exceeds simple CRUD.
- Domain modules define enums/value objects that are independent of FastAPI, SQLAlchemy, and operating system details.
- Persistence modules own SQLAlchemy engine/session setup, models, migrations, and repository behavior.
- Storage modules own filesystem path generation, safe name handling, temporary file locations, final backup locations, and atomic finalization.
- Core modules own configuration, logging, and application errors.

Avoid generic interfaces unless they protect a real boundary. The filesystem storage boundary is justified because it isolates platform path behavior, partial/final safety rules, and test directories. A repository boundary is justified where tests need to verify database behavior without involving FastAPI. Trivial pure functions should not get interface wrappers.

## Proposed Package Structure

```text
desktop/backend/
    pyproject.toml
    README.md
    alembic.ini
    app/
        __init__.py
        main.py
        api/
            __init__.py
            deps.py
            v1/
                __init__.py
                router.py
                health.py
                schemas.py
        core/
            __init__.py
            config.py
            errors.py
            logging.py
        db/
            __init__.py
            base.py
            session.py
        domain/
            __init__.py
            enums.py
        models/
            __init__.py
            device.py
            upload_session.py
            backup_record.py
        repositories/
            __init__.py
            devices.py
            upload_sessions.py
            backup_records.py
        services/
            __init__.py
            health.py
        storage/
            __init__.py
            local_filesystem.py
            names.py
            paths.py
    migrations/
        env.py
        script.py.mako
        versions/
            <revision>_initial_backend_foundation.py
    tests/
        conftest.py
        test_health.py
        test_config.py
        test_database.py
        test_repositories.py
        test_storage_paths.py
```

Important choices:

- `app/main.py` exposes the FastAPI application factory and app object.
- `api/v1/router.py` keeps versioned API composition explicit.
- `core/config.py` centralizes settings and environment parsing.
- `db/session.py` owns engine/session lifecycle.
- `models/` contains SQLAlchemy ORM models; `domain/` contains platform-neutral non-ORM concepts.
- `storage/` is the only module that should resolve paths for backup or partial files.
- `tests/` sits inside `desktop/backend/` to keep backend test commands local.

If implementation tooling requires a `src/` layout, prefer the above direct package first unless there is a concrete reason to change. The direct `app/` layout is simpler for FastAPI, Alembic, and this early repository.

## Dependency / Tooling Decisions

Use modern Python project metadata in `desktop/backend/pyproject.toml`.

Production dependencies:

- `fastapi`: HTTP API framework.
- `uvicorn`: local ASGI runtime.
- `pydantic-settings`: typed settings loaded from environment and optional `.env` files.
- `sqlalchemy`: ORM and database abstraction over SQLite.
- `alembic`: managed migrations.

Development dependencies:

- `pytest`: test runner.
- `httpx`: FastAPI test client dependency for async-compatible HTTP testing.
- `ruff`: fast linting and formatting with one tool.
- `mypy` may be added if the implementation is typed enough to make type checking valuable immediately. If it creates more configuration than signal in Phase 1, defer it and document that decision.

Do not lock exact dependency versions during Phase 1 unless an incompatibility is discovered during implementation. Use sensible lower bounds only if needed to avoid known breaking API differences.

Do not add Zeroconf/mDNS in Phase 1. Discovery is Phase 6 and should not become an unused dependency.

## Configuration Approach

Configuration should be loaded from environment variables with safe development defaults that point inside the backend working area or explicit temp paths in tests.

Planned settings:

- `LOCALSYNC_ENV`: `development`, `test`, or future `production`.
- `LOCALSYNC_DATABASE_URL`: SQLAlchemy URL. Default may be a local SQLite file under an ignored data directory for development.
- `LOCALSYNC_BACKUP_ROOT`: root directory for finalized backup files.
- `LOCALSYNC_TEMP_UPLOAD_ROOT`: root directory for partial/incomplete files.
- `LOCALSYNC_LOG_LEVEL`: default `INFO`.

Rules:

- No committed secrets.
- No production credentials in defaults.
- Tests override settings with temp directories and temp databases.
- Configuration validation should reject backup and temporary roots that resolve to the same directory.
- Configuration should create directories only where explicitly appropriate, preferably during app startup or storage initialization rather than at import time.

## Database Approach

Use SQLAlchemy ORM with SQLite and Alembic migrations.

Initial schema is an empty Alembic baseline. Phase 1 establishes SQLAlchemy, SQLite configuration, Alembic, migration workflow, and test database isolation. It does not create Device, UploadSession, BackupRecord, StoredFile, or other domain tables because no current Phase 1 behavior requires them.

Future phases should introduce tables through Alembic migrations when their behavior is actually implemented. Do not include BLOB columns for media bytes.

Migration rules:

- Initialize Alembic under `desktop/backend/migrations/`.
- `migrations/env.py` must import model metadata from `app.db.base`.
- Tests should verify migrations can apply to a temporary SQLite database, or at minimum that the model metadata and migration head are consistent.
- Do not create unmanaged schemas with `metadata.create_all()` in application startup. `create_all()` may be acceptable only in isolated tests if explicitly chosen and documented, but migration-based tests are preferred.

## Storage Approach

Create a local filesystem storage component, not a broad storage interface hierarchy.

Responsibilities:

- Resolve all backup and partial paths under configured roots.
- Generate server-controlled storage keys/relative paths.
- Sanitize original filenames for display or optional suffix use.
- Reject path traversal and absolute untrusted paths.
- Keep partial files separate from finalized backup files.
- Provide primitive operations needed now and later, such as:
  - ensure storage roots exist;
  - compute partial path for a session;
  - compute final path/storage key;
  - validate that a resolved path stays inside the configured root;
  - atomically move a completed partial file into final storage using same-volume paths where possible;
  - detect existing final destinations to avoid overwrite.
- Provide an available disk-space check helper using standard-library facilities such as `shutil.disk_usage`.

Phase 1 should not write real upload chunks or implement resume offsets. The design must preserve room for later chunked writes by making partial files addressable by session/storage key and by keeping finalization separate.

Incomplete files must use a naming/location convention that cannot be mistaken for successful backups, for example a dedicated temp root and/or `.partial` suffix.

## API Approach

Establish API conventions without pretending future security exists.

Minimum endpoint:

- `GET /api/v1/health`

Suggested response:

```json
{
  "status": "ok",
  "service": "localSync desktop backend",
  "api_version": "v1"
}
```

Do not expose upload, pairing, media check, authentication, or transfer endpoints in Phase 1.

API conventions:

- Version routes under `/api/v1/`.
- Use Pydantic response models.
- Use structured error responses with machine-readable codes.
- Avoid exposing raw internal exceptions, local filesystem paths, tracebacks, database details, or configuration secrets.
- Keep route modules small and grouped by feature.

## Error Handling

Define an application error type with:

- stable error code;
- safe message;
- HTTP status mapping where relevant;
- optional safe details.

Register FastAPI exception handlers that return structured JSON. Unexpected exceptions should become generic internal errors in API responses while still being logged safely.

Candidate error codes for Phase 1:

- `configuration_error`
- `storage_path_invalid`
- `storage_conflict`
- `database_error`
- `not_found`
- `internal_error`

Future protocol errors such as `invalid_offset`, `hash_mismatch`, and `unauthorized_device` should be documented but not implemented unless needed by Phase 1 code.

## Logging Approach

Use Python logging configured from settings.

Rules:

- Log application startup, configuration shape, database initialization/migration operations, and storage root readiness.
- Do not log file contents.
- Do not log future authentication secrets, authorization headers, or pairing tokens.
- Avoid per-chunk logs in future transfer code; log transfer summaries and errors instead.
- When logging paths, prefer storage keys or safe relative paths where possible. Avoid exposing unnecessary full user paths in API responses.

Structured JSON logging can be deferred unless it is simple and dependency-free. Do not add a logging dependency in Phase 1 merely for formatting.

## Testing Strategy

Establish pytest as part of Phase 1. Tests must use temporary directories and temporary SQLite databases.

Planned tests:

- Application startup:
  - app factory returns a FastAPI app;
  - versioned router is mounted.
- Health endpoint:
  - `GET /api/v1/health` returns 200;
  - response includes `status = ok` and `api_version = v1`.
- Configuration:
  - defaults are safe for development;
  - environment overrides work;
  - backup root and temp upload root cannot resolve to the same directory.
- Database initialization:
  - SQLAlchemy engine/session can be created for temp SQLite;
  - Alembic migration applies to temp SQLite;
  - expected tables exist after migration.
- Repository behavior where implemented:
  - create/read minimal Device;
  - create/read minimal UploadSession if implemented;
  - create/read completed BackupRecord/StoredFile if implemented.
- Storage path safety:
  - rejects absolute untrusted paths;
  - rejects `..` traversal;
  - sanitizes unsafe filenames;
  - resolved partial/final paths stay under configured roots;
  - collision/overwrite protection is enforced for final paths.
- Temporary/final storage separation:
  - partial path is outside final backup root or clearly separate within controlled roots;
  - finalization operation does not leave a completed record when storage move fails, if record creation is implemented.

Do not write tests that touch a real user backup directory.

## Developer Workflow

Document these commands in `desktop/backend/README.md` during implementation. Exact commands may vary depending on chosen package manager, but prefer minimal standard commands.

Recommended approach:

```powershell
cd desktop/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

If mypy is added:

```powershell
python -m mypy app tests
```

Rationale:

- `venv` and `pip` are standard and avoid introducing a package manager before the project needs one.
- `pyproject.toml` keeps package and tool configuration in one modern metadata file.
- Ruff provides formatting and linting with low setup cost.
- Type checking should be added when it provides useful signal without slowing Phase 1 with heavy configuration.

## Database Migrations

Implementation should:

1. Add Alembic configuration under `desktop/backend/`.
2. Wire migration metadata to SQLAlchemy models.
3. Create one initial migration for the minimal schema.
4. Add a test or documented validation command that applies migrations to a temporary SQLite database.
5. Avoid application startup auto-migrating production data unless explicitly designed. For Phase 1, provide a developer command for migrations instead.

Candidate validation commands:

```powershell
cd desktop/backend
python -m alembic upgrade head
python -m alembic current
```

Tests should override the database URL so migration validation never touches a user database.

## Security Considerations

Phase 1 implements groundwork only. Security documentation must continue to say that pairing/authenticated upload does not exist yet.

Groundwork required:

- Path traversal protection in storage path resolution.
- Unsafe filename handling.
- Server-controlled final and partial paths.
- Overwrite prevention for finalized files.
- Clear database/file consistency boundaries.
- No unrestricted upload endpoints.
- No secrets in config defaults or logs.
- No file contents in logs.
- Structured API errors that do not expose raw paths or internals.

Database/file consistency rule:

- A successful backup record must not be created until storage finalization succeeds.
- If Phase 1 implements only storage primitives and repository tests, document this as an invariant for later transfer implementation.

## Documentation Impact

During Phase 1 implementation, likely update:

- `desktop/backend/README.md`: setup, run, test, lint, migration commands, configuration variables.
- `docs/current-state.md`: move from Phase 0 to Phase 1 completed or Phase 2 ready when implementation finishes.
- `docs/development.md`: backend tooling commands once they exist.
- `docs/architecture.md`: only if implementation materially changes backend boundaries from this plan.
- `docs/security.md`: update "currently implemented security" to reflect actual path safety, structured errors, and lack of auth.
- `docs/testing.md`: record backend test harness and commands.
- `docs/repo-map.md`: add concrete backend package/migration/test paths.

No ADR is expected for the basic backend scaffold unless implementation makes a cross-cutting choice beyond accepted Phase 0 decisions.

## Implementation Milestones

- [ ] Milestone 1: Python project/tooling bootstrap.
  - Create `desktop/backend/pyproject.toml`.
  - Add package skeleton and test skeleton.
  - Configure pytest and Ruff.
  - Leave repository valid with `python -m pytest` runnable, even if tests are minimal.

- [ ] Milestone 2: FastAPI app and configuration.
  - Add app factory in `app/main.py`.
  - Add settings in `app/core/config.py`.
  - Add `/api/v1/health` with Pydantic response model.
  - Add tests for startup, config, and health endpoint.

- [ ] Milestone 3: Database and migrations.
  - Add SQLAlchemy session/metadata setup.
  - Add minimal justified models.
  - Initialize Alembic.
  - Create initial migration.
  - Add migration/database tests using temp SQLite.

- [ ] Milestone 4: Repository foundations.
  - Add minimal repositories only for models introduced.
  - Add tests for create/read behavior.
  - Avoid service abstractions until behavior needs coordination.

- [ ] Milestone 5: Filesystem storage foundation.
  - Add storage path/safe filename/finalization primitives.
  - Add tests for traversal rejection, root containment, partial/final separation, and overwrite prevention.
  - Do not implement chunk writes or upload endpoints.

- [ ] Milestone 6: Error and logging conventions.
  - Add application error type and FastAPI exception handlers.
  - Add logging setup from configuration.
  - Add tests for structured error response where feasible.

- [ ] Milestone 7: Documentation and validation.
  - Update backend README and relevant docs listed above.
  - Run pytest, Ruff check, Ruff format check, migration validation, and type check if configured.
  - Update this ExecPlan progress, discoveries, decision log, and final results.

Each milestone should leave the backend importable and tests runnable. Do not defer broken imports or failing tests to a later milestone.

## Files / Modules Expected to Change

Expected creates:

- `desktop/backend/pyproject.toml`
- `desktop/backend/alembic.ini`
- `desktop/backend/app/**`
- `desktop/backend/migrations/**`
- `desktop/backend/tests/**`

Expected updates:

- `desktop/backend/README.md`
- `docs/current-state.md`
- `docs/development.md`
- `docs/repo-map.md`
- `docs/security.md`
- `docs/testing.md`
- `docs/plans/active/phase-1-desktop-backend-foundations.md`

Possibly updated if implementation choices require it:

- `docs/architecture.md`
- `docs/protocol.md`
- new ADR under `docs/decisions/`

Do not change Android, frontend, fake-device, or cloud-related areas for Phase 1 except if correcting documentation references.

## Testing and Validation

Required validation by the end of Phase 1:

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic current
```

If mypy is configured:

```powershell
cd desktop/backend
python -m mypy app tests
```

Additional manual validation:

- Start backend with Uvicorn.
- Request `GET /api/v1/health`.
- Confirm no upload, pairing, media check, discovery, or transfer endpoints were added.
- Confirm tests use temporary directories/databases and do not write to real backup roots.

If any command cannot run, document why in the final implementation report and in this plan's Final Results section.

## Risks / Unknowns

- Exact package dependency versions may need adjustment after implementation tests.
- Alembic test setup on Windows paths may need careful URL handling.
- SQLite behavior around concurrent writes and file locks may matter in later transfer phases, but should not be over-solved in Phase 1.
- Atomic move semantics depend on source and destination being on the same filesystem/volume. Configuration should keep temp and final roots compatible or detect unsafe cases before finalization.
- The minimal schema may need revision when pairing/authentication design lands.
- Whether to include mypy in Phase 1 should be decided based on implementation signal, not preference alone.

## Architecture Review

1. Are we introducing any Android-specific assumptions into the backend?
   - No. The plan uses Device, File, Backup, UploadSession, and Storage terminology. Android details remain outside backend protocol/domain names.

2. Are we introducing unnecessary abstraction?
   - Mostly no. The plan includes API, config, database, repository, and storage boundaries because they are testability or platform boundaries. It explicitly avoids interfaces for trivial functions and avoids service layers until coordination logic exists.

3. Could the filesystem design support large/resumable uploads later?
   - Yes. Partial files are addressable by session/storage key, finalization is separate, and storage operations are streaming-compatible. Chunk writing and offsets are deliberately deferred.

4. Could an incomplete file accidentally appear as a completed backup?
   - The plan requires separate partial/final storage and no successful backup record until finalization succeeds. Tests should cover this separation.

5. Are tests isolated from real user data?
   - Yes. Tests must use temporary directories and temporary SQLite databases, and must never write to a real backup directory.

6. Are database and filesystem responsibilities clearly separated?
   - Yes. Database stores metadata and state; filesystem storage owns media/file bytes and path operations. No BLOB media storage is planned.

7. Are we accidentally implementing Phase 2+ concepts?
   - No. Fake-device, discovery, pairing/authentication, uploads, resumable chunks, SHA-256 workflow, Android, and UI are explicitly out of scope.

## Progress

- 2026-08-15: Created Phase 1 ExecPlan from Phase 0 repository instructions and documentation. No application code implemented.
- 2026-08-15: Milestone 1 completed. Added `pyproject.toml`, backend package skeleton, pytest/Ruff configuration, and a package import smoke test. `python -m pytest` passed.
- 2026-08-15: Milestone 2 completed. Added FastAPI app factory, typed settings, versioned router, and `GET /api/v1/health` returning `{"status": "ok"}`. `python -m pytest` passed with 6 tests.
- 2026-08-15: Milestone 3 completed. Added SQLAlchemy engine/session helpers, Alembic configuration, and an empty baseline migration. No domain tables were created. `python -m pytest` passed with 8 tests.
- 2026-08-15: Milestone 4 intentionally deferred. No repositories were added because Phase 1 has no domain tables or current repository behavior to implement.
- 2026-08-15: Milestone 5 completed. Added local filesystem storage foundation with temp/final roots under one data root, containment checks, unsafe filename sanitization, overwrite protection, and partial finalization primitive. `python -m pytest` passed with 19 tests.
- 2026-08-15: Milestone 6 completed. Added a single structured `AppError` convention, FastAPI exception handler registration, and standard-library logging configuration. `python -m pytest` passed with 21 tests.
- 2026-08-15: Milestone 7 completed. Updated backend README, current state, development, repo map, security, testing, and this plan to match the implemented no-domain-table Phase 1 foundation. Final validation passed.

## Discoveries

- `desktop/backend/` currently contains only `AGENTS.md` and `README.md`.
- Phase 0 docs are aligned with the requested backend foundation; no architectural contradiction was found during planning.
- `.codex/config.toml` intentionally does not exist; Phase 1 should not add Codex configuration unless a specific safe repo-local need appears.
- Local validation environment is Python 3.10.6, so backend metadata uses `requires-python >=3.10`.
- Installed FastAPI 0.141.1 exposes included routers differently during direct route inspection; tests use OpenAPI and TestClient behavior instead of depending on internal route object shape.
- Alembic baseline migration creates only `alembic_version`; this verifies migration workflow without speculative schema.
- Storage defaults to `<data-root>/.localsync-temp` and `<data-root>/backups`, keeping partial and final locations under one configured data root for future same-volume finalization.
- Default Alembic validation creates `desktop/backend/data/localsync.db`; this path is ignored as runtime data.
- The only exposed API path after Phase 1 is `/api/v1/health`.

## Decision Log

- Use a direct `app/` package under `desktop/backend/` instead of a `src/` layout for early FastAPI/Alembic simplicity.
- Use `venv` + `pip` + `pyproject.toml` as the initial Python workflow to avoid introducing an extra package manager before needed.
- Include Ruff as the initial lint/format tool because it is low-overhead and covers both concerns.
- Defer Zeroconf/mDNS because discovery is Phase 6.
- Defer mypy unless implementation quality justifies the setup cost in Phase 1.
- Do not add upload, pairing, or authentication endpoints in Phase 1.
- Do not add mypy during Phase 1 per implementation instruction; use annotations, Ruff, pytest, and FastAPI/Pydantic validation.
- Do not create Device, UploadSession, BackupRecord, StoredFile, or repositories in Phase 1 without current behavior requiring them.
- Narrowed the root `.gitignore` runtime `storage/` pattern so backend source under `app/storage/` is not ignored.

## Completion Criteria

Phase 1 is complete when:

- Backend project metadata and package skeleton exist.
- FastAPI app starts and exposes `GET /api/v1/health`.
- Configuration is externalized and tested.
- SQLAlchemy and Alembic are initialized.
- Minimal justified schema exists through migration.
- Storage foundation enforces safe paths, partial/final separation, and overwrite protection.
- Structured error handling and logging conventions exist.
- pytest infrastructure and focused tests pass.
- Backend README and relevant docs are updated.
- Validation commands have been run or failures/gaps are documented.
- This plan's Progress, Discoveries, Decision Log, and Final Results sections are updated.
- No Phase 2+ behavior has been implemented.

## Final Results

Completed on 2026-08-15.

Implemented:

- Backend Python project metadata using `pyproject.toml`, standard `venv`/`pip` workflow, and separated `dev` extra.
- FastAPI app factory and app object.
- Versioned `/api/v1/health` endpoint returning `{"status": "ok"}`.
- Typed Pydantic settings for environment, data root, optional database URL, and log level.
- SQLAlchemy engine/session helpers.
- Alembic configuration and empty `0001_baseline` migration.
- Local filesystem storage foundation with `<data-root>/.localsync-temp` and `<data-root>/backups`.
- Storage path containment, traversal/absolute/separator rejection, unsafe filename sanitization, overwrite protection, disk usage helper, and partial finalization primitive.
- Single structured `AppError` convention and FastAPI handler.
- Standard-library logging configuration.
- Backend tests and documentation updates.

Validation:

- `python -m pytest`: 22 passed.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m alembic upgrade head`: passed.
- `python -m alembic current`: reported `0001_baseline (head)`.
- Direct FastAPI TestClient request to `GET /api/v1/health`: returned status 200 and `{"status": "ok"}`.
- API path inspection confirmed only `/api/v1/health` is exposed.
- Source search found no Android/Windows-specific protocol/domain route/type names and no Phase 2+ route concepts in backend implementation.

Intentional deviations:

- No domain tables or repositories were created. This follows the implementation instruction to avoid speculative schema until behavior requires it.
- No mypy configuration was added. Phase 1 uses annotations, Ruff, pytest, and FastAPI/Pydantic validation.

Remaining risks:

- No pairing, authentication, upload authorization, quota enforcement, resumable upload, hash verification workflow, or transfer endpoints exist yet.
- Atomic finalization is prepared by same-root temp/final layout and rename primitive, but full transfer consistency must be designed when upload behavior is implemented.
