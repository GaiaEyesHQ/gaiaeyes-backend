package com.gaiaeyes.app.visualharness

import android.content.Context
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.gaiaeyes.app.ui.MigraineFollowUpForm
import com.gaiaeyes.app.ui.MigraineFollowUpPhase
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme
import java.util.Locale

/** Hosts the exact production form/controller. No HomeViewModel or auth/health startup. */
open class IsolatedFormActivity : ComponentActivity() {
    protected open val harnessFontScale: Float get() = 1f
    internal lateinit var fixture: SyntheticFixture
        private set

    override fun attachBaseContext(newBase: Context) {
        val configuration = Configuration(newBase.resources.configuration).apply {
            fontScale = harnessFontScale
            setLocale(Locale.US)
        }
        super.attachBaseContext(newBase.createConfigurationContext(configuration))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        fixture = SyntheticFixture(this, intent.getStringExtra("scenario") ?: "editable")
        setContent {
            GaiaEyesTheme {
                val state by fixture.controller.state.collectAsState()
                val ui by fixture.controller.ui.collectAsState()
                if (state.phase == MigraineFollowUpPhase.CLOSED) {
                    Surface(Modifier.fillMaxSize()) { Text("Synthetic session closed") }
                } else {
                    MigraineFollowUpForm(state, ui, fixture.controller)
                }
            }
        }
        fixture.controller.open(fixture.item)
    }

    override fun onDestroy() {
        fixture.close()
        super.onDestroy()
    }
}

/** Only the isolated Activity's configuration changes; device and host settings stay intact. */
class IsolatedLargeFontActivity : IsolatedFormActivity() {
    override val harnessFontScale: Float get() = 1.6f
}
