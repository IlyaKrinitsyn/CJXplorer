package com.cjxplorer.android.service

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * Обёртка над MediaProjection для захвата скриншотов.
 * Жизненный цикл: requestPermission -> onPermissionResult -> capture -> release.
 */
class CJXplorerScreenCapture(private val context: Context) {

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null

    private val handler = Handler(Looper.getMainLooper())

    val projectionManager: MediaProjectionManager
        get() = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

    fun createScreenCaptureIntent(): Intent = projectionManager.createScreenCaptureIntent()

    fun onPermissionResult(resultCode: Int, data: Intent) {
        mediaProjection = projectionManager.getMediaProjection(resultCode, data)
    }

    val isReady: Boolean get() = mediaProjection != null

    /**
     * Захватывает один кадр экрана и возвращает JPEG base64.
     */
    suspend fun capture(width: Int, height: Int, densityDpi: Int): String {
        val bitmap = captureBitmap(width, height, densityDpi)
        return try {
            bitmapToBase64(bitmap)
        } finally {
            bitmap.recycle()
        }
    }

    /**
     * Захватывает один кадр как [Bitmap] (вызывающий код должен recycle).
     */
    suspend fun captureBitmap(width: Int, height: Int, densityDpi: Int): Bitmap =
        suspendCancellableCoroutine { cont ->
            val projection = mediaProjection
            if (projection == null) {
                cont.resumeWithException(IllegalStateException("MediaProjection not initialized"))
                return@suspendCancellableCoroutine
            }

            val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
            imageReader = reader

            val display = projection.createVirtualDisplay(
                "CJXplorerCapture",
                width, height, densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface, null, handler
            )
            virtualDisplay = display

            reader.setOnImageAvailableListener({ ir ->
                val image = ir.acquireLatestImage()
                if (image != null) {
                    try {
                        val plane = image.planes[0]
                        val buffer = plane.buffer
                        val pixelStride = plane.pixelStride
                        val rowStride = plane.rowStride
                        val rowPadding = rowStride - pixelStride * width

                        val bitmap = Bitmap.createBitmap(
                            width + rowPadding / pixelStride,
                            height,
                            Bitmap.Config.ARGB_8888
                        )
                        bitmap.copyPixelsFromBuffer(buffer)

                        val cropped = if (bitmap.width != width) {
                            Bitmap.createBitmap(bitmap, 0, 0, width, height).also {
                                bitmap.recycle()
                            }
                        } else {
                            bitmap
                        }

                        display.release()
                        virtualDisplay = null
                        reader.setOnImageAvailableListener(null, null)
                        reader.close()
                        imageReader = null

                        if (cont.isActive) cont.resume(cropped)
                    } catch (e: Exception) {
                        Log.e(TAG, "Error capturing image", e)
                        if (cont.isActive) cont.resumeWithException(e)
                    } finally {
                        image.close()
                    }
                }
            }, handler)

            cont.invokeOnCancellation {
                display.release()
                virtualDisplay = null
                reader.setOnImageAvailableListener(null, null)
                reader.close()
                imageReader = null
            }
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
