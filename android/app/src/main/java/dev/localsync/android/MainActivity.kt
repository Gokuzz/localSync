package dev.localsync.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.localsync.android.ui.home.HomeScreen
import dev.localsync.android.ui.home.HomeViewModel

class MainActivity : ComponentActivity() {
    private val viewModel: HomeViewModel by viewModels {
        val container = (application as LocalSyncApplication).container
        viewModelFactory {
            initializer { HomeViewModel(this@MainActivity, container.backupRepository) }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val permissionLauncher = rememberLauncherForActivityResult(
                ActivityResultContracts.RequestMultiplePermissions(),
            ) {
                viewModel.refreshPermissionState()
                viewModel.refreshInventory()
            }

            LaunchedEffect(Unit) {
                viewModel.refreshPermissionState()
                viewModel.refreshInventory()
            }

            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    HomeScreen(
                        viewModel = viewModel,
                        onRequestPermissions = {
                            permissionLauncher.launch(viewModel.permissionsToRequest())
                        },
                    )
                }
            }
        }
    }
}
