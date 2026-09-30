package dev.localsync.android.data.discovery

import dev.localsync.android.data.security.InMemoryCredentialStore
import dev.localsync.android.data.security.PairedCredentials
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TrustedServerDiscoveryTest {
    private val credentials = PairedCredentials(
        serverLocatorUrl = "https://192.168.1.20:8000",
        serverLogicalHost = "localsync.local",
        serverFingerprint = "spki-sha256:pin-a",
        serverDisplayName = "Laptop",
        deviceId = "device-a",
        deviceCredential = "credential",
    )

    @Test
    fun matchingTxtHintStillRequiresPinnedTlsVerification() = runTest {
        val store = InMemoryCredentialStore(credentials)
        val probe = RecordingProbe(ServerIdentityProbeResult.Verified)
        val result = TrustedServerDiscovery(
            FakeDiscovery(listOf(candidate("192.168.1.45", "spki-sha256:pin-a"))),
            store,
            probe,
        ).findTrustedServer()

        assertEquals(TrustedDiscoveryResult.Verified("https://192.168.1.45:8000"), result)
        assertEquals(1, probe.calls)
        assertEquals("https://192.168.1.45:8000", store.load()?.serverLocatorUrl)
        assertEquals("spki-sha256:pin-a", store.load()?.serverFingerprint)
    }

    @Test
    fun wrongTxtHintIsFilteredWithoutTlsOrLocatorMutation() = runTest {
        val store = InMemoryCredentialStore(credentials)
        val probe = RecordingProbe(ServerIdentityProbeResult.Verified)
        val result = TrustedServerDiscovery(
            FakeDiscovery(listOf(candidate("192.168.1.45", "spki-sha256:pin-b"))),
            store,
            probe,
        ).findTrustedServer()

        assertEquals(TrustedDiscoveryResult.NotFound, result)
        assertEquals(0, probe.calls)
        assertEquals(credentials.serverLocatorUrl, store.load()?.serverLocatorUrl)
    }

    @Test
    fun matchingTxtWithWrongPresentedIdentityIsRejected() = runTest {
        val store = InMemoryCredentialStore(credentials)
        val probe = RecordingProbe(ServerIdentityProbeResult.IdentityMismatch)
        val result = TrustedServerDiscovery(
            FakeDiscovery(listOf(candidate("192.168.1.45", "spki-sha256:pin-a"))),
            store,
            probe,
        ).findTrustedServer()

        assertTrue(result is TrustedDiscoveryResult.IdentityMismatch)
        assertEquals(credentials.serverLocatorUrl, store.load()?.serverLocatorUrl)
        assertEquals("spki-sha256:pin-a", store.load()?.serverFingerprint)
    }

    @Test
    fun missingTxtHintStillRequiresAndAcceptsPinnedTls() = runTest {
        val store = InMemoryCredentialStore(credentials)
        val probe = RecordingProbe(ServerIdentityProbeResult.Verified)
        val result = TrustedServerDiscovery(
            FakeDiscovery(listOf(candidate("192.168.1.45", null))),
            store,
            probe,
        ).findTrustedServer()

        assertTrue(result is TrustedDiscoveryResult.Verified)
        assertEquals(1, probe.calls)
    }

    @Test
    fun fullyQualifiedDnsSdServiceTypeIsSupported() {
        assertTrue(
            candidate("192.168.1.45", "spki-sha256:pin-a")
                .copy(serviceType = "_localsync._tcp.local.")
                .isSupported(),
        )
    }

    private fun candidate(host: String, fingerprint: String?): DiscoveredServer = DiscoveredServer(
        instanceName = "Laptop localSync",
        serviceType = LOCALSYNC_NSD_SERVICE_TYPE,
        host = host,
        port = 8000,
        protocolVersion = SUPPORTED_DISCOVERY_PROTOCOL,
        tlsRequired = true,
        logicalHost = "localsync.local",
        advertisedSpkiFingerprint = fingerprint,
        lastSeenAt = 1,
    )

    private class FakeDiscovery(private val candidates: List<DiscoveredServer>) : LocalNetworkDiscovery {
        override suspend fun discover(timeoutMillis: Long): List<DiscoveredServer> = candidates
    }

    private class RecordingProbe(private val result: ServerIdentityProbeResult) : ServerIdentityProbe {
        var calls: Int = 0

        override suspend fun verify(
            locator: dev.localsync.android.data.network.ServerLocator,
            expectedFingerprint: String,
        ): ServerIdentityProbeResult {
            calls += 1
            return result
        }
    }
}
