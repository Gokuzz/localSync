package dev.localsync.android.data.discovery

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MulticastLockPolicyTest {
    @Test
    fun olderAndroidUsesScopedMulticastLock() {
        assertTrue(shouldAcquireDiscoveryMulticastLock(32, 0))
        assertTrue(shouldAcquireDiscoveryMulticastLock(33, 6))
    }

    @Test
    fun newerAndroidDoesNotAcquireUnconditionally() {
        assertFalse(shouldAcquireDiscoveryMulticastLock(33, 7))
        assertFalse(shouldAcquireDiscoveryMulticastLock(34, 0))
    }
}
