package dev.localsync.android.data.discovery

import android.os.Build
import android.os.ext.SdkExtensions

fun shouldAcquireDiscoveryMulticastLock(
    sdkInt: Int,
    tiramisuExtension: Int,
): Boolean = when {
    sdkInt <= Build.VERSION_CODES.S_V2 -> true
    sdkInt == Build.VERSION_CODES.TIRAMISU -> tiramisuExtension < 7
    else -> false
}

fun currentDiscoveryMulticastLockPolicy(): Boolean = shouldAcquireDiscoveryMulticastLock(
    Build.VERSION.SDK_INT,
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        SdkExtensions.getExtensionVersion(Build.VERSION_CODES.TIRAMISU)
    } else {
        0
    },
)
