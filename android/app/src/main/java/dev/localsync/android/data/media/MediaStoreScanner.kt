package dev.localsync.android.data.media

import android.content.Context
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import dev.localsync.android.core.model.MediaItem
import dev.localsync.android.core.model.MediaKind

class MediaStoreScanner(context: Context) : MediaScanner {
    private val applicationContext = context.applicationContext
    private val contentResolver = applicationContext.contentResolver

    override fun scan(): List<MediaItem> = buildList {
        mediaVolumes().forEach { volumeName ->
            addAll(queryKind(MediaKind.IMAGE, volumeName))
            addAll(queryKind(MediaKind.VIDEO, volumeName))
        }
    }.sortedByDescending { it.dateTaken ?: it.dateModified ?: it.dateAdded ?: 0L }

    private fun queryKind(kind: MediaKind, volumeName: String): List<MediaItem> {
        val collection = collectionFor(kind, volumeName)
        val projection = arrayOf(
            MediaStore.MediaColumns._ID,
            MediaStore.MediaColumns.DISPLAY_NAME,
            MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.DATE_ADDED,
            MediaStore.MediaColumns.DATE_MODIFIED,
            MediaStore.MediaColumns.DATE_TAKEN,
        )
        contentResolver.query(
            collection,
            projection,
            null,
            null,
            "${MediaStore.MediaColumns.DATE_MODIFIED} DESC",
        ).use { cursor ->
            if (cursor == null) return emptyList()
            return cursor.toMediaItems(collection, volumeName, kind)
        }
    }

    private fun Cursor.toMediaItems(
        collection: Uri,
        volumeName: String,
        kind: MediaKind,
    ): List<MediaItem> {
        val idColumn = getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
        val nameColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
        val sizeColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)
        val mimeColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE)
        val addedColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_ADDED)
        val modifiedColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)
        val takenColumn = getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_TAKEN)

        val items = mutableListOf<MediaItem>()
        while (moveToNext()) {
            val id = getLong(idColumn)
            val size = getLong(sizeColumn)
            if (size < 0) continue
            items += MediaItem(
                mediaStoreId = id,
                volumeName = volumeName,
                contentUri = Uri.withAppendedPath(collection, id.toString()).toString(),
                displayName = getString(nameColumn) ?: "media-$id",
                size = size,
                mimeType = getString(mimeColumn),
                mediaKind = kind,
                dateAdded = getNullableLong(addedColumn),
                dateModified = getNullableLong(modifiedColumn),
                dateTaken = getNullableLong(takenColumn),
            )
        }
        return items
    }

    private fun Cursor.getNullableLong(index: Int): Long? =
        if (isNull(index)) null else getLong(index)

    private fun mediaVolumes(): Set<String> = if (Build.VERSION.SDK_INT >= 29) {
        MediaStore.getExternalVolumeNames(applicationContext)
    } else {
        setOf(MediaStore.VOLUME_EXTERNAL)
    }

    private fun collectionFor(kind: MediaKind, volumeName: String): Uri = if (Build.VERSION.SDK_INT >= 29) {
        when (kind) {
            MediaKind.IMAGE -> MediaStore.Images.Media.getContentUri(volumeName)
            MediaKind.VIDEO -> MediaStore.Video.Media.getContentUri(volumeName)
        }
    } else {
        when (kind) {
            MediaKind.IMAGE -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            MediaKind.VIDEO -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        }
    }
}
