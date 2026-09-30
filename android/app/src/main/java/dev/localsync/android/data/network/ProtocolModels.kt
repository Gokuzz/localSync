package dev.localsync.android.data.network

data class FileCheckRequest(
    val filename: String,
    val size: Long,
    val sha256: String,
    val contentType: String?,
)

data class FileCheckResponse(
    val exists: Boolean,
    val storedFileId: String?,
    val storedPath: String?,
)

data class UploadCreateRequest(
    val filename: String,
    val expectedSize: Long,
    val expectedSha256: String,
    val contentType: String?,
)

data class UploadSessionResponse(
    val status: String,
    val uploadId: String?,
    val nextOffset: Long?,
    val expectedSize: Long?,
    val chunkSizeHint: Long?,
    val storedFileId: String?,
    val storedPath: String?,
)

data class ProtocolError(
    val code: String,
    val message: String,
    val expectedOffset: Long? = null,
    val nextOffset: Long? = null,
)

class ProtocolException(
    val statusCode: Int,
    val protocolError: ProtocolError,
) : Exception(protocolError.message)

data class PairingCompleteRequest(
    val pairingId: String,
    val pairingCode: String,
    val displayName: String,
    val platform: String,
    val clientInstanceId: String,
)

data class PairingCompleteResponse(
    val deviceId: String,
    val deviceCredential: String,
    val serverFingerprint: String,
    val serverDisplayName: String,
)
