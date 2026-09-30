package dev.localsync.android.ui.home

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dev.localsync.android.data.media.MediaPermissionPolicy
import dev.localsync.android.data.repository.BackupRepository
import dev.localsync.android.data.discovery.TrustedDiscoveryResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class HomeViewModel(
    context: Context,
    private val repository: BackupRepository,
) : ViewModel() {
    private val permissionPolicy = MediaPermissionPolicy(context.applicationContext)
    private val mutableState = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = mutableState

    init {
        viewModelScope.launch {
            val settings = repository.settings()
            val credentials = repository.pairedCredentials()
            mutableState.update {
                it.copy(
                    serverUrl = credentials?.serverUrl ?: settings.serverUrl,
                    deviceId = settings.deviceId,
                    pairedDeviceId = credentials?.deviceId,
                    pairedServerFingerprint = credentials?.serverFingerprint,
                    pairedServerDisplayName = credentials?.serverDisplayName,
                )
            }
        }
    }

    fun permissionsToRequest(): Array<String> = permissionPolicy.permissionsToRequest()

    fun refreshPermissionState() {
        mutableState.update { it.copy(accessState = permissionPolicy.currentState()) }
    }

    fun refreshInventory() {
        viewModelScope.launch {
            mutableState.update { it.copy(isLoading = true, message = null) }
            runCatching { repository.refreshInventory() }
                .onSuccess { media ->
                    mutableState.update { it.copy(media = media, isLoading = false) }
                }
                .onFailure { failure ->
                    mutableState.update {
                        it.copy(isLoading = false, message = failure.message ?: "Inventory failed")
                    }
                }
        }
    }

    fun saveSettings(serverUrl: String, deviceId: String) {
        viewModelScope.launch {
            repository.saveSettings(serverUrl, deviceId)
            mutableState.update { it.copy(serverUrl = serverUrl, deviceId = deviceId) }
        }
    }

    fun observeServerIdentity(serverUrl: String) {
        viewModelScope.launch {
            mutableState.update {
                it.copy(
                    isObservingServer = true,
                    observedServerFingerprint = null,
                    fingerprintConfirmed = false,
                    message = null,
                )
            }
            runCatching { repository.observeServerIdentity(serverUrl) }
                .onSuccess { identity ->
                    mutableState.update {
                        it.copy(
                            isObservingServer = false,
                            serverUrl = identity.locatorUrl,
                            observedServerFingerprint = identity.fingerprint,
                            message = "Compare the observed fingerprint with the laptop.",
                        )
                    }
                }
                .onFailure { failure ->
                    mutableState.update {
                        it.copy(
                            isObservingServer = false,
                            message = failure.message ?: "Could not observe server identity",
                        )
                    }
                }
        }
    }

    fun confirmObservedFingerprint(expectedServerFingerprint: String) {
        mutableState.update { current ->
            val observed = current.observedServerFingerprint?.trim()
            val expected = expectedServerFingerprint.trim()
            if (observed != null && observed == expected) {
                current.copy(fingerprintConfirmed = true, message = "Fingerprint confirmed")
            } else {
                current.copy(fingerprintConfirmed = false, message = "Fingerprint does not match")
            }
        }
    }

    fun completePairing(
        serverUrl: String,
        pairingId: String,
        pairingCode: String,
        expectedServerFingerprint: String,
    ) {
        viewModelScope.launch {
            mutableState.update { it.copy(isPairing = true, message = null) }
            runCatching {
                repository.completePairing(
                    serverUrl,
                    pairingId,
                    pairingCode,
                    expectedServerFingerprint,
                    mutableState.value.observedServerFingerprint.orEmpty(),
                    mutableState.value.fingerprintConfirmed,
                    "Android device",
                )
            }.onSuccess { credentials ->
                mutableState.update {
                    it.copy(
                        isPairing = false,
                        serverUrl = credentials.serverUrl,
                        pairedDeviceId = credentials.deviceId,
                        pairedServerFingerprint = credentials.serverFingerprint,
                        pairedServerDisplayName = credentials.serverDisplayName,
                        observedServerFingerprint = null,
                        fingerprintConfirmed = false,
                        message = "Paired with laptop",
                    )
                }
            }.onFailure { failure ->
                mutableState.update {
                    it.copy(isPairing = false, message = failure.message ?: "Pairing failed")
                }
            }
        }
    }

    fun forgetPairing() {
        viewModelScope.launch {
            repository.forgetPairing()
            mutableState.update {
                it.copy(
                    pairedDeviceId = null,
                    pairedServerFingerprint = null,
                    pairedServerDisplayName = null,
                    observedServerFingerprint = null,
                    fingerprintConfirmed = false,
                    message = "Pairing forgotten locally",
                )
            }
        }
    }

    fun backupNow() {
        viewModelScope.launch {
            mutableState.update { it.copy(isBackingUp = true, message = null) }
            runCatching { repository.backupNow() }
                .onSuccess {
                    val media = repository.listMedia()
                    mutableState.update {
                        it.copy(isBackingUp = false, media = media, message = "Backup finished")
                    }
                }
                .onFailure { failure ->
                    val media = repository.listMedia()
                    mutableState.update {
                        it.copy(
                            isBackingUp = false,
                            media = media,
                            message = failure.message ?: "Backup failed",
                        )
                    }
                }
        }
    }

    fun findLaptop() {
        viewModelScope.launch {
            mutableState.update { it.copy(isFindingLaptop = true, discoveryStatus = "Searching for trusted laptop...") }
            runCatching { repository.findTrustedLaptop() }
                .onSuccess { result ->
                    mutableState.update {
                        when (result) {
                            is TrustedDiscoveryResult.Verified -> it.copy(
                                isFindingLaptop = false,
                                serverUrl = result.locatorUrl,
                                discoveryStatus = "Connected securely at ${result.locatorUrl}",
                            )
                            is TrustedDiscoveryResult.IdentityMismatch -> it.copy(
                                isFindingLaptop = false,
                                discoveryStatus = "Server identity changed; verify the laptop before continuing.",
                            )
                            TrustedDiscoveryResult.NotFound -> it.copy(
                                isFindingLaptop = false,
                                discoveryStatus = "Trusted laptop not found. Manual locator remains available.",
                            )
                            TrustedDiscoveryResult.NotPaired -> it.copy(
                                isFindingLaptop = false,
                                discoveryStatus = "Pair with a laptop before using discovery.",
                            )
                        }
                    }
                }
                .onFailure { failure ->
                    mutableState.update {
                        it.copy(
                            isFindingLaptop = false,
                            discoveryStatus = failure.message ?: "Discovery unavailable. Manual locator remains available.",
                        )
                    }
                }
        }
    }
}
