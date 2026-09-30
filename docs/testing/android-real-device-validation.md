# Android Real-Device Validation

This checkpoint validates the Android app against the real localSync desktop backend.

Phase 4 real-device photo backup has been completed. Phase 5 pairing/authentication and required real-device validation have been completed.

Use a test device/profile or Android 14+ selected-media access. The current Phase 4 `Backup Now` action processes all visible MediaStore items, so do not run it with full access on a phone containing personal media you do not intend to copy.

## Validation Record

Status as of 2026-08-22:

- Real Android phone to laptop backend validation was performed.
- Photo backup from Android to the laptop completed successfully.
- Completed files appeared under the configured backend backup root.
- A configuration defect was discovered: Alembic used the hardcoded `alembic.ini` database URL instead of the app's `LOCALSYNC_DATA_ROOT` / `LOCALSYNC_DATABASE_URL` settings. That defect has been corrected.
- Phase 5 real-device pairing was later performed successfully on a real Android phone:
  - Android connected to the localSync HTTPS backend.
  - The pairing ID/code flow was exercised.
  - Android displayed/used the observed server fingerprint.
  - The observed fingerprint was manually verified against the laptop CLI fingerprint before pairing confirmation.
  - Pairing completed successfully.
  - Android became paired with the laptop.
- Phase 5 server-side revocation enforcement was later performed successfully on a real Android phone:
  - The paired Android device was revoked from the backend.
  - The backend rejected the revoked Android credential with `401 Unauthorized` on repeated `POST /api/v1/files/check` requests.
  - This confirms backend revoked-device enforcement.
  - Android initially retried `/files/check` repeatedly across remaining media instead of stopping; that client retry-policy defect was fixed after the manual test.
- The rebuilt Android client was then manually validated on a real Android phone:
  - Android stopped the current Backup Now run after the first revoked-auth failure and did not continue checking remaining media.
  - Old completed backup files remained after revocation.
  - The phone was paired again successfully.
  - The new pairing received a new server-generated device ID.
  - Authenticated Backup Now after re-pair succeeded.
  - Because `/files/check` is scoped by authenticated device ID, the newly paired device did not recognize backups belonging to the revoked prior device ID and uploaded the same content into the new namespace.
- The remaining Phase 5 real-device checks were later completed:
  - Unauthenticated protected requests were rejected.
  - Wrong bearer credentials were rejected.
  - Android rejected an unexpected TLS/server identity.
  - The same trusted server identity worked after the locator/IP changed.
  - Real Android interrupted upload resumed from a nonzero server offset and completed successfully.
  - Final source/destination SHA-256 values matched.

Current safe limitation: revoking device A and pairing the same physical phone again creates device B. Existing backups remain associated with device A. Device B does not automatically inherit or claim device A's `StoredFile` namespace, so the same media may currently upload again after revoke/re-pair. Phase 5 intentionally does not merge device namespaces, reuse revoked device IDs, associate devices using filename, associate devices using Android local instance ID alone, let a new paired device claim another device's backups, or introduce cross-device deduplication. A future design may separate authenticated paired-device identity, source/library identity, and stored content identity, or add an explicit laptop-admin-approved credential rotation/re-authorization flow.

## Phase 5 Pairing Validation Addendum

For Phase 5, run the backend over HTTPS with the generated identity and create a pairing session:

```powershell
cd desktop/backend
.\.venv\Scripts\Activate.ps1
$env:LOCALSYNC_DATA_ROOT = "data-real-device"
python -m alembic upgrade head
python -m app.cli pairing create --server-url https://<laptop-lan-ip>:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile data-real-device\security\server-cert.pem --ssl-keyfile data-real-device\security\server-key.pem
```

On Android:

1. Enter the HTTPS server locator URL, pairing ID, pairing code, and laptop fingerprint shown by the CLI.
2. Tap `Observe server fingerprint`.
3. Confirm the observed `spki-sha256:` fingerprint exactly matches the laptop CLI output.
4. Tap `I verified this fingerprint`.
5. Tap `Pair with laptop`.

The app must not send the pairing code before the fingerprint is observed and explicitly confirmed. Backup Now should be enabled only after credentials are stored.

Required Phase 5 checks before marking this complete:

- real Android device pairing succeeds after fingerprint observation and manual confirmation; confirmed
- unauthenticated transfer request is rejected; confirmed
- wrong bearer credential is rejected; confirmed
- paired Android backup succeeds over HTTPS; confirmed after re-pair
- pairing code is sent only after Android displays and confirms the observed SPKI fingerprint; confirmed by manual flow
- revoking the Android device with `python -m app.cli devices revoke <device-id>` causes the backend to reject subsequent backup attempts; confirmed
- Android stops the backup run after the first revoked/authentication failure and does not continue checking remaining media; confirmed after rebuild
- completed backup data remains after revocation; confirmed
- re-pairing allows backup again; confirmed
- an unexpected server identity is rejected rather than silently trusted; confirmed

For quick local validation, a revoked paired device can be reactivated without re-pairing:

```powershell
python -m app.cli devices activate <device-id>
```

This clears `revoked_at` for that same paired device credential and namespace. It is not a namespace merge and does not make a newly paired device claim backups that belong to an older revoked device ID.

Phase 5 real-device security validation has been performed. Do not infer Phase 6 discovery, automatic backup, or production internet security from this result.

## Phase 6 Local-Network Discovery Validation

Phase 6 adds foreground DNS-SD discovery only for locating an already-paired laptop. It does not replace Phase 5 pairing, change the trusted SPKI pin, or start a backup.

Prerequisites:

1. The Android phone is already paired with the laptop and has a working pinned HTTPS locator.
2. The backend is installed with `zeroconf` and is started with the same HTTPS port that is configured as `LOCALSYNC_SERVER_PORT`.
3. The phone and laptop are on the same non-isolated private LAN.
4. Windows permits UDP 5353 and the configured HTTPS TCP port on the Private profile only as needed.

Run the backend from `desktop/backend` with the persistent Phase 5 identity:

```powershell
$env:LOCALSYNC_SERVER_PORT = "8000"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile data\security\server-cert.pem --ssl-keyfile data\security\server-key.pem
```

In the Android app, open Home and tap `Find Laptop`. Expected behavior:

- the paired laptop is found through `_localsync._tcp.`;
- its resolved port is the configured HTTPS port;
- Android performs a public pinned-TLS preflight before accepting the locator;
- the Developer Settings server URL changes only after the existing SPKI pin verifies;
- `Backup Now` remains a separate explicit action.

Change the laptop locator/IP while keeping the same persistent `server-key.pem` and `server-cert.pem`, restart the backend on the new reachable address, and tap `Find Laptop` again. The phone should reconnect without pairing. A service with a matching TXT `spki` hint but a different certificate must be rejected; the stored pin and old trusted state must remain unchanged. Stop the backend and confirm the app reports the trusted laptop unavailable while retaining pairing. Restore the backend and confirm discovery works again.

If mDNS is blocked, leave the manual HTTPS locator in Developer Settings and verify that the normal Phase 5 pinned path still works. Do not treat discovery failure as data loss or as permission to disable TLS verification.

Current validation observation: the backend registered `_localsync._tcp.` successfully, and a local Zeroconf browser observed `DESKTOP-0EIT515 localSync` on the laptop. The Android phone remained on the same `192.168.1.x` network and could ping the laptop, but Android `NsdManager` received zero candidates. This indicates that the current network path is allowing unicast traffic while filtering mDNS multicast between clients. Same-LAN discovery is therefore not marked complete; repeat on a network that permits client mDNS or retain the manual locator fallback.

## Prerequisites

- Windows laptop on a trusted private Wi-Fi/LAN.
- Android device or emulator on the same network.
- Android SDK platform tools available through `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `E:\andr`.
- Python backend dependencies installed:

```powershell
cd desktop/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

- Android app builds:

```powershell
cd android
.\gradlew.bat assembleDebug
```

## Start The Backend

For a physical Android device, bind Uvicorn to the LAN interface:

```powershell
cd desktop/backend
.\.venv\Scripts\Activate.ps1
$env:LOCALSYNC_DATA_ROOT = "data-real-device"
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Alembic and FastAPI both resolve the database URL through the same application configuration. Keep `LOCALSYNC_DATA_ROOT` or `LOCALSYNC_DATABASE_URL` set in the same shell for migration and server startup.

Expected health URL:

```text
http://<laptop-lan-ip>:8000/api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

The validation data root is:

```text
desktop/backend/data-real-device/
    .localsync-temp/
    backups/
    localsync.db
```

## Find The Laptop LAN IP

In another PowerShell window:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.254*" } |
    Select-Object InterfaceAlias, IPAddress
```

Use the IPv4 address for the active Wi-Fi/Ethernet adapter, for example:

```text
http://192.168.1.20:8000
```

Do not use `127.0.0.1` from a physical Android device. For the Android emulator, use:

```text
http://10.0.2.2:8000
```

## Firewall And Port 8000

Keep this narrow:

- Use a trusted Private network profile.
- Allow inbound TCP port `8000` only for this development backend if Windows prompts.
- Do not disable Windows Firewall globally.
- Remove the temporary firewall rule after validation if you created one manually.

Optional administrator-scoped rule:

```powershell
New-NetFirewallRule `
    -DisplayName "localSync dev backend 8000" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8000 `
    -Profile Private
```

Remove it later with:

```powershell
Remove-NetFirewallRule -DisplayName "localSync dev backend 8000"
```

## Build And Install The Debug App

Set an `adb` helper in PowerShell:

```powershell
$adb = if ($env:ANDROID_HOME) {
    Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
} elseif ($env:ANDROID_SDK_ROOT) {
    Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe"
} else {
    "E:\andr\platform-tools\adb.exe"
}
```

Build and install:

```powershell
cd android
.\gradlew.bat assembleDebug
& $adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Launch from the Android launcher as `localSync`.

## Connect With USB Debugging

1. Enable Developer options on the Android device.
2. Enable USB debugging.
3. Connect USB and accept the device authorization prompt.
4. Verify:

```powershell
& $adb devices
```

The device should show as `device`, not `unauthorized`.

## Connect With Wireless Debugging

On Android 11+:

1. Enable Developer options.
2. Open Wireless debugging.
3. Choose Pair device with pairing code.
4. Pair:

```powershell
& $adb pair <device-ip>:<pairing-port>
```

5. Connect:

```powershell
& $adb connect <device-ip>:<debug-port>
& $adb devices
```

Use the exact ports shown by Android. Pairing port and debug port are usually different.

## Configure localSync On Android

1. Open `localSync`.
2. Open the `Developer` tab.
3. For Phase 4 fallback validation, set `Server URL` to:

```text
http://<laptop-lan-ip>:8000
```

4. For Phase 5 validation, use the Pairing section with the backend CLI pairing ID, code, and fingerprint.
5. Tap `Observe server fingerprint`, compare the observed value with the laptop CLI value, then tap `I verified this fingerprint`.
6. Tap `Pair with laptop`.

The local Android installation ID is advisory metadata. It is not authentication.

Legacy Phase 4 builds exposed a development namespace such as:

```text
android-dev-real-device-1
```

5. Tap `Save` if editing the server locator.

## Create Safe Test Media

Create generated, non-personal media on the device:

```powershell
& $adb shell mkdir -p /sdcard/Pictures/localSyncValidation
& $adb shell mkdir -p /sdcard/Movies/localSyncValidation
& $adb shell screencap -p /sdcard/Pictures/localSyncValidation/ls-image-a.png
& $adb shell screenrecord --time-limit 3 /sdcard/Movies/localSyncValidation/ls-video-a.mp4
& $adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/localSyncValidation/ls-image-a.png
& $adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Movies/localSyncValidation/ls-video-a.mp4
```

If `screenrecord` is unavailable, use a short non-personal test video created on the device. Do not use important personal media.

## Grant Full Media Access

1. Open the `Home` tab.
2. Tap `Allow access`.
3. On Android 13+, allow photos and videos.
4. On Android 14+, choose full access for the full-access validation case.
5. Tap `Refresh`.

Expected Home state:

- `Photos & videos`
- A nonzero accessible count.

Expected Media tab:

- Generated image/video filenames appear.
- Initial status is `NOT_BACKED_UP`, unless they were already backed up.

## Basic Backup Now Test

1. Keep the backend running.
2. In the Android app, open `Home`.
3. Tap `Backup Now`.
4. Wait for the button to stop showing `Backing up`.

Expected UI:

- Home message: `Backup finished`.
- Media tab shows generated items as `BACKED_UP`.

Expected backend logs may include:

- `upload chunk accepted`
- `upload session completed`

Do not expect credential values in logs; Authorization and pairing secrets must remain unlogged.

## Find The Laptop Backup File

List completed files:

```powershell
cd desktop/backend
Get-ChildItem .\data-real-device\backups -Recurse -File |
    Select-Object FullName, Length
```

Expected path shape:

```text
desktop/backend/data-real-device/backups/<device-namespace>/<safe-original-name>_<first-12-sha256-hex>.<ext>
```

Example:

```text
data-real-device/backups/android-dev-real-device-1/ls-image-a_0123456789ab.png
```

Completed files must not appear under `.localsync-temp`.

## Verify Source And Destination SHA-256

Pull the source file back from Android for comparison:

```powershell
New-Item -ItemType Directory -Force .\validation-pulled | Out-Null
& $adb pull /sdcard/Pictures/localSyncValidation/ls-image-a.png .\validation-pulled\ls-image-a.png
```

Hash source and destination:

```powershell
$sourceHash = (Get-FileHash .\validation-pulled\ls-image-a.png -Algorithm SHA256).Hash
$dest = Get-ChildItem .\data-real-device\backups -Recurse -File |
    Where-Object { $_.Name -like "ls-image-a_*.png" } |
    Select-Object -First 1
$destHash = (Get-FileHash $dest.FullName -Algorithm SHA256).Hash
$sourceHash
$destHash
$sourceHash -eq $destHash
```

Expected result:

```text
True
```

Repeat for `ls-video-a.mp4` if generated.

## Already-Backed-Up Second Run

1. Count completed files:

```powershell
$before = (Get-ChildItem .\data-real-device\backups -Recurse -File).Count
```

2. In Android, tap `Backup Now` again.
3. Count again:

```powershell
$after = (Get-ChildItem .\data-real-device\backups -Recurse -File).Count
$before
$after
```

Expected:

- Counts are equal.
- UI finishes successfully.
- Existing backup hashes still match.

## Same-Name Different-Content Test

Create another generated image with the same display filename in a different device directory:

```powershell
& $adb shell mkdir -p /sdcard/Pictures/localSyncValidationCollision
& $adb shell screencap -p /sdcard/Pictures/localSyncValidationCollision/ls-image-a.png
& $adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/localSyncValidationCollision/ls-image-a.png
```

If the two screenshots are identical, change the device screen contents and run `screencap` again.

In Android:

1. Tap `Refresh`.
2. Confirm both `ls-image-a.png` entries appear in `Media`, or at least the new one appears.
3. Tap `Backup Now`.

Expected laptop result:

- The original backup remains unchanged.
- A different-content same-name file is stored at another non-overwriting path, usually with a different hash suffix.

Check:

```powershell
Get-ChildItem .\data-real-device\backups -Recurse -File |
    Where-Object { $_.Name -like "ls-image-a_*.png" } |
    Select-Object Name, Length, FullName
```

## Interrupted Transfer And Resume Test

Use a generated video large enough to require multiple chunks. Android uses an 8 MiB target chunk and the backend max chunk size defaults to 16 MiB.

Create a longer screen recording if needed:

```powershell
& $adb shell screenrecord --time-limit 30 /sdcard/Movies/localSyncValidation/ls-video-resume.mp4
& $adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Movies/localSyncValidation/ls-video-resume.mp4
```

Run:

1. Tap `Refresh`.
2. Tap `Backup Now`.
3. While upload is in progress, stop the backend with `Ctrl+C`.
4. Confirm Android eventually shows a failed state or stops backing up.
5. Restart the backend with the same `LOCALSYNC_DATA_ROOT`:

```powershell
cd desktop/backend
.\.venv\Scripts\Activate.ps1
$env:LOCALSYNC_DATA_ROOT = "data-real-device"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

6. Tap `Backup Now` again.

Expected:

- Backend recovers the existing upload session.
- Transfer resumes from a nonzero offset if at least one chunk was accepted.
- No partial file appears under `backups`.
- Final source/destination SHA-256 matches.

Useful inspection while interrupted:

```powershell
Get-ChildItem .\data-real-device\.localsync-temp -File | Select-Object Name, Length
```

## Source-Deletion Safety Test

After a successful backup:

```powershell
& $adb shell rm /sdcard/Pictures/localSyncValidation/ls-image-a.png
& $adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/localSyncValidation/ls-image-a.png
```

Then in Android:

1. Tap `Refresh`.
2. Tap `Backup Now`.

Expected:

- The source item may disappear from the Media list or stop being visible.
- No backend delete request exists.
- The laptop backup file still exists.

Verify:

```powershell
Get-ChildItem .\data-real-device\backups -Recurse -File |
    Where-Object { $_.Name -like "ls-image-a_*.png" }
```

The file must still be present.

## Android 14+ Partial-Access Test

On Android 14+:

1. Open app settings for localSync and revoke photo/video access, or tap `Manage access` from the app.
2. Choose selected photos/videos only.
3. Select only the generated validation media.
4. Return to localSync and tap `Refresh`.

Expected:

- Home shows `Limited photo access`.
- The detail text says only the selected accessible subset can be backed up.
- The app must not claim all phone media is protected.
- `Backup Now` backs up only visible selected media.

## Failure Troubleshooting

- Health URL fails from laptop:
  - Confirm backend is running.
  - Confirm `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` is used.
  - Confirm `python -m alembic upgrade head` ran with the same `LOCALSYNC_DATA_ROOT`.
- Health URL works on laptop but not Android:
  - Use laptop LAN IP, not `127.0.0.1`.
  - Confirm phone and laptop are on the same network.
  - Check Windows Firewall private-profile inbound rule for TCP 8000.
- Android install fails:
  - Confirm `adb devices` shows `device`.
  - Re-run `.\gradlew.bat assembleDebug`.
  - Use `adb install -r`.
- Media not visible:
  - Run the media scan broadcast commands.
  - Reopen localSync and tap `Refresh`.
  - Check permission state: full or selected access is required.
- Backup fails immediately:
  - Confirm Developer tab Server URL is `http://<laptop-lan-ip>:8000`.
  - Confirm debug APK is installed; release cleartext HTTP is not configured for production.
  - Confirm backend logs show incoming requests.
- Hash mismatch:
  - Do not edit or replace the source media during upload.
  - Recreate generated test media and retry.
- Resume does not show nonzero offset:
  - The interruption may have occurred before the first chunk was accepted.
  - Use a larger video and interrupt after backend logs `upload chunk accepted`.

## Pass/Fail Checklist

- [ ] Backend health endpoint returns `{"status":"ok"}` from the Android-reachable URL.
- [ ] Debug APK installs and opens.
- [ ] Server URL is configured as `https://<laptop-lan-ip>:8000` or emulator `https://10.0.2.2:8000`.
- [x] Phase 5 real-device pairing succeeds after Android displays the observed fingerprint and the user verifies it against the laptop fingerprint.
- [x] Phase 5 pairing credentials are present before Backup Now.
- [x] Backend returns `401 Unauthorized` for the revoked Android credential.
- [x] Android rebuilt with the retry-policy fix stops after the first revoked/authentication failure instead of repeatedly calling `/files/check`.
- [x] Completed backup files remain after revocation.
- [x] Re-pair after revocation succeeds and receives a new server-generated device ID.
- [x] Authenticated Backup Now after re-pair succeeds.
- [x] Unauthenticated protected request is rejected.
- [x] Wrong bearer credential is rejected.
- [x] Android rejects an unexpected TLS/server identity.
- [x] Same trusted server identity works after locator/IP changes.
- [x] Real Android interrupted upload resumes from a nonzero server offset and completes.
- [ ] Generated image/video media appears in MediaStore through localSync.
- [ ] Full-access validation shows `Photos & videos`.
- [ ] Android 14+ partial-access validation shows `Limited photo access` when selected access is used.
- [ ] `Backup Now` completes with `Backup finished`.
- [ ] Generated media status becomes `BACKED_UP`.
- [ ] Completed files appear under `data-real-device/backups/<device-namespace>/`.
- [ ] No completed backup appears under `.localsync-temp`.
- [x] Source and destination SHA-256 match.
- [ ] Second `Backup Now` does not create duplicate files for identical content.
- [ ] Same-name different-content media does not overwrite the first backup.
- [x] Interrupted transfer can be retried and complete with matching SHA-256.
- [ ] Deleting source media does not delete the laptop backup.
- [ ] No personal media was used unless explicitly intended for this development test.
