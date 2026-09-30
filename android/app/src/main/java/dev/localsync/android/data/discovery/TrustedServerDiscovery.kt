package dev.localsync.android.data.discovery

import dev.localsync.android.data.network.ServerLocator
import dev.localsync.android.data.network.pinnedLocalSyncHttpClient
import dev.localsync.android.data.network.parseServerLocator
import dev.localsync.android.data.security.CredentialStore
import dev.localsync.android.data.security.PairedCredentials
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.IOException
import javax.net.ssl.SSLPeerUnverifiedException
import javax.net.ssl.SSLHandshakeException

sealed interface TrustedDiscoveryResult {
    data class Verified(val locatorUrl: String) : TrustedDiscoveryResult
    data class IdentityMismatch(val locatorUrl: String) : TrustedDiscoveryResult
    data object NotPaired : TrustedDiscoveryResult
    data object NotFound : TrustedDiscoveryResult
}

sealed interface ServerIdentityProbeResult {
    data object Verified : ServerIdentityProbeResult
    data object IdentityMismatch : ServerIdentityProbeResult
    data object Unavailable : ServerIdentityProbeResult
}

fun interface ServerIdentityProbe {
    suspend fun verify(locator: ServerLocator, expectedFingerprint: String): ServerIdentityProbeResult
}

class PinnedServerIdentityProbe : ServerIdentityProbe {
    override suspend fun verify(
        locator: ServerLocator,
        expectedFingerprint: String,
    ): ServerIdentityProbeResult = withContext(Dispatchers.IO) {
        try {
            val client = pinnedLocalSyncHttpClient(locator, expectedFingerprint)
            val request = Request.Builder()
                .url("${locator.logicalBaseUrl}/api/v1/health")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) ServerIdentityProbeResult.Verified
                else ServerIdentityProbeResult.Unavailable
            }
        } catch (_: SSLPeerUnverifiedException) {
            ServerIdentityProbeResult.IdentityMismatch
        } catch (_: SSLHandshakeException) {
            ServerIdentityProbeResult.IdentityMismatch
        } catch (_: IOException) {
            ServerIdentityProbeResult.Unavailable
        }
    }
}

class TrustedServerDiscovery(
    private val discovery: LocalNetworkDiscovery,
    private val credentialStore: CredentialStore,
    private val identityProbe: ServerIdentityProbe,
) {
    suspend fun findTrustedServer(timeoutMillis: Long = DEFAULT_DISCOVERY_TIMEOUT_MS): TrustedDiscoveryResult =
        withContext(Dispatchers.IO) {
            val credentials = credentialStore.load() ?: return@withContext TrustedDiscoveryResult.NotPaired
            var mismatch: TrustedDiscoveryResult.IdentityMismatch? = null
            discovery.discover(timeoutMillis)
                .asSequence()
                .filter(DiscoveredServer::isSupported)
                .filter { candidate ->
                    candidate.advertisedSpkiFingerprint == null ||
                        candidate.advertisedSpkiFingerprint == credentials.serverFingerprint
                }
                .forEach { candidate ->
                    val locator = parseServerLocator(candidate.locatorUrl)
                    when (identityProbe.verify(locator, credentials.serverFingerprint)) {
                        ServerIdentityProbeResult.Verified -> {
                            credentialStore.save(credentials.copy(serverLocatorUrl = locator.normalizedLocatorUrl))
                            return@withContext TrustedDiscoveryResult.Verified(locator.normalizedLocatorUrl)
                        }
                        ServerIdentityProbeResult.IdentityMismatch -> {
                            mismatch = TrustedDiscoveryResult.IdentityMismatch(locator.normalizedLocatorUrl)
                        }
                        ServerIdentityProbeResult.Unavailable -> Unit
                    }
                }
            mismatch ?: TrustedDiscoveryResult.NotFound
        }
}
