# ADR-0005: Paired Device Authentication

## Status

Accepted.

## Context

Phase 4 used development-only `device_id` namespaces. Any LAN client could choose another namespace and call upload APIs. Phase 5 needs real device authentication without introducing cloud accounts, OAuth, JWT infrastructure, or platform-specific protocol names.

## Decision

localSync uses server-generated paired-device IDs plus high-entropy opaque bearer credentials.

The backend generates 32 cryptographically secure random bytes for each long-term device credential and encodes them as base64url. SQLite stores only a SHA-256 verifier over a versioned/domain-separated credential representation. The plaintext credential is returned once during successful pairing and is never stored server-side.

Authenticated device requests use:

```http
Authorization: Bearer <device-credential>
```

The authenticated principal supplies device identity. Client-supplied `device_id` is not authorization proof. JWT is not used because localSync has one local server, no distributed verifier, and needs immediate local revocation.

## Consequences

- Revocation is immediate by setting `paired_devices.revoked_at`.
- Existing transfer routes can remain platform-neutral.
- Server compromise of SQLite does not reveal plaintext credentials, but a stolen client credential remains replayable until revoked.
- Existing `stored_files.device_id` and `upload_sessions.device_id` remain string namespaces for now; new authenticated transfers populate them with server-generated paired-device IDs.
- Completed backups are retained after revocation.

## Alternatives Considered

- JWT: rejected because it adds signing and revocation complexity without a localSync need.
- Human passwords or PINs as long-term credentials: rejected because long-term credentials must have strong entropy.
- Asymmetric per-device signatures: deferred because opaque credentials over pinned TLS are simpler for the current single-server local model.
- Storing plaintext bearer credentials server-side: rejected because verifier-only storage is straightforward.
