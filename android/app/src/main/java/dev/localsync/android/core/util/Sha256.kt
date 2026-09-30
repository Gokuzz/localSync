package dev.localsync.android.core.util

import java.security.MessageDigest

class Sha256 {
    private val digest = MessageDigest.getInstance("SHA-256")

    fun update(buffer: ByteArray, byteCount: Int) {
        digest.update(buffer, 0, byteCount)
    }

    fun finish(): String = digest.digest().joinToString("") { "%02x".format(it) }
}
