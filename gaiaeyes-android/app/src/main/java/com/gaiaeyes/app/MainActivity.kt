package com.gaiaeyes.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.gaiaeyes.app.ui.GaiaEyesApp
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )

        val container = (application as GaiaEyesApplication).container
        container.authRepository.handleDeepLink(intent)
        intent.data = null
        setContent {
            GaiaEyesTheme {
                GaiaEyesApp(
                    authRepository = container.authRepository,
                    bodyRepository = container.bodyRepository,
                    dashboardRepository = container.dashboardRepository,
                    healthRepository = container.healthRepository,
                    homeContextRepository = container.homeContextRepository,
                    journalRepository = container.journalRepository,
                    outlookRepository = container.outlookRepository,
                    patternsRepository = container.patternsRepository,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        (application as GaiaEyesApplication).container.authRepository.handleDeepLink(intent)
        intent.data = null
        setIntent(intent)
    }
}
