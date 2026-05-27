package com.cjxplorer.android.presentation.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val CJXplorerColorScheme = darkColorScheme(
    primary = CJXplorerGreen,
    secondary = CJXplorerGreenLight,
    background = CJXplorerDark,
    surface = CJXplorerSurface,
    onSurface = CJXplorerOnSurface
)

@Composable
fun CJXplorerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CJXplorerColorScheme,
        typography = CJXplorerTypography,
        content = content
    )
}
