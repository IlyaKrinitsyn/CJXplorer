package com.cjxplorer.android.data.websocket

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class WsOutgoingState(
    val type: String = "state",
    val screenshot: String,
    val nodes: List<WsAccessibilityNode>
)

@Serializable
data class WsAccessibilityNode(
    val id: String,
    @SerialName("class_name") val className: String = "",
    val text: String = "",
    @SerialName("content_description") val contentDescription: String = "",
    val bounds: WsBounds,
    val clickable: Boolean = false,
    val scrollable: Boolean = false,
    val children: List<WsAccessibilityNode> = emptyList()
)

@Serializable
data class WsBounds(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int
)

@Serializable
data class WsIncomingMessage(
    val type: String,
    val task: String? = null,
    val action: String? = null,
    @SerialName("node_id") val nodeId: String? = null,
    val direction: String? = null,
    val text: String? = null,
    val value: String? = null,
    val prompt: String? = null
)
