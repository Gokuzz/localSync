package dev.localsync.android.data.media

import dev.localsync.android.core.model.MediaAccessState
import org.junit.Assert.assertEquals
import org.junit.Test

class MediaPermissionPolicyTest {
    @Test
    fun android10To12UsesReadExternalStorage() {
        assertEquals(
            MediaAccessState.FULL,
            MediaPermissionPolicy.stateFor(
                sdkInt = 32,
                hasReadExternalStorage = true,
                hasReadImages = false,
                hasReadVideo = false,
                hasSelectedVisual = false,
            ),
        )
        assertEquals(
            MediaAccessState.DENIED,
            MediaPermissionPolicy.stateFor(
                sdkInt = 32,
                hasReadExternalStorage = false,
                hasReadImages = false,
                hasReadVideo = false,
                hasSelectedVisual = false,
            ),
        )
    }

    @Test
    fun android13UsesGranularMediaPermissions() {
        assertEquals(
            MediaAccessState.FULL,
            MediaPermissionPolicy.stateFor(
                sdkInt = 33,
                hasReadExternalStorage = false,
                hasReadImages = true,
                hasReadVideo = false,
                hasSelectedVisual = false,
            ),
        )
        assertEquals(
            MediaAccessState.DENIED,
            MediaPermissionPolicy.stateFor(
                sdkInt = 33,
                hasReadExternalStorage = true,
                hasReadImages = false,
                hasReadVideo = false,
                hasSelectedVisual = false,
            ),
        )
    }

    @Test
    fun android14DistinguishesPartialAccess() {
        assertEquals(
            MediaAccessState.PARTIAL,
            MediaPermissionPolicy.stateFor(
                sdkInt = 34,
                hasReadExternalStorage = false,
                hasReadImages = false,
                hasReadVideo = false,
                hasSelectedVisual = true,
            ),
        )
        assertEquals(
            MediaAccessState.FULL,
            MediaPermissionPolicy.stateFor(
                sdkInt = 34,
                hasReadExternalStorage = false,
                hasReadImages = true,
                hasReadVideo = true,
                hasSelectedVisual = true,
            ),
        )
    }
}
