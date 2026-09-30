package dev.localsync.android.core.model

data class MediaWithBackupState(
    val item: MediaItem,
    val status: BackupStatus,
    val sha256: String?,
    val lastError: String?,
)
