package com.cjxplorer.android.data.websocket

import android.util.Log
import com.cjxplorer.android.data.settings.CJXplorerSettingsRepository
import com.cjxplorer.android.domain.model.TaskInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/**
 * Persistent WS-клиент к /ws/device.
 * Получает push-уведомления о новых задачах и пробрасывает [TaskInfo]
 * через [newTasks]. Автоматически переподключается при обрыве.
 */
class CJXplorerDeviceClient(
    private val okHttpClient: OkHttpClient,
    private val settingsRepository: CJXplorerSettingsRepository
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var webSocket: WebSocket? = null
    private var reconnectJob: Job? = null

    @Volatile
    private var shouldConnect = false

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected

    private val _connectionErrors = Channel<String>(Channel.BUFFERED)
    val connectionErrors: Flow<String> = _connectionErrors.receiveAsFlow()

    private val _newTasks = Channel<TaskInfo>(Channel.BUFFERED)
    val newTasks: Flow<TaskInfo> = _newTasks.receiveAsFlow()

    private val json = Json { ignoreUnknownKeys = true }

    fun connect() {
        shouldConnect = true
        doConnect()
    }

    fun disconnect() {
        shouldConnect = false
        reconnectJob?.cancel()
        reconnectJob = null
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _isConnected.value = false
    }

    private fun doConnect() {
        val baseUrl = settingsRepository.getServerUrl()
        val request = Request.Builder()
            .url("$baseUrl/ws/device")
            .build()

        webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _isConnected.value = true
                Log.i(TAG, "Device WS connected to $baseUrl/ws/device")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
                _isConnected.value = false
                scheduleReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "Device WS failure", t)
                _isConnected.value = false
                val reason = t.message ?: t.javaClass.simpleName
                _connectionErrors.trySend(reason)
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (!shouldConnect) return
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(RECONNECT_DELAY_MS)
            if (shouldConnect) {
                Log.i(TAG, "Reconnecting to /ws/device...")
                doConnect()
            }
        }
    }

    private fun handleMessage(text: String) {
        try {
            val obj = json.parseToJsonElement(text).jsonObject
            when (obj["type"]?.jsonPrimitive?.content) {
                "connected" -> Log.i(TAG, "Device registered on server")
                "new_task" -> {
                    val taskId = obj["task_id"]?.jsonPrimitive?.content.orEmpty()
                    val appName = obj["app_name"]?.jsonPrimitive?.content.orEmpty()
                    val journey = obj["journey_description"]?.jsonPrimitive?.content.orEmpty()
                    val task = TaskInfo(taskId, appName, journey)
                    Log.i(TAG, "New task received: $taskId")
                    _newTasks.trySend(task)
                }
                else -> Log.w(TAG, "Unknown device WS message: $text")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse device WS message: $text", e)
        }
    }

    companion object {
        private const val TAG = "CJXplorerDevice"
        private const val RECONNECT_DELAY_MS = 3000L
    }
}
