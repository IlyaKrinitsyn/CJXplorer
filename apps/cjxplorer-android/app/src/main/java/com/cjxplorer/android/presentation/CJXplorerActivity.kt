package com.cjxplorer.android.presentation

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import com.cjxplorer.android.presentation.screen.CJXplorerHomeScreen
import com.cjxplorer.android.presentation.theme.CJXplorerTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class CJXplorerActivity : ComponentActivity() {

    private lateinit var viewModel: CJXplorerViewModel

    private val projectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            viewModel.saveProjectionResult(result.resultCode, result.data!!)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            CJXplorerTheme {
                viewModel = hiltViewModel()
                val uiState by viewModel.uiState.collectAsState()

                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    CJXplorerHomeScreen(
                        uiState = uiState,
                        onSaveUrl = viewModel::saveServerUrl,
                        onConnect = viewModel::connectToServer,
                        onDisconnect = viewModel::disconnectFromServer,
                        onStopNavigation = viewModel::stopNavigation,
                        onRequestProjection = ::requestMediaProjection,
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }

    private fun requestMediaProjection() {
        val pm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projectionLauncher.launch(pm.createScreenCaptureIntent())
    }
}
