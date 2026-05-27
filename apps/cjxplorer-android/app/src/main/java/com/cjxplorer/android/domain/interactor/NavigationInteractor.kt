package com.cjxplorer.android.domain.interactor

import com.cjxplorer.android.domain.model.NavigationAction
import com.cjxplorer.android.domain.model.ScreenState
import com.cjxplorer.android.domain.repository.NavigationRepository
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Координирует весь навигационный цикл:
 * подключение к задаче, отправка состояния экрана,
 * получение и маршрутизация действий от бэкенда.
 */
@Singleton
class NavigationInteractor @Inject constructor(
    private val repository: NavigationRepository
) {
    val incomingActions: Flow<NavigationAction> = repository.incomingActions
    val isConnected: Flow<Boolean> = repository.isConnected

    suspend fun startTask(taskId: String) {
        repository.connect(taskId)
    }

    suspend fun stopTask() {
        repository.disconnect()
    }

    suspend fun reportScreenState(state: ScreenState) {
        repository.sendScreenState(state)
    }
}
