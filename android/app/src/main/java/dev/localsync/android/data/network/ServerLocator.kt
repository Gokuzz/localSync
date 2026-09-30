package dev.localsync.android.data.network

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl

const val LOCALSYNC_LOGICAL_HOST = "localsync.local"

data class ServerLocator(
    val locatorUrl: HttpUrl,
    val logicalHost: String = LOCALSYNC_LOGICAL_HOST,
) {
    val logicalBaseUrl: String
        get() = locatorUrl.newBuilder()
            .host(logicalHost)
            .build()
            .toString()
            .trimEnd('/')

    val normalizedLocatorUrl: String
        get() = locatorUrl.toString().trimEnd('/')
}

fun parseServerLocator(serverUrl: String): ServerLocator {
    val locator = serverUrl.trim().trimEnd('/').toHttpUrl()
    require(locator.scheme == "https") {
        "Authenticated localSync connections require HTTPS."
    }
    return ServerLocator(locator)
}
