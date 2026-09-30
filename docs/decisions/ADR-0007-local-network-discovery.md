# ADR-0007: Local Network Discovery

Status: Accepted for Phase 6

## Context

Phase 5 already establishes the trusted laptop identity through a persistent TLS certificate and canonical `spki-sha256:` pin. Android still needs a way to find the laptop after its LAN address changes. A discovery mechanism must not become a second authentication mechanism.

## Decision

localSync advertises a DNS-SD/mDNS service of type `_localsync._tcp.`. The backend uses Python `zeroconf` and registers the advertisement with the application lifecycle. The advertised port comes from `LOCALSYNC_SERVER_PORT`, which must match the HTTPS listener port.

The minimal TXT metadata is:

- `protocol=1`
- `tls=required`
- `host=localsync.local`
- `spki=spki-sha256:<base64url-sha256-SPKI>`

The SPKI value is an unauthenticated advisory filter. Service names, TXT records, addresses, and ports are not trusted. Android uses platform `NsdManager` through a testable discovery abstraction, then performs the existing Phase 5 pinned TLS preflight. Only successful verification of the persistent SPKI pin permits updating the current locator. Discovery never changes the trusted pin, credential, paired device ID, or revoked state.

Android keeps manual locator entry as a fallback. Discovery is foreground and bounded, exposed through `Find Laptop`; it does not use WorkManager, run periodically, or trigger Backup Now. Discovered candidates are in-memory only and do not require a database migration.

The Phase 6 Android project remains targetSdk 36. Android 17/API 37 local-network permission changes, including `ACCESS_LOCAL_NETWORK`, must be revisited when the target SDK is raised.

## Consequences

- Discovery can relocate an already-paired trusted laptop without re-pairing after a DHCP change.
- A malicious LAN peer can advertise the same service or TXT fingerprint but cannot pass the pinned TLS check without the trusted server identity.
- mDNS may fail on isolated, multicast-blocked, VPN, guest, or cross-subnet networks; manual HTTPS locator entry remains available.
- No fake discovery authentication or cloud service is introduced.
