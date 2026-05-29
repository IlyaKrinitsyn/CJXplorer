package com.cjxplorer.android.service

import android.graphics.Bitmap
import android.graphics.Canvas
import android.util.Log
import kotlin.math.max
import kotlin.math.min

/**
 * Склеивает несколько скриншотов с перекрытием (overlap) после скролла.
 */
object ScreenshotStitcher {

    private const val TAG = "ScreenshotStitcher"
    const val DEFAULT_OVERLAP_RATIO = 0.25f

    fun stitchVertical(bitmaps: List<Bitmap>, overlapRatio: Float = DEFAULT_OVERLAP_RATIO): Bitmap {
        require(bitmaps.isNotEmpty()) { "No bitmaps to stitch" }
        if (bitmaps.size == 1) return bitmaps.first()

        val overlapPx = (bitmaps.first().height * overlapRatio).toInt()
        val width = bitmaps.first().width
        val totalHeight = bitmaps.sumOf { it.height } - overlapPx * (bitmaps.size - 1)
        val result = Bitmap.createBitmap(width, totalHeight, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(result)

        var y = 0
        for (i in bitmaps.indices) {
            val bmp = bitmaps[i]
            val srcTop = if (i == 0) 0 else overlapPx
            val sliceHeight = bmp.height - srcTop
            val slice = Bitmap.createBitmap(bmp, 0, srcTop, bmp.width, sliceHeight)
            canvas.drawBitmap(slice, 0f, y.toFloat(), null)
            slice.recycle()
            y += sliceHeight
        }

        Log.i(TAG, "stitchVertical: ${bitmaps.size} frames -> ${width}x$totalHeight")
        return result
    }

    fun stitchHorizontal(bitmaps: List<Bitmap>, overlapRatio: Float = DEFAULT_OVERLAP_RATIO): Bitmap {
        require(bitmaps.isNotEmpty()) { "No bitmaps to stitch" }
        if (bitmaps.size == 1) return bitmaps.first()

        val overlapPx = (bitmaps.first().width * overlapRatio).toInt()
        val height = bitmaps.first().height
        val totalWidth = bitmaps.sumOf { it.width } - overlapPx * (bitmaps.size - 1)
        val result = Bitmap.createBitmap(totalWidth, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(result)

        var x = 0
        for (i in bitmaps.indices) {
            val bmp = bitmaps[i]
            val srcLeft = if (i == 0) 0 else overlapPx
            val sliceWidth = bmp.width - srcLeft
            val slice = Bitmap.createBitmap(bmp, srcLeft, 0, sliceWidth, bmp.height)
            canvas.drawBitmap(slice, x.toFloat(), 0f, null)
            slice.recycle()
            x += sliceWidth
        }

        Log.i(TAG, "stitchHorizontal: ${bitmaps.size} frames -> ${totalWidth}x$height")
        return result
    }

    /**
     * Уменьшает bitmap, если превышает лимиты (чтобы не раздувать WebSocket payload).
     */
    fun constrainSize(bitmap: Bitmap, maxWidth: Int, maxHeight: Int): Bitmap {
        var w = bitmap.width
        var h = bitmap.height
        if (w <= maxWidth && h <= maxHeight) return bitmap

        val scale = min(maxWidth.toFloat() / w, maxHeight.toFloat() / h)
        val newW = max(1, (w * scale).toInt())
        val newH = max(1, (h * scale).toInt())
        Log.i(TAG, "constrainSize: ${w}x$h -> ${newW}x$newH")
        val scaled = Bitmap.createScaledBitmap(bitmap, newW, newH, true)
        if (scaled !== bitmap) bitmap.recycle()
        return scaled
    }

    /**
     * Грубая проверка: два кадра почти одинаковые (скролл не сдвинул контент).
     */
    fun areSimilar(a: Bitmap, b: Bitmap, sampleStep: Int = 32): Boolean {
        if (a.width != b.width || a.height != b.height) return false
        var diff = 0
        var samples = 0
        val w = a.width
        val h = a.height
        var y = h / 4
        while (y < h * 3 / 4) {
            var x = w / 4
            while (x < w * 3 / 4) {
                val pa = a.getPixel(x, y)
                val pb = b.getPixel(x, y)
                if (pa != pb) diff++
                samples++
                x += sampleStep
            }
            y += sampleStep
        }
        if (samples == 0) return true
        return diff.toFloat() / samples < 0.02f
    }
}
