package dev.localsync.android.data.database

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import dev.localsync.android.core.model.MediaItem
import dev.localsync.android.core.model.MediaKind

@Entity(
    tableName = "media_items",
    indices = [Index(value = ["volumeName", "mediaStoreId"], unique = true)],
)
data class MediaItemEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val mediaStoreId: Long,
    val volumeName: String,
    val contentUri: String,
    val displayName: String,
    val size: Long,
    val mimeType: String?,
    val mediaType: String,
    val dateAdded: Long?,
    val dateModified: Long?,
    val dateTaken: Long?,
    val lastSeenAt: Long,
    val isMissing: Boolean,
) {
    fun toMediaItem(): MediaItem = MediaItem(
        mediaStoreId = mediaStoreId,
        volumeName = volumeName,
        contentUri = contentUri,
        displayName = displayName,
        size = size,
        mimeType = mimeType,
        mediaKind = MediaKind.valueOf(mediaType),
        dateAdded = dateAdded,
        dateModified = dateModified,
        dateTaken = dateTaken,
    )
}

fun MediaItem.toEntity(now: Long, isMissing: Boolean = false): MediaItemEntity = MediaItemEntity(
    mediaStoreId = mediaStoreId,
    volumeName = volumeName,
    contentUri = contentUri,
    displayName = displayName,
    size = size,
    mimeType = mimeType,
    mediaType = mediaKind.name,
    dateAdded = dateAdded,
    dateModified = dateModified,
    dateTaken = dateTaken,
    lastSeenAt = now,
    isMissing = isMissing,
)
