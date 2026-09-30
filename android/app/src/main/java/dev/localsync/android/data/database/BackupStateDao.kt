package dev.localsync.android.data.database

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface BackupStateDao {
    @Query("SELECT * FROM backup_states WHERE mediaItemId = :mediaItemId")
    suspend fun findForMedia(mediaItemId: Long): BackupStateEntity?

    @Query("SELECT * FROM backup_states")
    suspend fun listAll(): List<BackupStateEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: BackupStateEntity): Long
}
