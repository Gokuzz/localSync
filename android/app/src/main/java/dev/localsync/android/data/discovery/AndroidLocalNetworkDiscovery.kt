package dev.localsync.android.data.discovery

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap

class AndroidLocalNetworkDiscovery(
    context: Context,
    private val lockPolicy: () -> Boolean = ::currentDiscoveryMulticastLockPolicy,
) : LocalNetworkDiscovery {
    private companion object {
        const val TAG = "LocalSyncDiscovery"
    }

    private val applicationContext = context.applicationContext

    override suspend fun discover(timeoutMillis: Long): List<DiscoveredServer> = withContext(Dispatchers.IO) {
        val manager = applicationContext.getSystemService(NsdManager::class.java)
            ?: return@withContext emptyList()
        val candidates = ConcurrentHashMap<String, DiscoveredServer>()
        val multicastLock = acquireMulticastLockIfNeeded()
        var started = false
        lateinit var discoveryListener: NsdManager.DiscoveryListener
        val resolveListener = object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.w(TAG, "Service resolution failed: ${serviceInfo.serviceName} code=$errorCode")
            }

            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                toDiscoveredServer(serviceInfo)?.let { candidate ->
                    candidates[candidateKey(candidate)] = candidate
                    Log.d(TAG, "Resolved candidate ${candidate.instanceName} at ${candidate.host}:${candidate.port}")
                }
            }
        }
        discoveryListener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {
                Log.d(TAG, "Discovery started for $serviceType")
            }

            override fun onDiscoveryStopped(serviceType: String) {
                Log.d(TAG, "Discovery stopped for $serviceType")
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w(TAG, "Discovery start failed: $serviceType code=$errorCode")
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w(TAG, "Discovery stop failed: $serviceType code=$errorCode")
            }
            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                candidates.entries.removeIf { (_, candidate) -> candidate.instanceName == serviceInfo.serviceName }
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                Log.d(TAG, "Service found: ${serviceInfo.serviceName} type=${serviceInfo.serviceType}")
                if (normalizeServiceType(serviceInfo.serviceType) == normalizeServiceType(LOCALSYNC_NSD_SERVICE_TYPE)) {
                    manager.resolveService(serviceInfo, resolveListener)
                }
            }
        }
        try {
            manager.discoverServices(
                LOCALSYNC_NSD_SERVICE_TYPE,
                NsdManager.PROTOCOL_DNS_SD,
                discoveryListener,
            )
            started = true
            Log.d(TAG, "Discovery request submitted")
            delay(timeoutMillis)
            candidates.values.toList().also { Log.d(TAG, "Discovery completed with ${it.size} candidate(s)") }
        } finally {
            if (started) {
                runCatching { manager.stopServiceDiscovery(discoveryListener) }
            }
            Log.d(TAG, "Discovery resources released")
            multicastLock?.let { lock ->
                if (lock.isHeld) lock.release()
            }
        }
    }

    private fun acquireMulticastLockIfNeeded(): WifiManager.MulticastLock? {
        if (!lockPolicy()) return null
        val wifiManager = applicationContext.getSystemService(WifiManager::class.java) ?: return null
        return wifiManager.createMulticastLock("localSync-discovery").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun toDiscoveredServer(serviceInfo: NsdServiceInfo): DiscoveredServer? {
        val host = serviceInfo.host?.hostAddress ?: return null
        val attributes = serviceInfo.attributes.mapValues { (_, value) ->
            String(value, StandardCharsets.UTF_8)
        }
        return DiscoveredServer(
            instanceName = serviceInfo.serviceName,
            serviceType = serviceInfo.serviceType,
            host = host,
            port = serviceInfo.port,
            protocolVersion = attributes["protocol"]?.toIntOrNull(),
            tlsRequired = attributes["tls"] == "required",
            logicalHost = attributes["host"],
            advertisedSpkiFingerprint = attributes["spki"],
            lastSeenAt = System.currentTimeMillis(),
        )
    }

    private fun candidateKey(candidate: DiscoveredServer): String =
        "${candidate.instanceName}|${candidate.host}|${candidate.port}"
}
