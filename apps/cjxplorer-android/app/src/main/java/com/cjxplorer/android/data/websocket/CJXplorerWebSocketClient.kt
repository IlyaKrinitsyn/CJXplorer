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
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    private var webSocket: WebSocket? = null

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected

    private var _actions = Channel<NavigationAction>(Channel.BUFFERED)
    val actions: Flow<NavigationAction> get() = _actions.receiveAsFlow()

    fun connect(taskId: String) {
        disconnect()

        _actions.close()
        _actions = Channel(Channel.BUFFERED)

        val baseUrl = settingsRepository.getServerUrl().trimEnd('/')
        val url = "$baseUrl/ws/navigate/$taskId"
        Log.i(TAG, "Connecting to $url")

        val request = Request.Builder()
            .url(url)
            .build()

        webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _isConnected.value = true
                Log.i(TAG, "WS OPEN for task $taskId")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "WS MESSAGE: $text")
                handleMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WS CLOSING: code=$code reason=$reason")
                webSocket.close(1000, null)
                _isConnected.value = false
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WS CLOSED: code=$code reason=$reason")
                _isConnected.value = false
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WS FAILURE: ${t.message}, response=${response?.code}", t)
                _isConnected.value = false
            }
        })
    }

    fun disconnect() {
        Log.i(TAG, "disconnect() called, webSocket=${webSocket != null}")
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _isConnected.value = false
    }

    private var lastStateSentAt: Long = 0L

    fun sendState(state: WsOutgoingState) {
        val ws = webSocket
        if (ws == null) {
            Log.e(TAG, "sendState: webSocket is null!")
            return
        }
        val payload = json.encodeToString(state)
        lastStateSentAt = System.currentTimeMillis()
        val sent = ws.send(payload)
        Log.i(TAG, "sendState: sent=$sent, payload=${payload.length} chars, " +
            "screenshot=${state.screenshot.length} chars, nodes=${state.nodes.size}")
    }

    private fun handleMessage(text: String) {
        val now = System.currentTimeMillis()
        val waitMs = if (lastStateSentAt > 0) now - lastStateSentAt else -1
        try {
            val msg = json.decodeFromString<WsIncomingMessage>(text)
            Log.i(TAG, "<<< WS RECEIVED (wait=${waitMs}ms): type=${msg.type}, action=${msg.action}, " +
                "raw=${text.take(500)}")
            val action = parseAction(msg)
            if (action == null) {
                Log.w(TAG, "parseAction returned null for type=${msg.type} action=${msg.action}")
                return
            }
            Log.i(TAG, "Sending action to channel: $action")
            val result = _actions.trySend(action)
            Log.i(TAG, "Channel trySend: success=${result.isSuccess}, failure=${result.isFailure}, closed=${result.isClosed}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse WS message (wait=${waitMs}ms): ${text.take(300)}", e)
        }
    }

    private fun parseAction(msg: WsIncomingMessage): NavigationAction? = when (msg.type) {
        "start" -> NavigationAction.Start(msg.task.orEmpty())
        "action" -> when (msg.action) {
            "click" -> NavigationAction.Click(
                nodeId = msg.nodeId.orEmpty(),
                desc = msg.desc,
                boundsLeft = msg.bounds?.left,
                boundsTop = msg.bounds?.top,
                boundsRight = msg.bounds?.right,
                boundsBottom = msg.bounds?.bottom
            )
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
