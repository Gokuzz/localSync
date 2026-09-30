package dev.localsync.android.data.network

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class LocalSyncProtocolClient(private val httpClient: OkHttpClient) : LocalSyncClient {
    override fun checkFile(baseUrl: String, request: FileCheckRequest): FileCheckResponse {
        val response = executeJsonPost(
                "$baseUrl/api/v1/files/check",
                JSONObject()
                .put("filename", request.filename)
                .put("size", request.size)
                .put("sha256", request.sha256)
                .putNullable("content_type", request.contentType),
        )
        return FileCheckResponse(
            exists = response.getBoolean("exists"),
            storedFileId = response.optStringOrNull("stored_file_id"),
            storedPath = response.optStringOrNull("stored_path"),
        )
    }

    override fun createUpload(baseUrl: String, request: UploadCreateRequest): UploadSessionResponse {
        val response = executeJsonPost(
                "$baseUrl/api/v1/uploads",
                JSONObject()
                .put("filename", request.filename)
                .put("expected_size", request.expectedSize)
                .put("expected_sha256", request.expectedSha256)
                .putNullable("content_type", request.contentType),
        )
        return response.toUploadSessionResponse()
    }

    override fun getUpload(baseUrl: String, uploadId: String): UploadSessionResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/uploads/$uploadId")
            .get()
            .build()
        return execute(request).toUploadSessionResponse()
    }

    override fun appendChunk(
        baseUrl: String,
        uploadId: String,
        offset: Long,
        length: Long,
        body: MediaRangeRequestBody,
    ): UploadSessionResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/uploads/$uploadId")
            .header("X-localSync-Offset", offset.toString())
            .header("Content-Length", length.toString())
            .put(body)
            .build()
        return execute(request).toUploadSessionResponse()
    }

    override fun completeUpload(baseUrl: String, uploadId: String): UploadSessionResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/uploads/$uploadId/complete")
            .post(ByteArray(0).toRequestBody(null, 0, 0))
            .build()
        return execute(request).toUploadSessionResponse()
    }

    override fun completePairing(
        baseUrl: String,
        request: PairingCompleteRequest,
    ): PairingCompleteResponse {
        val response = executeJsonPost(
            "$baseUrl/api/v1/pairing-sessions/${request.pairingId}/complete",
            JSONObject()
                .put("pairing_code", request.pairingCode)
                .put("display_name", request.displayName)
                .put("platform", request.platform)
                .put("client_instance_id", request.clientInstanceId),
        )
        return PairingCompleteResponse(
            deviceId = response.getString("device_id"),
            deviceCredential = response.getString("device_credential"),
            serverFingerprint = response.getString("server_fingerprint"),
            serverDisplayName = response.getString("server_display_name"),
        )
    }

    private fun executeJsonPost(url: String, payload: JSONObject): JSONObject {
        val request = Request.Builder()
            .url(url)
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        return execute(request)
    }

    private fun execute(request: Request): JSONObject {
        httpClient.newCall(request).execute().use { response ->
            val body = response.body.string()
            val json = if (body.isBlank()) JSONObject() else JSONObject(body)
            if (!response.isSuccessful) {
                throw ProtocolException(response.code, json.toProtocolError())
            }
            return json
        }
    }

    private fun JSONObject.toUploadSessionResponse(): UploadSessionResponse = UploadSessionResponse(
        status = getString("status"),
        uploadId = optStringOrNull("upload_id"),
        nextOffset = optLongOrNull("next_offset"),
        expectedSize = optLongOrNull("expected_size"),
        chunkSizeHint = optLongOrNull("chunk_size_hint"),
        storedFileId = optStringOrNull("stored_file_id"),
        storedPath = optStringOrNull("stored_path"),
    )

    private fun JSONObject.toProtocolError(): ProtocolError {
        val error = optJSONObject("error") ?: JSONObject()
        val details = error.optJSONObject("details")
        return ProtocolError(
            code = error.optString("code", "http_error"),
            message = error.optString("message", "HTTP request failed"),
            expectedOffset = details?.optLongOrNull("expected_offset"),
            nextOffset = details?.optLongOrNull("next_offset"),
        )
    }

    private fun JSONObject.putNullable(name: String, value: String?): JSONObject {
        if (value == null) {
            put(name, JSONObject.NULL)
        } else {
            put(name, value)
        }
        return this
    }

    private fun JSONObject.optStringOrNull(name: String): String? =
        if (isNull(name)) null else optString(name)

    private fun JSONObject.optLongOrNull(name: String): Long? =
        if (isNull(name) || !has(name)) null else optLong(name)

    private companion object {
        val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}
