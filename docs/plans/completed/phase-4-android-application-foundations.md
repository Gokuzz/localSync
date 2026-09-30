# Phase 4: Android Application Foundations and Manual Media Backup

## Purpose / User Outcome

Build the first real Android client for localSync.

At the end of Phase 4 implementation, a user should be able to install/open the Android application, grant photo/video access, view accessible MediaStore photos/videos, manually enter a development backend URL, press Backup Now, and transfer selected accessible media through the existing Phase 3 resumable protocol without changing source bytes.

Phase 4 is manual backup only. It does not implement automatic background backup, pairing, discovery, production security, or arbitrary document transfer.

## Scope

Phase 4 includes:

- Native Android project bootstrap under `android/`.
- Kotlin, Gradle Kotlin DSL, Jetpack Compose, Material 3, AndroidX, Room, Coroutines/Flow, and OkHttp.
- Single Android app module with clear package boundaries.
- Version-aware photo/video permission handling.
- MediaStore scanner for accessible images and videos.
- Media inventory/status UI.
- Development-only backend URL and device namespace settings.
- Android-side metadata persistence with Room.
- Incremental SHA-256 hashing from source `content://` media.
- Opaque-byte transfer through Phase 3 `/api/v1/files/check` and `/api/v1/uploads`.
- Sequential manual Backup Now workflow.
- Resume from nonzero server offsets when a previous upload session exists.
- Android unit/instrumentation tests where practical.
- One real backend/device or emulator demonstration when Android tooling/device access permits.
- Documentation updates for actual Android setup, security limits, and validation.

## Out of Scope

Do not implement in Phase 4:

- Automatic background backup.
- Periodic WorkManager jobs.
- Charging constraints.
- Automatic Wi-Fi detection.
- mDNS/NSD discovery.
- QR pairing.
- Authentication.
- Tokens.
- TLS certificate pinning.
- Production HTTPS identity.
- React desktop UI.
- Manual arbitrary document transfer.
- Storage Access Framework document picker.
- Two-way file transfer.
- Laptop-to-phone transfer.
- Cloud services.
- Photo deletion.
- Remote deletion.
- Thumbnails/gallery polish.
- Albums.
- EXIF extraction.
- Photo/video transcoding.
- Media compression.
- Parallel uploads.
- Multiple simultaneous files.
- Bandwidth throttling.
- Phase 5+ security/discovery work.

## Current System Context

Repository state:

- `android/` currently contains only `AGENTS.md` and `README.md`.
- Planned V1 platforms are Android mobile client and Windows desktop/laptop application.
- Desktop backend Phase 3 is complete.
- Fake-device client uses the Phase 3 resumable protocol successfully.

Relevant backend API as actually implemented:

- `POST /api/v1/files/check`
  - JSON request: `device_id`, `filename`, `size`, `sha256`, optional `content_type`.
  - JSON response: `exists`, optional `stored_file_id`, optional `stored_path`.
- `POST /api/v1/uploads`
  - JSON request: `device_id`, `filename`, `expected_size`, `expected_sha256`, optional `content_type`.
  - JSON response status is `already_stored` or `receiving`.
  - Receiving response includes `upload_id`, `next_offset`, `expected_size`, and `chunk_size_hint`.
- `GET /api/v1/uploads/{upload_id}`
  - Returns status and authoritative `next_offset`.
- `PUT /api/v1/uploads/{upload_id}`
  - Raw request body.
  - Required `X-localSync-Offset` header.
  - Required `Content-Length`.
  - Offset mismatch returns structured `409 offset_mismatch` with `details.expected_offset`.
- `POST /api/v1/uploads/{upload_id}/complete`
  - Idempotent completion.
  - Success returns `completed`, `upload_id`, `stored_file_id`, `stored_path`.

Relevant protocol constraints:

- `device_id` is a development namespace only, not authentication.
- `upload_id` is an identifier only, not authorization.
- Full identity is size plus full SHA-256 within the development device namespace.
- Completed backups are finalized only after server size and SHA-256 verification.
- Phase 3 default fake-client chunk size is 8 MiB.
- Backend default maximum chunk request size is 16 MiB.
- Existing `/api/v1/files` remains legacy non-resumable development upload, but Android should use `/uploads`.

Relevant ADRs:

- ADR-0001: protocol/domain concepts are platform-neutral.
- ADR-0002: backup semantics are one-way and deletion-safe.
- ADR-0003: media bytes are preserved and verified by SHA-256.
- ADR-0004: resumable transfer uses server-side `UploadSession`, append-only offsets, and actual partial-file length as authoritative.

## Assumptions

- Phase 4 targets Android 10+ with `minSdk = 29`.
- Exact Android Gradle Plugin, Kotlin, Compose BOM, compileSdk, and targetSdk versions will be selected and recorded during implementation after checking installed SDK/toolchain support and stable official releases.
- Use stable Android tooling only; no preview/canary SDKs or plugins.
- JDK 17 is the expected baseline unless the selected stable Android Gradle Plugin requires a newer JDK.
- Use application ID `dev.localsync.android` for development unless implementation discovers a concrete conflict.
- Android app remains one module in Phase 4.
- Android transfer is sequential and foreground/user-initiated.
- The app may be interrupted by Android while in foreground/manual use; a later Backup Now can recover via backend resumable sessions.
- The backend remains manually configured by URL in Phase 4.
- The development backend is HTTP, so debug cleartext support may be needed.
- The implementation environment may not have Android SDK/emulator/device available; report that as environment limitation rather than project failure.

## Architecture / Approach

Use a simple Android architecture:

```text
Compose UI
    ViewModel
        Repository / application logic
            MediaStore data source
            Room data source
            localSync HTTP data source
            Media byte source
```

Rules:

- Composables render immutable UI state and emit user actions.
- ViewModels coordinate UI state, permission state, inventory refresh, and Backup Now actions.
- Repositories coordinate MediaStore, Room, byte source, hashing, and HTTP protocol client.
- MediaStore code stays Android-specific under `android/`.
- The HTTP protocol client uses generic DTO names such as UploadSession, FileCheck, MediaCandidate, Transfer.
- Do not introduce Hilt/Dagger in Phase 4. Use constructor dependency injection and a small application-level dependency container.
- Do not introduce use-case classes for every operation. Add a use case only if logic becomes genuinely reusable or complex.
- Do not modify backend API semantics for Android.

## Proposed SDK / Toolchain Baseline

Planned baseline:

- Kotlin.
- Gradle Kotlin DSL.
- Single `:app` Android application module.
- `minSdk = 29`.
- `compileSdk` and `targetSdk`: latest stable installed SDK supported by the selected stable Android Gradle Plugin at implementation time.
- Android Gradle Plugin: latest stable official release available and compatible with local tooling at implementation time; do not use alpha/beta/canary.
- Kotlin plugin: stable version compatible with the selected AGP and Compose compiler/toolchain.
- JDK: 17 unless the selected stable AGP requires a newer supported JDK.

Implementation must record exact versions in this ExecPlan and Android README once chosen.

Rationale:

- Android 10/API 29 aligns with scoped storage and avoids legacy broad filesystem assumptions.
- Modern target SDK is needed to handle Android 13 granular media permissions and Android 14+ selected photos access correctly.
- A single module avoids premature build complexity.

## Proposed Package Structure

Initial structure:

```text
android/
    settings.gradle.kts
    build.gradle.kts
    gradle/
    app/
        build.gradle.kts
        src/main/
            AndroidManifest.xml
            java/dev/localsync/android/
                MainActivity.kt
                LocalSyncApplication.kt
                AppContainer.kt

                core/
                    model/
                    result/
                    util/

                data/
                    database/
                    media/
                    network/
                    repository/
                    settings/

                transfer/

                ui/
                    home/
                    media/
                    settings/
                    components/

        src/test/
        src/androidTest/
        src/debug/
            res/xml/network_security_config.xml
```

Avoid:

- Generic `utils` dumping ground.
- BaseRepository/BaseViewModel hierarchies.
- Multi-module split before clear boundaries require it.

## Android Permissions Strategy

Represent app media access as a first-class model:

```text
MediaAccessState:
    FullAccess
    PartialAccess
    Denied
    Unknown
```

The UI must never claim all media is protected when only partial/user-selected access was granted.

Version-specific plan:

- Android 10-12/API 29-32:
  - Request `READ_EXTERNAL_STORAGE` where required for reading other apps' shared images/videos.
  - Query images/videos through MediaStore under scoped storage.
  - Do not request `MANAGE_EXTERNAL_STORAGE`.
- Android 13/API 33:
  - Request `READ_MEDIA_IMAGES` and `READ_MEDIA_VIDEO`.
  - Treat granted image/video permissions as full accessible media scope for the granted media types.
  - Do not request audio permission.
- Android 14+/API 34+:
  - Request `READ_MEDIA_IMAGES`, `READ_MEDIA_VIDEO`, and declare/use `READ_MEDIA_VISUAL_USER_SELECTED` so selected-photos access can be represented explicitly.
  - Distinguish full library access from selected media access.
  - Expose a Manage Access action that re-launches the permission request/reselection flow.

Permission UI states:

- Before permission: explain photo/video access is needed for media the user wants backed up.
- Denied: show that no media can be discovered until access is granted.
- Full access: show "Photos & videos" and accessible count.
- Partial access: show "Limited photo access" or equivalent and accessible count.

Do not use manipulative permission text or request unrelated permissions.

## MediaStore Model

Use ContentResolver/MediaStore queries. Do not crawl raw filesystem paths and do not use `MediaStore.DATA`.

Discover accessible:

- Images.
- Videos.

Android-specific discovery model can include:

- `mediaStoreId: Long`
- `volumeName: String`
- `contentUri: Uri`
- `displayName: String`
- `size: Long`
- `mimeType: String?`
- `dateAdded: Long?`
- `dateModified: Long?`
- `dateTaken: Long?`
- `mediaType: image | video`

Expose platform-neutral application model:

```text
MediaItem:
    id
    sourceUri
    displayName
    size
    mimeType
    mediaKind
    dateTaken/dateModified
```

Scan behavior:

- Initial scan collects inexpensive MediaStore metadata only.
- Do not compute SHA-256 for every discovered item during inventory.
- If a previously inventoried item disappears, Android local inventory may mark it missing or remove it locally.
- Disappearance must never create a backend deletion request.

No EXIF parsing, thumbnails, album organization, or media decoding in Phase 4.

## Room Model

Use Room for Android-side metadata and state only. Do not store media bytes.

Minimum planned entities:

`MediaItemEntity`

- `id`: local Room ID.
- `mediaStoreId`: platform row ID.
- `volumeName`: where available.
- `contentUri`: persisted string form of MediaStore content URI.
- `displayName`.
- `size`.
- `mimeType`.
- `mediaType`: image/video.
- `dateAdded`, `dateModified`, `dateTaken` where available.
- `lastSeenAt`.
- `isMissing`: marks source no longer visible without implying remote delete.

`BackupStateEntity`

- `mediaItemId`: references local media item.
- `status`: `not_backed_up`, `checking`, `hashing`, `uploading`, `backed_up`, `failed`.
- `sha256`: nullable full hash computed when needed.
- `hashedSize`: nullable size used when hash was computed.
- `storedFileId`: nullable backend metadata ID after success.
- `storedPath`: nullable server-controlled relative path after success.
- `lastAttemptAt`.
- `lastSuccessAt`.
- `failureCode`: nullable stable category.
- `failureMessage`: nullable short display/debug text.

Rationale:

- Media identity/inventory and backup state evolve separately.
- Local state can survive app restarts.
- Backend remains authoritative for exact already-backed-up checks.

Room rules:

- Schema versioning must be explicit.
- Do not use `fallbackToDestructiveMigration()` as a casual shortcut.
- Configure schema export if supported by the selected toolchain.
- Add migration tests once schema evolves.

## Media Byte Source / Resume Strategy

Create a narrow Android-side byte source abstraction, for example:

```text
MediaByteSource
    open(uri)
    size(uri)
    sha256(uri)
    streamRange(uri, offset, length)
```

Implementation requirements:

- Use `ContentResolver` and source `content://` URIs.
- Read with bounded buffers.
- Do not expose filesystem paths to higher layers.
- Do not load full videos into memory.
- Do not decode/re-encode, resize, compress, transcode, rewrite metadata, or create replacement files.
- Hash source bytes incrementally.

Resume from nonzero offset:

- Preferred path for MediaStore-backed local media:
  - Open a file/asset descriptor through `ContentResolver`.
  - Use a `FileChannel`/descriptor-backed stream where seeking is supported.
  - Position to server `next_offset`.
  - Stream at most the configured chunk size into OkHttp.
- If a provider returns a non-seekable pipe/stream:
  - Do not skip gigabytes into RAM.
  - For Phase 4, mark that item as requiring restart or unsupported resume if seeking is unavailable.
  - Because Phase 4 primary scope is MediaStore local photos/videos, this should be rare but must be handled predictably.

Implementation must investigate `ContentResolver.openFileDescriptor` and `openAssetFileDescriptor` behavior with MediaStore URIs. The Android API docs note that read-only descriptors can be pipes and that asset descriptors may have offsets, so code must not assume all content URIs are normal seekable files.

Source mutation:

- Compute full SHA-256 and size before session creation.
- Store hash only with the size and metadata used to compute it.
- If MediaStore metadata changes later, do not assume the old hash is valid.
- Server completion remains the final integrity authority.
- If source bytes change mid-transfer, completion must fail rather than marking Backed Up.

## Network Client Design

Use OkHttp directly.

Do not add Retrofit in Phase 4 because the protocol needs:

- raw binary PUT request bodies;
- custom metadata headers;
- explicit offset handling;
- direct streaming control.

Network package responsibilities:

- Base URL validation for development settings.
- DTOs matching actual backend schemas.
- `FileCheckClient`.
- `UploadSessionClient`.
- Structured error parsing, especially:
  - `offset_mismatch` with `details.expected_offset`;
  - `upload_incomplete` with `details.next_offset`;
  - `hash_mismatch`;
  - `disk_space_insufficient`;
  - `upload_failed`.

Android DTOs must match actual Phase 3 backend names:

- `/files/check`: `device_id`, `filename`, `size`, `sha256`, `content_type`.
- `/uploads`: `device_id`, `filename`, `expected_size`, `expected_sha256`, `content_type`.
- `PUT /uploads/{upload_id}`: raw body, `X-localSync-Offset`, `Content-Length`.

No Android-specific backend routes or DTO names.

## Resumable Transfer Workflow

Manual Backup Now flow:

```text
load accessible media inventory
for each candidate sequentially:
    mark Checking
    if known hash is stale or missing:
        mark Hashing
        compute SHA-256 incrementally
    POST /api/v1/files/check
    if exists:
        persist Backed up
        continue
    POST /api/v1/uploads
    if already_stored:
        persist Backed up
        continue
    read next_offset
    while next_offset < size:
        open source URI
        seek/position to next_offset
        stream bounded chunk with PUT /api/v1/uploads/{upload_id}
        if offset_mismatch:
            update next_offset and continue
        update progress
    POST /api/v1/uploads/{upload_id}/complete
    only then persist Backed up
```

Workflow rules:

- Sequential only.
- No parallel chunks.
- No concurrent media uploads.
- Default Android chunk size should start at 8 MiB for consistency with fake client.
- Centralize protocol constants and allow implementation to use server `chunk_size_hint` when present while respecting backend max.
- Backend success, not Android local optimism, marks Backed Up.
- Network failures set retryable Failed state and do not modify source media.

## Developer Settings

Phase 4 has no discovery or pairing, so add development settings:

- Server URL, for example `http://192.168.1.20:8000`.
- Development device namespace, for example `android-dev-<stable-local-id>`.

Rules:

- Do not hardcode a laptop IP.
- Do not assume `127.0.0.1` is the laptop from Android.
- Persist settings locally, likely via DataStore Preferences or simple SharedPreferences.
- Prefer the simplest persistent settings mechanism; do not add a large settings framework.
- Label this as development-only UX in docs and UI copy where appropriate.

Device namespace:

- Generate a stable local ID on first run and prefix with `android-dev-`.
- Store it locally.
- Do not call it authentication.
- Do not store tokens because none exist.

## Debug Cleartext HTTP Strategy

The Phase 3 backend is HTTP. If Android requires cleartext for development:

- Use debug-specific Android Network Security Configuration under `src/debug`.
- Allow cleartext only for debug/development builds.
- Do not globally weaken release networking.
- Release manifest/config must not inherit unrestricted cleartext settings.
- Document that production security and pairing are Phase 5+ work.

## UI Plan

Use Jetpack Compose and Material 3.

Screens:

1. Home
   - App title.
   - Permission/access state.
   - Accessible media count.
   - Backed up / not backed up / failed counts.
   - Backup Now button.
   - Current transfer progress when running.
2. Media
   - Simple list: display name, type/size, backup status.
   - No gallery grid or thumbnails in Phase 4 unless needed for usability.
3. Developer Settings
   - Server URL.
   - Device namespace.
   - Save/validation state.

UI states:

- Permission required.
- Denied.
- Limited access.
- Full access.
- Loading inventory.
- Ready.
- Backup running.
- Backup completed.
- Backup failed with retry option.

Compose rules:

- Composables render state.
- ViewModels own actions.
- MediaStore, Room, and network logic never live directly in Composables.

## Dependencies Proposed

Expected production dependencies:

- Android Gradle Plugin and Kotlin plugin.
- AndroidX Core.
- Lifecycle/ViewModel.
- Jetpack Compose.
- Material 3.
- Kotlin Coroutines.
- Room runtime/compiler/KSP or kapt.
- OkHttp.

Expected test dependencies:

- JUnit.
- AndroidX test/core where needed.
- Coroutine test library.
- Room testing.
- MockWebServer if justified for OkHttp-compatible protocol tests.
- Compose UI test where practical.

Avoid in Phase 4:

- Hilt/Dagger.
- Retrofit.
- Coil/Glide.
- RxJava.
- Realm.
- Firebase.
- Google Drive SDK.
- Cloud SDKs.
- WorkManager.

Dependency rationale:

- Room is justified for persistent Android-side media inventory and backup state.
- OkHttp is justified because Phase 3 needs raw streaming request bodies and custom offset headers.
- MockWebServer is justified if network parsing/retry behavior is tested without requiring a Python backend for every Android unit test.

## Milestones

- [x] Milestone 1: Android Gradle/Compose project bootstrap.
  - Create single `:app` module.
  - Choose stable AGP/Kotlin/Compose/compileSdk/targetSdk versions and record them.
  - Configure `dev.localsync.android`.
  - Add debug-only cleartext network config if needed.
  - Validate `./gradlew assembleDebug` where environment permits.

- [x] Milestone 2: Application architecture and dependency container.
  - Add `LocalSyncApplication`, `AppContainer`, package boundaries, coroutine dispatchers, and simple settings store.
  - No Hilt/Dagger.

- [x] Milestone 3: Version-aware media permission handling.
  - Implement permission-state mapping for Android 10-12, Android 13, and Android 14+.
  - Distinguish full, partial, denied, and unknown states.
  - Add tests for permission-state mapping.

- [x] Milestone 4: MediaStore scanner and application models.
  - Query accessible images/videos only.
  - Map rows into platform-neutral media candidates.
  - Avoid `MediaStore.DATA` and raw filesystem crawl.
  - Add mapper/scanner tests.

- [x] Milestone 5: Room media inventory/state persistence.
  - Add Room database, DAOs, `MediaItemEntity`, and `BackupStateEntity`.
  - Persist metadata/state only.
  - Add Room tests for insert/update/query and source deletion/local missing state.

- [x] Milestone 6: Basic Compose UI.
  - Home, Media, Developer Settings.
  - Permission states and accessible count.
  - Backup Now action.
  - Functional list UI, not gallery polish.

- [x] Milestone 7: Media byte source and incremental SHA-256.
  - Implement bounded reads from ContentResolver.
  - Implement incremental SHA-256.
  - Implement seek/range reads for MediaStore where descriptors support it.
  - Define unsupported behavior for non-seekable sources.
  - Add tests for hashing and bounded reads.

- [x] Milestone 8: OkHttp localSync protocol client.
  - Implement `/files/check`, `/uploads`, status, PUT chunk, complete.
  - Parse structured errors and offset conflicts.
  - Add MockWebServer tests.

- [x] Milestone 9: Manual sequential Backup Now workflow.
  - Connect MediaStore, Room, byte source, hashing, and protocol client.
  - Sequential transfer only.
  - Persist status only after backend completion.
  - Add tests for success, already-backed-up, network failure, resume, and source mutation failure.

- [x] Milestone 10: Android tests and validation hardening.
  - Unit tests for permissions, mapping, Room, hashing, protocol client, and workflow.
  - Compose/UI tests where practical.
  - Instrumented tests for MediaStore/ContentResolver behavior where emulator/device is available.

- [ ] Milestone 11: Real backend/device integration demonstration.
  - Use generated/test media on emulator or device.
  - Configure backend URL manually.
  - Backup Now transfers to real localSync backend.
  - Verify source/destination size and SHA-256.
  - Demonstrate resume from nonzero offset where practical.

- [x] Milestone 12: Documentation and final validation.
  - Update Android README and project docs.
  - Record exact versions, commands, demo results, limitations.
  - Move this ExecPlan to completed only after completion criteria pass.

## Files / Modules Expected to Change

Expected creates/updates:

- `android/settings.gradle.kts`
- `android/build.gradle.kts`
- `android/gradle/**`
- `android/app/build.gradle.kts`
- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/debug/res/xml/network_security_config.xml` if debug cleartext is needed
- `android/app/src/main/java/dev/localsync/android/MainActivity.kt`
- `android/app/src/main/java/dev/localsync/android/LocalSyncApplication.kt`
- `android/app/src/main/java/dev/localsync/android/AppContainer.kt`
- `android/app/src/main/java/dev/localsync/android/core/**`
- `android/app/src/main/java/dev/localsync/android/data/media/**`
- `android/app/src/main/java/dev/localsync/android/data/database/**`
- `android/app/src/main/java/dev/localsync/android/data/network/**`
- `android/app/src/main/java/dev/localsync/android/data/repository/**`
- `android/app/src/main/java/dev/localsync/android/data/settings/**`
- `android/app/src/main/java/dev/localsync/android/transfer/**`
- `android/app/src/main/java/dev/localsync/android/ui/**`
- `android/app/src/test/**`
- `android/app/src/androidTest/**`
- `android/README.md`

Expected docs:

- `docs/current-state.md`
- `docs/architecture.md`
- `docs/security.md`
- `docs/testing.md`
- `docs/development.md`
- `docs/repo-map.md`
- `docs/protocol.md` only if Android integration exposes a genuine clarification
- this ExecPlan

Possible ADR:

- Consider ADR only if Phase 4 makes a durable cross-cutting Android baseline decision beyond ordinary implementation, such as a long-lived minimum supported Android version policy.
- Do not create ADRs merely for Compose, Room, or OkHttp because these were already planned stack choices.

## Testing and Validation

Required planned tests:

1. Permission-state mapping.
2. Full vs partial media-access representation.
3. MediaStore row to application model mapping.
4. Room insert/update/query behavior.
5. Source deletion/local disappearance does not imply remote deletion.
6. Incremental SHA-256.
7. Bounded source reads.
8. Source media remains unchanged.
9. `/files/check` client parsing.
10. Upload-session creation parsing.
11. Resume from nonzero offset.
12. Old-offset response recovery.
13. Final completion parsing.
14. Network failure surfaces retryable state.
15. Already-backed-up content skips transfer.
16. Manual Backup Now flow.
17. Backend success only marks Backed Up after completion.
18. Source mutation causes integrity failure rather than false success.
19. Debug cleartext config does not leak into release.
20. Room contains no media-byte columns.

Expected validation commands:

```powershell
cd android
.\gradlew assembleDebug
.\gradlew test
.\gradlew lint
```

Instrumented validation when emulator/device is available:

```powershell
cd android
.\gradlew connectedDebugAndroidTest
```

If Android SDK, Gradle wrapper download, emulator, or device access is unavailable in the Codex environment, document that clearly. Do not weaken implementation or tests to hide environment limits.

Network tests:

- Prefer MockWebServer for OkHttp protocol tests.
- Do not require Python backend for every Android unit test.
- Phase 4 completion still requires at least one real backend/device or emulator demonstration if environment permits.

Real demo:

- Create/copy generated test media onto emulator/device.
- Start real localSync backend.
- Enter backend URL in Android Developer Settings.
- Grant media permission.
- Press Backup Now.
- Verify destination bytes/size/SHA-256 match source.
- Demonstrate interruption/resume where practical by interrupting app/network/request and pressing Backup Now again.

## Security Considerations

Phase 4 remains development-security only.

Security limitations to document:

- Backend endpoints are not authenticated.
- `device_id` is not identity proof.
- Manual backend URL is temporary.
- Debug cleartext HTTP may be enabled for local development only.
- Pairing is future work.
- No tokens or secrets exist yet.
- Do not claim users' photos are protected from other LAN devices.

Implementation safeguards:

- Do not log media bytes.
- Avoid logging full content URIs and private filenames at high volume.
- Do not log future secrets or auth material.
- Do not request `MANAGE_EXTERNAL_STORAGE`.
- Do not crawl filesystem paths.
- Do not store media bytes in Room.
- Do not modify source media.
- Do not issue any backend delete request when source media disappears.

## Risks / Unknowns

- Exact stable Android tooling versions depend on installed SDK/toolchain availability.
- Android 14+ partial access behavior must be tested on a compatible emulator/device.
- Some content providers can return non-seekable streams; Phase 4 must handle that without unbounded skip/read.
- MediaStore metadata may be absent or inconsistent across devices.
- Hashing large videos before upload is expensive but necessary for the Phase 3 protocol.
- Foreground manual transfer may be interrupted by lifecycle/network conditions; Phase 4 relies on a later manual retry, not WorkManager.
- Debug cleartext setup must not leak into release builds.
- Real device/emulator demonstration may be blocked in Codex if no Android SDK/device is available.

## Architecture Review

1. Does Android use the existing generic protocol unchanged?
   - Yes. Android consumes `/files/check` and `/uploads` as implemented. No Android-specific backend endpoints or schemas are planned.

2. Can photos/videos be transferred without recompression?
   - Yes. Source bytes are read from MediaStore content URIs and streamed as opaque bytes. No decode/re-encode pipeline is planned.

3. Can hashing and transfer occur without loading entire media into RAM?
   - Yes. Hashing and transfer use bounded buffers and chunked OkHttp request bodies.

4. How will a MediaStore source resume from a nonzero offset?
   - Prefer descriptor-backed seeking through ContentResolver for MediaStore URIs. If a source is non-seekable, Phase 4 must fail/restart predictably rather than loading skipped bytes into memory.

5. How are Android 10-12, Android 13, and Android 14+ permission differences handled?
   - Android 10-12 use `READ_EXTERNAL_STORAGE`; Android 13 uses `READ_MEDIA_IMAGES`/`READ_MEDIA_VIDEO`; Android 14+ also handles selected visual access with `READ_MEDIA_VISUAL_USER_SELECTED`.

6. How does the app distinguish full vs partial library access?
   - Permission state is modeled as FullAccess, PartialAccess, Denied, or Unknown and displayed in UI.

7. Can the app accidentally claim all media is protected when access is partial?
   - It must not. Partial access UI must state only accessible selected media can be seen/backed up.

8. Does deleting Android media cause any remote deletion?
   - No. Source disappearance may update local inventory only. There is no remote delete request or protocol.

9. Is Room metadata-only?
   - Yes. Room stores inventory, status, hashes, and backend metadata IDs/paths only.

10. Are source bytes never copied into Room?
    - Correct. Media bytes stay in MediaStore and are streamed to the backend.

11. Is WorkManager completely deferred?
    - Yes. No WorkManager jobs or background scheduling are planned for Phase 4.

12. Is development cleartext configuration isolated from release?
    - Yes. Plan uses debug-specific network security configuration only if needed.

13. Is pairing/authentication still explicitly absent?
    - Yes. Device namespace is development-only and not auth.

14. Can an Android app restart recover a server-side resumable upload?
    - Yes. It recomputes size/SHA-256, calls `POST /uploads`, receives recovered `next_offset`, and resumes if the source is seekable.

15. Does the design avoid Android-specific backend changes?
    - Yes. All Android-specific code remains under `android/`.

16. Are we introducing unnecessary dependencies?
    - No. Hilt, Retrofit, WorkManager, image loaders, RxJava, Firebase, and cloud SDKs are deferred.

17. Can future automatic backup reuse the MediaStore/Room/transfer foundations cleanly?
    - Yes. Future WorkManager/automatic scheduling can reuse scanner, byte source, Room state, and protocol client without changing backend protocol.

## Documentation Impact

Expected Phase 4 documentation updates:

- `android/README.md`: setup, build, run, permissions, development backend URL, validation, known limitations.
- `docs/current-state.md`: Phase 4 completion status only after validation.
- `docs/architecture.md`: Android client component if actual implementation establishes details.
- `docs/security.md`: Android development URL, debug cleartext, no pairing/auth claims.
- `docs/testing.md`: Android unit/instrumented tests and real-device demo.
- `docs/development.md`: Android setup/build/test commands.
- `docs/repo-map.md`: Android project structure.
- `docs/protocol.md`: only if implementation discovers a real protocol clarification.

ADR recommendation:

- Do not create an ADR for Compose, Room, or OkHttp.
- Consider an ADR for `minSdk = 29` only if implementation confirms this is a durable project policy with meaningful tradeoffs.

## Progress

- 2026-08-16: Created Phase 4 ExecPlan after reading root and Android agent instructions, current architecture/protocol/security/testing/development/roadmap docs, ADRs including ADR-0004, completed Phase 3 plan, and actual backend/fake-client protocol implementation. No Phase 4 code implemented.
- 2026-08-16: Milestone 1 started. Local environment has JDK 21 and Android SDK platform/build-tools 36 installed, no system Gradle, and no SDK 37. Selected compileSdk/targetSdk 36 for local compatibility and used Gradle 9.6.1 because the official Gradle distribution list has 9.6.0/9.6.1 but no `gradle-9.6-bin.zip`. AGP 9.4.0 was attempted but did not resolve from Google/Maven/Plugin Portal in this environment; switched to closest resolvable stable AGP 9.3.0. KSP uses stable plugin version 2.3.10. Compose uses the official Kotlin Compose compiler plugin 2.3.10; no separate `org.jetbrains.kotlin.android` plugin was added.
- 2026-08-16: Implemented a single-module Android app under `android/app` with application ID `dev.localsync.android`, Compose UI, Room metadata/state persistence, MediaStore scanning, version-aware permission mapping, development settings, `ContentResolver` byte-source streaming, OkHttp Phase 3 protocol client, and manual sequential Backup Now workflow.
- 2026-08-16: Added narrow Android boundary interfaces for media scanning, settings, byte-source, and protocol client where they improve testability without adding a DI framework or broad service hierarchy.
- 2026-08-16: Added Android JVM tests for permission mapping, bounded hashing/streaming primitives, protocol parsing/offset conflicts, and manual Backup Now repository behavior including already-backed-up skip, offset recovery, source-disappearance deletion safety, and backend-completion authority.
- 2026-08-16: Generated the Gradle wrapper for Gradle 9.6.1 and validated Android build/test/lint. A parallel validation attempt caused Kotlin incremental-cache contention on Windows, so final validation was rerun sequentially with `.\gradlew.bat --no-daemon --max-workers=1 clean assembleDebug test lint`; it passed.
- 2026-08-16: Checked for Android device/emulator availability with `adb devices`; no connected device was available, so real Android MediaStore/backend integration and interruption/resume demonstration were not executed in this environment.
- 2026-08-16: Updated Android README and shared architecture, development, security, testing, repo-map, and current-state documentation.

## Discoveries

- Android directory has no Gradle project yet.
- Phase 3 backend uses `/api/v1/uploads`, not `/api/v1/upload-sessions`.
- Actual upload create request uses `expected_size` and `expected_sha256`.
- Actual append request requires raw body, `X-localSync-Offset`, and `Content-Length`.
- Offset mismatch details use `expected_offset`.
- Fake client default chunk size is 8 MiB.
- Phase 3 backend default max chunk request size is 16 MiB.
- Backend session recovery currently matches receiving sessions by development device namespace, original filename, expected size, and expected SHA-256.
- Local Android SDK path is `E:\andr`; installed platform is `android-36`, so SDK 37 validation is not possible in this environment without installing another SDK.
- MockWebServer 5 requires explicit `start()` before calling `url()`.
- Android JVM unit tests use stubbed platform `org.json`; adding `org.json:json:20260522` as a test-only dependency is required for protocol JSON parsing tests.
- `MediaStore.getExternalVolumeNames` requires a `Context`; the scanner boundary accepts Android `Context` and still exposes platform-neutral `MediaItem` values.
- No emulator or physical device is attached in this environment.

## Decision Log

- Plan Phase 4 as a single-module native Android app.
- Use application ID `dev.localsync.android` unless implementation finds a concrete conflict.
- Keep Phase 4 manual/foreground only; WorkManager is deferred.
- Use OkHttp directly instead of Retrofit.
- Model full vs partial media access explicitly.
- Use Room for metadata/state only.
- Use debug-only cleartext configuration if HTTP is needed.
- Use server-side resumable session recovery instead of local upload-ID persistence as the primary resume strategy.
- Toolchain deviation: use AGP 9.3.0 because AGP 9.4.0 did not resolve, Gradle 9.6.1 instead of non-existent distribution label 9.6, and compile/target SDK 36 because SDK 37 is unavailable locally.
- Use SharedPreferences for the temporary development server URL and development device namespace because Phase 4 has only two non-secret settings.
- Keep debug cleartext HTTP in `src/debug`; release manifest does not set a blanket production `usesCleartextTraffic`.
- Query MediaStore external volume names on API 29+ instead of assuming a single primary volume.
- Do not persist backend upload IDs in Room; app restart recovery uses full SHA-256/size plus `POST /uploads`.
- Do not create an ADR for Phase 4. Compose, Room, OkHttp, and minSdk 29 were already planned stack/baseline choices and did not introduce a new cross-cutting protocol decision.

## Completion Criteria

Phase 4 is complete only when:

- Android project builds as a native Kotlin/Compose app.
- Media permissions are version-aware and distinguish full, partial, denied, and unknown states.
- MediaStore scanner discovers accessible images/videos without raw filesystem crawling.
- Room stores media inventory and backup state metadata only.
- Basic Home, Media, and Developer Settings UI exists.
- Developer backend URL and device namespace can be configured.
- Manual Backup Now computes SHA-256 incrementally and transfers media through `/api/v1/uploads`.
- Transfers are resumable from backend nonzero offsets when the MediaStore source supports seeking.
- Successful state is persisted only after backend completion.
- Source media remains untouched.
- Source disappearance does not issue remote delete.
- Required Android tests are implemented where practical.
- Android build/test/lint validation passes, or environment limitations are documented.
- Real backend/device or emulator demo is performed where environment permits.
- Docs are updated.
- This ExecPlan is updated and moved to completed only if criteria are satisfied.

## Final Results

Phase 4 implementation is complete for buildable/testable repository work in this environment.

Implemented:

- Native single-module Android app at `android/app`.
- Kotlin/Compose/Material 3 UI with Home, Media, and Developer Settings surfaces.
- Version-aware media permission mapping for Android 10-12, Android 13, and Android 14+ selected visual access.
- MediaStore image/video scanner using `ContentResolver` and external volume names on API 29+.
- Room database version 1 with metadata-only `media_items` and `backup_states` tables.
- Development server URL and `android-dev-<uuid>` namespace persistence.
- Bounded incremental SHA-256 and ranged `ContentResolver` byte-source reads with descriptor seek and read-discard fallback.
- OkHttp client for `POST /files/check`, `POST /uploads`, `GET /uploads/{id}`, `PUT /uploads/{id}`, and `POST /uploads/{id}/complete`.
- Manual sequential Backup Now workflow using the Phase 3 resumable protocol.
- Source disappearance marks local inventory missing but does not issue any backend deletion request.
- Debug-only cleartext HTTP network security configuration.

Validation passed:

```powershell
cd android
.\gradlew.bat --no-daemon --max-workers=1 clean assembleDebug test lint
```

Non-failing validation warnings:

- Material 3 `TabRow` is deprecated in favor of newer tab row components.
- Debug packaging could not strip `libandroidx.graphics.path.so`, so it was packaged as-is.

Not executed:

- Real Android device/emulator backend integration.
- Real Android interruption/resume demonstration.

Reason: `adb devices` reported no connected devices in this environment.
