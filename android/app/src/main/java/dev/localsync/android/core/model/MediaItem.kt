package dev.localsync.android.core.model

data class MediaItem(
    val mediaStoreId: Long,
    val volumeName: String,
    val contentUri: String,
    val displayName: String,
    val size: Long,
    val mimeType: String?,
    val mediaKind: MediaKind,
    val dateAdded: Long?,
    val dateModified: Long?,
    val dateTaken: Long?,
)
