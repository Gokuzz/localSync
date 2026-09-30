package dev.localsync.android.data.media

import dev.localsync.android.core.util.Sha256
import java.io.Closeable
import java.io.InputStream

interface MediaByteSource {
    suspend fun sha256(contentUri: String): String
    suspend fun openRange(contentUri: String, offset: Long, length: Long): MediaRange
}

class MediaRange(
    val inputStream: InputStream,
    val length: Long,
    private val onClose: () -> Unit = {},
) : Closeable {
    override fun close() {
        try {
            inputStream.close()
        } finally {
            onClose()
        }
    }
}

fun hashStream(inputStream: InputStream, bufferSize: Int = DEFAULT_BUFFER_SIZE): String {
    inputStream.use { stream ->
        val hasher = Sha256()
        val buffer = ByteArray(bufferSize)
        while (true) {
            val read = stream.read(buffer)
            if (read == -1) break
            if (read > 0) hasher.update(buffer, read)
        }
        return hasher.finish()
    }
}
