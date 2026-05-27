package com.cjxplorer.android.domain.model

data class ScreenState(
    val screenshotBase64: String,
    val nodes: List<AccessibilityNode>
)

data class AccessibilityNode(
    val id: String,
    val className: String = "",
    val text: String = "",
    val contentDescription: String = "",
    val bounds: NodeBounds,
    val isClickable: Boolean = false,
    val isScrollable: Boolean = false,
    val children: List<AccessibilityNode> = emptyList()
)

data class NodeBounds(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int
)
