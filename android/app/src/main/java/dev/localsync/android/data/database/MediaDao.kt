package dev.localsync.android.data.database

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction

@Dao
interface MediaDao {
    @Query("SELECT * FROM media_items WHERE isMissing = 0 ORDER BY dateTaken DESC, dateModified DESC")
    suspend fun listVisible(): List<MediaItemEntity>

    @Query("SELECT * FROM media_items WHERE volumeName = :volumeName AND mediaStoreId = :mediaStoreId")
    suspend fun findBySource(volumeName: String, mediaStoreId: Long): MediaItemEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(entity: MediaItemEntity): Long

    @Query(
        """
        UPDATE media_items
        SET contentUri = :contentUri,
            displayName = :displayName,
            size = :size,
            mimeType = :mimeType,
            mediaType = :mediaType,
            dateAdded = :dateAdded,
            dateModified = :dateModified,
            dateTaken = :dateTaken,
            lastSeenAt = :lastSeenAt,
            isMissing = 0
        WHERE id = :id
        """,
    )
    suspend fun updateSeen(
        id: Long,
        contentUri: String,
        displayName: String,
        size: Long,
        mimeType: String?,
        mediaType: String,
        dateAdded: Long?,
        dateModified: Long?,
        dateTaken: Long?,
        lastSeenAt: Long,
    )

    @Query("UPDATE media_items SET isMissing = 1 WHERE lastSeenAt < :scanStartedAt")
    suspend fun markMissingBefore(scanStartedAt: Long)

    @Transaction
    suspend fun upsertSeen(entity: MediaItemEntity): Long {
        val existing = findBySource(entity.volumeName, entity.mediaStoreId)
        return if (existing == null) {
            insert(entity)
        } else {
            updateSeen(
                id = existing.id,
                contentUri = entity.contentUri,
                displayName = entity.displayName,
                size = entity.size,
                mimeType = entity.mimeType,
                mediaType = entity.mediaType,
                dateAdded = entity.dateAdded,
                dateModified = entity.dateModified,
                dateTaken = entity.dateTaken,
                lastSeenAt = entity.lastSeenAt,
            )
            existing.id
        }
    }
}
