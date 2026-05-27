package com.cjxplorer.android.domain.model

sealed class NavigationAction {
    data class Click(val nodeId: String) : NavigationAction()
    data class Scroll(val direction: ScrollDirection) : NavigationAction()
    data class TypeText(val nodeId: String, val text: String) : NavigationAction()
    data class InputNeeded(val nodeId: String, val prompt: String) : NavigationAction()
    data object Back : NavigationAction()
    data object Done : NavigationAction()
}

enum class ScrollDirection { UP, DOWN, LEFT, RIGHT }
