# Android Client

The Android app is a native manual backup client for accessible photos and videos. Phase 5 adds paired credentials, pre-secret server fingerprint observation, and pinned-TLS authenticated transfer requests. Phase 6 adds bounded foreground discovery of an already-paired laptop through Android `NsdManager`.

## Current Capabilities

- Single Android app module at `android/app`.
- Kotlin, Jetpack Compose, Material 3, Room, Coroutines, and OkHttp.
- Application ID: `dev.localsync.android`.
- `minSdk = 29`, `compileSdk = 36`, `targetSdk = 36`.
- Manual MediaStore inventory for accessible images/videos.
- Explicit media access states: unknown, denied, partial, full.
- Room metadata/state storage only; media bytes are never stored in Room.
- Development server locator, pairing fields, paired credential storage, and local forget.
- Manual `Backup Now` flow using the Phase 3 `/api/v1/uploads` resumable protocol.
- Pre-secret pairing flow: observe the presented SPKI fingerprint, compare it with the laptop CLI, explicitly confirm, then send the pairing code.
- Bearer-authenticated transfer requests after pairing over pinned TLS.
- Android Keystore-backed credential storage boundary.
- Incremental SHA-256 hashing and bounded streaming from `content://` sources.
- Debug-only cleartext HTTP configuration for local backend development.
- `Find Laptop` discovery for paired devices; discovery updates only the current locator after pinned TLS verification.

## Toolchain

The implementation uses:

- Gradle wrapper: 9.6.1.
- Android Gradle Plugin: 9.3.0.
- Kotlin/Compose compiler plugin: 2.3.10.
- KSP: 2.3.10.
- Compose BOM: 2026.06.00.
- Room: 2.8.0.
- OkHttp/MockWebServer: 5.1.0.

The initial preference was AGP 9.4.0, Gradle 9.6, and SDK 37. In this environment AGP 9.4.0 did not resolve, Gradle's available distribution is 9.6.1, and only SDK 36 is installed, so Phase 4 uses the closest stable compatible set.

## Build And Test

```powershell
cd android
.\gradlew.bat assembleDebug
.\gradlew.bat test
.\gradlew.bat lint
```

Run instrumented tests only when a device/emulator is available:

```powershell
cd android
.\gradlew.bat connectedDebugAndroidTest
```

## Development Backend

Start the desktop backend separately over HTTPS, then enter its LAN locator URL in the app's Developer Settings screen.

Do not use `127.0.0.1` for a physical Android device unless the backend is actually running on that device. For the Android emulator, the host machine is usually reachable through `https://10.0.2.2:8000`.

Pair the app with a backend-created pairing session before running Backup Now. The local Android installation ID is advisory metadata and is not authentication.

## Security Limits

Phase 5 improves authentication but is not complete production security:

- Backend transfer endpoints require bearer device credentials.
- Device credentials are stored through an Android Keystore-backed boundary.
- Pairing observes the server SPKI fingerprint before sending the pairing code.
- Normal authenticated Android traffic uses `localsync.local` as the TLS identity host and maps it to the configured LAN locator for connection.
- Debug builds still allow cleartext HTTP for older local development paths, but authenticated Phase 5 traffic requires HTTPS.
- Discovery TXT records and service names are advisory and never authenticate a laptop. Manual locator entry remains available when mDNS is blocked.
- The app targets SDK 36. Android 17/API 37 local-network permission changes must be revisited before raising targetSdk.
- Real-device Phase 6 discovery validation remains to be performed.

Do not use this app with personal irreplaceable media as though it were production backup software.
