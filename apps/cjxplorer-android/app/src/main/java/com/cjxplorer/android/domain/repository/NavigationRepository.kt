package com.cjxplorer.android.domain.repository

import com.cjxplorer.android.domain.model.NavigationAction
import com.cjxplorer.android.domain.model.ScreenState
import kotlinx.coroutines.flow.Flow

interface NavigationRepository {
    val incomingActions: Flow<NavigationAction>
    val isConnected: Flow<Boolean>

    suspend fun connect(taskId: String)
    suspend fun disconnect()
    suspend fun sendScreenState(state: ScreenState)
}
