package dev.localsync.android.data.network

import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SNIHostName
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLParameters
import javax.net.ssl.SSLSocket
import javax.net.ssl.X509TrustManager

data class ObservedServerIdentity(
    val locatorUrl: String,
    val logicalHost: String,
    val fingerprint: String,
)

interface ServerIdentityObserver {
    fun observe(serverUrl: String): ObservedServerIdentity
}

class TlsServerIdentityObserver : ServerIdentityObserver {
    override fun observe(serverUrl: String): ObservedServerIdentity {
        val locator = parseServerLocator(serverUrl)
        val trustManager = ObservingTrustManager()
        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, arrayOf(trustManager), SecureRandom())
        sslContext.socketFactory.createSocket(locator.locatorUrl.host, locator.locatorUrl.port).use { socket ->
            val sslSocket = socket as SSLSocket
            sslSocket.sslParameters = SSLParameters().apply {
                serverNames = listOf(SNIHostName(locator.logicalHost))
            }
            sslSocket.startHandshake()
            val certificate = sslSocket.session.peerCertificates
                .filterIsInstance<X509Certificate>()
                .firstOrNull()
                ?: trustManager.observedCertificate
                ?: error("Server did not present an X.509 certificate.")
            return ObservedServerIdentity(
                locatorUrl = locator.normalizedLocatorUrl,
                logicalHost = locator.logicalHost,
                fingerprint = serverSpkiFingerprint(certificate),
            )
        }
    }
}

private class ObservingTrustManager : X509TrustManager {
    var observedCertificate: X509Certificate? = null
        private set

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = Unit

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        observedCertificate = chain?.firstOrNull()
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}
