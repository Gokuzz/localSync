package dev.localsync.android.core.model

enum class BackupStatus {
    NOT_BACKED_UP,
    CHECKING,
    HASHING,
    UPLOADING,
    BACKED_UP,
    FAILED,
    AUTH_REQUIRED,
    REVOKED,
    SERVER_IDENTITY_CHANGED,
}
