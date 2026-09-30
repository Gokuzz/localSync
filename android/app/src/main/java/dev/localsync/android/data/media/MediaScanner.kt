package dev.localsync.android.data.media

import dev.localsync.android.core.model.MediaItem

interface MediaScanner {
    fun scan(): List<MediaItem>
}
