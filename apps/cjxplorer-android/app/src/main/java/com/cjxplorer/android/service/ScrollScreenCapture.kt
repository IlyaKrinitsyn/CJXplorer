package com.cjxplorer.android.service

import android.graphics.Bitmap
import android.util.Log
import com.cjxplorer.android.domain.model.AccessibilityNode
import com.cjxplorer.android.domain.model.ScrollDirection
import kotlinx.coroutines.delay

/**
 * Захват длинного/широкого экрана: несколько скриншотов со скроллом + склейка.
 */
object ScrollScreenCapture {

    private const val TAG = "ScrollScreenCapture"
    private const val MAX_FRAMES = 8
    private const val SCROLL_SETTLE_MS = 700L
    private const val MAX_STITCHED_HEIGHT_MULTIPLIER = 3
    private const val MAX_STITCHED_WIDTH_MULTIPLIER = 2

    enum class StitchAxis { NONE, VERTICAL, HORIZONTAL }

    fun detectStitchAxis(nodeTree: AccessibilityNode?, screenW: Int, screenH: Int): StitchAxis {
        if (nodeTree == null) return StitchAxis.NONE
        val offRight = hasOffScreen(nodeTree, screenW, screenH, horizontal = true)
        val offBottom = hasOffScreen(nodeTree, screenW, screenH, horizontal = false)
        return when {
            offBottom -> StitchAxis.VERTICAL
            offRight -> StitchAxis.HORIZONTAL
            else -> StitchAxis.NONE
        }
    }

    private fun hasOffScreen(
        node: AccessibilityNode,
        screenW: Int,
        screenH: Int,
        horizontal: Boolean
    ): Boolean {
        if (horizontal) {
            if (node.bounds.right > screenW + 50 || node.bounds.left < -50) return true
        } else {
            if (node.bounds.bottom > screenH + 50 || node.bounds.top < -50) return true
        }
        for (child in node.children) {
            if (hasOffScreen(child, screenW, screenH, horizontal)) return true
        }
        return false
    }

    suspend fun capture(
        screenCapture: CJXplorerScreenCapture,
        a11y: CJXplorerAccessibilityService,
        width: Int,
        height: Int,
        densityDpi: Int,
        axis: StitchAxis
    ): String {
        if (axis == StitchAxis.NONE) {
            return screenCapture.capture(width, height, densityDpi)
        }

        val frames = mutableListOf<Bitmap>()
        try {
            val first = screenCapture.captureBitmap(width, height, densityDpi)
            frames.add(first)

            val scrollDirection = when (axis) {
                StitchAxis.VERTICAL -> ScrollDirection.DOWN
                StitchAxis.HORIZONTAL -> ScrollDirection.RIGHT
                StitchAxis.NONE -> return CJXplorerScreenCapture.bitmapToBase64(first)
            }

            while (frames.size < MAX_FRAMES) {
                val scrolled = a11y.scrollForCapture(scrollDirection, width, height)
                if (!scrolled) {
                    Log.i(TAG, "capture: scroll stopped at frame ${frames.size}")
                    break
                }
                delay(SCROLL_SETTLE_MS)

                val next = screenCapture.captureBitmap(width, height, densityDpi)
                if (ScreenshotStitcher.areSimilar(frames.last(), next)) {
                    Log.i(TAG, "capture: frame ${frames.size + 1} similar to previous, stop")
                    next.recycle()
                    break
                }
                frames.add(next)
            }

            val stitched = when (axis) {
                StitchAxis.VERTICAL -> {
                    val maxH = height * MAX_STITCHED_HEIGHT_MULTIPLIER
                    val raw = ScreenshotStitcher.stitchVertical(frames)
                    ScreenshotStitcher.constrainSize(raw, width, maxH)
                }
                StitchAxis.HORIZONTAL -> {
                    val maxW = width * MAX_STITCHED_WIDTH_MULTIPLIER
                    val raw = ScreenshotStitcher.stitchHorizontal(frames)
                    ScreenshotStitcher.constrainSize(raw, maxW, height)
                }
                StitchAxis.NONE -> frames.first()
            }

            val scrollSteps = frames.size - 1
            frames.forEach { if (it !== stitched) it.recycle() }
            Log.i(TAG, "capture: axis=$axis, frames=${scrollSteps + 1}, result=${stitched.width}x${stitched.height}")

            restoreScrollPosition(a11y, width, height, axis, scrollSteps)

            return CJXplorerScreenCapture.bitmapToBase64(stitched).also { stitched.recycle() }
        } catch (e: Exception) {
            Log.e(TAG, "capture failed, fallback to single frame", e)
            frames.forEach { it.recycle() }
            return screenCapture.capture(width, height, densityDpi)
        }
    }

    private suspend fun restoreScrollPosition(
        a11y: CJXplorerAccessibilityService,
        width: Int,
        height: Int,
        axis: StitchAxis,
        scrollCount: Int
    ) {
        if (scrollCount <= 0) return
        val restoreDirection = when (axis) {
            StitchAxis.VERTICAL -> ScrollDirection.UP
            StitchAxis.HORIZONTAL -> ScrollDirection.LEFT
            StitchAxis.NONE -> return
        }
        repeat(scrollCount) {
            a11y.scrollForCapture(restoreDirection, width, height)
            delay(SCROLL_SETTLE_MS)
        }
        Log.i(TAG, "restoreScrollPosition: $scrollCount x $restoreDirection")
    }
}
