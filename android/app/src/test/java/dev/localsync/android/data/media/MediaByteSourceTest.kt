package dev.localsync.android.data.media

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.ByteArrayInputStream

class MediaByteSourceTest {
    @Test
    fun hashStreamComputesSha256Incrementally() {
        val hash = hashStream(ByteArrayInputStream("abc".toByteArray()), bufferSize = 2)

        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            hash,
        )
    }

    @Test
    fun limitedInputStreamStopsAtDeclaredLength() {
        val stream = LimitedInputStream(ByteArrayInputStream("abcdef".toByteArray()), 3)
        val buffer = ByteArray(8)

        val read = stream.read(buffer)

        assertEquals(3, read)
        assertArrayEquals("abc".toByteArray(), buffer.copyOf(3))
        assertEquals(-1, stream.read())
    }

    @Test
    fun limitedInputStreamRejectsPrematureEndThroughHashCaller() {
        assertThrows(IllegalStateException::class.java) {
            val body = dev.localsync.android.data.network.MediaRangeRequestBody(
                rangeFactory = { MediaRange(ByteArrayInputStream("ab".toByteArray()), 3) },
                byteCount = 3,
            )
            val sink = okio.Buffer()
            body.writeTo(sink)
        }
    }
}
