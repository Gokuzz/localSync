# ADR-0003: Media Integrity

## Status

Accepted.

## Context

The initial use case is preserving original photos and videos. Any resize, recompression, transcoding, format conversion, or metadata stripping would violate user expectations for a backup archive.

Large videos may be interrupted during transfer and require resumability without corrupting completed backups.

## Decision

Media is copied without re-encoding or content modification. SHA-256 is the planned strong integrity verification mechanism.

Actual media bytes are stored as normal filesystem files. The database stores metadata and transfer state only. Uploads finalize only after expected size and integrity verification pass.

## Consequences

- Transfer code must stream bytes and avoid full-file memory loading.
- Temporary or partial files must be distinguishable from finalized backups.
- Hash mismatch must fail the upload instead of producing a successful backup record.
- Future optimizations must not change media bytes.

## Alternatives Considered

- Image/video optimization during backup: rejected because it changes backup contents.
- Storing media as database BLOBs: rejected because filesystem storage is simpler, inspectable, and better suited for large files.
