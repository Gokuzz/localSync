package dev.localsync.android.data.database

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [MediaItemEntity::class, BackupStateEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class LocalSyncDatabase : RoomDatabase() {
    abstract fun mediaDao(): MediaDao
    abstract fun backupStateDao(): BackupStateDao
}
