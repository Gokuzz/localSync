package dev.localsync.android.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ListItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.localsync.android.core.model.MediaAccessState
import dev.localsync.android.core.model.MediaKind

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onRequestPermissions: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    var selectedTab by remember { mutableIntStateOf(0) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("localSync") }) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabRow(selectedTabIndex = selectedTab) {
                listOf("Home", "Media", "Developer").forEachIndexed { index, label ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(label) },
                    )
                }
            }
            when (selectedTab) {
                0 -> HomeTab(
                    state,
                    onRequestPermissions,
                    viewModel::refreshInventory,
                    viewModel::backupNow,
                    viewModel::findLaptop,
                )
                1 -> MediaTab(state)
                2 -> SettingsTab(
                    state,
                    viewModel::saveSettings,
                    viewModel::observeServerIdentity,
                    viewModel::confirmObservedFingerprint,
                    viewModel::completePairing,
                    viewModel::forgetPairing,
                )
            }
        }
    }
}

@Composable
private fun HomeTab(
    state: HomeUiState,
    onRequestPermissions: () -> Unit,
    onRefresh: () -> Unit,
    onBackupNow: () -> Unit,
    onFindLaptop: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(permissionTitle(state.accessState))
                Text(permissionDetail(state))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onRequestPermissions) {
                        Text(if (state.accessState == MediaAccessState.PARTIAL) "Manage access" else "Allow access")
                    }
                    Button(onClick = onRefresh, enabled = !state.isLoading) {
                        Text("Refresh")
                    }
                }
            }
        }
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Backed up: ${state.backedUpCount}")
                Text("Pending: ${state.pendingCount}")
                Text("Failed: ${state.failedCount}")
                Button(
                    onClick = onBackupNow,
                    enabled = !state.isBackingUp && state.isPaired,
                ) {
                    Text(if (state.isBackingUp) "Backing up" else "Backup Now")
                }
                Button(
                    onClick = onFindLaptop,
                    enabled = state.isPaired && !state.isFindingLaptop,
                ) {
                    Text(if (state.isFindingLaptop) "Searching" else "Find Laptop")
                }
                state.discoveryStatus?.let { Text(it) }
                state.message?.let { Text(it) }
            }
        }
    }
}

@Composable
private fun MediaTab(state: HomeUiState) {
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(state.media) { item ->
            ListItem(
                headlineContent = { Text(item.item.displayName) },
                supportingContent = {
                    Text("${if (item.item.mediaKind == MediaKind.IMAGE) "Image" else "Video"} - ${item.status}")
                },
            )
        }
    }
}

@Composable
private fun SettingsTab(
    state: HomeUiState,
    onSave: (String, String) -> Unit,
    onObserveServer: (String) -> Unit,
    onConfirmFingerprint: (String) -> Unit,
    onPair: (String, String, String, String) -> Unit,
    onForget: () -> Unit,
) {
    var serverUrl by remember(state.serverUrl) { mutableStateOf(state.serverUrl) }
    var deviceId by remember(state.deviceId) { mutableStateOf(state.deviceId) }
    var pairingId by remember { mutableStateOf("") }
    var pairingCode by remember { mutableStateOf("") }
    var expectedFingerprint by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Pairing")
        state.message?.let { Text(it) }
        if (state.isPaired) {
            Text("Paired with: ${state.pairedServerDisplayName ?: "localSync laptop"}")
            Text("Device: ${state.pairedDeviceId}")
            Text("Fingerprint: ${state.pairedServerFingerprint}")
            Button(onClick = onForget) {
                Text("Forget laptop")
            }
        } else {
            OutlinedTextField(
                value = pairingId,
                onValueChange = { pairingId = it },
                label = { Text("Pairing ID") },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = pairingCode,
                onValueChange = { pairingCode = it },
                label = { Text("Pairing code") },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = expectedFingerprint,
                onValueChange = { expectedFingerprint = it },
                label = { Text("Laptop fingerprint") },
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { onObserveServer(serverUrl) },
                enabled = !state.isObservingServer && serverUrl.isNotBlank(),
            ) {
                Text(if (state.isObservingServer) "Observing" else "Observe server fingerprint")
            }
            state.observedServerFingerprint?.let { fingerprint ->
                Text("Observed server fingerprint:")
                Text(fingerprint)
                Button(
                    onClick = { onConfirmFingerprint(expectedFingerprint) },
                    enabled = expectedFingerprint.isNotBlank(),
                ) {
                    Text("I verified this fingerprint")
                }
            }
            if (state.fingerprintConfirmed) {
                Text("Fingerprint verified. Pairing code can now be sent.")
            }
            Button(
                onClick = { onPair(serverUrl, pairingId, pairingCode, expectedFingerprint) },
                enabled = !state.isPairing && state.fingerprintConfirmed && serverUrl.isNotBlank(),
            ) {
                Text(if (state.isPairing) "Pairing" else "Pair with laptop")
            }
        }
        Spacer(Modifier.height(8.dp))
        Text("Development server locator")
        OutlinedTextField(
            value = serverUrl,
            onValueChange = { serverUrl = it },
            label = { Text("Server URL") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = deviceId,
            onValueChange = { deviceId = it },
            label = { Text("Device namespace") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = { onSave(serverUrl, deviceId) }) {
            Text("Save")
        }
        Spacer(Modifier.height(8.dp))
        Text("Pairing credentials are required before backup. Local forget does not revoke the laptop record.")
    }
}

private fun permissionTitle(accessState: MediaAccessState): String = when (accessState) {
    MediaAccessState.UNKNOWN -> "Photo & video access"
    MediaAccessState.DENIED -> "Photo & video access required"
    MediaAccessState.PARTIAL -> "Limited photo access"
    MediaAccessState.FULL -> "Photos & videos"
}

private fun permissionDetail(state: HomeUiState): String = when (state.accessState) {
    MediaAccessState.UNKNOWN -> "Choose the media you want backed up to your laptop."
    MediaAccessState.DENIED -> "localSync can only back up photos and videos after access is granted."
    MediaAccessState.PARTIAL -> "${state.accessibleCount} accessible. Only this selected subset can be backed up."
    MediaAccessState.FULL -> "${state.accessibleCount} accessible."
}
