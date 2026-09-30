package dev.localsync.android.data.discovery

import dev.localsync.android.data.network.LOCALSYNC_LOGICAL_HOST

// NsdManager expects the browse type without the DNS-SD trailing dot.
// The backend advertises the equivalent wire type `_localsync._tcp.`.
const val LOCALSYNC_NSD_SERVICE_TYPE = "_localsync._tcp"
const val SUPPORTED_DISCOVERY_PROTOCOL = 1

data class DiscoveredServer(
    val instanceName: String,
    val serviceType: String,
    val host: String,
    val port: Int,
    val protocolVersion: Int?,
    val tlsRequired: Boolean,
    val logicalHost: String?,
    val advertisedSpkiFingerprint: String?,
    val lastSeenAt: Long,
) {
    val locatorUrl: String
        get() {
            val formattedHost = if (host.contains(":")) {
                "[${host.replace("%", "%25")}]"
            } else {
                host
            }
            return "https://$formattedHost:$port"
        }

    fun isSupported(): Boolean =
        normalizeServiceType(serviceType) == normalizeServiceType(LOCALSYNC_NSD_SERVICE_TYPE) &&
            protocolVersion == SUPPORTED_DISCOVERY_PROTOCOL &&
            tlsRequired &&
            logicalHost == LOCALSYNC_LOGICAL_HOST
}

fun normalizeServiceType(value: String): String = value
    .trimEnd('.')
    .removeSuffix(".local")
