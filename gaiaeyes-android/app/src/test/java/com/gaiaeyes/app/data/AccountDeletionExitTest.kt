package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.AccountDeletionPreflight
import com.gaiaeyes.app.core.network.AccountDeletionResult
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class AccountDeletionExitTest {
    @Test fun expiredUnconfirmedAccountCanExitAndReplacementWorksWhileOldUploadsStayBlocked() = runBlocking {
        val f = Fixture(); f.delete = { error("synthetic lost response") }; f.submit()
        f.token = { error("synthetic expired session") }
        f.controller.open()!!.join()
        assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
        val tokenCalls = f.tokenCalls
        f.controller.signOutLocally()!!.join()
        assertEquals(tokenCalls, f.tokenCalls); assertNull(f.account)
        assertEquals(AccountDeletionPhase.CLOSED, f.phase); assertEquals(1, f.deleteCalls)
        assertEquals(AccountDeletionRecord.SUBMITTED, f.records.read("a")); assertEquals(0, f.cleanupCalls)
        f.switchTo("b"); f.gate.track("b")
        assertFalse(f.gate.isBlocked("b"))
        assertTrue(AccountOperationGate(f.records).isBlocked("a"))
        f.switchTo("a"); assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
        assertTrue(runCatching { f.gate.track("a") }.exceptionOrNull() is AccountWorkPausedException)
        assertEquals(1, f.deleteCalls)
    }

    @Test fun cleanupFailureCanExitAndRetainsCleanupOnlyRecoveryAcrossControllerRestart() = runBlocking {
        val f = Fixture(); f.cleanup = { error("synthetic local failure") }; f.submit()
        assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        f.controller.signOutLocally()!!.join()
        assertEquals(AccountDeletionRecord.CONFIRMED, f.records.read("a")); assertNull(f.account)
        val restarted = Fixture(f.records)
        assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, restarted.phase)
        assertNull(restarted.controller.confirm()); assertNull(restarted.controller.open())
        restarted.controller.retryCleanup()!!.join()
        assertEquals(0, restarted.deleteCalls); assertEquals(AccountDeletionPhase.COMPLETE, restarted.phase)
    }

    @Test fun lateExitCannotClearReplacementAccountOrOverwriteItsScreen() = runBlocking {
        val f = Fixture(); f.delete = { error("synthetic") }; f.submit()
        val resume = CompletableDeferred<Unit>()
        f.clearSession = { expected -> resume.await(); if (f.account == expected) f.switchTo(null) }
        val exit = f.controller.signOutLocally()!!
        assertEquals(AccountDeletionPhase.SIGNING_OUT, f.phase)
        f.switchTo("b"); resume.complete(Unit); exit.join()
        assertEquals("b", f.account); assertEquals("b", f.controller.state.value.accountId)
        assertEquals(AccountDeletionPhase.CLOSED, f.phase)
        assertTrue(f.gate.isBlocked("a")); assertFalse(f.gate.isBlocked("b"))
    }

    @Test fun failedLocalExitKeepsRecoveryAndAllowsOnlyExplicitLocalRetry() = runBlocking {
        val f = Fixture(); f.delete = { error("synthetic") }; f.submit()
        f.clearSession = { error("synthetic encrypted storage failure") }
        f.controller.signOutLocally()!!.join()
        assertEquals("a", f.account); assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
        assertTrue(f.controller.state.value.localExitFailed)
        assertEquals(1, f.deleteCalls); assertTrue(f.gate.isBlocked("a"))
        f.clearSession = { if (f.account == it) f.switchTo(null) }
        f.controller.signOutLocally()!!.join()
        assertNull(f.account); assertEquals(1, f.deleteCalls)
    }

    @Test fun pendingRemoteRequestCannotBeAbandonedThroughLocalExitButton() = runBlocking {
        val f = Fixture(); val resume = CompletableDeferred<Unit>()
        f.delete = { resume.await(); error("synthetic uncertainty") }
        f.controller.open()!!.join(); val deletion = f.controller.confirm()!!
        assertNull(f.controller.signOutLocally()); assertEquals(0, f.clearSessionCalls)
        resume.complete(Unit); deletion.join()
        assertNotNull(f.controller.signOutLocally())
    }

    @Test fun confirmedProofMustBePersistedBeforeLocalExit() = runBlocking {
        val f = Fixture(); f.records.failConfirmation = true; f.submit()
        assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        f.controller.signOutLocally()!!.join()
        assertEquals("a", f.account); assertEquals(0, f.clearSessionCalls)
        assertTrue(f.controller.state.value.localExitFailed)
        f.records.failConfirmation = false; f.controller.signOutLocally()!!.join()
        assertNull(f.account); assertEquals(AccountDeletionRecord.CONFIRMED, f.records.read("a"))
        assertEquals(1, f.deleteCalls); assertEquals(0, f.cleanupCalls)
    }

    @Test fun alreadyClearedSessionCanLeaveCleanupErrorWithoutLosingEvidence() = runBlocking {
        val f = Fixture()
        f.clearSession = { f.switchTo(null); error("synthetic late SDK failure") }; f.submit()
        assertNull(f.account); assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        val priorCalls = f.clearSessionCalls
        f.controller.signOutLocally()!!.join()
        assertEquals(AccountDeletionPhase.CLOSED, f.phase); assertEquals(priorCalls, f.clearSessionCalls)
        assertEquals(AccountDeletionRecord.COMPLETE, f.records.read("a")); assertEquals(1, f.deleteCalls)
    }

    @Test fun cancellingLocalExitRetainsPauseAndDoesNotRepeatRemoteDeletion() = runBlocking {
        val f = Fixture(); f.delete = { error("synthetic") }; f.submit()
        f.clearSession = { awaitCancellation() }
        val exit = f.controller.signOutLocally()!!
        f.controller.cancel(); assertEquals(AccountDeletionPhase.SIGNING_OUT, f.phase)
        exit.cancelAndJoin()
        assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase); assertTrue(f.controller.state.value.localExitFailed)
        assertTrue(f.gate.isBlocked("a")); assertEquals(1, f.deleteCalls)
    }

    private class Fixture(val records: Records = Records()) {
        var account: String? = "a"
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val gate = AccountOperationGate(records)
        var token: suspend () -> String = { "synthetic-a" }
        var delete: suspend () -> AccountDeletionResult = { AccountDeletionResult("a", 1, 1) }
        var cleanup: suspend () -> Unit = {}
        var clearSession: suspend (String) -> Unit = { if (account == it) switchTo(null) }
        var tokenCalls = 0; var deleteCalls = 0; var cleanupCalls = 0; var clearSessionCalls = 0
        val controller = AccountDeletionController(scope, { account }, { tokenCalls++; token() },
            { AccountDeletionPreflight("a", true, true) }, { deleteCalls++; delete() }, gate, records,
            { cleanupCalls++; cleanup() }, { clearSessionCalls++; clearSession(it) })
        init { controller.authChanged(account) }
        val phase get() = controller.state.value.phase
        fun switchTo(next: String?) { account = next; controller.authChanged(next) }
        suspend fun submit() { controller.open()!!.join(); controller.confirm()!!.join() }
    }
    private class Records : AccountDeletionRecords {
        val values = mutableMapOf<String, AccountDeletionRecord>()
        var failConfirmation = false
        override fun read(accountId: String) = values[accountId]
        override fun write(accountId: String, record: AccountDeletionRecord?) {
            if (failConfirmation && record == AccountDeletionRecord.CONFIRMED) error("synthetic persistence failure")
            if (record == null) values.remove(accountId) else values[accountId] = record
        }
    }
}
