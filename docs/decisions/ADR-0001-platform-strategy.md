# ADR-0001: Platform Strategy

## Status

Accepted.

## Context

V1 targets an Android mobile client and a Windows desktop/laptop application. The product should later support clients such as iOS, macOS, Linux, NAS, or other trusted devices.

Tying protocol or domain concepts to Android or Windows would make later clients harder to add and would distort the backup model.

## Decision

localSync is platform-neutral at the protocol and domain level.

Use generic concepts such as Device, Client, UploadSession, MediaItem, Transfer, and Backup. Platform-specific implementation details may exist inside platform directories such as `android/` or `desktop/`, but must not leak into protocol names or core storage semantics.

## Consequences

- V1 can ship Android and Windows implementations without making them architectural assumptions.
- Protocol contracts must avoid names like `AndroidUpload` or `WindowsDevice`.
- Platform adapters translate native APIs into generic domain concepts.

## Alternatives Considered

- Android-first protocol naming: rejected because it would create avoidable migration cost for future clients.
- Separate protocol per platform: rejected because it increases compatibility and testing burden without a V1 benefit.
