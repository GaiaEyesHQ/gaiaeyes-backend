package com.gaiaeyes.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.gaiaeyes.app.data.BillingController
import com.gaiaeyes.app.data.BillingState
import com.gaiaeyes.app.data.PlusPlan
import com.gaiaeyes.app.ui.theme.GaiaPanel

@Composable
internal fun BillingSettingsCard(controller: BillingController, isGuest: Boolean, onPurchase: (String) -> Unit) {
    val state by controller.state.collectAsStateWithLifecycle()
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { controller.refresh() }
    BillingSettingsContent(state, isGuest, onPurchase, { controller.restore() }, { controller.refresh() })
}

@Composable
internal fun BillingSettingsContent(
    state: BillingState,
    isGuest: Boolean,
    onPurchase: (String) -> Unit,
    onRestore: () -> Unit,
    onRefresh: () -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    Card(colors = CardDefaults.cardColors(containerColor = GaiaPanel), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Gaia Eyes Plus", style = MaterialTheme.typography.titleLarge, modifier = Modifier.fillMaxWidth())
            Text(when {
                state.backendPlus == true -> "Plus access is active on your Gaia Eyes account."
                state.storePlus == true -> "Your purchase is active. Account membership is syncing."
                state.backendPlus == false -> "Your account is using Gaia Eyes Free."
                else -> "Your membership status has not been confirmed."
            }, modifier = Modifier.fillMaxWidth())
            if (isGuest) Text("Add a recovery email in Account below to protect your membership and use it on other devices.",
                modifier = Modifier.fillMaxWidth())
            if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            state.message?.let { Text(it, modifier = Modifier.fillMaxWidth()) }
            if (state.backendPlus != true && state.storePlus != true) {
                state.products.forEach { product ->
                    val term = if (product.plan == PlusPlan.MONTHLY) "month" else "year"
                    Text("${product.plan.label} · regular price ${product.price} / $term", modifier = Modifier.fillMaxWidth())
                    Button(onClick = { onPurchase(product.id) }, enabled = state.canPurchase,
                        modifier = Modifier.fillMaxWidth()) {
                        Text("Continue with ${product.plan.label.lowercase()} Plus",
                            modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
                    }
                }
                if (state.products.isNotEmpty()) {
                    Text("Google Play shows any available offer, the final price and renewal terms before you confirm.",
                        modifier = Modifier.fillMaxWidth())
                }
            }
            Text("Use the Gaia Eyes account you originally subscribed with. Restore checks purchases from the Google Play account on this device.",
                modifier = Modifier.fillMaxWidth())
            OutlinedButton(onClick = onRestore,
                enabled = state.accountId != null && state.storeAvailable && !state.busy,
                modifier = Modifier.fillMaxWidth()) { Text("Restore purchases") }
            TextButton(onClick = onRefresh, enabled = state.accountId != null && !state.busy) {
                Text("Refresh membership")
            }
            TextButton(onClick = {
                uriHandler.openUri("https://play.google.com/store/account/subscriptions")
            }) { Text("Manage Google Play subscriptions") }
        }
    }
}
