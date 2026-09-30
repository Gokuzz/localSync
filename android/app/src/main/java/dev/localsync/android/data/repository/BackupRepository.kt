package dev.localsync.android.data.repository

import dev.localsync.android.core.model.BackupStatus
import dev.localsync.android.core.model.MediaWithBackupState
import dev.localsync.android.data.database.BackupStateDao
import dev.localsync.android.data.database.BackupStateEntity
import dev.localsync.android.data.database.MediaDao
import dev.localsync.android.data.database.toEntity
import dev.localsync.android.data.discovery.DEFAULT_DISCOVERY_TIMEOUT_MS
import dev.localsync.android.data.discovery.TrustedDiscoveryResult
import dev.localsync.android.data.discovery.TrustedServerDiscovery
import dev.localsync.android.data.media.MediaByteSource
import dev.localsync.android.data.media.MediaScanner
import dev.localsync.android.data.network.FileCheckRequest
import dev.localsync.android.data.network.LocalSyncClient
import dev.localsync.android.data.network.MediaRangeRequestBody
import dev.localsync.android.data.network.PairingCompleteRequest
import dev.localsync.android.data.network.PairingClient
import dev.localsync.android.data.network.ProtocolException
import dev.localsync.android.data.network.UploadCreateRequest
import dev.localsync.android.data.network.parseServerLocator
import dev.localsync.android.data.security.CredentialStore
import dev.localsync.android.data.security.PairedCredentials
import dev.localsync.android.data.settings.DevelopmentSettings
import dev.localsync.android.data.settings.SettingsDataSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.net.ssl.SSLException

class BackupRepository(
    private val mediaScanner: MediaScanner,
    private val mediaDao: MediaDao,
    private val backupStateDao: BackupStateDao,
    private val settingsStore: SettingsDataSource,
    private val credentialStore: CredentialStore,
    private val byteSource: MediaByteSource,
    private val protocolClient: LocalSyncClient,
    private val pairingClient: PairingClient,
    private val trustedServerDiscovery: TrustedServerDiscovery? = null,
    private val clock: () -> Long = { System.currentTimeMillis() },
) {
    suspend fun settings(): DevelopmentSettings = withContext(Dispatchers.IO) {
        settingsStore.get()
    }

    suspend fun pairedCredentials(): PairedCredentials? = withContext(Dispatchers.IO) {
        credentialStore.load()
    }

    suspend fun findTrustedLaptop(
        timeoutMillis: Long = DEFAULT_DISCOVERY_TIMEOUT_MS,
    ): TrustedDiscoveryResult = withContext(Dispatchers.IO) {
        trustedServerDiscovery?.findTrustedServer(timeoutMillis)
            ?: TrustedDiscoveryResult.NotPaired
    }

    suspend fun saveSettings(serverUrl: String, deviceId: String) = withContext(Dispatchers.IO) {
        settingsStore.saveServerUrl(serverUrl)
        settingsStore.saveDeviceId(deviceId)
    }

    suspend fun observeServerIdentity(serverUrl: String) = withContext(Dispatchers.IO) {
        pairingClient.observeServerIdentity(serverUrl)
    }

    suspend fun completePairing(
        serverUrl: String,
        pairingId: String,
        pairingCode: String,
        expectedServerFingerprint: String,
        observedServerFingerprint: String,
        fingerprintConfirmed: Boolean,
        displayName: String,
    ): PairedCredentials = withContext(Dispatchers.IO) {
        require(fingerprintConfirmed) {
            "Confirm the server fingerprint before pairing."
        }
        val locator = parseServerLocator(serverUrl)
        val expected = expectedServerFingerprint.trim()
        val observed = observedServerFingerprint.trim()
        require(expected.isNotBlank() && observed == expected) {
            "Observed server fingerprint did not match the laptop."
        }
        val response = pairingClient.completePairing(
            serverUrl,
            expected,
            PairingCompleteRequest(
                pairingId = pairingId,
                pairingCode = pairingCode,
                displayName = displayName,
                platform = "android",
                clientInstanceId = settingsStore.get().deviceId,
            ),
        )
        require(response.serverFingerprint == expected) {
            "Server fingerprint did not match the laptop."
        }
        val credentials = PairedCredentials(
            serverLocatorUrl = locator.normalizedLocatorUrl,
            serverLogicalHost = locator.logicalHost,
            serverFingerprint = response.serverFingerprint,
            serverDisplayName = response.serverDisplayName,
            deviceId = response.deviceId,
            deviceCredential = response.deviceCredential,
        )
        credentialStore.save(credentials)
        credentials
    }

    suspend fun forgetPairing() = withContext(Dispatchers.IO) {
        credentialStore.clear()
    }

    suspend fun refreshInventory(): List<MediaWithBackupState> = withContext(Dispatchers.IO) {
        val scanStartedAt = clock()
        mediaScanner.scan().forEach { item ->
            mediaDao.upsertSeen(item.toEntity(scanStartedAt))
        }
        mediaDao.markMissingBefore(scanStartedAt)
        listMedia()
    }

    suspend fun listMedia(): List<MediaWithBackupState> = withContext(Dispatchers.IO) {
        val states = backupStateDao.listAll().associateBy { it.mediaItemId }
        mediaDao.listVisible().map { entity ->
            val state = states[entity.id]
            MediaWithBackupState(
                item = entity.toMediaItem(),
                status = state?.backupStatus ?: BackupStatus.NOT_BACKED_UP,
                sha256 = state?.contentSha256,
                lastError = state?.failureMessage,
            )
        }
    }

    suspend fun backupNow(onProgress: suspend (MediaWithBackupState?) -> Unit = {}) = withContext(Dispatchers.IO) {
        val settings = settingsStore.get()
        val credentials = credentialStore.load()
            ?: throw IllegalStateException("Pair with a laptop before backing up.")
        val serverUrl = credentials.serverUrl.ifBlank { settings.serverUrl }
        parseServerLocator(serverUrl)
        val media = mediaDao.listVisible()
        for (entity in media) {
            val item = entity.toMediaItem()
            val mediaId = entity.id
            try {
                mark(mediaId, BackupStatus.HASHING)
                val sha256 = byteSource.sha256(item.contentUri)
                val size = item.size

                mark(mediaId, BackupStatus.CHECKING, sha256 = sha256, hashedSize = size)
                val check = protocolClient.checkFile(
                    serverUrl,
                    FileCheckRequest(
                        filename = item.displayName,
                        size = size,
                        sha256 = sha256,
                        contentType = item.mimeType,
                    ),
                )
                if (check.exists) {
                    markBackedUp(mediaId, sha256, size, check.storedFileId, check.storedPath)
                    onProgress(null)
                    continue
                }

                mark(mediaId, BackupStatus.UPLOADING, sha256 = sha256, hashedSize = size)
                val created = protocolClient.createUpload(
                    serverUrl,
                    UploadCreateRequest(
                        filename = item.displayName,
                        expectedSize = size,
                        expectedSha256 = sha256,
                        contentType = item.mimeType,
                    ),
                )
                if (created.status == "already_stored") {
                    markBackedUp(mediaId, sha256, size, created.storedFileId, created.storedPath)
                    onProgress(null)
                    continue
                }

                val uploadId = requireNotNull(created.uploadId)
                var nextOffset = requireNotNull(created.nextOffset)
                val chunkSize = minOf(
                    created.chunkSizeHint ?: DEFAULT_CHUNK_SIZE,
                    DEFAULT_CHUNK_SIZE,
                    MAX_CHUNK_SIZE,
                )
                while (nextOffset < size) {
                    val length = minOf(chunkSize, size - nextOffset)
                    try {
                        val range = byteSource.openRange(item.contentUri, nextOffset, length)
                        val response = protocolClient.appendChunk(
                            serverUrl,
                            uploadId,
                            nextOffset,
                            length,
                            MediaRangeRequestBody(rangeFactory = { range }, byteCount = length),
                        )
                        nextOffset = requireNotNull(response.nextOffset)
                    } catch (exc: ProtocolException) {
                        if (exc.protocolError.code == "offset_mismatch") {
                            nextOffset = exc.protocolError.expectedOffset
                                ?: throw exc
                        } else {
                            throw exc
                        }
                    }
                }

                val completed = protocolClient.completeUpload(serverUrl, uploadId)
                if (completed.status == "completed") {
                    markBackedUp(mediaId, sha256, size, completed.storedFileId, completed.storedPath)
                } else {
                    markFailed(mediaId, "completion_unexpected", "Unexpected completion status")
                }
                onProgress(null)
            } catch (exc: Exception) {
                val nonRetryable = classifyNonRetryable(exc)
                if (nonRetryable != null) {
                    markFailed(mediaId, nonRetryable.status, nonRetryable.code, nonRetryable.message)
                    onProgress(null)
                    throw BackupRunStoppedException(nonRetryable.message, exc)
                }
                markFailed(mediaId, exc::class.simpleName ?: "backup_failed", exc.message ?: "Backup failed")
                onProgress(null)
            }
        }
    }

    private suspend fun mark(
        mediaItemId: Long,
        status: BackupStatus,
        sha256: String? = null,
        hashedSize: Long? = null,
    ) {
        val existing = backupStateDao.findForMedia(mediaItemId)
        backupStateDao.upsert(
            BackupStateEntity(
                id = existing?.id ?: 0,
                mediaItemId = mediaItemId,
                contentSha256 = sha256 ?: existing?.contentSha256,
                hashedSize = hashedSize ?: existing?.hashedSize,
                status = status.name,
                storedFileId = existing?.storedFileId,
                storedPath = existing?.storedPath,
                lastAttemptAt = clock(),
                lastSuccessfulBackupAt = existing?.lastSuccessfulBackupAt,
                failureCode = null,
                failureMessage = null,
            ),
        )
    }

    private suspend fun markBackedUp(
        mediaItemId: Long,
        sha256: String,
        size: Long,
        storedFileId: String?,
        storedPath: String?,
    ) {
        val existing = backupStateDao.findForMedia(mediaItemId)
        backupStateDao.upsert(
            BackupStateEntity(
                id = existing?.id ?: 0,
                mediaItemId = mediaItemId,
                contentSha256 = sha256,
                hashedSize = size,
                status = BackupStatus.BACKED_UP.name,
                storedFileId = storedFileId,
                storedPath = storedPath,
                lastAttemptAt = clock(),
                lastSuccessfulBackupAt = clock(),
                failureCode = null,
                failureMessage = null,
            ),
        )
    }

    private suspend fun markFailed(
        mediaItemId: Long,
        code: String,
        message: String,
    ) = markFailed(mediaItemId, BackupStatus.FAILED, code, message)

    private suspend fun markFailed(
        mediaItemId: Long,
        status: BackupStatus,
        code: String,
        message: String,
    ) {
        val existing = backupStateDao.findForMedia(mediaItemId)
        backupStateDao.upsert(
            BackupStateEntity(
                id = existing?.id ?: 0,
                mediaItemId = mediaItemId,
                contentSha256 = existing?.contentSha256,
                hashedSize = existing?.hashedSize,
                status = status.name,
                storedFileId = existing?.storedFileId,
                storedPath = existing?.storedPath,
                lastAttemptAt = clock(),
                lastSuccessfulBackupAt = existing?.lastSuccessfulBackupAt,
                failureCode = code,
                failureMessage = message,
            ),
        )
    }

    companion object {
        const val DEFAULT_CHUNK_SIZE = 8L * 1024L * 1024L
        const val MAX_CHUNK_SIZE = 16L * 1024L * 1024L
    }
}

private data class NonRetryableBackupFailure(
    val status: BackupStatus,
    val code: String,
    val message: String,
)

private class BackupRunStoppedException(
    message: String,
    cause: Throwable,
) : Exception(message, cause)

private fun classifyNonRetryable(exc: Exception): NonRetryableBackupFailure? {
    if (exc is ProtocolException) {
        if (exc.statusCode == 401) {
            return when (exc.protocolError.code) {
                "device_revoked" -> NonRetryableBackupFailure(
                    BackupStatus.REVOKED,
                    exc.protocolError.code,
                    "This device is no longer authorized for this laptop. Pair again to continue.",
                )

                else -> NonRetryableBackupFailure(
                    BackupStatus.AUTH_REQUIRED,
                    exc.protocolError.code,
                    "Authentication is required. Pair with the laptop again to continue.",
                )
            }
        }
        if (exc.statusCode == 403) {
            return NonRetryableBackupFailure(
                BackupStatus.AUTH_REQUIRED,
                exc.protocolError.code,
                "This device is not authorized to complete the backup.",
            )
        }
    }
    if (exc is SSLException) {
        return NonRetryableBackupFailure(
            BackupStatus.SERVER_IDENTITY_CHANGED,
            "server_identity_changed",
            "Server identity changed. Forget and pair again only if this is your laptop.",
        )
    }
    return null
}
