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
        routeIntent(intent)
        setContent {
            GaiaEyesTheme {
                GaiaEyesApp(
                    authRepository = container.authRepository,
                    bodyRepository = container.bodyRepository,
                    dashboardRepository = container.dashboardRepository,
                    healthRepository = container.healthRepository,
                    healthConnectRepository = container.healthConnectRepository,
                    homeContextRepository = container.homeContextRepository,
                    journalRepository = container.journalRepository,
                    outlookRepository = container.outlookRepository,
                    patternsRepository = container.patternsRepository,
                    quickLogCoordinator = container.quickLogCoordinator,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        routeIntent(intent)
        setIntent(intent)
    }

    private fun routeIntent(intent: Intent) {
        val container = (application as GaiaEyesApplication).container
        val handledAsQuickLog = container.quickLogCoordinator.handleIntent(intent)
        if (!handledAsQuickLog) {
            container.authRepository.handleDeepLink(intent)
        }
        intent.data = null
        intent.action = Intent.ACTION_MAIN
    }
}
