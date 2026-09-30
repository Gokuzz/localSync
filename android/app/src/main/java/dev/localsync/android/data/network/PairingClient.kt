package dev.localsync.android.data.network

interface PairingClient {
    fun observeServerIdentity(serverUrl: String): ObservedServerIdentity

    fun completePairing(
        serverUrl: String,
        expectedFingerprint: String,
        request: PairingCompleteRequest,
    ): PairingCompleteResponse
}

class LocalSyncPairingClient(
    private val observer: ServerIdentityObserver = TlsServerIdentityObserver(),
) : PairingClient {
    override fun observeServerIdentity(serverUrl: String): ObservedServerIdentity =
        observer.observe(serverUrl)

    override fun completePairing(
        serverUrl: String,
        expectedFingerprint: String,
        request: PairingCompleteRequest,
    ): PairingCompleteResponse {
        val locator = parseServerLocator(serverUrl)
        val httpClient = pinnedLocalSyncHttpClient(locator, expectedFingerprint)
        return LocalSyncProtocolClient(httpClient).completePairing(locator.logicalBaseUrl, request)
    }
}
