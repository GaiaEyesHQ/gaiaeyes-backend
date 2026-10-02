package com.gaiaeyes.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import com.gaiaeyes.app.data.AccountDeletionPhase
import com.gaiaeyes.app.data.AccountDeletionState

@Composable
internal fun AccountDeletionScreen(
    state: AccountDeletionState,
    accountLabel: String,
    onConfirm: () -> Unit,
    onRetry: () -> Unit,
    onRetryCleanup: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var acknowledged by rememberSaveable(state.accountId, state.phase) { mutableStateOf(false) }
    val uriHandler = LocalUriHandler.current
    val canClose = !state.syncPaused && state.phase != AccountDeletionPhase.DELETING
    BackHandler { if (canClose) onClose() }
    Surface(modifier = modifier.fillMaxSize()) {
        Column(
            Modifier.safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Delete account", style = MaterialTheme.typography.headlineMedium)
            if (state.accountId != null) Text(accountLabel)
            when (state.phase) {
                AccountDeletionPhase.CHECKING -> {
                    CircularProgressIndicator()
                    Text("Checking whether this account can be deleted…")
                }
                AccountDeletionPhase.CONFIRM -> {
                    Text("Permanently delete this Gaia Eyes account and its account-linked data handled by the deletion service? This cannot be undone.")
                    Text("After the service confirms deletion, this device’s cached account data and queued entries will be removed and you will be signed out.")
                    Text("Deleting your account does not cancel a store subscription. Manage any active subscription separately in Google Play or the store where you subscribed.")
                    Text("Records in Health Connect or other providers are separate. This action does not confirm erasure from provider systems or backups.")
                    if (state.syncPaused) Text("Sync remains paused while you retry. Some server data may already have been deleted.")
                    Row {
                        Checkbox(checked = acknowledged, onCheckedChange = { acknowledged = it })
                        Text("I understand that deletion is permanent.", Modifier.padding(top = 12.dp).weight(1f))
                    }
                    Button(
                        onClick = onConfirm, enabled = acknowledged,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Permanently delete my account") }
                }
                AccountDeletionPhase.DELETING -> {
                    CircularProgressIndicator()
                    Text("Finishing account deletion and local cleanup. Sync is paused. A submitted request cannot be cancelled here.")
                }
                AccountDeletionPhase.UNAVAILABLE -> {
                    Text("The deletion check could not be completed. No deletion request was sent. Check your connection and try again.")
                    Button(onClick = onRetry) { Text("Try again") }
                }
                AccountDeletionPhase.UNCONFIRMED -> {
                    Text("Deletion is not confirmed. Some server data may already have been deleted. Sync stays paused, including after restarting the app.")
                    Text("Check again to review a new deletion attempt, or contact support if your session no longer works. There is no automatic retry.")
                    Button(onClick = onRetry) { Text("Check deletion again") }
                }
                AccountDeletionPhase.CLEANUP_REQUIRED -> {
                    Text("The service confirmed account deletion, but local cleanup has not finished. Sync remains paused.")
                    Button(onClick = onRetryCleanup) { Text("Finish local cleanup") }
                }
                AccountDeletionPhase.COMPLETE -> {
                    Text("The service confirmed account deletion. Cached account data and queued entries on this device were cleared, and the local session was removed.")
                    Text("Any store subscription must still be managed separately. This does not confirm deletion from backups or other providers.")
                }
                AccountDeletionPhase.CLOSED -> Unit
            }
            if (canClose) {
                TextButton(onClick = onClose) {
                    Text(if (state.phase == AccountDeletionPhase.COMPLETE) "Done" else "Cancel")
                }
            } else if (state.phase == AccountDeletionPhase.CONFIRM) {
                TextButton(onClick = onClose) { Text("Back to deletion status") }
            }
            if (state.phase in listOf(AccountDeletionPhase.UNAVAILABLE, AccountDeletionPhase.UNCONFIRMED, AccountDeletionPhase.CLEANUP_REQUIRED)) {
                Text("Support: help@gaiaeyes.com")
                TextButton(onClick = { runCatching { uriHandler.openUri("mailto:help@gaiaeyes.com") } }) {
                    Text("Contact support")
                }
            }
        }
    }
}
