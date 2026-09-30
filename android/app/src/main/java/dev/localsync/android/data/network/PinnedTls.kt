package dev.localsync.android.data.network

import okhttp3.Dns
import okhttp3.OkHttpClient
import java.net.InetAddress
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

class ServerIdentityMismatchException(message: String) : Exception(message)

class LocatorDns(
    private val logicalHost: String,
    private val locatorHost: String,
) : Dns {
    override fun lookup(hostname: String): List<InetAddress> =
        if (hostname.equals(logicalHost, ignoreCase = true)) {
            InetAddress.getAllByName(locatorHost).toList()
        } else {
            Dns.SYSTEM.lookup(hostname)
        }
}

class SpkiPinTrustManager(private val expectedFingerprint: String) : X509TrustManager {
    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = Unit

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val certificate = chain?.firstOrNull()
            ?: throw CertificateException("Server did not present a certificate.")
        val actual = serverSpkiFingerprint(certificate)
        if (actual != expectedFingerprint) {
            throw CertificateException("Server identity changed.")
        }
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

fun pinnedLocalSyncHttpClient(
    locator: ServerLocator,
    expectedFingerprint: String,
    authorizationCredential: String? = null,
): OkHttpClient {
    val trustManager = SpkiPinTrustManager(expectedFingerprint)
    val sslContext = SSLContext.getInstance("TLS")
    sslContext.init(null, arrayOf(trustManager), SecureRandom())
    val builder = OkHttpClient.Builder()
        .dns(LocatorDns(locator.logicalHost, locator.locatorUrl.host))
        .sslSocketFactory(sslContext.socketFactory, trustManager)
    if (!authorizationCredential.isNullOrBlank()) {
        builder.addInterceptor(AuthInterceptor { authorizationCredential })
    }
    return builder.build()
}
