package com.cjxplorer.android.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.cjxplorer.android.data.accessibility.AccessibilityNodeParser
import com.cjxplorer.android.domain.model.AccessibilityNode
import com.cjxplorer.android.domain.model.NavigationAction
import com.cjxplorer.android.domain.model.ScrollDirection

/**
 * AccessibilityService для навигации по приложениям.
 * Предоставляет дерево UI-нод и выполняет действия (клик, скролл, ввод текста).
 */
class CJXplorerAccessibilityService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Не реагируем на события — работаем по запросу
    }

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted")
    }

    fun getNodeTree(): AccessibilityNode? {
        for (attempt in 1..ROOT_RETRY_COUNT) {
            val root = rootInActiveWindow
            if (root != null) {
                return AccessibilityNodeParser.parse(root)
            }
            if (attempt < ROOT_RETRY_COUNT) {
                Log.w(TAG, "rootInActiveWindow is null (attempt $attempt/$ROOT_RETRY_COUNT), retrying...")
                Thread.sleep(ROOT_RETRY_DELAY_MS)
            }
        }
        Log.e(TAG, "rootInActiveWindow is null after $ROOT_RETRY_COUNT attempts")
        return null
    }

    fun performAction(action: NavigationAction): Boolean = when (action) {
        is NavigationAction.Click -> findAndClick(action)
        is NavigationAction.Scroll -> performScroll(action.direction)
        is NavigationAction.TypeText -> findAndType(action.nodeId, action.text)
        is NavigationAction.Back -> performGlobalAction(GLOBAL_ACTION_BACK)
        else -> false
    }

    private fun findAndClick(click: NavigationAction.Click): Boolean {
        val root = rootInActiveWindow
        val nodeId = click.nodeId
        val desc = click.desc

        // 1. По viewIdResourceName
        if (nodeId.isNotEmpty() && root != null) {
            val candidates = root.findAccessibilityNodeInfosByViewId(nodeId)
            if (!candidates.isNullOrEmpty()) {
                if (candidates.size == 1 || desc.isNullOrEmpty()) {
                    Log.i(TAG, "click: by id=$nodeId (${candidates.size} found)")
                    return scrollToAndClick(candidates.first())
                }
                val match = candidates.firstOrNull { node ->
                    node.contentDescription?.toString()?.contains(desc, ignoreCase = true) == true ||
                        node.text?.toString()?.contains(desc, ignoreCase = true) == true
                }
                if (match != null) {
                    Log.i(TAG, "click: by id=$nodeId + desc='$desc'")
                    return scrollToAndClick(match)
                }
                Log.i(TAG, "click: by id=$nodeId (desc='$desc' not matched, using first)")
                return scrollToAndClick(candidates.first())
            }
        }

        // 2. По координатам (bounds) — только если элемент на экране
        if (click.boundsLeft != null && click.boundsTop != null &&
            click.boundsRight != null && click.boundsBottom != null
        ) {
            val centerX = (click.boundsLeft + click.boundsRight) / 2f
            val centerY = (click.boundsTop + click.boundsBottom) / 2f
            if (centerX > 0 && centerY > 0 &&
                click.boundsRight > click.boundsLeft &&
                click.boundsBottom > click.boundsTop
            ) {
                Log.i(TAG, "click: by bounds tap at ($centerX, $centerY)")
                return tapAt(centerX, centerY)
            }
            Log.w(TAG, "click: bounds off-screen (center=$centerX,$centerY), skipping tap")
        }

        // 3. По contentDescription / text — с автоскроллом до элемента
        if (!desc.isNullOrEmpty() && root != null) {
            val byDesc = findNodeByDescription(root, desc)
            if (byDesc != null) {
                Log.i(TAG, "click: by desc='$desc', visible=${byDesc.isVisibleToUser}")
                return scrollToAndClick(byDesc)
            }
        }

        Log.e(TAG, "click: all strategies failed for id=$nodeId, desc=$desc")
        return false
    }

    @Suppress("DEPRECATION")
    private fun scrollToAndClick(node: AccessibilityNodeInfo): Boolean {
        if (!node.isVisibleToUser) {
            Log.i(TAG, "scrollToAndClick: element not visible, scrolling into view...")
            node.performAction(
                AccessibilityNodeInfo.AccessibilityAction.ACTION_SHOW_ON_SCREEN.id
            )
            Thread.sleep(SCROLL_SETTLE_MS)
        }

        if (node.isClickable) {
            return node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }

        val clickableParent = findClickableParent(node)
        if (clickableParent != null) {
            Log.i(TAG, "scrollToAndClick: using clickable parent")
            return clickableParent.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }

        val bounds = android.graphics.Rect()
        node.getBoundsInScreen(bounds)
        val cx = (bounds.left + bounds.right) / 2f
        val cy = (bounds.top + bounds.bottom) / 2f
        if (cx > 0 && cy > 0) {
            Log.i(TAG, "scrollToAndClick: tapping at ($cx, $cy)")
            return tapAt(cx, cy)
        }

        Log.e(TAG, "scrollToAndClick: failed, bounds=($bounds)")
        return false
    }

    private fun findClickableParent(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current = node.parent
        while (current != null) {
            if (current.isClickable) return current
            current = current.parent
        }
        return null
    }

    private fun tapAt(x: Float, y: Float): Boolean {
        if (x < 0 || y < 0) {
            Log.e(TAG, "tapAt: invalid coordinates ($x, $y)")
            return false
        }
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 100)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        return dispatchGesture(gesture, null, null)
    }

    private fun findNodeByDescription(
        node: AccessibilityNodeInfo,
        desc: String
    ): AccessibilityNodeInfo? {
        val nodeDesc = node.contentDescription?.toString().orEmpty()
        val nodeText = node.text?.toString().orEmpty()
        if (nodeDesc.contains(desc, ignoreCase = true) || nodeText.contains(desc, ignoreCase = true)) {
            return node
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findNodeByDescription(child, desc)
            if (result != null) return result
        }
        return null
    }

    private fun findAndType(nodeId: String, text: String): Boolean {
        val node = findNodeById(nodeId) ?: return false
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun scrollForCapture(direction: ScrollDirection, screenWidth: Int, screenHeight: Int): Boolean {
        val scrollAction = when (direction) {
            ScrollDirection.DOWN, ScrollDirection.RIGHT ->
                AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            ScrollDirection.UP, ScrollDirection.LEFT ->
                AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        }
        val scrollable = findScrollableNode(rootInActiveWindow)
        if (scrollable?.performAction(scrollAction) == true) {
            Log.i(TAG, "scrollForCapture: by a11y action $direction")
            return true
        }
        val byGesture = swipeScroll(direction, screenWidth, screenHeight)
        if (byGesture) Log.i(TAG, "scrollForCapture: by gesture $direction")
        return byGesture
    }

    private fun swipeScroll(direction: ScrollDirection, screenWidth: Int, screenHeight: Int): Boolean {
        val cx = screenWidth / 2f
        val cy = screenHeight / 2f
        val path = Path()
        when (direction) {
            ScrollDirection.DOWN -> {
                path.moveTo(cx, screenHeight * 0.75f)
                path.lineTo(cx, screenHeight * 0.25f)
            }
            ScrollDirection.UP -> {
                path.moveTo(cx, screenHeight * 0.25f)
                path.lineTo(cx, screenHeight * 0.75f)
            }
            ScrollDirection.RIGHT -> {
                path.moveTo(screenWidth * 0.75f, cy)
                path.lineTo(screenWidth * 0.25f, cy)
            }
            ScrollDirection.LEFT -> {
                path.moveTo(screenWidth * 0.25f, cy)
                path.lineTo(screenWidth * 0.75f, cy)
            }
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 350)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        return dispatchGesture(gesture, null, null)
    }

    private fun performScroll(direction: ScrollDirection): Boolean {
        if (rootInActiveWindow == null) return false
        val dm = resources.displayMetrics
        return scrollForCapture(direction, dm.widthPixels, dm.heightPixels)
    }

    private fun findNodeById(id: String): AccessibilityNodeInfo? {
        val root = rootInActiveWindow ?: return null
        val nodes = root.findAccessibilityNodeInfosByViewId(id)
        return nodes?.firstOrNull()
    }

    private fun findScrollableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        node ?: return null
        if (node.isScrollable) return node
        for (i in 0 until node.childCount) {
            val result = findScrollableNode(node.getChild(i))
            if (result != null) return result
        }
        return null
    }

    companion object {
        private const val TAG = "CJXplorerA11y"
        private const val SCROLL_SETTLE_MS = 600L
        private const val ROOT_RETRY_COUNT = 5
        private const val ROOT_RETRY_DELAY_MS = 500L
        var instance: CJXplorerAccessibilityService? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "Accessibility service connected")
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }
}
