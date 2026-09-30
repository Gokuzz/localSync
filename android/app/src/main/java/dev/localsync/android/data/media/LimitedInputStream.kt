package dev.localsync.android.data.media

import java.io.FilterInputStream
import java.io.InputStream

class LimitedInputStream(
    input: InputStream,
    private var remaining: Long,
) : FilterInputStream(input) {
    override fun read(): Int {
        if (remaining <= 0) return -1
        val value = super.read()
        if (value != -1) remaining--
        return value
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (remaining <= 0) return -1
        val allowed = minOf(length.toLong(), remaining).toInt()
        val read = super.read(buffer, offset, allowed)
        if (read > 0) remaining -= read
        return read
    }
}
