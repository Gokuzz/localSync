package dev.localsync.android.data.media

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import dev.localsync.android.core.model.MediaAccessState

class MediaPermissionPolicy(private val context: Context) {
    fun currentState(): MediaAccessState = stateFor(
        sdkInt = Build.VERSION.SDK_INT,
        hasReadExternalStorage = hasPermission(Manifest.permission.READ_EXTERNAL_STORAGE),
        hasReadImages = if (Build.VERSION.SDK_INT >= 33) {
            hasPermission(Manifest.permission.READ_MEDIA_IMAGES)
        } else {
            false
        },
        hasReadVideo = if (Build.VERSION.SDK_INT >= 33) {
            hasPermission(Manifest.permission.READ_MEDIA_VIDEO)
        } else {
            false
        },
        hasSelectedVisual = if (Build.VERSION.SDK_INT >= 34) {
            hasPermission(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
        } else {
            false
        },
    )

    fun permissionsToRequest(): Array<String> = when {
        Build.VERSION.SDK_INT >= 34 -> arrayOf(
            Manifest.permission.READ_MEDIA_IMAGES,
            Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED,
        )

        Build.VERSION.SDK_INT >= 33 -> arrayOf(
            Manifest.permission.READ_MEDIA_IMAGES,
            Manifest.permission.READ_MEDIA_VIDEO,
        )

        else -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
    }

    private fun hasPermission(permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    companion object {
        fun stateFor(
            sdkInt: Int,
            hasReadExternalStorage: Boolean,
            hasReadImages: Boolean,
            hasReadVideo: Boolean,
            hasSelectedVisual: Boolean,
        ): MediaAccessState = when {
            sdkInt >= 34 && (hasReadImages || hasReadVideo) -> MediaAccessState.FULL
            sdkInt >= 34 && hasSelectedVisual -> MediaAccessState.PARTIAL
            sdkInt >= 34 -> MediaAccessState.DENIED
            sdkInt >= 33 && (hasReadImages || hasReadVideo) -> MediaAccessState.FULL
            sdkInt >= 33 -> MediaAccessState.DENIED
            hasReadExternalStorage -> MediaAccessState.FULL
            else -> MediaAccessState.DENIED
        }
    }
}
