package dev.localsync.android.data.network

import dev.localsync.android.data.security.CredentialStore

class AuthenticatedLocalSyncClient(
    private val credentialStore: CredentialStore,
) : LocalSyncClient {
    override fun checkFile(baseUrl: String, request: FileCheckRequest): FileCheckResponse =
        withDelegate { client, logicalBaseUrl -> client.checkFile(logicalBaseUrl, request) }

    override fun createUpload(baseUrl: String, request: UploadCreateRequest): UploadSessionResponse =
        withDelegate { client, logicalBaseUrl -> client.createUpload(logicalBaseUrl, request) }

    override fun getUpload(baseUrl: String, uploadId: String): UploadSessionResponse =
        withDelegate { client, logicalBaseUrl -> client.getUpload(logicalBaseUrl, uploadId) }

    override fun appendChunk(
        baseUrl: String,
        uploadId: String,
        offset: Long,
        length: Long,
        body: MediaRangeRequestBody,
    ): UploadSessionResponse =
        withDelegate { client, logicalBaseUrl ->
            client.appendChunk(logicalBaseUrl, uploadId, offset, length, body)
        }

    override fun completeUpload(baseUrl: String, uploadId: String): UploadSessionResponse =
        withDelegate { client, logicalBaseUrl -> client.completeUpload(logicalBaseUrl, uploadId) }

    override fun completePairing(
        baseUrl: String,
        request: PairingCompleteRequest,
    ): PairingCompleteResponse {
        throw UnsupportedOperationException("Pairing must use the pairing client.")
    }

    private fun <T> withDelegate(block: (LocalSyncProtocolClient, String) -> T): T {
        val credentials = credentialStore.load()
            ?: throw IllegalStateException("Pair with a laptop before backing up.")
        val locator = parseServerLocator(credentials.serverLocatorUrl)
        require(credentials.serverLogicalHost == locator.logicalHost) {
            "Unsupported localSync server identity host."
        }
        val httpClient = pinnedLocalSyncHttpClient(
            locator = locator,
            expectedFingerprint = credentials.serverFingerprint,
            authorizationCredential = credentials.deviceCredential,
        )
        return block(LocalSyncProtocolClient(httpClient), locator.logicalBaseUrl)
    }
}
