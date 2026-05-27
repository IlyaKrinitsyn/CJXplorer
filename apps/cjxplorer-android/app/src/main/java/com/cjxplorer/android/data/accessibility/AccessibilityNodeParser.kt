package com.cjxplorer.android.data.accessibility

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.cjxplorer.android.domain.model.AccessibilityNode
import com.cjxplorer.android.domain.model.NodeBounds

/**
 * Преобразует дерево AccessibilityNodeInfo в domain-модель.
 */
object AccessibilityNodeParser {

    fun parse(nodeInfo: AccessibilityNodeInfo?, depth: Int = 0): AccessibilityNode? {
        nodeInfo ?: return null
        if (depth > 30) return null

        val bounds = Rect()
        nodeInfo.getBoundsInScreen(bounds)

        val children = mutableListOf<AccessibilityNode>()
        for (i in 0 until nodeInfo.childCount) {
            val child = parse(nodeInfo.getChild(i), depth + 1)
            if (child != null) children.add(child)
        }

        return AccessibilityNode(
            id = nodeInfo.viewIdResourceName.orEmpty(),
            className = nodeInfo.className?.toString().orEmpty(),
            text = nodeInfo.text?.toString().orEmpty(),
            contentDescription = nodeInfo.contentDescription?.toString().orEmpty(),
            bounds = NodeBounds(bounds.left, bounds.top, bounds.right, bounds.bottom),
            isClickable = nodeInfo.isClickable,
            isScrollable = nodeInfo.isScrollable,
            children = children
        )
    }
}
