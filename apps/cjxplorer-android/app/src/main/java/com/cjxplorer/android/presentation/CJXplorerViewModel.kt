package com.cjxplorer.android.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.cjxplorer.android.domain.interactor.NavigationInteractor
import com.cjxplorer.android.domain.model.NavigationAction
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CJXplorerUiState(
    val isConnected: Boolean = false,
    val taskId: String = "",
    val currentStep: Int = 0,
    val lastAction: String = "",
    val logs: List<String> = emptyList()
)

@HiltViewModel
class CJXplorerViewModel @Inject constructor(
    private val navigationInteractor: NavigationInteractor
) : ViewModel() {

    private val _uiState = MutableStateFlow(CJXplorerUiState())
    val uiState: StateFlow<CJXplorerUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            navigationInteractor.isConnected.collect { connected ->
                _uiState.value = _uiState.value.copy(isConnected = connected)
                addLog(if (connected) "Подключено к бэкенду" else "Отключено")
            }
        }

        viewModelScope.launch {
            navigationInteractor.incomingActions.collect { action ->
                val description = when (action) {
                    is NavigationAction.Click -> "Click: ${action.nodeId}"
                    is NavigationAction.Scroll -> "Scroll: ${action.direction}"
                    is NavigationAction.TypeText -> "Type: ${action.nodeId}"
                    is NavigationAction.InputNeeded -> "Input needed: ${action.prompt}"
                    is NavigationAction.Back -> "Back"
                    is NavigationAction.Done -> "Done"
                }
                _uiState.value = _uiState.value.copy(
                    lastAction = description,
                    currentStep = _uiState.value.currentStep + 1
                )
                addLog("Шаг ${_uiState.value.currentStep}: $description")
            }
        }
    }

    fun connectToTask(taskId: String) {
        _uiState.value = _uiState.value.copy(taskId = taskId, currentStep = 0, logs = emptyList())
        viewModelScope.launch {
            addLog("Подключение к задаче $taskId…")
            navigationInteractor.startTask(taskId)
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            navigationInteractor.stopTask()
            addLog("Задача остановлена")
        }
    }

    private fun addLog(message: String) {
        val current = _uiState.value
        _uiState.value = current.copy(logs = current.logs + message)
    }
}
