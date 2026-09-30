package dev.localsync.android.data.network

import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(private val credentialProvider: () -> String?) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val credential = credentialProvider()
        val request = if (credential.isNullOrBlank()) {
            chain.request()
        } else {
            chain.request().newBuilder()
                .header("Authorization", "Bearer $credential")
                .build()
        }
        return chain.proceed(request)
    }
}
