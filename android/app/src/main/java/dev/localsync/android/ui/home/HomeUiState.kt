package dev.localsync.android.ui.home

import dev.localsync.android.core.model.BackupStatus
import dev.localsync.android.core.model.MediaAccessState
import dev.localsync.android.core.model.MediaWithBackupState

data class HomeUiState(
    val accessState: MediaAccessState = MediaAccessState.UNKNOWN,
    val media: List<MediaWithBackupState> = emptyList(),
    val serverUrl: String = "",
    val deviceId: String = "",
    val pairedDeviceId: String? = null,
    val pairedServerFingerprint: String? = null,
    val pairedServerDisplayName: String? = null,
    val observedServerFingerprint: String? = null,
    val isObservingServer: Boolean = false,
    val fingerprintConfirmed: Boolean = false,
    val isLoading: Boolean = false,
    val isBackingUp: Boolean = false,
    val isPairing: Boolean = false,
    val isFindingLaptop: Boolean = false,
    val discoveryStatus: String? = null,
    val message: String? = null,
) {
    val accessibleCount: Int = media.size
    val backedUpCount: Int = media.count { it.status == BackupStatus.BACKED_UP }
    val failedCount: Int = media.count {
        it.status in setOf(
            BackupStatus.FAILED,
            BackupStatus.AUTH_REQUIRED,
            BackupStatus.REVOKED,
            BackupStatus.SERVER_IDENTITY_CHANGED,
        )
    }
    val pendingCount: Int = media.count { it.status != BackupStatus.BACKED_UP }
    val isPaired: Boolean = pairedDeviceId != null
}
