# Desktop Backend Agent Instructions

This directory is for the future desktop backend service.

## Expected Stack

- Python.
- FastAPI for HTTP API boundaries.
- Pydantic for request and response validation.
- SQLAlchemy for persistence.
- SQLite for local metadata storage.
- Alembic for schema migrations.
- pytest for tests.
- Uvicorn for local service runtime.
- Zeroconf/mDNS for discovery.

## Boundaries

- Keep API, service, repository, and filesystem storage responsibilities separate.
- API handlers validate and translate requests; business rules belong in services.
- Repositories own persistence details.
- Filesystem storage owns path generation, partial files, finalization, and collision handling.
- Store media/file bytes on disk, not in database BLOBs.

## Large Files and Integrity

- Stream uploads; do not load large files completely into memory.
- Support chunked/resumable upload design.
- Incomplete uploads must remain partial and must not appear as successful backups.
- Finalization must verify expected size and planned SHA-256 integrity before marking success.

## Security

- Do not expose unrestricted upload endpoints.
- Validate device authorization, offsets, sizes, filenames, paths, and session state.
- Never log credentials, pairing tokens, or authorization headers.
- Use structured errors with stable machine-readable codes.

## Database Discipline

- Use migrations for schema changes once Alembic exists.
- Keep schema changes documented when they affect storage semantics or public API behavior.

## Testing

Add focused pytest coverage for services, repositories, storage behavior, protocol boundaries, interruption/resume behavior, and deletion safety as implementation appears.
