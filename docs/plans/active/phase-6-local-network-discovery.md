# Phase 6: Local Network Discovery

## Purpose / User Outcome

Add automatic same-LAN discovery of localSync laptop/server instances while preserving the Phase 5 trust model.

At the end of Phase 6, an already-paired Android app should be able to find the current network locator for its trusted laptop after the laptop IP changes, verify that locator through the existing pinned TLS path, update the current locator, and continue manual Backup Now without re-pairing.

Discovery answers only "where might a localSync server be reachable?" It does not answer "is this my trusted laptop?"

## Scope

Phase 6 includes:

- DNS-SD/mDNS service advertisement from the desktop backend.
- A stable service type and minimal non-secret TXT metadata.
- Backend advertisement lifecycle tied to localSync server lifecycle.
- Android local-network discovery through platform NSD APIs.
- Android in-memory discovered-server state.
- Verification of discovered candidates through the existing Phase 5 pinned TLS client.
- Automatic locator update only after the trusted SPKI identity is verified.
- Small Android UI for Find Laptop / searching / found / unavailable / manual fallback.
- Tests for discovery metadata, lifecycle, candidate filtering, spoof rejection, locator update, and no pin mutation.
- Real-device same-LAN discovery validation, including locator/IP change.
- ADR-0007 recommendation for the durable discovery protocol decision.

## Out of Scope

Do not implement in Phase 6:

- WorkManager.
- Automatic photo/video backup.
- Background periodic discovery.
- Boot receivers.
- Charging or Wi-Fi scheduling constraints.
- Source deletion or remote deletion.
- Manual arbitrary document transfer.
- Desktop React UI.
- QR pairing UX redesign.
- Cross-device deduplication.
- Namespace merge.
- Credential rotation or re-authorization.
- Cloud discovery.
- Internet access, NAT traversal, or relay servers.
- Bluetooth, Nearby Connections, or Wi-Fi Direct.
- Laptop-to-phone transfer.
- Any Phase 7 automatic-backup trigger.

Discovery must not automatically start backup. The user still presses Backup Now.

## Current System Context

Repository and docs inspected before planning:

- Root, Android, backend, and tools `AGENTS.md` files.
- `.agent/PLANS.md`.
- `docs/index.md`, `docs/current-state.md`, `docs/product-scope.md`, `docs/architecture.md`, `docs/protocol.md`, `docs/security.md`, `docs/testing.md`, `docs/development.md`, `docs/repo-map.md`, `docs/roadmap.md`.
- ADR-0001 through ADR-0006.
- Completed Phase 4 and Phase 5 ExecPlans.
- `docs/testing/android-real-device-validation.md`.
- `android/README.md` and `desktop/backend/README.md`.

Actual implementation inspected:

- Backend `Settings` has `LOCALSYNC_DATA_ROOT`, `LOCALSYNC_DATABASE_URL`, `LOCALSYNC_LOG_LEVEL`, and `LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE`; no server host/port/discovery config exists yet.
- Backend app creation is in `desktop/backend/app/main.py`. It creates FastAPI directly, configures logging, creates DB/session/storage, ensures the persistent server identity, registers error handlers, and includes `/api/v1`.
- Backend TLS identity lives in `app/core/security.py`: ECDSA P-256 self-signed certificate, SAN `localsync.local`, canonical `spki-sha256:` fingerprint over DER SubjectPublicKeyInfo.
- Backend HTTPS startup is currently a Uvicorn command that passes `--ssl-certfile` and `--ssl-keyfile`; port is currently supplied to Uvicorn, not to application settings.
- Backend pairing and device admin are CLI-only in `app/cli/__main__.py`: pairing create, devices list, devices revoke, devices activate.
- Transfer endpoints are authenticated; `GET /api/v1/health` is public and minimal.
- Android stores paired server state as `serverLocatorUrl`, `serverLogicalHost`, `serverFingerprint`, `serverDisplayName`, `deviceId`, and encrypted `deviceCredential`.
- Android `ServerLocator` requires HTTPS and maps a locator URL to logical URL host `localsync.local`.
- Android `PinnedTls` maps `localsync.local` to the mutable locator host with scoped OkHttp `Dns`, verifies SPKI pin through a scoped trust manager, and attaches `Authorization` only on the pinned client path.
- Android `AuthenticatedLocalSyncClient` rebuilds a pinned protocol client from stored credentials for each request.
- Android `BackupRepository` uses stored paired credentials and stops on non-retryable auth/TLS identity failures.
- Android `HomeViewModel` and `HomeScreen` currently expose manual pairing, manual locator settings, media inventory, and Backup Now.
- fake_phone stores server locator and SPKI pin in a local JSON config and verifies the presented SPKI before pairing-code or bearer transmission, but has no discovery support.

Important Phase 5 constraints:

- Server identity and network address are separate.
- Trusted SPKI pin must never be replaced from an unauthenticated source.
- Bearer credentials must not be sent until pinned TLS validates the trusted server identity.
- Revoke/re-pair creates a new authenticated device namespace; Phase 6 must not solve this through discovery.

## Assumptions

- Phase 6 targets discovery on the same local link/subnet.
- The backend will continue to run on a single HTTPS TCP port chosen at startup.
- A new backend setting for advertised HTTPS port is probably needed because the application cannot reliably infer Uvicorn's CLI `--port`.
- No database migration is expected. Discovery state is ephemeral; trusted server identity already exists in runtime files and Android credential storage.
- Android production discovery should use `NsdManager`, not a third-party mDNS library, unless implementation proves platform APIs insufficient.
- Backend advertisement should use the Python `zeroconf` package if selected during implementation.
- Android minSdk remains 29 and targetSdk currently 36. If targetSdk rises to API 37 later, local network permission behavior must be revisited.
- Some networks block multicast/mDNS. Manual locator fallback remains mandatory.

## Architecture / Approach

### Discovery Technology

Use DNS-SD over mDNS.

Backend:

- Use a small backend abstraction around Zeroconf so tests can validate service records and lifecycle without relying on real multicast.
- Advertise one TCP service instance while the backend is running.

Android:

- Use Android `NsdManager`.
- Wrap callback APIs behind a `LocalNetworkDiscovery` abstraction so ViewModels and repository code do not depend directly on platform callback objects.
- Keep discovered candidates in memory.

Why:

- DNS-SD/mDNS is the standard same-link service discovery mechanism and aligns with Android `NsdManager`.
- It avoids custom UDP broadcast design.
- It remains platform-neutral for future iOS, desktop, and NAS clients.

Official Android documentation notes that `NsdManager` is DNS-SD over mDNS, is asynchronous, and discovery continues until stopped. It also documents Wi-Fi multicast behavior: before T extensions 7, foreground apps may need an explicit `WifiManager.MulticastLock`; from T extensions 7 onward, foreground multicast reception is system-managed. Android API 37 introduces `ACCESS_LOCAL_NETWORK` considerations for local device access.

### Service Type

Use DNS-SD service type:

```text
_localsync._tcp.
```

The trailing dot is the fully qualified DNS-SD form. Implementation may use the exact format required by each library, but docs and tests should preserve this service type as an interoperability contract.

This service type should be recorded in ADR-0007 during implementation.

### Service Instance Name

Use a human-readable advisory instance name, for example:

```text
<hostname> localSync
```

The instance name is not authentication. Duplicate names and mDNS conflict renaming are acceptable and must not affect trusted server identity.

### Advertisement / TXT Design

Advertise only non-secret locator and compatibility metadata:

- TCP port: advertised as the DNS-SD service port.
- `protocol=1`: localSync API/discovery protocol compatibility marker.
- `tls=required`: signals that authenticated traffic is HTTPS.
- `host=localsync.local`: stable logical TLS hostname from ADR-0006.
- `spki=spki-sha256:<base64url>`: optional advisory SPKI fingerprint hint.

Do not advertise:

- bearer credentials;
- pairing codes;
- pairing session IDs;
- TLS private key material;
- backup paths;
- database paths;
- filenames;
- media counts;
- device list/auth state;
- user account data.

### SPKI In TXT

Include the full canonical `spki-sha256:` fingerprint in TXT as an advisory filter.

Reason:

- It lets an already-paired Android app cheaply ignore candidates whose advertised fingerprint does not match the stored trusted pin.
- It improves UX when multiple localSync instances are on the LAN.

Security limitation:

- TXT records are unauthenticated and spoofable.
- A matching TXT value is not trusted.
- Android must still establish the normal Phase 5 pinned TLS connection and verify the actual presented SPKI before updating the locator or sending bearer credentials.
- Discovery must never mutate the stored trusted pin.

### Trusted Server Matching

For an already-paired Android app:

```text
load persisted paired credentials
trusted pin = credentials.serverFingerprint
trusted logical host = credentials.serverLogicalHost

discover DNS-SD candidates
discard candidates with unsupported protocol
if TXT spki exists and spki != trusted pin:
    mark/ignore as untrusted candidate
else:
    build candidate locator https://<resolved-address>:<port>
    create ServerLocator(candidate locator, trusted logical host)
    call existing pinned TLS/protocol path without sending credentials until TLS verifies
    if presented SPKI == trusted pin:
        save current locator as candidate locator
        report trusted server verified
    else:
        report server identity mismatch and keep old pin/locator unchanged
```

The final verification must use the existing pinned TLS behavior. Discovery cannot authorize requests.

### Unpaired Device Behavior

Primary Phase 6 scope is already-paired relocation.

Unpaired Android devices may optionally show discovered localSync candidates as a convenience for filling the server locator field, but they must still use the Phase 5 pairing flow:

- laptop CLI creates pairing session;
- Android observes server fingerprint before sending pairing code;
- user explicitly confirms fingerprint;
- pairing code is sent only after confirmation;
- normal pinned TLS is established after pairing.

Do not auto-pair discovered servers. Do not replace QR pairing UX work.

### Backend Advertisement Lifecycle

Add a backend service such as `app/services/discovery.py` with a small interface:

```text
DiscoveryAdvertisement
    start()
    stop()
```

Use a FastAPI lifespan handler in `create_app` to:

1. initialize application state as today;
2. start advertisement after server app startup;
3. unregister advertisement during shutdown.

Important caveat: FastAPI app startup runs before Uvicorn is fully accepting sockets. This is acceptable for Phase 6 if the service is usable immediately after startup completes, but the implementation should avoid advertising when configuration is missing or invalid. Abnormal process termination may leave stale mDNS cache entries temporarily; clients must treat them as candidates and verify with pinned TLS.

### HTTPS Port Configuration

Do not hardcode port 8000 in the advertisement.

Add a backend setting such as:

```text
LOCALSYNC_SERVER_PORT=8000
```

The development startup command must pass the same value to Uvicorn:

```powershell
$env:LOCALSYNC_SERVER_PORT = "8000"
python -m uvicorn app.main:app --host 0.0.0.0 --port $env:LOCALSYNC_SERVER_PORT --ssl-certfile ...
```

Because Uvicorn CLI settings are outside FastAPI application settings, Phase 6 should document that the advertised port comes from localSync config and must match Uvicorn. A future packaged launcher can make this single-source automatically.

### Backend Interface Selection

Initial backend advertisement should use Zeroconf's default appropriate interfaces if practical, while avoiding loopback-only advertisement.

Implementation should evaluate:

- Zeroconf `InterfaceChoice.All` versus default interfaces;
- whether the library includes virtual adapters on Windows;
- a simple optional setting for interface behavior only if real validation shows unusable interface advertisement.

Do not hardcode a Windows interface name. Do not modify Windows Firewall automatically.

### Android Discovery Lifecycle

Discovery should be lifecycle-aware and bounded:

- Start when the user taps Find Laptop or when the Home screen becomes active and paired credentials exist.
- Run for a bounded window, for example 10 to 30 seconds.
- Stop when the trusted server has been verified or when the screen/app leaves the active state.
- Provide manual Refresh/Find Laptop.
- Prevent duplicate discovery sessions from accumulating.

Do not run continuous background discovery. Do not add WorkManager.

### Android Permissions / Multicast

Planned Android manifest additions to evaluate during implementation:

- `ACCESS_NETWORK_STATE` if using NsdManager overloads that require a `NetworkRequest` or network-aware discovery.
- `CHANGE_WIFI_MULTICAST_STATE` if a `WifiManager.MulticastLock` is needed for Android versions before T extensions 7.
- `ACCESS_LOCAL_NETWORK` only if targetSdk/API 37 support is actually introduced. Current project targetSdk is 36, so this should be documented as a future tooling consideration, not added blindly.

Do not add broad location or Wi-Fi Direct permissions for DNS-SD browsing unless official APIs require them for the exact implementation.

MulticastLock policy:

- Acquire only while foreground discovery is active on devices/extension levels that require it.
- Release on stop/failure/lifecycle cleanup.
- Do not hold it during normal backup transfers.

### Android Discovery State

Introduce platform-neutral Android-side models under `core/model` or `data/network/discovery`:

```text
DiscoveredServer
    instanceName
    serviceType
    host/address
    port
    protocolVersion
    advertisedSpkiFingerprint?
    lastSeenAt

TrustedServerAvailability
    idle
    searching
    candidateFound
    verifying
    verified(locator)
    unavailable
    discoveryUnavailable
    identityMismatch
    manualLocatorActive
```

Do not persist arbitrary discovered candidates in Room. They are ephemeral network observations. Persist only the accepted current locator after pinned TLS verification succeeds.

### Multiple Candidates

When multiple candidates are discovered:

- Prefer candidates whose TXT `spki` matches the trusted stored pin.
- Verify candidates one at a time through pinned TLS.
- First verified candidate may update the locator.
- Candidates without SPKI can still be attempted if no matching-SPKI hint is available, but they must pass pinned TLS before use.
- Candidates with wrong SPKI hint should be ignored or marked untrusted; do not show them as trusted laptop.
- Duplicate advertisements should update existing candidate state rather than creating duplicate UI rows.

### IPv4 / IPv6

Plan to support both IPv4 and IPv6 locators where Android and Zeroconf expose usable addresses.

Implementation details:

- Android `NsdServiceInfo` may expose one or more addresses depending on API level.
- Normalize IPv4 as `https://a.b.c.d:<port>`.
- Normalize IPv6 as `https://[addr]:<port>`.
- Existing `parseServerLocator` uses OkHttp `HttpUrl`, which supports bracketed IPv6 literals.
- `LocatorDns` maps `localsync.local` to `InetAddress.getAllByName(locatorHost)`, which can resolve IPv4 or IPv6 literal/host values.

If implementation cannot reliably extract multiple addresses on older APIs, document the Phase 6 limitation and use the first resolved address without assuming IPv4 is the only future path.

### Manual Locator Fallback

Keep the current manual server locator.

Reasons:

- mDNS may be blocked by guest/corporate Wi-Fi, VLANs, AP isolation, VPNs, or firewalls.
- Manual IP entry remains useful for debugging.
- Manual locator still uses Phase 5 pinned TLS, so changing the locator cannot replace the trusted pin.

### Windows Firewall

Do not automatically edit firewall rules in Phase 6.

Document that development validation may require:

- inbound TCP for the configured HTTPS port, usually 8000;
- UDP 5353 multicast for mDNS.

Users should keep firewall rules scoped to Private/trusted networks and should not disable the firewall globally.

### Fake Client

Do not require fake_phone discovery support for Phase 6.

Optional: add a tiny diagnostic command or helper only if it materially improves backend advertisement testing. The primary Phase 6 producer is the backend; the primary consumer is Android.

## Milestones

- [ ] Milestone 1: Finalize discovery protocol and Android API requirements.
  - Confirm service type `_localsync._tcp.`.
  - Finalize TXT metadata and advisory SPKI behavior.
  - Confirm Android NsdManager permission and MulticastLock approach against targetSdk/minSdk.
  - Decide whether ADR-0007 is created during implementation.

- [ ] Milestone 2: Add backend discovery settings and advertisement abstraction.
  - Add configured service port and optional enable flag if needed.
  - Add service record builder.
  - Add test fake for registration/unregistration.
  - Keep runtime bytes/secrets out of TXT metadata.

- [ ] Milestone 3: Implement backend DNS-SD advertisement with Zeroconf.
  - Add `zeroconf` only if selected.
  - Register service type, instance name, port, protocol TXT, logical host, and advisory SPKI.
  - Reuse existing Phase 5 server identity.
  - Do not add database tables.

- [ ] Milestone 4: Integrate backend advertisement lifecycle.
  - Add FastAPI lifespan startup/shutdown integration.
  - Ensure advertisement unregisters on normal shutdown.
  - Document Uvicorn port/config alignment.
  - Add tests using the abstraction, not real multicast.

- [ ] Milestone 5: Add Android discovery abstraction and models.
  - Add `LocalNetworkDiscovery` interface.
  - Add `DiscoveredServer` and availability state.
  - Add fake discovery implementation for JVM tests.
  - Keep candidates in memory.

- [ ] Milestone 6: Implement Android NsdManager discovery.
  - Discover `_localsync._tcp.`.
  - Resolve service records and TXT metadata.
  - Handle found/lost/resolve failure/duplicate/already-running states.
  - Bound discovery lifetime and cleanup listeners.
  - Use MulticastLock only if required and release it deterministically.

- [ ] Milestone 7: Verify discovered locators through pinned TLS.
  - Compare optional TXT SPKI hint against stored trusted pin.
  - Use existing `ServerLocator`, logical host, `LocatorDns`, and pinned TLS path.
  - Persist current locator only after TLS verifies the trusted SPKI.
  - Never mutate stored pin from discovery.
  - Never send bearer credentials to unverified candidates.

- [ ] Milestone 8: Add Android UI for discovery and manual fallback.
  - Home/Developer Settings shows trusted laptop availability.
  - Add Find Laptop action.
  - Show searching, verified, unavailable, discovery unavailable, identity mismatch, and manual locator active states.
  - Keep UI functional; no network-browser polish.

- [ ] Milestone 9: Add discovery security and regression tests.
  - Spoofed TXT matching trusted SPKI but wrong actual certificate is rejected.
  - Wrong TXT SPKI is ignored.
  - Same trusted identity at changed locator succeeds.
  - Duplicate advertisements do not duplicate trusted state.
  - Service lost does not forget pairing.
  - Revoked credential is not restored by discovery.

- [ ] Milestone 10: Run backend and Android validation.
  - Backend `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m alembic current`.
  - Android `.\gradlew.bat assembleDebug`, `.\gradlew.bat test`, `.\gradlew.bat lint`.
  - Fake client validation only if fake_phone changes.

- [ ] Milestone 11: Run real-device local-network discovery validation.
  - Pair Android using existing Phase 5 flow.
  - Start backend with discovery enabled.
  - Discover and verify trusted laptop.
  - Change laptop locator/IP while retaining the same TLS identity.
  - Rediscover, verify, update locator, and complete Backup Now.
  - Validate untrusted/spoofed candidate rejection where practical.
  - Validate manual fallback when discovery is unavailable or blocked.

- [ ] Milestone 12: Documentation, ADR, and completion.
  - Create ADR-0007 if implementation confirms the durable service type/metadata model.
  - Update docs and READMEs.
  - Move this ExecPlan to completed only when completion criteria pass.

## Files / Modules Expected to Change

Backend likely changes:

- `desktop/backend/pyproject.toml`
- `desktop/backend/app/core/config.py`
- `desktop/backend/app/main.py`
- `desktop/backend/app/services/discovery.py`
- `desktop/backend/app/core/security.py` only if exposing existing identity constants/helpers is needed
- `desktop/backend/tests/test_discovery.py`
- existing backend tests if app lifespan/config setup changes

Android likely changes:

- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/main/java/dev/localsync/android/AppContainer.kt`
- `android/app/src/main/java/dev/localsync/android/core/model/**`
- `android/app/src/main/java/dev/localsync/android/data/network/**`
- `android/app/src/main/java/dev/localsync/android/data/repository/BackupRepository.kt`
- `android/app/src/main/java/dev/localsync/android/ui/home/HomeUiState.kt`
- `android/app/src/main/java/dev/localsync/android/ui/home/HomeViewModel.kt`
- `android/app/src/main/java/dev/localsync/android/ui/home/HomeScreen.kt`
- `android/app/src/test/**`

Docs likely changes:

- `docs/current-state.md`
- `docs/architecture.md`
- `docs/protocol.md` for DNS-SD service type/TXT metadata
- `docs/security.md`
- `docs/testing.md`
- `docs/development.md`
- `docs/repo-map.md`
- `docs/roadmap.md` only if sequencing needs clarification
- `docs/testing/android-real-device-validation.md`
- `desktop/backend/README.md`
- `android/README.md`

Possible new ADR:

- `docs/decisions/ADR-0007-local-network-discovery.md`

No expected database migration.

## Testing and Validation

Backend tests should cover:

1. Service type is `_localsync._tcp.`.
2. TXT record includes protocol version, TLS-required marker, logical host, and advisory SPKI.
3. TXT record excludes credentials, pairing codes, paths, filenames, and auth state.
4. Advertised port comes from localSync settings, not a hardcoded constant.
5. Advertisement uses the existing Phase 5 server identity/fingerprint.
6. Registration and unregistration lifecycle through a fake registrar.
7. App startup/shutdown starts/stops advertisement when enabled.
8. Discovery can be disabled for tests if needed.
9. No Alembic migration is introduced.

Android JVM tests should cover:

1. NsdManager wrapper maps found/resolved services into `DiscoveredServer`.
2. Duplicate candidate updates do not create duplicate trusted entries.
3. Service lost updates availability without forgetting pairing.
4. Unsupported/missing protocol version is ignored or not auto-used.
5. TXT SPKI mismatch prevents candidate verification.
6. TXT SPKI match still requires pinned TLS verification.
7. Spoofed TXT claiming trusted SPKI but presenting wrong certificate is rejected.
8. Same trusted SPKI at a changed locator updates current locator.
9. Stored trusted pin is never overwritten from discovery.
10. Bearer credential is not attached before candidate TLS verification.
11. Discovery failure leaves manual locator available.
12. Revoked/auth failures remain non-retryable and are not fixed by discovery.
13. Discovery start/stop is idempotent and lifecycle-safe.
14. IPv6 locator formatting where supported by the normalization layer.

Real-device validation should cover:

1. Pair Android using the completed Phase 5 flow.
2. Start HTTPS backend with persistent identity and discovery enabled.
3. Android discovers the laptop automatically.
4. Android verifies discovered candidate through pinned TLS.
5. Authenticated Backup Now succeeds.
6. Laptop locator/IP changes while the TLS identity remains the same.
7. Android discovers the new locator and reconnects without re-pairing.
8. Backup succeeds after locator update.
9. A second untrusted/spoofed localSync service is ignored/rejected where practical.
10. Spoofed TXT claiming the trusted SPKI but presenting another certificate is rejected where practical.
11. Stopping backend/advertisement shows unavailable while preserving pairing.
12. Restarting backend rediscovers the trusted laptop.
13. Blocking/disabling discovery leaves manual locator fallback usable.

Validation commands to run during implementation:

Backend:

```powershell
cd desktop/backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m alembic current
```

Android:

```powershell
cd android
.\gradlew.bat assembleDebug
.\gradlew.bat test
.\gradlew.bat lint
```

Fake client:

```powershell
cd tools/fake_phone
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Run fake-client validation only if fake_phone changes.

## Security Considerations

Threats Phase 6 must handle:

- Malicious LAN peer advertises `_localsync._tcp.`.
- Malicious peer advertises the trusted SPKI fingerprint in TXT but presents another certificate.
- Discovery result tries to overwrite trusted pin.
- Discovery result causes bearer credential to be sent to an unverified host.
- Revoked credential sees the laptop via discovery and attempts to restore authorization.
- Multiple localSync servers or duplicate instance names confuse UI state.

Required protections:

- Discovery TXT and service names are untrusted metadata.
- Stored trusted SPKI pin is never mutated by discovery.
- Locator is saved only after pinned TLS verifies the existing trusted SPKI.
- Authorization is attached only on the normal verified pinned TLS path.
- Discovery cannot create pairing sessions, consume pairing codes, revoke/activate devices, or merge namespaces.
- Health may remain public and minimal.
- Manual locator fallback still uses pinned TLS.
- Logs must not include bearer credentials, pairing codes, private key material, media data, or full sensitive paths.

Security claims not made:

- mDNS discovery is not authenticated.
- Discovery does not protect against LAN denial of service.
- Discovery does not make localSync safe for internet exposure.
- Discovery does not add cloud identity or account security.

## Risks / Unknowns

- Android NSD behavior varies by OS release, SDK extension level, OEM, and Wi-Fi network.
- Wi-Fi multicast may be blocked by AP/client isolation, guest networks, corporate Wi-Fi, VPN routing, or firewall rules.
- Backend Zeroconf may advertise on virtual/Docker/WSL/VPN interfaces. Real-device validation must check address usability.
- App startup may advertise shortly before Uvicorn accepts sockets; clients must tolerate connection retry/failure.
- Current backend server port is not in app settings, so implementation must avoid hardcoded advertisement drift.
- Android API 37 local-network permission may affect future targetSdk upgrades.
- IPv6 address handling must be tested carefully if exposed by NSD.
- The official Android newer `registerServiceInfoCallback(DiscoveryRequest, Executor, ServiceInfoCallback)` path is only broadly available on Android 14+ via SDK extensions; minSdk 29 likely needs compatibility with older `discoverServices` / `resolveService` listener APIs.

## Architecture Review

1. What exact DNS-SD service type is used?
   - `_localsync._tcp.`

2. What does the backend advertise?
   - TCP port plus TXT metadata: `protocol=1`, `tls=required`, `host=localsync.local`, and advisory `spki=spki-sha256:<...>`.

3. Does advertisement contain SPKI fingerprint?
   - Yes, the full canonical SPKI fingerprint is planned as an advisory filter.

4. If yes, why is that still not trusted?
   - DNS-SD TXT records are unauthenticated and spoofable. A TXT match only selects candidates for pinned TLS verification.

5. How does Android find services?
   - Through a `LocalNetworkDiscovery` abstraction backed by Android `NsdManager`.

6. Does Android require any new permission?
   - Likely `ACCESS_NETWORK_STATE` for network-aware discovery if used. `CHANGE_WIFI_MULTICAST_STATE` may be needed for MulticastLock on older devices. API 37 `ACCESS_LOCAL_NETWORK` is a future targetSdk consideration.

7. Does Android need MulticastLock?
   - Possibly on Android 12 and below or Android 13 devices without T extensions 7. Phase 6 should acquire it only during foreground discovery when required and release it on stop.

8. How is discovery lifecycle bounded?
   - Start on Find Laptop or active paired screen, run for a bounded window, stop on verification/screen stop/timeout, and avoid multiple active sessions.

9. How does Android choose among multiple candidates?
   - Prefer matching TXT SPKI hints, verify candidates sequentially with pinned TLS, and accept only the first candidate whose actual SPKI matches the stored trusted pin.

10. What happens if candidate TXT fingerprint matches but TLS certificate does not?
    - Reject the candidate as identity mismatch, do not send bearer credentials, do not update locator, and keep the stored pin unchanged.

11. Can discovery ever overwrite the trusted pin?
    - No.

12. Can discovery restore a revoked credential?
    - No.

13. Can a new IP for the same trusted SPKI identity work without re-pairing?
    - Yes. Discovery updates the locator only after the same pinned identity is verified.

14. Is the manual locator retained?
    - Yes, as a fallback and debugging path.

15. What happens when mDNS is blocked?
    - Android shows trusted laptop unavailable or discovery unavailable and keeps manual locator usable. Pairing and backup state are not deleted.

16. How are duplicate service names handled?
    - Service instance name is advisory. Duplicates are normalized as candidate updates; identity is SPKI verification, not name.

17. How are IPv4/IPv6 handled?
    - Plan to normalize both where platform APIs expose addresses. IPv6 literals must use bracketed URL syntax. Any implementation limitation must be documented.

18. Which laptop interfaces advertise?
    - Prefer appropriate non-loopback LAN interfaces through Zeroconf defaults/all interfaces, validated on Windows. Do not hardcode interface names.

19. Is a database migration needed?
    - No expected migration. Discovery state is ephemeral and trusted identity already exists.

20. Does Phase 6 trigger Backup Now automatically?
    - No.

21. Does Phase 6 add WorkManager?
    - No.

22. How can Phase 7 reuse this foundation safely?
    - Phase 7 can reuse bounded discovery state and verified locator updates before scheduling automatic backup, while still requiring pinned TLS and explicit auth for every transfer.

## Documentation Impact

Expected updates during implementation:

- `docs/current-state.md`: Phase 6 implementation/validation state.
- `docs/architecture.md`: discovery component and trust boundary.
- `docs/protocol.md`: DNS-SD service type and TXT metadata as interoperability behavior.
- `docs/security.md`: discovery is locator-only, TXT is untrusted, pinned TLS remains authoritative.
- `docs/testing.md`: backend/Android discovery tests and real-device validation.
- `docs/development.md`: discovery-enabled backend startup, port config, firewall/mDNS notes.
- `docs/repo-map.md`: backend discovery module and Android discovery package.
- `docs/testing/android-real-device-validation.md`: same-LAN discovery and locator-change validation steps.
- `desktop/backend/README.md`: discovery configuration/startup.
- `android/README.md`: Find Laptop behavior, permissions, known network limitations.
- `docs/decisions/ADR-0007-local-network-discovery.md`: if implementation confirms the design.

Also correct stale wording in `docs/development.md` and `android/README.md` that still describes Phase 5 as in progress or validation outstanding.

## ADR Recommendation

Create `docs/decisions/ADR-0007-local-network-discovery.md` during implementation if the design is confirmed.

ADR-0007 should record:

- DNS-SD/mDNS selected for same-LAN discovery.
- Service type `_localsync._tcp.`.
- Minimal TXT metadata.
- SPKI TXT is advisory only.
- Phase 5 pinned TLS identity remains the trust authority.
- Android uses NsdManager.
- Backend uses Zeroconf.
- Manual locator fallback remains.
- No background discovery or automatic backup in Phase 6.

## Dependencies Proposed

Backend:

- Add `zeroconf` if selected for DNS-SD/mDNS advertisement.

Android:

- Prefer no new production dependency; use Android `NsdManager`.
- No WorkManager, Firebase, Nearby, Bluetooth, Wi-Fi Direct, or cloud discovery SDK.

Fake client:

- No dependency change expected.

## Progress

- 2026-08-30: Created Phase 6 ExecPlan after reading repository, Android, backend, and tools agent instructions; planning template; current state, product scope, architecture, protocol, security, testing, development, repo-map, roadmap, real-device validation, backend/Android READMEs; ADR-0001 through ADR-0006; completed Phase 4 and Phase 5 ExecPlans; and actual backend, Android, and fake-client implementation around settings, TLS identity, pairing/auth, locators, pinned TLS, CLI, app lifecycle, and fake-client pinning. No Phase 6 code implemented.
- 2026-09-26: Added backend `zeroconf` advertisement boundary, configured discovery port/enable/name settings, FastAPI lifespan registration, and isolated metadata/lifecycle tests. Added Android `NsdManager` discovery, ephemeral candidate normalization, scoped multicast-lock policy, pinned-TLS trusted-server verification, locator-only credential-store updates, Home `Find Laptop` action, JVM trust/lifecycle policy tests, and Phase 6 documentation/ADR updates.
- 2026-09-26: Backend tests pass in the repository virtual environment and Android JVM tests pass. Real-device mDNS discovery, changed-locator, and spoofed-candidate checks have not yet been executed in this environment; the plan remains active.
- 2026-09-26: `zeroconf` resolved to `0.151.3` after installing the declared editable backend extra. Backend pytest passed 94 tests; Ruff check/format, Alembic current, Android `test`, `assembleDebug`, and `lint` passed. Gradle emitted only existing/deprecation warnings for Android NSD and Compose APIs.
- 2026-09-26: Real backend startup exposed an event-loop integration defect: synchronous Zeroconf registration attached to FastAPI's loop and timed out with `EventLoopBlocked`. The registrar now explicitly uses Zeroconf's dedicated internal loop (`use_asyncio=False`); backend pytest, Ruff check, and Ruff format pass after the fix. Real discovery validation must be repeated after restarting the backend.
- 2026-09-26: Real-device checkpoint confirmed the backend advertisement is observable from a local Zeroconf browser, but Android `NsdManager` received zero candidates on the current Wi-Fi despite successful phone-to-laptop ping. Treat this as a multicast-network limitation until another LAN/hotspot test demonstrates otherwise; do not weaken trust or add a custom UDP fallback.

## Discoveries

- Backend has no lifespan integration yet; `create_app` currently constructs `FastAPI(title=...)` directly.
- Backend does not have an application-level server port setting. Uvicorn port is currently supplied only on the command line.
- Phase 5 already generates a stable certificate with SAN `localsync.local` and canonical SPKI pin.
- Android already separates persisted trusted server identity from mutable locator in `PairedCredentials`.
- Android `ServerLocator` and `LocatorDns` already support using `localsync.local` as request host while connecting to the current locator host.
- Android manifest currently has media and internet permissions only; discovery may require network/multicast permissions.
- fake_phone verifies SPKI before pairing-code or bearer transmission but has no discovery support.
- `docs/development.md` and `android/README.md` contain stale Phase 5 wording that should be corrected during Phase 6 documentation updates.
- Official Android documentation says `NsdManager` discovery is DNS-SD over mDNS, callback-based, should be stopped when no longer needed, and may require explicit Wi-Fi multicast handling on older extension/device combinations.

## Decision Log

- Plan DNS-SD/mDNS rather than custom UDP broadcast or cloud discovery.
- Use service type `_localsync._tcp.`.
- Advertise canonical SPKI fingerprint as advisory TXT only; pinned TLS remains authoritative.
- Make Phase 6 primarily already-paired laptop relocation, not pairing UX redesign.
- Keep manual locator fallback.
- Do not create discovery database tables or migrations.
- Do not add WorkManager or automatic backup triggers.
- Prefer Android platform `NsdManager` and backend Zeroconf abstraction.

## Completion Criteria

Phase 6 is complete only when:

- Backend advertises `_localsync._tcp.` with minimal non-secret TXT metadata.
- Advertisement uses the existing Phase 5 server identity and configured HTTPS port.
- Advertisement lifecycle starts/stops with the backend or documented localSync server lifecycle.
- Android discovers localSync candidates through `NsdManager`.
- Android keeps discovery state bounded and lifecycle-aware.
- Android verifies discovered candidates through existing pinned TLS before updating locator.
- Bearer credentials are never sent to unverified discovered hosts.
- Discovery never overwrites the trusted SPKI pin.
- Manual locator fallback remains.
- Revoked credentials remain revoked after discovery.
- Tests cover backend advertisement metadata/lifecycle and Android discovery trust behavior.
- Backend and Android validation commands pass, or limitations are explicitly recorded.
- Real-device same-LAN discovery, locator change, trusted reconnect, and spoof/untrusted behavior are validated where practical.
- Docs and README files are updated.
- ADR-0007 is created if the implemented discovery protocol confirms this durable design.
- This ExecPlan is updated and moved to completed only after completion criteria pass.

## Final Results

Implementation is in progress. Backend advertisement and Android discovery foundations are present and validated by automated tests, but the required real-device same-LAN discovery checkpoint is outstanding. Keep this plan under `docs/plans/active/` until that checkpoint and the remaining Phase 6 validation are genuinely completed.

## Next Checkpoint

1. Start the HTTPS backend with the persistent Phase 5 certificate and the configured `LOCALSYNC_SERVER_PORT`.
2. Confirm the backend log reports discovery registration and inspect the phone/laptop network is a single non-isolated private LAN.
3. On the already-paired Android device, use `Find Laptop` and record whether `_localsync._tcp.` resolves to the usable HTTPS address and port.
4. Confirm the existing SPKI pin is verified before the locator changes and that an explicit `Backup Now` is still required.
5. Repeat with a changed laptop locator/IP while retaining the same certificate/key.
6. Where practical, test a wrong-certificate or spoofed-TXT candidate and confirm rejection without pin or locator mutation.
7. Test backend stop/restart and manual-locator fallback.
8. Update this plan and the validation record with actual results. Move it to `docs/plans/completed/` only when all required criteria pass; do not create or start the Phase 7 plan automatically.
