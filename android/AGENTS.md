# Android Agent Instructions

This directory is for the future Android client. Keep Android implementation details here and keep protocol/domain language platform-neutral.

## Expected Stack

- Kotlin.
- Jetpack Compose for UI.
- MediaStore for photo/video discovery.
- Room for local metadata and queue state.
- WorkManager for durable background backup work.
- OkHttp for local-network API calls.
- Android Network Service Discovery / mDNS for discovery.
- Storage Access Framework for manually selected files.
- Android Keystore for protecting secrets.

## Boundaries

- Compose UI should not own backup business rules.
- MediaStore code discovers automatic photo/video candidates only.
- Arbitrary documents and files must require explicit user selection in V1.
- Room stores local state and metadata, not media bytes.
- WorkManager jobs should be idempotent and resumable.
- Network code should use generic protocol concepts such as Device, UploadSession, MediaItem, Transfer, and Backup.

## Media and Permissions

- Do not re-encode, resize, recompress, transcode, strip metadata, or modify media.
- Avoid unrestricted filesystem permissions unless genuinely required and documented.
- Handle Android permissions explicitly and degrade predictably when permission is denied.
- Background execution must respect Android platform limits and user expectations.
