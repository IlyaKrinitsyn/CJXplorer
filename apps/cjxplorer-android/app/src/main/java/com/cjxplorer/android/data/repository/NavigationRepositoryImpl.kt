package com.cjxplorer.android.data.repository

import com.cjxplorer.android.data.websocket.CJXplorerWebSocketClient
import com.cjxplorer.android.data.websocket.WsAccessibilityNode
import com.cjxplorer.android.data.websocket.WsBounds
import com.cjxplorer.android.data.websocket.WsOutgoingState
import com.cjxplorer.android.domain.model.AccessibilityNode
import com.cjxplorer.android.domain.model.NavigationAction
import com.cjxplorer.android.domain.model.ScreenState
import com.cjxplorer.android.domain.repository.NavigationRepository
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class NavigationRepositoryImpl @Inject constructor(
    private val wsClient: CJXplorerWebSocketClient
) : NavigationRepository {

    override val incomingActions: Flow<NavigationAction> = wsClient.actions
    override val isConnected: Flow<Boolean> = wsClient.isConnected

    override suspend fun connect(taskId: String) {
        wsClient.connect(taskId)
    }

    override suspend fun disconnect() {
        wsClient.disconnect()
    }

    override suspend fun sendScreenState(state: ScreenState) {
        wsClient.sendState(
            WsOutgoingState(
                screenshot = state.screenshotBase64,
                nodes = state.nodes.map { it.toWs() }
            )
        )
    }

    private fun AccessibilityNode.toWs(): WsAccessibilityNode = WsAccessibilityNode(
        id = id,
        className = className,
        text = text,
        contentDescription = contentDescription,
        bounds = WsBounds(bounds.left, bounds.top, bounds.right, bounds.bottom),
        clickable = isClickable,
        scrollable = isScrollable,
        children = children.map { it.toWs() }
    )
}
