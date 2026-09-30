# ADR-0004: Resumable Transfer Sessions

## Status

Accepted.

## Context

localSync must handle large files over local networks where Wi-Fi loss, process exit, backend restart, laptop restart, HTTP timeout, or lost responses can interrupt transfer.

Restarting a multi-gigabyte video from byte zero after every interruption is not acceptable for backup reliability. At the same time, incomplete bytes must never appear as completed backups, and the protocol must remain platform-neutral for Android, iOS, desktop senders, NAS clients, and other future devices.

## Decision

Use server-persisted `UploadSession` records for resumable transfer.

The resumable protocol is append-only and offset-based:

- clients create or recover sessions with expected filename metadata, size, and full SHA-256;
- clients send raw byte chunks with an explicit offset;
- the server accepts only `client_offset == actual_partial_file_length`;
- actual partial-file length is the authoritative accepted offset;
- filesystem write, flush, and `fsync` happen before the database offset commit and success response;
- full SHA-256 is recomputed by reading the complete partial file during completion;
- completed storage remains separate from partial storage.

Persisted session states are limited to `receiving`, `completed`, and `failed`.

## Consequences

- Uploads can resume after client or backend restart when the partial file and session row remain available.
- Lost-response retries do not duplicate bytes because stale offsets are rejected with the authoritative next offset.
- Future-offset requests cannot create holes or sparse logical uploads.
- Completion requires an extra full-file disk read to verify SHA-256, which is acceptable for Phase 3 reliability.
- SQLite and filesystem operations are not a distributed transaction, so narrow reconciliation logic is required.
- The protocol remains sequential and simple; parallel/out-of-order chunks are deferred.
- `device_id` and `upload_id` remain identifiers only, not authentication credentials.

## Alternatives Considered

- Restart failed uploads from byte zero: rejected because it does not meet large-file reliability needs.
- Persist per-chunk database rows: rejected for Phase 3 because append-only offset tracking is sufficient.
- Persist Python hash state between chunks: rejected because it is brittle and implementation-specific.
- Support sparse or out-of-order chunk writes: rejected because it increases complexity before correctness requires it.
- Treat database offset as authoritative over partial-file length: rejected because only bytes present on disk can be resumed safely.
