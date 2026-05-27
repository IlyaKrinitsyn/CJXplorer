package com.cjxplorer.android.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.cjxplorer.android.R

/**
 * Foreground Service для навигации по клиентскому пути.
 * Поддерживает WebSocket-соединение и координирует
 * AccessibilityService + MediaProjection.
 */
class CJXplorerNavigationService : Service() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val taskId = intent?.getStringExtra(EXTRA_TASK_ID)
        Log.i(TAG, "Navigation service started for task: $taskId")

        val notification = buildNotification()
        startForeground(NOTIFICATION_ID, notification)

        // TODO: запуск навигационного цикла (шаг 3)

        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        Log.i(TAG, "Navigation service destroyed")
        super.onDestroy()
    }

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
        const val EXTRA_TASK_ID = "task_id"

        fun start(context: Context, taskId: String) {
            val intent = Intent(context, CJXplorerNavigationService::class.java).apply {
                putExtra(EXTRA_TASK_ID, taskId)
            }
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CJXplorerNavigationService::class.java))
        }
    }
}
