package com.cjxplorer.android.service

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream

/**
 * Обёртка над MediaProjection для захвата скриншотов.
 * Жизненный цикл: requestPermission -> onPermissionResult -> capture -> release.
 */
class CJXplorerScreenCapture(private val context: Context) {

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null

    val projectionManager: MediaProjectionManager
        get() = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

    fun createScreenCaptureIntent(): Intent = projectionManager.createScreenCaptureIntent()

    fun onPermissionResult(resultCode: Int, data: Intent) {
        mediaProjection = projectionManager.getMediaProjection(resultCode, data)
    }

    fun capture(width: Int, height: Int, densityDpi: Int): String? {
        val projection = mediaProjection ?: return null

        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        virtualDisplay = projection.createVirtualDisplay(
            "CJXplorerCapture",
            width, height, densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface, null, null
        )

        // TODO: реализовать асинхронный захват с ImageReader.OnImageAvailableListener
        // Сейчас — заглушка
        Log.i(TAG, "Screen capture requested (${width}x${height})")
        return null
    }

    fun release() {
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        virtualDisplay = null
        imageReader = null
        mediaProjection = null
    }

    companion object {
        private const val TAG = "CJXplorerCapture"
        const val REQUEST_CODE = 1001

        fun bitmapToBase64(bitmap: Bitmap): String {
            val stream = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 80, stream)
            return Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
        }
    }
}
