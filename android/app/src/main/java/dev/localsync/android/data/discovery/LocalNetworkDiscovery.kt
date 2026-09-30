package dev.localsync.android.data.discovery

const val DEFAULT_DISCOVERY_TIMEOUT_MS = 15_000L

interface LocalNetworkDiscovery {
    suspend fun discover(timeoutMillis: Long = DEFAULT_DISCOVERY_TIMEOUT_MS): List<DiscoveredServer>
}
