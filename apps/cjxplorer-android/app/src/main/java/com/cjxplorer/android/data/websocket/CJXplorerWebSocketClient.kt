package com.cjxplorer.android.data.websocket

import android.util.Log
import com.cjxplorer.android.data.settings.CJXplorerSettingsRepository
import com.cjxplorer.android.domain.model.NavigationAction
import com.cjxplorer.android.domain.model.ScrollDirection
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class CJXplorerWebSocketClient(
    private val okHttpClient: OkHttpClient,
    private val settingsRepository: CJXplorerSettingsRepository
) {
    private val json = Json { ignoreUnknownKeys = true }

    private var webSocket: WebSocket? = null

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected

    private val _actions = Channel<NavigationAction>(Channel.BUFFERED)
    val actions: Flow<NavigationAction> = _actions.receiveAsFlow()

    fun connect(taskId: String) {
        val baseUrl = settingsRepository.getServerUrl()
        val request = Request.Builder()
            .url("$baseUrl/ws/navigate/$taskId")
            .build()

        webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _isConnected.value = true
                Log.i(TAG, "WebSocket connected for task $taskId")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
                _isConnected.value = false
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket failure", t)
                _isConnected.value = false
            }
        })
    }

    fun disconnect() {
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _isConnected.value = false
    }

    fun sendState(state: WsOutgoingState) {
        val payload = json.encodeToString(state)
        webSocket?.send(payload)
    }

    private fun handleMessage(text: String) {
        try {
            val msg = json.decodeFromString<WsIncomingMessage>(text)
            val action = parseAction(msg) ?: return
            _actions.trySend(action)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse WS message: $text", e)
        }
    }

    private fun parseAction(msg: WsIncomingMessage): NavigationAction? = when (msg.type) {
        "action" -> when (msg.action) {
            "click" -> NavigationAction.Click(msg.nodeId.orEmpty())
            "scroll" -> NavigationAction.Scroll(
                when (msg.direction) {
                    "up" -> ScrollDirection.UP
                    "down" -> ScrollDirection.DOWN
                    "left" -> ScrollDirection.LEFT
                    "right" -> ScrollDirection.RIGHT
                    else -> ScrollDirection.DOWN
                }
            )
            "type" -> NavigationAction.TypeText(msg.nodeId.orEmpty(), msg.text.orEmpty())
            "back" -> NavigationAction.Back
            "done" -> NavigationAction.Done
            "input_needed" -> NavigationAction.InputNeeded(msg.nodeId.orEmpty(), msg.prompt.orEmpty())
            else -> null
        }
        "input_response" -> NavigationAction.TypeText(msg.nodeId.orEmpty(), msg.value.orEmpty())
        "done" -> NavigationAction.Done
        else -> null
    }

    companion object {
        private const val TAG = "CJXplorerWS"
    }
}
