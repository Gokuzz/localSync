package dev.localsync.android.data.settings

import android.content.Context
import java.util.UUID

data class DevelopmentSettings(
    val serverUrl: String,
    val deviceId: String,
)

interface SettingsDataSource {
    fun get(): DevelopmentSettings

    fun saveServerUrl(serverUrl: String)

    fun saveDeviceId(deviceId: String)
}

class SettingsStore(context: Context) : SettingsDataSource {
    private val preferences = context.getSharedPreferences("localsync-dev-settings", Context.MODE_PRIVATE)

    override fun get(): DevelopmentSettings {
        val deviceId = preferences.getString(KEY_DEVICE_ID, null) ?: createDeviceId()
        return DevelopmentSettings(
            serverUrl = preferences.getString(KEY_SERVER_URL, "") ?: "",
            deviceId = deviceId,
        )
    }

    override fun saveServerUrl(serverUrl: String) {
        preferences.edit().putString(KEY_SERVER_URL, serverUrl.trim().trimEnd('/')).apply()
    }

    override fun saveDeviceId(deviceId: String) {
        preferences.edit().putString(KEY_DEVICE_ID, deviceId.trim()).apply()
    }

    private fun createDeviceId(): String {
        val deviceId = "android-dev-${UUID.randomUUID()}"
        preferences.edit().putString(KEY_DEVICE_ID, deviceId).apply()
        return deviceId
    }

    private companion object {
        const val KEY_SERVER_URL = "server_url"
        const val KEY_DEVICE_ID = "device_id"
    }
}
