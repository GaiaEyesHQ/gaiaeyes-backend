package com.gaiaeyes.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme

/** Health Connect's privacy entry is available without an account or health access. */
class HealthPermissionsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GaiaEyesTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    var browserUnavailable by remember { mutableStateOf(false) }
                    Column(
                        modifier = Modifier
                            .safeDrawingPadding()
                            .verticalScroll(rememberScrollState())
                            .padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Text("Health Connect and your data", style = MaterialTheme.typography.headlineSmall)
                        Text("Connecting Health Connect is optional. You can use Gaia Eyes without connecting it.")
                        Text("With your permission, Gaia Eyes reads sleep, steps, heart rate, resting heart rate, respiratory rate, and oxygen saturation. These readings add body context to your gauges and help you compare your health patterns with environmental conditions.")
                        Text("Imported readings are sent to Gaia Eyes and stored with your account. Readings waiting to sync are kept on your device until they can be uploaded. Gaia Eyes does not write records to Health Connect.")
                        Text("You can change or remove access in Health Connect. Removing permission stops future reads; it does not by itself delete information already imported into Gaia Eyes.")
                        Button(onClick = {
                            try {
                                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(PRIVACY_POLICY_URL)))
                                browserUnavailable = false
                            } catch (_: ActivityNotFoundException) {
                                browserUnavailable = true
                            }
                        }) {
                            Text("Read the full privacy policy")
                        }
                        if (browserUnavailable) {
                            Text("Open $PRIVACY_POLICY_URL in a browser, or contact help@gaiaeyes.com for privacy support.")
                        }
                        TextButton(onClick = ::finish) { Text("Back") }
                    }
                }
            }
        }
    }

    private companion object {
        const val PRIVACY_POLICY_URL = "https://gaiaeyes.com/privacy-policy/"
    }
}
