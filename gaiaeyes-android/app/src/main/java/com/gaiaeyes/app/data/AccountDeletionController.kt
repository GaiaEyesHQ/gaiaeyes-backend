package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.AccountDeletionPreflight
import com.gaiaeyes.app.core.network.AccountDeletionResult
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

enum class AccountDeletionPhase { CLOSED, CHECKING, CONFIRM, DELETING, UNAVAILABLE, UNCONFIRMED, CLEANUP_REQUIRED, COMPLETE }

data class AccountDeletionState(
    val accountId: String? = null,
    val phase: AccountDeletionPhase = AccountDeletionPhase.CLOSED,
    val syncPaused: Boolean = false,
)

/** No automatic destructive retry: every remote attempt follows a fresh preflight and confirmation. */
class AccountDeletionController(
    private val scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val tokenForAccount: suspend (String) -> String,
    private val preflight: suspend (String) -> AccountDeletionPreflight,
    private val delete: suspend (String) -> AccountDeletionResult,
    private val gate: AccountOperationGate,
    private val records: AccountDeletionRecords,
    private val clearLocalData: suspend (String) -> Unit,
    private val clearSession: suspend (String) -> Unit,
) {
    private val _state = MutableStateFlow(AccountDeletionState())
    val state = _state.asStateFlow()
    private var epoch = 0L
    private var observedAccount: String? = null
    private var preparing: Job? = null
    private var deleting: Job? = null
    private var clearingSessionFor: String? = null
    private val confirmedAccounts = mutableSetOf<String>()

    fun authChanged(accountId: String?) {
        if (accountId == observedAccount) return
        if (accountId == null && clearingSessionFor == observedAccount) {
            observedAccount = null
            return
        }
        observedAccount = accountId
        epoch++
        preparing?.cancel()
        _state.value = recoveryState(accountId)
    }

    private fun recoveryState(accountId: String?): AccountDeletionState {
        val record = accountId?.let { if (it in confirmedAccounts) AccountDeletionRecord.CONFIRMED else records.read(it) }
        return AccountDeletionState(accountId, when (record) {
            null -> AccountDeletionPhase.CLOSED
            AccountDeletionRecord.PAUSED, AccountDeletionRecord.SUBMITTED -> AccountDeletionPhase.UNCONFIRMED
            AccountDeletionRecord.CONFIRMED, AccountDeletionRecord.COMPLETE -> AccountDeletionPhase.CLEANUP_REQUIRED
        }, record != null)
    }

    fun open(): Job? {
        if (deleting?.isActive == true || preparing?.isActive == true) return null
        val account = currentAccountId() ?: return null
        val generation = epoch
        if (account in confirmedAccounts || records.read(account) in listOf(AccountDeletionRecord.CONFIRMED, AccountDeletionRecord.COMPLETE)) {
            _state.value = recoveryState(account)
            return null
        }
        _state.value = AccountDeletionState(account, AccountDeletionPhase.CHECKING, gate.isBlocked(account))
        preparing = scope.launch {
            try {
                val token = tokenForAccount(account)
                currentCoroutineContext().ensureActive()
                check(matches(account, generation))
                val result = preflight(token)
                if (!matches(account, generation)) return@launch
                check(result.userId == account && result.deleteReady && result.authDeleteReady)
                _state.value = AccountDeletionState(account, AccountDeletionPhase.CONFIRM, gate.isBlocked(account))
            } catch (cancelled: CancellationException) {
                if (matches(account, generation)) {
                    _state.value = AccountDeletionState(account,
                        if (gate.isBlocked(account)) AccountDeletionPhase.UNCONFIRMED else AccountDeletionPhase.UNAVAILABLE,
                        gate.isBlocked(account))
                }
                throw cancelled
            } catch (_: Exception) {
                if (matches(account, generation)) {
                    _state.value = AccountDeletionState(account,
                        if (gate.isBlocked(account)) AccountDeletionPhase.UNCONFIRMED else AccountDeletionPhase.UNAVAILABLE,
                        gate.isBlocked(account))
                }
            }
        }
        return preparing
    }

    fun cancel() {
        if (_state.value.phase == AccountDeletionPhase.DELETING) return
        preparing?.cancel()
        epoch++ // invalidates even a non-cooperative late preflight
        val account = currentAccountId()
        _state.value = recoveryState(account)
    }

    fun confirm(): Job? {
        if (deleting?.isActive == true || _state.value.phase != AccountDeletionPhase.CONFIRM) return null
        val account = _state.value.accountId ?: return null
        val generation = epoch
        if (!matches(account, generation)) return null
        _state.value = AccountDeletionState(account, AccountDeletionPhase.DELETING, true)
        deleting = scope.launch {
            val wasPaused = gate.isBlocked(account)
            var submitted = false
            var confirmed = false
            try {
                gate.pauseAndCancel(account)
                check(matches(account, generation))
                val token = tokenForAccount(account)
                currentCoroutineContext().ensureActive()
                check(matches(account, generation))
                // Persist uncertainty before the network request; process death cannot resume old uploads.
                records.write(account, AccountDeletionRecord.SUBMITTED)
                submitted = true
                val result = delete(token)
                check(result.deletedUserId == account && result.rowsDeleted >= 0 && result.tablesTouched >= 0)
                confirmed = true
                confirmedAccounts.add(account)
                records.write(account, AccountDeletionRecord.CONFIRMED)
                finishCleanup(account, generation)
            } catch (cancelled: CancellationException) {
                if (!submitted && !wasPaused) runCatching { gate.resumeBeforeSubmission(account) }
                if (canReportCleanup(account, generation)) _state.value = recoveryState(account)
                throw cancelled
            } catch (_: Exception) {
                if (!submitted && !wasPaused) runCatching { gate.resumeBeforeSubmission(account) }
                if (canReportCleanup(account, generation)) {
                    _state.value = AccountDeletionState(account, when {
                        confirmed -> AccountDeletionPhase.CLEANUP_REQUIRED
                        submitted || gate.isBlocked(account) -> AccountDeletionPhase.UNCONFIRMED
                        else -> AccountDeletionPhase.UNAVAILABLE
                    }, gate.isBlocked(account))
                }
            }
        }
        return deleting
    }

    fun retryCleanup(): Job? {
        if (deleting?.isActive == true) return null
        val account = currentAccountId() ?: _state.value.takeIf { it.phase == AccountDeletionPhase.CLEANUP_REQUIRED }?.accountId ?: return null
        if (account !in confirmedAccounts && records.read(account) !in listOf(AccountDeletionRecord.CONFIRMED, AccountDeletionRecord.COMPLETE)) return null
        val generation = epoch
        _state.value = AccountDeletionState(account, AccountDeletionPhase.DELETING, true)
        deleting = scope.launch {
            try {
                gate.pauseAndCancel(account)
                records.write(account, AccountDeletionRecord.CONFIRMED)
                finishCleanup(account, generation)
            } catch (cancelled: CancellationException) {
                if (canReportCleanup(account, generation)) _state.value = recoveryState(account)
                throw cancelled
            } catch (_: Exception) {
                if (canReportCleanup(account, generation)) _state.value = recoveryState(account)
            }
        }
        return deleting
    }

    private suspend fun finishCleanup(account: String, generation: Long) {
        // Cleanup is scoped to the confirmed account even if a different account is now active.
        clearLocalData(account)
        records.write(account, AccountDeletionRecord.COMPLETE)
        if (!canReportCleanup(account, generation)) return
        clearingSessionFor = account
        try {
            clearSession(account)
            check(currentAccountId() != account)
            if (epoch == generation && currentAccountId() == null) {
                _state.value = AccountDeletionState(null, AccountDeletionPhase.COMPLETE)
            }
        } finally {
            clearingSessionFor = null
        }
    }

    private fun canReportCleanup(account: String, generation: Long) =
        epoch == generation && (currentAccountId() == account || currentAccountId() == null)

    private fun matches(account: String, generation: Long) = epoch == generation && currentAccountId() == account
}
