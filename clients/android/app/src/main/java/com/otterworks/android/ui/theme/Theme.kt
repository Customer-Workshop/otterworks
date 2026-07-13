package com.otterworks.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val OtterBlue = Color(0xFF1F6FEB)
private val OtterBlueDark = Color(0xFF1451B0)

private val LightColors = lightColorScheme(
    primary = OtterBlue,
    secondary = OtterBlueDark,
)

private val DarkColors = darkColorScheme(
    primary = OtterBlue,
    secondary = OtterBlueDark,
)

@Composable
fun OtterWorksTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
