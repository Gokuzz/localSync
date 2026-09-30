package dev.localsync.android.data.network

import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream

class ProtocolClientTest {
    @Test
    fun parsesFileCheckResponse() {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(
                MockResponse.Builder()
                    .body("""{"exists":true,"stored_file_id":"s1","stored_path":"p"}""")
                    .build(),
            )
            val client = LocalSyncProtocolClient(okhttp3.OkHttpClient())

            val response = client.checkFile(
                server.url("/").toString().trimEnd('/'),
                FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"),
            )

            assertEquals(true, response.exists)
            assertEquals("s1", response.storedFileId)
            assertEquals("POST /api/v1/files/check HTTP/1.1", server.takeRequest().requestLine)
        }
    }

    @Test
    fun sendsAuthorizationHeaderWhenInterceptorHasCredential() {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(MockResponse.Builder().body("""{"exists":false}""").build())
            val client = LocalSyncProtocolClient(
                okhttp3.OkHttpClient.Builder()
                    .addInterceptor(AuthInterceptor { "secret" })
                    .build(),
            )

            client.checkFile(
                server.url("/").toString().trimEnd('/'),
                FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"),
            )

            assertEquals("Bearer secret", server.takeRequest().headers["Authorization"])
        }
    }

    @Test
    fun parsesPairingCompletionResponse() {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(
                MockResponse.Builder()
                    .body(
                        """
                        {
                          "device_id":"device-1",
                          "device_credential":"secret",
                          "server_fingerprint":"spki-sha256:test",
                          "server_display_name":"localSync laptop"
                        }
                        """.trimIndent(),
                    )
                    .build(),
            )
            val client = LocalSyncProtocolClient(okhttp3.OkHttpClient())

            val response = client.completePairing(
                server.url("/").toString().trimEnd('/'),
                PairingCompleteRequest("pairing-1", "ABCD-EFGH-JKMP", "Android", "android", "id"),
            )

            assertEquals("device-1", response.deviceId)
            assertEquals("secret", response.deviceCredential)
            assertTrue(
                server.takeRequest().requestLine
                    .startsWith("POST /api/v1/pairing-sessions/pairing-1/complete HTTP/"),
            )
        }
    }

    @Test
    fun parsesOffsetMismatchDetails() {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(
                MockResponse.Builder()
                    .code(409)
                    .body(
                        """
                        {
                          "error": {
                            "code": "offset_mismatch",
                            "message": "mismatch",
                            "details": {"expected_offset": 16}
                          }
                        }
                        """.trimIndent(),
                    )
                    .build(),
            )
            val client = LocalSyncProtocolClient(okhttp3.OkHttpClient())

            val exception = assertThrows(ProtocolException::class.java) {
                client.appendChunk(
                    server.url("/").toString().trimEnd('/'),
                    "upload-1",
                    8,
                    3,
                    MediaRangeRequestBody(
                        rangeFactory = {
                            dev.localsync.android.data.media.MediaRange(
                                ByteArrayInputStream("abc".toByteArray()),
                                3,
                            )
                        },
                        byteCount = 3,
                    ),
                )
            }

            assertEquals("offset_mismatch", exception.protocolError.code)
            assertEquals(16L, exception.protocolError.expectedOffset)
        }
    }

    @Test
    fun pairingCompletionUsesPinnedServerIdentity() {
        val serverIdentity = tlsIdentity()
        httpsServer(serverIdentity).use { server ->
            server.enqueue(
                MockResponse.Builder()
                    .body(
                        """
                        {
                          "device_id":"device-1",
                          "device_credential":"secret",
                          "server_fingerprint":"${serverIdentity.fingerprint}",
                          "server_display_name":"localSync laptop"
                        }
                        """.trimIndent(),
                    )
                    .build(),
            )
            val client = LocalSyncPairingClient()

            val response = client.completePairing(
                server.url("/").toString().trimEnd('/'),
                serverIdentity.fingerprint,
                PairingCompleteRequest("pairing-1", "ABCD-EFGH-JKMP", "Android", "android", "id"),
            )

            assertEquals("device-1", response.deviceId)
            assertTrue(
                server.takeRequest().requestLine
                    .startsWith("POST /api/v1/pairing-sessions/pairing-1/complete HTTP/"),
            )
        }
    }

    @Test
    fun pairingCompletionDoesNotSendCodeWhenPinChanges() {
        val expectedIdentity = tlsIdentity()
        val presentedIdentity = tlsIdentity()
        httpsServer(presentedIdentity).use { server ->
            val client = LocalSyncPairingClient()

            assertThrows(Exception::class.java) {
                client.completePairing(
                    server.url("/").toString().trimEnd('/'),
                    expectedIdentity.fingerprint,
                    PairingCompleteRequest("pairing-1", "ABCD-EFGH-JKMP", "Android", "android", "id"),
                )
            }

            assertEquals(0, server.requestCount)
        }
    }

    @Test
    fun authenticatedClientAttachesBearerOnlyOnPinnedHttps() {
        val identity = tlsIdentity()
        httpsServer(identity).use { server ->
            server.enqueue(MockResponse.Builder().body("""{"exists":false}""").build())
            val client = AuthenticatedLocalSyncClient(
                dev.localsync.android.data.security.InMemoryCredentialStore(
                    dev.localsync.android.data.security.PairedCredentials(
                        serverLocatorUrl = server.url("/").toString().trimEnd('/'),
                        serverLogicalHost = LOCALSYNC_LOGICAL_HOST,
                        serverFingerprint = identity.fingerprint,
                        serverDisplayName = "localSync laptop",
                        deviceId = "device-1",
                        deviceCredential = "secret",
                    ),
                ),
            )

            client.checkFile(
                "ignored",
                FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"),
            )

            assertEquals("Bearer secret", server.takeRequest().headers["Authorization"])
        }
    }

    @Test
    fun authenticatedClientRejectsHttpBeforeSendingBearer() {
        MockWebServer().use { server ->
            server.start()
            val client = AuthenticatedLocalSyncClient(
                dev.localsync.android.data.security.InMemoryCredentialStore(
                    dev.localsync.android.data.security.PairedCredentials(
                        serverLocatorUrl = server.url("/").toString().trimEnd('/'),
                        serverLogicalHost = LOCALSYNC_LOGICAL_HOST,
                        serverFingerprint = "spki-sha256:test",
                        serverDisplayName = "localSync laptop",
                        deviceId = "device-1",
                        deviceCredential = "secret",
                    ),
                ),
            )

            assertThrows(IllegalArgumentException::class.java) {
                client.checkFile("ignored", FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"))
            }

            assertEquals(0, server.requestCount)
        }
    }

    @Test
    fun authenticatedClientRejectsUnexpectedServerIdentity() {
        val expectedIdentity = tlsIdentity()
        val presentedIdentity = tlsIdentity()
        httpsServer(presentedIdentity).use { server ->
            val client = AuthenticatedLocalSyncClient(
                dev.localsync.android.data.security.InMemoryCredentialStore(
                    dev.localsync.android.data.security.PairedCredentials(
                        serverLocatorUrl = server.url("/").toString().trimEnd('/'),
                        serverLogicalHost = LOCALSYNC_LOGICAL_HOST,
                        serverFingerprint = expectedIdentity.fingerprint,
                        serverDisplayName = "localSync laptop",
                        deviceId = "device-1",
                        deviceCredential = "secret",
                    ),
                ),
            )

            assertThrows(Exception::class.java) {
                client.checkFile("ignored", FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"))
            }

            assertEquals(0, server.requestCount)
        }
    }

    @Test
    fun authenticatedClientAcceptsSameIdentityAtDifferentLocator() {
        val identity = tlsIdentity()
        httpsServer(identity).use { firstServer ->
            firstServer.enqueue(MockResponse.Builder().body("""{"exists":false}""").build())
            val firstClient = authenticatedClient(firstServer, identity)
            firstClient.checkFile("ignored", FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"))
            assertEquals("Bearer secret", firstServer.takeRequest().headers["Authorization"])
        }
        httpsServer(identity).use { secondServer ->
            secondServer.enqueue(MockResponse.Builder().body("""{"exists":false}""").build())
            val secondClient = authenticatedClient(secondServer, identity)
            secondClient.checkFile("ignored", FileCheckRequest("a.jpg", 3, "a".repeat(64), "image/jpeg"))
            assertEquals("Bearer secret", secondServer.takeRequest().headers["Authorization"])
        }
    }

    private fun authenticatedClient(
        server: MockWebServer,
        identity: TestTlsIdentity,
    ): AuthenticatedLocalSyncClient = AuthenticatedLocalSyncClient(
        dev.localsync.android.data.security.InMemoryCredentialStore(
            dev.localsync.android.data.security.PairedCredentials(
                serverLocatorUrl = server.url("/").toString().trimEnd('/'),
                serverLogicalHost = LOCALSYNC_LOGICAL_HOST,
                serverFingerprint = identity.fingerprint,
                serverDisplayName = "localSync laptop",
                deviceId = "device-1",
                deviceCredential = "secret",
            ),
        ),
    )

    private fun httpsServer(identity: TestTlsIdentity): MockWebServer {
        val server = MockWebServer()
        server.useHttps(identity.serverCertificates.sslSocketFactory())
        server.start()
        return server
    }

    private fun tlsIdentity(): TestTlsIdentity {
        val heldCertificate = HeldCertificate.Builder()
            .commonName(LOCALSYNC_LOGICAL_HOST)
            .addSubjectAlternativeName(LOCALSYNC_LOGICAL_HOST)
            .build()
        val serverCertificates = HandshakeCertificates.Builder()
            .heldCertificate(heldCertificate)
            .build()
        return TestTlsIdentity(
            serverCertificates = serverCertificates,
            fingerprint = serverSpkiFingerprint(heldCertificate.certificate),
        )
    }

    private data class TestTlsIdentity(
        val serverCertificates: HandshakeCertificates,
        val fingerprint: String,
    )
}
