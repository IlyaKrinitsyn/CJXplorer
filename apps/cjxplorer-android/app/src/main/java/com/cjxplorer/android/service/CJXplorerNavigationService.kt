package com.cjxplorer.android.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import com.cjxplorer.android.R
import com.cjxplorer.android.data.websocket.CJXplorerWebSocketClient
import com.cjxplorer.android.data.websocket.WsAccessibilityNode
import com.cjxplorer.android.data.websocket.WsBounds
import com.cjxplorer.android.data.websocket.WsOutgoingState
import com.cjxplorer.android.domain.model.AccessibilityNode
import com.cjxplorer.android.domain.model.NavigationAction
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Foreground Service для навигации по клиентскому пути.
 * Координирует WebSocket-соединение, AccessibilityService и MediaProjection.
 *
 * Навигационный цикл:
 * 1. Захват скриншота через [CJXplorerScreenCapture]
 * 2. Получение дерева нод через [CJXplorerAccessibilityService]
 * 3. Отправка screenshot + nodes на бэкенд через [CJXplorerWebSocketClient]
 * 4. Получение действия от бэкенда
 * 5. Выполнение действия через [CJXplorerAccessibilityService]
 * 6. Возврат к шагу 1
 */
@AndroidEntryPoint
class CJXplorerNavigationService : Service() {

    @Inject
    lateinit var wsClient: CJXplorerWebSocketClient

    private var screenCapture: CJXplorerScreenCapture? = null
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var navigationJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val taskId = intent?.getStringExtra(EXTRA_TASK_ID)
        val projectionResultCode = intent?.getIntExtra(EXTRA_PROJECTION_RESULT_CODE, -1) ?: -1
        val projectionData = intent?.getParcelableExtra<Intent>(EXTRA_PROJECTION_DATA)

        Log.i(TAG, "Navigation service started for task: $taskId")

        val notification = buildNotification()
        startForeground(NOTIFICATION_ID, notification)

        if (taskId == null) {
            Log.e(TAG, "No task ID provided, stopping")
            stopSelf()
            return START_NOT_STICKY
        }

        val capture = CJXplorerScreenCapture(this)
        if (projectionData != null && projectionResultCode != -1) {
            capture.onPermissionResult(projectionResultCode, projectionData)
        }
        screenCapture = capture

        wsClient.connect(taskId)
        startNavigationLoop()

        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        Log.i(TAG, "Navigation service destroyed")
        navigationJob?.cancel()
        wsClient.disconnect()
        screenCapture?.release()
        screenCapture = null
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun startNavigationLoop() {
        navigationJob = serviceScope.launch {
            delay(INITIAL_DELAY_MS)

            wsClient.actions.collect { action ->
                Log.i(TAG, "Received action: $action")

                if (action is NavigationAction.Done) {
                    Log.i(TAG, "Navigation complete")
                    stop(this@CJXplorerNavigationService)
                    return@collect
                }

                val a11y = CJXplorerAccessibilityService.instance
                if (a11y == null) {
                    Log.e(TAG, "AccessibilityService not available")
                    return@collect
                }

                val success = a11y.performAction(action)
                Log.i(TAG, "Action performed: success=$success")

                delay(ACTION_SETTLE_DELAY_MS)

                sendScreenState()
            }
        }

        serviceScope.launch {
            delay(INITIAL_DELAY_MS)
            sendScreenState()
        }
    }

    private suspend fun sendScreenState() {
        try {
            val a11y = CJXplorerAccessibilityService.instance
            val nodeTree = a11y?.getNodeTree()

            val capture = screenCapture
            val screenshot = if (capture?.isReady == true) {
                val dm = getDisplayMetrics()
                capture.capture(dm.widthPixels, dm.heightPixels, dm.densityDpi)
            } else {
                Log.w(TAG, "ScreenCapture not ready, sending empty screenshot")
                ""
            }

            val wsNodes = if (nodeTree != null) {
                listOf(nodeTree.toWs())
            } else {
                emptyList()
            }

            wsClient.sendState(
                WsOutgoingState(
                    screenshot = screenshot,
                    nodes = wsNodes
                )
            )
            Log.i(TAG, "Screen state sent (screenshot=${screenshot.length} chars, nodes=${wsNodes.size})")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send screen state", e)
        }
    }

    private fun getDisplayMetrics(): DisplayMetrics {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        return metrics
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

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.navigation_channel_name),
            NotificationManager.IMPORTANCE_LOW
        )
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification =
        Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.navigation_notification_title))
            .setContentText(getString(R.string.navigation_notification_text))
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .build()

    companion object {
        private const val TAG = "CJXplorerNavService"
        private const val CHANNEL_ID = "cjxplorer_navigation"
        private const val NOTIFICATION_ID = 1
        private const val INITIAL_DELAY_MS = 1000L
        private const val ACTION_SETTLE_DELAY_MS = 800L

        const val EXTRA_TASK_ID = "task_id"
        const val EXTRA_PROJECTION_RESULT_CODE = "projection_result_code"
        const val EXTRA_PROJECTION_DATA = "projection_data"

        fun start(
            context: Context,
            taskId: String,
            projectionResultCode: Int? = null,
            projectionData: Intent? = null
        ) {
            val intent = Intent(context, CJXplorerNavigationService::class.java).apply {
                putExtra(EXTRA_TASK_ID, taskId)
                if (projectionResultCode != null && projectionData != null) {
                    putExtra(EXTRA_PROJECTION_RESULT_CODE, projectionResultCode)
                    putExtra(EXTRA_PROJECTION_DATA, projectionData)
                }
            }
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CJXplorerNavigationService::class.java))
        }
    }
}
