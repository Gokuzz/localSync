package dev.localsync.android.data.database

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import dev.localsync.android.core.model.BackupStatus

@Entity(
    tableName = "backup_states",
    foreignKeys = [
        ForeignKey(
            entity = MediaItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["mediaItemId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index(value = ["mediaItemId"], unique = true)],
)
data class BackupStateEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val mediaItemId: Long,
    val contentSha256: String?,
    val hashedSize: Long?,
    val status: String,
    val storedFileId: String?,
    val storedPath: String?,
    val lastAttemptAt: Long?,
    val lastSuccessfulBackupAt: Long?,
    val failureCode: String?,
    val failureMessage: String?,
) {
    val backupStatus: BackupStatus
        get() = BackupStatus.valueOf(status)
}
