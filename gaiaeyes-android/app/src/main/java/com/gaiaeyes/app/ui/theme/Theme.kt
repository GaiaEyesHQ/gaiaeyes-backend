package com.gaiaeyes.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val GaiaEyesDarkColors = darkColorScheme(
    primary = GaiaBlue,
    secondary = GaiaGreen,
    tertiary = GaiaAmber,
    background = GaiaNavy,
    surface = GaiaPanel,
    onPrimary = GaiaNavy,
    onBackground = Color.White,
    onSurface = Color.White,
)

@Composable
fun GaiaEyesTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = GaiaEyesDarkColors,
        content = content,
    )
}

