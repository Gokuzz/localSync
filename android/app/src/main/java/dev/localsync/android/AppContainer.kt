package dev.localsync.android

import android.content.Context
import androidx.room.Room
import dev.localsync.android.data.database.LocalSyncDatabase
import dev.localsync.android.data.discovery.AndroidLocalNetworkDiscovery
import dev.localsync.android.data.discovery.PinnedServerIdentityProbe
import dev.localsync.android.data.discovery.TrustedServerDiscovery
import dev.localsync.android.data.media.AndroidMediaByteSource
import dev.localsync.android.data.media.MediaStoreScanner
import dev.localsync.android.data.network.AuthenticatedLocalSyncClient
import dev.localsync.android.data.network.LocalSyncPairingClient
import dev.localsync.android.data.repository.BackupRepository
import dev.localsync.android.data.security.AndroidCredentialStore
import dev.localsync.android.data.settings.SettingsStore

class AppContainer(context: Context) {
    private val applicationContext = context.applicationContext

    val database: LocalSyncDatabase = Room.databaseBuilder(
        applicationContext,
        LocalSyncDatabase::class.java,
        "localsync-android.db",
    ).build()

    val settingsStore = SettingsStore(applicationContext)
    val credentialStore = AndroidCredentialStore(applicationContext)
    val mediaScanner = MediaStoreScanner(applicationContext)
    val mediaByteSource = AndroidMediaByteSource(applicationContext.contentResolver)
    val protocolClient = AuthenticatedLocalSyncClient(credentialStore)
    val pairingClient = LocalSyncPairingClient()
    val localNetworkDiscovery = AndroidLocalNetworkDiscovery(applicationContext)
    val trustedServerDiscovery = TrustedServerDiscovery(
        localNetworkDiscovery,
        credentialStore,
        PinnedServerIdentityProbe(),
    )

    val backupRepository = BackupRepository(
        mediaScanner = mediaScanner,
        mediaDao = database.mediaDao(),
        backupStateDao = database.backupStateDao(),
        settingsStore = settingsStore,
        credentialStore = credentialStore,
        byteSource = mediaByteSource,
        protocolClient = protocolClient,
        pairingClient = pairingClient,
        trustedServerDiscovery = trustedServerDiscovery,
    )
}
