package dev.localsync.android.data.network

import java.security.MessageDigest
import java.security.cert.X509Certificate
import java.util.Base64

fun serverSpkiFingerprint(certificate: X509Certificate): String {
    val digest = MessageDigest.getInstance("SHA-256").digest(certificate.publicKey.encoded)
    return "spki-sha256:${Base64.getUrlEncoder().withoutPadding().encodeToString(digest)}"
}
