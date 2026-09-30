package dev.localsync.android.data.security

class InMemoryCredentialStore(initial: PairedCredentials? = null) : CredentialStore {
    private var credentials: PairedCredentials? = initial

    override fun load(): PairedCredentials? = credentials

    override fun save(credentials: PairedCredentials) {
        this.credentials = credentials
    }

    override fun clear() {
        credentials = null
    }
}
