package dev.localsync.android.data.network

import dev.localsync.android.data.media.MediaRange
import okhttp3.MediaType
import okhttp3.RequestBody
import okio.BufferedSink

class MediaRangeRequestBody(
    private val rangeFactory: () -> MediaRange,
    private val byteCount: Long,
) : RequestBody() {
    override fun contentType(): MediaType? = null

    override fun contentLength(): Long = byteCount

    override fun writeTo(sink: BufferedSink) {
        rangeFactory().use { range ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            var remaining = range.length
            while (remaining > 0) {
                val read = range.inputStream.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
                if (read == -1) error("Media source ended before request body completed")
                sink.write(buffer, 0, read)
                remaining -= read
            }
        }
    }
}
