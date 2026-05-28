package com.cjxplorer.android.presentation

import android.app.Application
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.cjxplorer.android.data.settings.CJXplorerSettingsRepository
import com.cjxplorer.android.data.websocket.CJXplorerDeviceClient
import com.cjxplorer.android.domain.model.TaskInfo
import com.cjxplorer.android.service.CJXplorerAccessibilityService
import com.cjxplorer.android.service.CJXplorerNavigationService
import android.util.Log
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CJXplorerUiState(
    val serverUrl: String = "",
    val isDeviceConnected: Boolean = false,
    val isConnecting: Boolean = false,
    val connectionError: String? = null,
    val isAccessibilityEnabled: Boolean = false,
    val hasProjectionPermission: Boolean = false,
    val currentTask: TaskInfo? = null,
    val isNavigating: Boolean = false,
    val logs: List<String> = emptyList()
)

@HiltViewModel
class CJXplorerViewModel @Inject constructor(
    application: Application,
    private val deviceClient: CJXplorerDeviceClient,
    private val settingsRepository: CJXplorerSettingsRepository
) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(
        CJXplorerUiState(serverUrl = settingsRepository.getServerUrl())
    )
    val uiState: StateFlow<CJXplorerUiState> = _uiState.asStateFlow()

    private var projectionResultCode: Int? = null
    private var projectionData: Intent? = null
    private var connectTimeoutJob: Job? = null

    init {
        viewModelScope.launch {
            deviceClient.isConnected.collect { connected ->
                if (connected) {
                    connectTimeoutJob?.cancel()
                    _uiState.value = _uiState.value.copy(
                        isDeviceConnected = true,
                        isConnecting = false,
                        connectionError = null
                    )
                    addLog("Подключено к серверу")
                } else if (_uiState.value.isDeviceConnected) {
                    _uiState.value = _uiState.value.copy(isDeviceConnected = false)
                    addLog("Отключено от сервера")
                }
            }
        }

        viewModelScope.launch {
            deviceClient.connectionErrors.collect { error ->
                addLog("Ошибка подключения: $error")
            }
        }

        viewModelScope.launch {
            deviceClient.newTasks.collect { task ->
                addLog("Новая задача: ${task.taskId}")
                addLog("Приложение: ${task.appName}")
                addLog("Сценарий: ${task.journeyDescription}")
                _uiState.value = _uiState.value.copy(currentTask = task)
                startNavigation(task)
            }
        }

        viewModelScope.launch {
            CJXplorerNavigationService.isRunning.collect { running ->
                if (!running && _uiState.value.isNavigating) {
                    _uiState.value = _uiState.value.copy(
                        isNavigating = false,
                        currentTask = null
                    )
                    addLog("Навигация завершена")
                }
            }
        }
    }

    fun saveServerUrl(url: String) {
        settingsRepository.setServerUrl(url)
        _uiState.value = _uiState.value.copy(serverUrl = url)
        addLog("Адрес сервера: $url")
    }

    fun connectToServer() {
        _uiState.value = _uiState.value.copy(
            isConnecting = true,
            connectionError = null
        )
        addLog("Подключение к серверу...")
        deviceClient.connect()

        connectTimeoutJob?.cancel()
        connectTimeoutJob = viewModelScope.launch {
            delay(CONNECTION_TIMEOUT_MS)
            if (!_uiState.value.isDeviceConnected) {
                _uiState.value = _uiState.value.copy(
                    isConnecting = false,
                    connectionError = "Не удалось подключиться. Проверьте адрес и доступность сервера."
                )
                addLog("Таймаут подключения (${CONNECTION_TIMEOUT_MS / 1000}с)")
                deviceClient.disconnect()
            }
        }
    }

    fun disconnectFromServer() {
        connectTimeoutJob?.cancel()
        _uiState.value = _uiState.value.copy(
            isDeviceConnected = false,
            isConnecting = false,
            connectionError = null,
            currentTask = null,
            isNavigating = false
        )
        addLog("Отключено от сервера")
        deviceClient.disconnect()
    }

    fun refreshAccessibilityStatus() {
        val enabled = CJXplorerAccessibilityService.instance != null
        _uiState.value = _uiState.value.copy(isAccessibilityEnabled = enabled)
    }

    fun saveProjectionResult(resultCode: Int, data: Intent) {
        projectionResultCode = resultCode
        projectionData = data
        _uiState.value = _uiState.value.copy(hasProjectionPermission = true)
        addLog("Разрешение на запись экрана получено")
    }

    private fun startNavigation(task: TaskInfo) {
        val ctx = getApplication<Application>()
        _uiState.value = _uiState.value.copy(isNavigating = true)
        addLog("Запуск навигации для задачи ${task.taskId}...")

        Log.i(TAG, "startNavigation: taskId=${task.taskId}")
        Log.i(TAG, "startNavigation: projectionResultCode=$projectionResultCode, projectionData=${projectionData != null}")

        CJXplorerNavigationService.start(
            context = ctx,
            taskId = task.taskId,
            projectionResultCode = projectionResultCode,
            projectionData = projectionData
        )
        Log.i(TAG, "startNavigation: service start requested")
    }

    fun stopNavigation() {
        val ctx = getApplication<Application>()
        CJXplorerNavigationService.stop(ctx)
        _uiState.value = _uiState.value.copy(isNavigating = false, currentTask = null)
        addLog("Навигация остановлена")
    }

    private fun addLog(message: String) {
        val current = _uiState.value
        _uiState.value = current.copy(logs = current.logs + message)
    }

    companion object {
        private const val TAG = "CJXplorerVM"
        private const val CONNECTION_TIMEOUT_MS = 15_000L
    }
}
