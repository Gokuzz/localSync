package dev.localsync.android.data.media

import android.content.ContentResolver
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.FileInputStream
import java.io.InputStream

class AndroidMediaByteSource(
    private val contentResolver: ContentResolver,
) : MediaByteSource {
    override suspend fun sha256(contentUri: String): String = withContext(Dispatchers.IO) {
        val uri = Uri.parse(contentUri)
        val stream = contentResolver.openInputStream(uri)
            ?: throw IllegalStateException("Unable to open media source")
        hashStream(stream)
    }

    override suspend fun openRange(contentUri: String, offset: Long, length: Long): MediaRange =
        withContext(Dispatchers.IO) {
            val uri = Uri.parse(contentUri)
            require(offset >= 0) { "offset must be non-negative" }
            require(length >= 0) { "length must be non-negative" }
            val descriptor = contentResolver.openFileDescriptor(uri, "r")
            if (descriptor != null) {
                try {
                    val stream = FileInputStream(descriptor.fileDescriptor)
                    val channel = stream.channel
                    channel.position(offset)
                    return@withContext MediaRange(
                        inputStream = LimitedInputStream(stream, length),
                        length = length,
                        onClose = { descriptor.close() },
                    )
                } catch (_: Exception) {
                    descriptor.close()
                }
            }

            val stream = contentResolver.openInputStream(uri)
                ?: throw IllegalStateException("Unable to open media source")
            skipExactly(stream, offset)
            MediaRange(LimitedInputStream(stream, length), length)
        }

    private fun skipExactly(stream: InputStream, bytesToSkip: Long) {
        var remaining = bytesToSkip
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (remaining > 0) {
            val read = stream.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
            if (read == -1) {
                throw IllegalStateException("Media source ended before requested offset")
            }
            remaining -= read
        }
    }
}
