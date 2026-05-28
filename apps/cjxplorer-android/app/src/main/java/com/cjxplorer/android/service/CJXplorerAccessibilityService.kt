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
        val root = rootInActiveWindow ?: return null
        return AccessibilityNodeParser.parse(root)
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
                    return candidates.first().performAction(AccessibilityNodeInfo.ACTION_CLICK)
                }
                val match = candidates.firstOrNull { node ->
                    node.contentDescription?.toString()?.contains(desc, ignoreCase = true) == true ||
                        node.text?.toString()?.contains(desc, ignoreCase = true) == true
                }
                if (match != null) {
                    Log.i(TAG, "click: by id=$nodeId + desc='$desc'")
                    return match.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                }
                Log.i(TAG, "click: by id=$nodeId (desc='$desc' not matched, using first)")
                return candidates.first().performAction(AccessibilityNodeInfo.ACTION_CLICK)
            }
        }

        // 2. По координатам (bounds) — надёжный вариант, координаты всегда уникальны
        if (click.boundsLeft != null && click.boundsTop != null &&
            click.boundsRight != null && click.boundsBottom != null
        ) {
            val centerX = (click.boundsLeft + click.boundsRight) / 2f
            val centerY = (click.boundsTop + click.boundsBottom) / 2f
            Log.i(TAG, "click: by bounds tap at ($centerX, $centerY)")
            return tapAt(centerX, centerY)
        }

        // 3. По contentDescription / text — когда bounds не доступны
        if (!desc.isNullOrEmpty() && root != null) {
            val byDesc = findNodeByDescription(root, desc)
            if (byDesc != null) {
                Log.i(TAG, "click: by desc='$desc'")
                return byDesc.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            }
        }

        Log.e(TAG, "click: all strategies failed for id=$nodeId, desc=$desc")
        return false
    }

    private fun tapAt(x: Float, y: Float): Boolean {
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
            if (node.isClickable) return node
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

    private fun performScroll(direction: ScrollDirection): Boolean {
        val scrollAction = when (direction) {
            ScrollDirection.DOWN, ScrollDirection.RIGHT ->
                AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            ScrollDirection.UP, ScrollDirection.LEFT ->
                AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        }
        val scrollable = findScrollableNode(rootInActiveWindow) ?: return false
        return scrollable.performAction(scrollAction)
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
