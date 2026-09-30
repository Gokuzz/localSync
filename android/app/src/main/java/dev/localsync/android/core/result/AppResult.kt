package dev.localsync.android.core.result

sealed interface AppResult<out T> {
    data class Ok<T>(val value: T) : AppResult<T>
    data class Failed(val code: String, val message: String) : AppResult<Nothing>
}
