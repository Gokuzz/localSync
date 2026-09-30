# localSync Agent Instructions

localSync is local-first backup software. Reliability, data integrity, and no silent data loss matter more than speed of implementation or UI polish.

## Product Invariants

- Automatic backup is one-way from a source device to laptop backup storage.
- Deleting photos or videos from the source device must never automatically delete the laptop backup.
- Do not implement automatic bidirectional synchronization.
- Photos and videos are transferred as opaque bytes. Do not resize, recompress, transcode, convert formats, strip metadata, or otherwise modify media contents.
- Destination media should ultimately match source bytes. SHA-256 is the planned strong integrity check.
- Store media and transferred files as normal filesystem files, not database BLOBs. Databases store metadata and transfer state only.
- Incomplete uploads must never appear as successfully backed-up files. Use partial storage and finalize only after verification.
- Architecture and protocol must support resumable/chunked transfers for large files.
- V1 has no cloud storage, mandatory online account, Google Drive, AWS storage, or Firebase storage.
- Photos/videos may be automatically backed up. Documents and arbitrary files are manual transfer only in V1.
- Keep protocol, API naming, device model, storage model, and transfer semantics platform-neutral.

## Required Context Reading

Before significant implementation work:

1. Read this file.
2. Read relevant nested `AGENTS.md` files.
3. Read [docs/index.md](docs/index.md).
4. Read [docs/current-state.md](docs/current-state.md).
5. Read relevant architecture, protocol, security, or testing docs.
6. Inspect relevant ADRs in [docs/decisions](docs/decisions).
7. Inspect any active ExecPlan in [docs/plans/active](docs/plans/active) relevant to the task.

For trivial one-line changes, read only the context needed to avoid breaking local conventions.

## Documentation Maintenance

When implementation materially changes architecture, protocol, security, storage semantics, platform behavior, public APIs, or developer workflow, update the corresponding documentation in the same task.

Significant irreversible or cross-cutting architectural decisions require an ADR. Do not create ADRs for trivial coding choices.

## Planning

For complex features, significant refactors, cross-platform work, security-sensitive changes, or multi-step work, create or update an ExecPlan following [.agent/PLANS.md](.agent/PLANS.md).

- Active plans live in `docs/plans/active/`.
- Completed plans move to `docs/plans/completed/`.
- ExecPlans are living documents and must be updated as implementation progresses.

## Validation

A task is not complete only because code was generated. Run relevant tests, formatting, linting, type checking, and build checks when those tools exist. If validation cannot be run, explicitly state why.

## Scope Control

Follow the current task. Do not silently implement adjacent features. Record useful future ideas in documentation instead of expanding scope automatically.

## Dependency Discipline

Do not add dependencies merely for convenience. Prefer standard-library and platform capabilities when reasonable. For substantial production dependencies, explain why they are needed.

## Security

Never commit secrets, hardcode production credentials, log authentication tokens, expose unrestricted upload endpoints, or weaken validation merely to make tests pass.

## Repository Cleanliness

Avoid generated junk, temporary debugging files, giant unrelated refactors, duplicate abstractions, and dead code.
