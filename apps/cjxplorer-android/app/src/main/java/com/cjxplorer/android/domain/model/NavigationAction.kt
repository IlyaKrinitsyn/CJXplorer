package com.cjxplorer.android.domain.model

sealed class NavigationAction {
    data class Start(val task: String) : NavigationAction()
    data class Click(
        val nodeId: String,
        val desc: String? = null,
        val boundsLeft: Int? = null,
        val boundsTop: Int? = null,
        val boundsRight: Int? = null,
        val boundsBottom: Int? = null
    ) : NavigationAction()
    data class Scroll(val direction: ScrollDirection) : NavigationAction()
    data class TypeText(val nodeId: String, val text: String) : NavigationAction()
    data class InputNeeded(val nodeId: String, val prompt: String) : NavigationAction()
    data object Back : NavigationAction()
    data object Done : NavigationAction()
}

enum class ScrollDirection { UP, DOWN, LEFT, RIGHT }
