package dev.localsync.android.data.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AndroidCredentialStore(context: Context) : CredentialStore {
    private val preferences = context.getSharedPreferences("localsync-paired-credentials", Context.MODE_PRIVATE)

    override fun load(): PairedCredentials? {
        val encryptedCredential = preferences.getString(KEY_CREDENTIAL, null) ?: return null
        val nonce = preferences.getString(KEY_NONCE, null) ?: return null
        val credential = decrypt(encryptedCredential, nonce)
        val serverLocator = preferences.getString(KEY_SERVER_LOCATOR_URL, null)
            ?: preferences.getString(KEY_SERVER_URL, "")
            ?: ""
        return PairedCredentials(
            serverLocatorUrl = serverLocator,
            serverLogicalHost = preferences.getString(KEY_SERVER_LOGICAL_HOST, DEFAULT_LOGICAL_HOST)
                ?: DEFAULT_LOGICAL_HOST,
            serverFingerprint = preferences.getString(KEY_SERVER_FINGERPRINT, "") ?: "",
            serverDisplayName = preferences.getString(KEY_SERVER_DISPLAY_NAME, "") ?: "",
            deviceId = preferences.getString(KEY_DEVICE_ID, "") ?: "",
            deviceCredential = credential,
        )
    }

    override fun save(credentials: PairedCredentials) {
        val encrypted = encrypt(credentials.deviceCredential)
        preferences.edit()
            .putString(KEY_SERVER_LOCATOR_URL, credentials.serverLocatorUrl.trim().trimEnd('/'))
            .putString(KEY_SERVER_LOGICAL_HOST, credentials.serverLogicalHost)
            .putString(KEY_SERVER_FINGERPRINT, credentials.serverFingerprint)
            .putString(KEY_SERVER_DISPLAY_NAME, credentials.serverDisplayName)
            .putString(KEY_DEVICE_ID, credentials.deviceId)
            .putString(KEY_CREDENTIAL, encrypted.ciphertext)
            .putString(KEY_NONCE, encrypted.nonce)
            .apply()
    }

    override fun clear() {
        preferences.edit().clear().apply()
    }

    private fun encrypt(value: String): EncryptedValue {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val ciphertext = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return EncryptedValue(
            ciphertext = Base64.encodeToString(ciphertext, Base64.NO_WRAP),
            nonce = Base64.encodeToString(cipher.iv, Base64.NO_WRAP),
        )
    }

    private fun decrypt(ciphertext: String, nonce: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            secretKey(),
            GCMParameterSpec(GCM_TAG_BITS, Base64.decode(nonce, Base64.NO_WRAP)),
        )
        return cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)).toString(Charsets.UTF_8)
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val existing = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
        if (existing != null) {
            return existing.secretKey
        }
        val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return keyGenerator.generateKey()
    }

    private data class EncryptedValue(val ciphertext: String, val nonce: String)

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "localsync-device-credential"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_BITS = 128
        const val KEY_SERVER_URL = "server_url"
        const val KEY_SERVER_LOCATOR_URL = "server_locator_url"
        const val KEY_SERVER_LOGICAL_HOST = "server_logical_host"
        const val KEY_SERVER_FINGERPRINT = "server_fingerprint"
        const val KEY_SERVER_DISPLAY_NAME = "server_display_name"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_CREDENTIAL = "credential_ciphertext"
        const val KEY_NONCE = "credential_nonce"
        const val DEFAULT_LOGICAL_HOST = "localsync.local"
    }
}
