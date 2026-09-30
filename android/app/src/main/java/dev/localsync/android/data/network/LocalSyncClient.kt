package dev.localsync.android.data.network

interface LocalSyncClient {
    fun checkFile(baseUrl: String, request: FileCheckRequest): FileCheckResponse

    fun createUpload(baseUrl: String, request: UploadCreateRequest): UploadSessionResponse

    fun getUpload(baseUrl: String, uploadId: String): UploadSessionResponse

    fun appendChunk(
        baseUrl: String,
        uploadId: String,
        offset: Long,
        length: Long,
        body: MediaRangeRequestBody,
    ): UploadSessionResponse

    fun completeUpload(baseUrl: String, uploadId: String): UploadSessionResponse

    fun completePairing(baseUrl: String, request: PairingCompleteRequest): PairingCompleteResponse
}
