package dev.localsync.android.data.repository

import dev.localsync.android.core.model.BackupStatus
import dev.localsync.android.core.model.MediaItem
import dev.localsync.android.core.model.MediaKind
import dev.localsync.android.data.database.BackupStateDao
import dev.localsync.android.data.database.BackupStateEntity
import dev.localsync.android.data.database.MediaDao
import dev.localsync.android.data.database.MediaItemEntity
import dev.localsync.android.data.database.toEntity
import dev.localsync.android.data.media.MediaByteSource
import dev.localsync.android.data.media.MediaRange
import dev.localsync.android.data.media.MediaScanner
import dev.localsync.android.data.network.FileCheckRequest
import dev.localsync.android.data.network.FileCheckResponse
import dev.localsync.android.data.network.LocalSyncClient
import dev.localsync.android.data.network.MediaRangeRequestBody
import dev.localsync.android.data.network.ObservedServerIdentity
import dev.localsync.android.data.network.PairingClient
import dev.localsync.android.data.network.ProtocolError
import dev.localsync.android.data.network.ProtocolException
import dev.localsync.android.data.network.PairingCompleteRequest
import dev.localsync.android.data.network.PairingCompleteResponse
import dev.localsync.android.data.network.UploadCreateRequest
import dev.localsync.android.data.network.UploadSessionResponse
import dev.localsync.android.data.security.CredentialStore
import dev.localsync.android.data.security.InMemoryCredentialStore
import dev.localsync.android.data.security.PairedCredentials
import dev.localsync.android.data.settings.DevelopmentSettings
import dev.localsync.android.data.settings.SettingsDataSource
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.security.MessageDigest
import javax.net.ssl.SSLHandshakeException

class BackupRepositoryTest {
    @Test
    fun refreshMarksMissingSourceWithoutRemoteRequest() = runTest {
        val scanner = FakeScanner(listOf(sampleItem()))
        val mediaDao = InMemoryMediaDao()
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient()
        val repository = repository(scanner, mediaDao, backupDao, client)

        repository.refreshInventory()
        scanner.items = emptyList()
        repository.refreshInventory()
        repository.backupNow()

        assertEquals(emptyList<MediaItemEntity>(), mediaDao.listVisible())
        assertEquals(0, client.checkRequests.size)
        assertEquals(0, client.uploadRequests.size)
    }

    @Test
    fun alreadyStoredContentIsMarkedBackedUpWithoutUpload() = runTest {
        val item = sampleItem(size = 3)
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(item.toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            checkResponse = FileCheckResponse(true, "stored-1", "device/a.bin")
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        repository.backupNow()

        val state = backupDao.findForMedia(1)
        assertEquals(BackupStatus.BACKED_UP.name, state?.status)
        assertEquals(1, client.checkRequests.size)
        assertEquals(0, client.uploadRequests.size)
        assertEquals(0, client.appendOffsets.size)
    }

    @Test
    fun offsetMismatchUpdatesToAuthoritativeOffsetAndContinues() = runTest {
        val item = sampleItem(size = 6)
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(item.toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            offsetMismatchOnFirstAppend = 3
            appendOffsetsToNextOffset[3] = 6
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abcdef".toByteArray(),
        )

        repository.backupNow()

        assertEquals(listOf(0L, 3L), client.appendOffsets)
        assertEquals(BackupStatus.BACKED_UP.name, backupDao.findForMedia(1)?.status)
    }

    @Test
    fun backupIsNotMarkedSuccessfulBeforeAuthoritativeCompletion() = runTest {
        val item = sampleItem(size = 3)
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(item.toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            completeResponse = UploadSessionResponse("receiving", "upload-1", 3, 3, null, null, null)
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        repository.backupNow()

        val state = backupDao.findForMedia(1)
        assertEquals(BackupStatus.FAILED.name, state?.status)
        assertTrue(state?.failureMessage?.contains("Unexpected completion status") == true)
    }

    @Test
    fun backupRequiresPairedCredential() = runTest {
        val item = sampleItem(size = 3)
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(item.toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient()
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
            credentialStore = InMemoryCredentialStore(),
        )

        val failure = runCatching { repository.backupNow() }.exceptionOrNull()

        assertTrue(failure is IllegalStateException)
        assertTrue(failure?.message?.contains("Pair with a laptop") == true)
        assertEquals(0, client.checkRequests.size)
    }

    @Test
    fun revokedCredentialStopsBackupRunAfterFirstFileCheck() = runTest {
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(sampleItem(size = 3).toEntity(1))
        mediaDao.upsertSeen(sampleItem(size = 3).copy(mediaStoreId = 43, displayName = "second.bin").toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            checkFailures += ProtocolException(
                401,
                ProtocolError("device_revoked", "Device credential is revoked."),
            )
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        val failure = runCatching { repository.backupNow() }.exceptionOrNull()

        assertTrue(failure?.message?.contains("no longer authorized") == true)
        assertEquals(1, client.checkRequests.size)
        assertEquals(BackupStatus.REVOKED.name, backupDao.findForMedia(1)?.status)
        assertEquals(null, backupDao.findForMedia(2))
    }

    @Test
    fun authenticationRequiredStopsBackupRun() = runTest {
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(sampleItem(size = 3).toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            checkFailures += ProtocolException(
                401,
                ProtocolError("authentication_failed", "Device authentication failed."),
            )
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        val failure = runCatching { repository.backupNow() }.exceptionOrNull()

        assertTrue(failure?.message?.contains("Authentication is required") == true)
        assertEquals(1, client.checkRequests.size)
        assertEquals(BackupStatus.AUTH_REQUIRED.name, backupDao.findForMedia(1)?.status)
    }

    @Test
    fun serverIdentityMismatchStopsBackupRun() = runTest {
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(sampleItem(size = 3).toEntity(1))
        mediaDao.upsertSeen(sampleItem(size = 3).copy(mediaStoreId = 43, displayName = "second.bin").toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            checkFailures += SSLHandshakeException("Server identity changed.")
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        val failure = runCatching { repository.backupNow() }.exceptionOrNull()

        assertTrue(failure?.message?.contains("Server identity changed") == true)
        assertEquals(1, client.checkRequests.size)
        assertEquals(BackupStatus.SERVER_IDENTITY_CHANGED.name, backupDao.findForMedia(1)?.status)
        assertEquals(null, backupDao.findForMedia(2))
    }

    @Test
    fun retryableFailureStillAllowsNextMediaItem() = runTest {
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(sampleItem(size = 3).toEntity(1))
        mediaDao.upsertSeen(sampleItem(size = 3).copy(mediaStoreId = 43, displayName = "second.bin").toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val client = FakeClient().apply {
            checkFailures += java.io.IOException("temporary network failure")
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = client,
            bytes = "abc".toByteArray(),
        )

        repository.backupNow()

        assertEquals(2, client.checkRequests.size)
        assertEquals(BackupStatus.FAILED.name, backupDao.findForMedia(1)?.status)
        assertEquals(BackupStatus.BACKED_UP.name, backupDao.findForMedia(2)?.status)
    }

    @Test
    fun successfulRepairingOverwritesRevokedState() = runTest {
        val mediaDao = InMemoryMediaDao()
        mediaDao.upsertSeen(sampleItem(size = 3).toEntity(1))
        val backupDao = InMemoryBackupStateDao()
        val credentialStore = InMemoryCredentialStore()
        val revokedClient = FakeClient().apply {
            checkFailures += ProtocolException(
                401,
                ProtocolError("device_revoked", "Device credential is revoked."),
            )
        }
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = revokedClient,
            bytes = "abc".toByteArray(),
        )

        runCatching { repository.backupNow() }
        assertEquals(BackupStatus.REVOKED.name, backupDao.findForMedia(1)?.status)

        val repairedRepository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = mediaDao,
            backupDao = backupDao,
            client = FakeClient(),
            bytes = "abc".toByteArray(),
            credentialStore = credentialStore,
        )
        repairedRepository.completePairing(
            serverUrl = "https://127.0.0.1:8000",
            pairingId = "pairing-1",
            pairingCode = "ABCD-EFGH-JKMP",
            expectedServerFingerprint = "spki-sha256:test",
            observedServerFingerprint = "spki-sha256:test",
            fingerprintConfirmed = true,
            displayName = "Android",
        )
        repairedRepository.backupNow()

        assertEquals(BackupStatus.BACKED_UP.name, backupDao.findForMedia(1)?.status)
    }

    @Test
    fun pairingSavesCredentialAndForgetClearsIt() = runTest {
        val credentialStore = InMemoryCredentialStore()
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = InMemoryMediaDao(),
            backupDao = InMemoryBackupStateDao(),
            client = FakeClient(),
            credentialStore = credentialStore,
        )

        val paired = repository.completePairing(
            serverUrl = "https://localsync.local:8000",
            pairingId = "pairing-1",
            pairingCode = "ABCD-EFGH-JKMP",
            expectedServerFingerprint = "spki-sha256:test",
            observedServerFingerprint = "spki-sha256:test",
            fingerprintConfirmed = true,
            displayName = "Android",
        )

        assertEquals("device-1", paired.deviceId)
        assertEquals("secret", credentialStore.load()?.deviceCredential)

        repository.forgetPairing()

        assertEquals(null, credentialStore.load())
    }

    @Test
    fun pairingCodeIsNotSentBeforeFingerprintConfirmation() = runTest {
        val credentialStore = InMemoryCredentialStore()
        val client = FakeClient()
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = InMemoryMediaDao(),
            backupDao = InMemoryBackupStateDao(),
            client = client,
            credentialStore = credentialStore,
        )

        val failure = runCatching {
            repository.completePairing(
                serverUrl = "https://127.0.0.1:8000",
                pairingId = "pairing-1",
                pairingCode = "ABCD-EFGH-JKMP",
                expectedServerFingerprint = "spki-sha256:test",
                observedServerFingerprint = "spki-sha256:test",
                fingerprintConfirmed = false,
                displayName = "Android",
            )
        }.exceptionOrNull()

        assertTrue(failure is IllegalArgumentException)
        assertEquals(0, client.securePairingRequests)
        assertEquals(null, credentialStore.load())
    }

    @Test
    fun pairingCodeIsNotSentWhenObservedFingerprintDiffers() = runTest {
        val client = FakeClient()
        val repository = repository(
            scanner = FakeScanner(emptyList()),
            mediaDao = InMemoryMediaDao(),
            backupDao = InMemoryBackupStateDao(),
            client = client,
            credentialStore = InMemoryCredentialStore(),
        )

        val failure = runCatching {
            repository.completePairing(
                serverUrl = "https://127.0.0.1:8000",
                pairingId = "pairing-1",
                pairingCode = "ABCD-EFGH-JKMP",
                expectedServerFingerprint = "spki-sha256:pin-a",
                observedServerFingerprint = "spki-sha256:pin-b",
                fingerprintConfirmed = true,
                displayName = "Android",
            )
        }.exceptionOrNull()

        assertTrue(failure is IllegalArgumentException)
        assertEquals(0, client.securePairingRequests)
    }

    private fun repository(
        scanner: FakeScanner,
        mediaDao: InMemoryMediaDao,
        backupDao: InMemoryBackupStateDao,
        client: FakeClient,
        bytes: ByteArray = ByteArray(0),
        credentialStore: CredentialStore = InMemoryCredentialStore(
            PairedCredentials(
                serverLocatorUrl = "https://127.0.0.1:8000",
                serverLogicalHost = "localsync.local",
                serverFingerprint = "spki-sha256:test",
                serverDisplayName = "localSync laptop",
                deviceId = "device-1",
                deviceCredential = "secret",
            ),
        ),
    ) = BackupRepository(
        mediaScanner = scanner,
        mediaDao = mediaDao,
        backupStateDao = backupDao,
        settingsStore = FakeSettings(),
        credentialStore = credentialStore,
        byteSource = FakeByteSource(bytes),
        protocolClient = client,
        pairingClient = client,
        clock = object {
            var now = 0L
            fun next() = ++now
        }::next,
    )

    private fun sampleItem(size: Long = 0): MediaItem = MediaItem(
        mediaStoreId = 42,
        volumeName = "external",
        contentUri = "content://media/external/images/media/42",
        displayName = "sample.bin",
        size = size,
        mimeType = "application/octet-stream",
        mediaKind = MediaKind.IMAGE,
        dateAdded = null,
        dateModified = null,
        dateTaken = null,
    )
}

private class FakeScanner(var items: List<MediaItem>) : MediaScanner {
    override fun scan(): List<MediaItem> = items
}

private class FakeSettings : SettingsDataSource {
    private var settings = DevelopmentSettings("http://127.0.0.1:8000", "android-dev-test")

    override fun get(): DevelopmentSettings = settings

    override fun saveServerUrl(serverUrl: String) {
        settings = settings.copy(serverUrl = serverUrl)
    }

    override fun saveDeviceId(deviceId: String) {
        settings = settings.copy(deviceId = deviceId)
    }
}

private class FakeByteSource(private val bytes: ByteArray) : MediaByteSource {
    override suspend fun sha256(contentUri: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
        return digest.joinToString("") { "%02x".format(it) }
    }

    override suspend fun openRange(contentUri: String, offset: Long, length: Long): MediaRange {
        val slice = bytes.copyOfRange(offset.toInt(), (offset + length).toInt())
        return MediaRange(ByteArrayInputStream(slice), length)
    }
}

private class FakeClient : LocalSyncClient, PairingClient {
    var checkResponse = FileCheckResponse(false, null, null)
    var completeResponse = UploadSessionResponse("completed", "upload-1", 3, 3, null, "stored-1", "device/sample.bin")
    var pairingResponse = PairingCompleteResponse(
        deviceId = "device-1",
        deviceCredential = "secret",
        serverFingerprint = "spki-sha256:test",
        serverDisplayName = "localSync laptop",
    )
    var offsetMismatchOnFirstAppend: Long? = null
    val checkFailures = mutableListOf<Exception>()
    val appendOffsetsToNextOffset = mutableMapOf<Long, Long>()
    val checkRequests = mutableListOf<FileCheckRequest>()
    val uploadRequests = mutableListOf<UploadCreateRequest>()
    val appendOffsets = mutableListOf<Long>()
    var securePairingRequests = 0

    override fun checkFile(baseUrl: String, request: FileCheckRequest): FileCheckResponse {
        checkRequests += request
        if (checkFailures.isNotEmpty()) {
            throw checkFailures.removeAt(0)
        }
        return checkResponse
    }

    override fun createUpload(baseUrl: String, request: UploadCreateRequest): UploadSessionResponse {
        uploadRequests += request
        return UploadSessionResponse("receiving", "upload-1", 0, request.expectedSize, 8, null, null)
    }

    override fun getUpload(baseUrl: String, uploadId: String): UploadSessionResponse =
        UploadSessionResponse("receiving", uploadId, 0, 0, null, null, null)

    override fun appendChunk(
        baseUrl: String,
        uploadId: String,
        offset: Long,
        length: Long,
        body: MediaRangeRequestBody,
    ): UploadSessionResponse {
        appendOffsets += offset
        offsetMismatchOnFirstAppend?.let { expected ->
            offsetMismatchOnFirstAppend = null
            throw ProtocolException(
                409,
                ProtocolError("offset_mismatch", "Offset mismatch", expectedOffset = expected),
            )
        }
        return UploadSessionResponse(
            "receiving",
            uploadId,
            appendOffsetsToNextOffset[offset] ?: (offset + length),
            null,
            null,
            null,
            null,
        )
    }

    override fun completeUpload(baseUrl: String, uploadId: String): UploadSessionResponse = completeResponse

    override fun completePairing(
        baseUrl: String,
        request: PairingCompleteRequest,
    ) = pairingResponse

    override fun observeServerIdentity(serverUrl: String): ObservedServerIdentity =
        ObservedServerIdentity(serverUrl, "localsync.local", "spki-sha256:test")

    override fun completePairing(
        serverUrl: String,
        expectedFingerprint: String,
        request: PairingCompleteRequest,
    ): PairingCompleteResponse {
        securePairingRequests += 1
        check(expectedFingerprint == "spki-sha256:test")
        return pairingResponse
    }
}

private class InMemoryMediaDao : MediaDao {
    private val records = linkedMapOf<Long, MediaItemEntity>()
    private var nextId = 1L

    override suspend fun listVisible(): List<MediaItemEntity> =
        records.values.filterNot { it.isMissing }

    override suspend fun findBySource(volumeName: String, mediaStoreId: Long): MediaItemEntity? =
        records.values.firstOrNull { it.volumeName == volumeName && it.mediaStoreId == mediaStoreId }

    override suspend fun insert(entity: MediaItemEntity): Long {
        val id = nextId++
        records[id] = entity.copy(id = id)
        return id
    }

    override suspend fun updateSeen(
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
    ) {
        val existing = records.getValue(id)
        records[id] = existing.copy(
            contentUri = contentUri,
            displayName = displayName,
            size = size,
            mimeType = mimeType,
            mediaType = mediaType,
            dateAdded = dateAdded,
            dateModified = dateModified,
            dateTaken = dateTaken,
            lastSeenAt = lastSeenAt,
            isMissing = false,
        )
    }

    override suspend fun markMissingBefore(scanStartedAt: Long) {
        records.replaceAll { _, entity ->
            if (entity.lastSeenAt < scanStartedAt) entity.copy(isMissing = true) else entity
        }
    }
}

private class InMemoryBackupStateDao : BackupStateDao {
    private val records = linkedMapOf<Long, BackupStateEntity>()
    private var nextId = 1L

    override suspend fun findForMedia(mediaItemId: Long): BackupStateEntity? =
        records.values.firstOrNull { it.mediaItemId == mediaItemId }

    override suspend fun listAll(): List<BackupStateEntity> = records.values.toList()

    override suspend fun upsert(entity: BackupStateEntity): Long {
        val id = if (entity.id == 0L) {
            findForMedia(entity.mediaItemId)?.id ?: nextId++
        } else {
            entity.id
        }
        records[id] = entity.copy(id = id)
        return id
    }
}
