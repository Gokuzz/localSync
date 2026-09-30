package dev.localsync.android.data.security

data class PairedCredentials(
    val serverLocatorUrl: String,
    val serverLogicalHost: String,
    val serverFingerprint: String,
    val serverDisplayName: String,
    val deviceId: String,
    val deviceCredential: String,
) {
    val serverUrl: String
        get() = serverLocatorUrl
}

interface CredentialStore {
    fun load(): PairedCredentials?

    fun save(credentials: PairedCredentials)

    fun clear()
}
