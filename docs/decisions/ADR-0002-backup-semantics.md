# ADR-0002: Backup Semantics

## Status

Accepted.

## Context

localSync protects media by copying it from a source device to laptop backup storage. Users may delete media from the source device after backup. A sync mirror model would risk propagating deletion to the backup and causing data loss.

## Decision

Automatic backup is one-way and deletion-safe.

Deleting photos or videos from the source device must never automatically delete the laptop backup. localSync must not implement automatic bidirectional synchronization for V1 backup behavior.

## Consequences

- Backup storage is treated as an archive, not a mirror.
- Source deletion events are not delete commands for backup storage.
- Future cleanup, retention, or pruning features must require explicit user intent and must be designed separately from automatic backup.
- Tests must eventually prove that source deletion followed by another sync pass does not remove the laptop copy.

## Alternatives Considered

- Bidirectional sync: rejected because it creates unacceptable accidental deletion risk.
- Mirror with trash/recycle protection: rejected for V1 because it still couples source deletion to backup mutation.
