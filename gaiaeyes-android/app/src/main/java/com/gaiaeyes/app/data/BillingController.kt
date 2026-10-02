package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

enum class PlusPlan(val label: String, val period: String) {
    MONTHLY("Monthly", "P1M"), YEARLY("Yearly", "P1Y"),
}

data class BillingProduct(val id: String, val plan: PlusPlan, val price: String)

data class BillingConfig(val apiKey: String, val productIds: Map<PlusPlan, String>) {
    val storeAvailable: Boolean get() = clean(apiKey).isNotEmpty()
    val configuredProducts: Map<PlusPlan, String> get() = productIds.mapValues { clean(it.value) }
        .filterValues { it.isNotEmpty() }

    companion object {
        private fun clean(value: String) = value.trim().takeUnless { it.startsWith("$(") }.orEmpty()
    }
}

interface BillingStore {
    suspend fun identify(accountId: String)
    suspend fun signOut()
    suspend fun products(): List<BillingProduct>
    suspend fun hasPlus(): Boolean
    suspend fun restore(): Boolean
}

enum class BillingFailure { CANCELLED, PENDING, UNAVAILABLE, FAILED }
class BillingStoreException(val reason: BillingFailure) : Exception(reason.name)

data class BillingState(
    val accountId: String? = null,
    val busy: Boolean = false,
    val storeAvailable: Boolean = false,
    val products: List<BillingProduct> = emptyList(),
    val backendPlus: Boolean? = null,
    val storePlus: Boolean? = null,
    val message: String? = null,
) {
    val canPurchase: Boolean get() = accountId != null && !busy && storeAvailable &&
        backendPlus == false && storePlus == false
}

/** Main-thread controller. All SDK identity changes and transactions share one lock.
 * An account transition clears the visible state immediately, but never cancels a
 * store callback and releases the lock early while that transaction is still running.
 */
class BillingController(
    private val config: BillingConfig,
    private val store: BillingStore,
    private val scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val readBackend: suspend (String) -> Boolean,
) {
    private val mutableState = MutableStateFlow(BillingState())
    val state = mutableState.asStateFlow()
    private val storeLock = Mutex()
    private var generation = 0L

    fun authChanged(auth: AuthState) {
        val account = when (auth) {
            is AuthState.SignedIn -> auth.accountId
            AuthState.Initializing, is AuthState.SessionProblem ->
                state.value.accountId?.takeIf { it == currentAccountId() }
            else -> null
        }
        if (account == state.value.accountId) return
        generation++
        mutableState.value = BillingState(accountId = account, storeAvailable = config.storeAvailable)
        if (account == null) {
            // A later login is queued behind this logout, including after a failed transaction.
            scope.launch { storeLock.withLock { runCatching { store.signOut() } } }
        } else {
            refresh()
        }
    }

    fun refresh(): Job? = operation { account, ticket ->
        var issue: String? = null
        var backend: Boolean? = null
        var customer: Boolean? = null
        var products = emptyList<BillingProduct>()
        try {
            backend = readBackend(account)
        } catch (error: Exception) {
            if (error is CancellationException) throw error
            issue = "Membership status could not be checked. Try refreshing."
        }
        requireCurrent(account, ticket)
        if (config.storeAvailable) {
            try {
                store.identify(account)
                requireCurrent(account, ticket)
                customer = store.hasPlus()
                requireCurrent(account, ticket)
                products = store.products()
                if (products.isEmpty() && backend != true && customer != true) {
                    issue = issue ?: "Plus plans are unavailable from Google Play right now."
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                issue = issue ?: "Google Play billing could not be loaded. Try refreshing."
            }
        } else {
            issue = issue ?: "Purchases and restore are unavailable in this build."
        }
        requireCurrent(account, ticket)
        mutableState.value = state.value.copy(
            backendPlus = backend, storePlus = customer, products = products, message = issue,
        )
    }

    fun purchase(productId: String, purchase: suspend () -> Boolean): Job? {
        if (!state.value.canPurchase || state.value.products.none { it.id == productId }) return null
        return transaction(purchase, restoring = false)
    }

    fun restore(): Job? {
        if (!config.storeAvailable) return null
        return transaction(store::restore, restoring = true)
    }

    private fun transaction(action: suspend () -> Boolean, restoring: Boolean): Job? = operation { account, ticket ->
        store.identify(account)
        requireCurrent(account, ticket)
        if (!restoring) {
            val existingStore = store.hasPlus()
            requireCurrent(account, ticket)
            val existingBackend = readBackend(account)
            requireCurrent(account, ticket)
            if (existingStore || existingBackend) {
                mutableState.value = state.value.copy(storePlus = existingStore, backendPlus = existingBackend,
                    message = "A membership is already active. Refresh its status or manage your existing subscription.")
                return@operation
            }
        }
        val active = action()
        requireCurrent(account, ticket)
        // Receipt confirmation is not a fabricated backend entitlement. A webhook may still be in flight.
        mutableState.value = state.value.copy(storePlus = if (active || restoring) active else null, backendPlus = null)
        var backend: Boolean? = null
        try {
            backend = readBackend(account)
        } catch (error: Exception) {
            if (error is CancellationException) throw error
        }
        requireCurrent(account, ticket)
        mutableState.value = state.value.copy(
            backendPlus = backend,
            message = when {
                backend == true -> "Your Gaia Eyes membership is active."
                active -> "Purchase confirmed. Your account membership is still syncing. Refresh in a moment."
                restoring -> "No active Plus purchase was found for this Google Play account."
                else -> "Purchase completed, but Plus is not active yet. Refresh or restore purchases before trying again."
            },
        )
    }

    private fun operation(block: suspend (String, Long) -> Unit): Job? {
        val account = state.value.accountId ?: return null
        val ticket = generation
        if (state.value.busy || currentAccountId() != account) return null
        mutableState.value = state.value.copy(busy = true, message = null)
        return scope.launch {
            storeLock.withLock {
                try {
                    requireCurrent(account, ticket)
                    block(account, ticket)
                } catch (error: Exception) {
                    if (isCurrent(account, ticket) && error !is CancellationException) {
                        val reason = (error as? BillingStoreException)?.reason
                        mutableState.value = state.value.copy(
                            storePlus = if (reason == BillingFailure.CANCELLED) state.value.storePlus else null,
                            message = when (reason) {
                            BillingFailure.CANCELLED -> "Purchase cancelled."
                            BillingFailure.PENDING -> "Payment is pending approval in Google Play. Plus will update after approval; refresh when ready."
                            BillingFailure.UNAVAILABLE -> "This Plus plan is unavailable. Refresh and try again."
                            else -> "Billing could not be completed. Refresh or restore purchases before trying again."
                        })
                    }
                } finally {
                    if (isCurrent(account, ticket)) mutableState.value = state.value.copy(busy = false)
                }
            }
        }
    }

    private fun isCurrent(account: String, ticket: Long) = generation == ticket &&
        state.value.accountId == account && currentAccountId() == account

    private fun requireCurrent(account: String, ticket: Long) {
        if (!isCurrent(account, ticket)) throw CancellationException("Billing account changed")
    }
}
