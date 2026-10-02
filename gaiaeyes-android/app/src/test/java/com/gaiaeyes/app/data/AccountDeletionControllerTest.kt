package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.AccountDeletionPreflight
import com.gaiaeyes.app.core.network.AccountDeletionResult
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class AccountDeletionControllerTest {
    @Test fun cancelBeforeConfirmationNeverDeletesOrPausesUploads() = runBlocking {
        val f = Fixture(); f.ready(); f.controller.cancel()
        assertEquals(AccountDeletionPhase.CLOSED, f.phase)
        assertNull(f.controller.confirm()); assertEquals(0, f.deleteCalls)
        assertFalse(f.gate.isBlocked("a")); assertTrue(f.cleaned.isEmpty())
    }

    @Test fun unreadyOrWrongAccountPreflightCannotBeConfirmed() = runBlocking {
        for (result in listOf(AccountDeletionPreflight("b", true, true), AccountDeletionPreflight("a", false, true), AccountDeletionPreflight("a", true, false))) {
            val f = Fixture(); f.preflight = { result }; f.controller.open()!!.join()
            assertEquals(AccountDeletionPhase.UNAVAILABLE, f.phase)
            assertNull(f.controller.confirm()); assertEquals(0, f.deleteCalls)
        }
    }

    @Test fun delayedPreflightCannotReopenCancelledConfirmation() = runBlocking {
        val f = Fixture(); val response = CompletableDeferred<Unit>()
        f.preflight = { withContext(NonCancellable) { response.await() }; readyResult() }
        val job = f.controller.open()!!; f.controller.cancel(); response.complete(Unit); job.join()
        assertEquals(AccountDeletionPhase.CLOSED, f.phase); assertNull(f.controller.confirm())
    }

    @Test fun switchingAccountsDuringPreflightDiscardsOldResult() = runBlocking {
        val f = Fixture(); val response = CompletableDeferred<Unit>()
        f.preflight = { withContext(NonCancellable) { response.await() }; readyResult() }
        val job = f.controller.open()!!; f.switchTo("b"); response.complete(Unit); job.join()
        assertEquals("b", f.controller.state.value.accountId)
        assertEquals(AccountDeletionPhase.CLOSED, f.phase); assertEquals(0, f.deleteCalls)
    }

    @Test fun switchBeforeConfirmationDoesNotSendDelete() = runBlocking {
        val f = Fixture(); f.ready(); f.switchTo("b")
        assertNull(f.controller.confirm()); assertEquals(0, f.deleteCalls)
    }

    @Test fun switchDuringTokenRefreshPreventsDeleteAndRestoresOnlyOriginalPause() = runBlocking {
        val f = Fixture(); f.ready(); val resume = CompletableDeferred<Unit>()
        f.token = { resume.await(); "token-a" }
        val job = f.controller.confirm()!!; f.switchTo("b"); resume.complete(Unit); job.join()
        assertEquals(0, f.deleteCalls); assertFalse(f.gate.isBlocked("a"))
        assertFalse(f.gate.isBlocked("b")); assertTrue(f.cleaned.isEmpty())
    }

    @Test fun cancellationDuringTokenRefreshBeforeSubmissionRestoresSync() = runBlocking {
        val f = Fixture(); f.ready(); f.token = { awaitCancellation() }
        val job = f.controller.confirm()!!; job.cancelAndJoin()
        assertEquals(0, f.deleteCalls); assertFalse(f.gate.isBlocked("a"))
        assertEquals(AccountDeletionPhase.CLOSED, f.phase)
    }

    @Test fun earlierUncertaintyCannotBeClearedByCancellingNewAttempt() = runBlocking {
        val f = Fixture(); f.records.write("a", AccountDeletionRecord.SUBMITTED)
        f.ready(); f.token = { awaitCancellation() }
        f.controller.confirm()!!.cancelAndJoin()
        assertTrue(f.gate.isBlocked("a")); assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
        assertEquals(0, f.deleteCalls)
    }

    @Test fun cancellingAfterDispatchRetainsPauseAcrossRestartAndDoesNotCleanup() = runBlocking {
        val f = Fixture(); f.ready(); f.delete = { awaitCancellation() }
        val job = f.controller.confirm()!!; assertEquals(1, f.deleteCalls)
        f.controller.cancel() // UI cancellation cannot cancel a dispatched request.
        assertEquals(AccountDeletionPhase.DELETING, f.phase)
        job.cancelAndJoin()
        assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
        assertTrue(AccountOperationGate(f.records).isBlocked("a")); assertTrue(f.cleaned.isEmpty())
        val restarted = Fixture(f.records)
        assertEquals(AccountDeletionPhase.UNCONFIRMED, restarted.phase)
        assertEquals(0, restarted.deleteCalls); assertNull(restarted.controller.confirm())
    }

    @Test fun failureOrPartialResponseDoesNotClaimSuccessOrCleanup() = runBlocking {
        val failures: List<suspend () -> AccountDeletionResult> = listOf(
            { error("synthetic HTTP 500 after row deletion") },
            { AccountDeletionResult("b", 3, 2) },
            { AccountDeletionResult("a", -1, 2) },
            { AccountDeletionResult("a", 1, -1) },
        )
        for (failure in failures) {
            val f = Fixture(); f.ready(); f.delete = failure; f.controller.confirm()!!.join()
            assertEquals(AccountDeletionPhase.UNCONFIRMED, f.phase)
            assertEquals(AccountDeletionRecord.SUBMITTED, f.records.read("a"))
            assertTrue(f.cleaned.isEmpty()); assertTrue(f.signedOut.isEmpty()); assertEquals("a", f.account)
        }
    }

    @Test fun retryRequiresNewPreflightAndConfirmation() = runBlocking {
        val f = Fixture(); f.ready(); f.delete = { error("synthetic") }; f.controller.confirm()!!.join()
        assertNull(f.controller.confirm()); assertEquals(1, f.preflightCalls)
        f.delete = { deletedResult() }; f.controller.open()!!.join()
        assertEquals(1, f.deleteCalls); assertEquals(2, f.preflightCalls)
        f.controller.confirm()!!.join(); assertEquals(2, f.deleteCalls)
        assertEquals(AccountDeletionPhase.COMPLETE, f.phase)
    }

    @Test fun duplicateClicksSendExactlyOneDelete() = runBlocking {
        val f = Fixture(); f.ready(); val response = CompletableDeferred<Unit>()
        f.delete = { response.await(); deletedResult() }
        val first = f.controller.confirm()!!
        assertNull(f.controller.confirm()); assertNull(f.controller.open())
        response.complete(Unit); first.join(); assertEquals(1, f.deleteCalls)
    }

    @Test fun successWaitsForOldUploadFinalizerThenDeletesAndCleansAccount() = runBlocking {
        val f = Fixture(); val events = mutableListOf<String>(); val finishOld = CompletableDeferred<Unit>()
        val old = f.scope.launch {
            f.gate.track("a")
            try { awaitCancellation() } finally { withContext(NonCancellable) { finishOld.await(); events += "old-finished" } }
        }
        f.delete = { events += "delete"; deletedResult() }
        f.cleanup = { events += "cleanup-$it" }
        f.ready(); val request = f.controller.confirm()!!
        assertTrue(old.isCancelled); assertEquals(0, f.deleteCalls)
        finishOld.complete(Unit); request.join()
        assertEquals(listOf("old-finished", "delete", "cleanup-a"), events)
        assertEquals(listOf("a"), f.signedOut); assertNull(f.account)
        assertEquals(AccountDeletionRecord.COMPLETE, f.records.read("a"))
        assertEquals(AccountDeletionPhase.COMPLETE, f.phase)
    }

    @Test fun switchDuringDeleteCleansOnlyOldAccountWithoutSigningOutNewOne() = runBlocking {
        val f = Fixture(); f.ready(); val response = CompletableDeferred<Unit>()
        f.delete = { response.await(); deletedResult() }
        val job = f.controller.confirm()!!; f.switchTo("b"); response.complete(Unit); job.join()
        assertEquals(listOf("a"), f.cleaned); assertTrue(f.signedOut.isEmpty())
        assertEquals("b", f.account); assertFalse(f.gate.isBlocked("b"))
        assertEquals(AccountDeletionPhase.CLOSED, f.phase)
    }

    @Test fun switchDuringCleanupCannotClearReplacementSession() = runBlocking {
        val f = Fixture(); f.ready(); val resume = CompletableDeferred<Unit>()
        f.cleanup = { resume.await() }
        val job = f.controller.confirm()!!; f.switchTo("b"); resume.complete(Unit); job.join()
        assertEquals("b", f.account); assertTrue(f.signedOut.isEmpty())
        assertEquals(listOf("a"), f.cleaned)
    }

    @Test fun cleanupFailureRetriesLocallyWithoutSecondDelete() = runBlocking {
        val f = Fixture(); f.ready(); f.cleanup = { error("synthetic storage failure") }
        f.controller.confirm()!!.join()
        assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        assertEquals(AccountDeletionRecord.CONFIRMED, f.records.read("a")); assertTrue(f.signedOut.isEmpty())
        f.cleanup = {}; f.controller.retryCleanup()!!.join()
        assertEquals(1, f.deleteCalls); assertEquals(AccountDeletionPhase.COMPLETE, f.phase)
    }

    @Test fun restartAfterConfirmationOnlyOffersLocalCleanup() = runBlocking {
        val records = Records(); records.write("a", AccountDeletionRecord.CONFIRMED)
        val f = Fixture(records); assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        assertNull(f.controller.open()); assertNull(f.controller.confirm())
        f.controller.retryCleanup()!!.join(); assertEquals(0, f.preflightCalls); assertEquals(0, f.deleteCalls)
        assertEquals(AccountDeletionPhase.COMPLETE, f.phase)
    }

    @Test fun failedPersistentPauseNeverSendsDelete() = runBlocking {
        val f = Fixture(); f.ready(); f.records.failOn = AccountDeletionRecord.PAUSED
        f.controller.confirm()!!.join(); assertEquals(0, f.deleteCalls)
        assertTrue(f.cleaned.isEmpty()); assertEquals(AccountDeletionPhase.UNAVAILABLE, f.phase)
    }

    @Test fun failedSubmittedMarkerNeverSendsDelete() = runBlocking {
        val f = Fixture(); f.ready(); f.records.failOn = AccountDeletionRecord.SUBMITTED
        f.controller.confirm()!!.join(); assertEquals(0, f.deleteCalls)
        assertFalse(f.gate.isBlocked("a")); assertEquals(AccountDeletionPhase.UNAVAILABLE, f.phase)
    }

    @Test fun failedConfirmedMarkerRetainsInMemoryProofForCleanupOnlyRetry() = runBlocking {
        val f = Fixture(); f.ready(); f.records.failOn = AccountDeletionRecord.CONFIRMED
        f.controller.confirm()!!.join(); assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        assertTrue(f.cleaned.isEmpty()); f.records.failOn = null
        f.controller.retryCleanup()!!.join(); assertEquals(1, f.deleteCalls)
        assertEquals(AccountDeletionPhase.COMPLETE, f.phase)
    }

    @Test fun failedSessionRemovalOffersLocalRetryEvenAfterSignedOutNotification() = runBlocking {
        val f = Fixture(); f.ready()
        f.clearSession = { f.switchTo(null); error("synthetic late SDK failure") }
        f.controller.confirm()!!.join(); assertEquals(AccountDeletionPhase.CLEANUP_REQUIRED, f.phase)
        f.clearSession = {}; f.controller.retryCleanup()!!.join()
        assertEquals(AccountDeletionPhase.COMPLETE, f.phase); assertEquals(1, f.deleteCalls)
    }

    @Test fun partialLocalCleanupAttemptsAllStoresAndReportsFailure() = runBlocking {
        val cleared = mutableListOf<String>()
        val result = runCatching { clearAccountLocalData("a", listOf(
            { cleared += "one-$it" }, { error("synthetic") }, { cleared += "three-$it" },
        )) }
        assertTrue(result.isFailure); assertEquals(listOf("one-a", "three-a"), cleared)
    }

    @Test fun cleanupCancellationDoesNotGetSwallowed() = runBlocking {
        var reached = false
        val error = runCatching { clearAccountLocalData("a", listOf(
            { throw CancellationException("synthetic") }, { reached = true },
        )) }.exceptionOrNull()
        assertTrue(error is CancellationException); assertFalse(reached)
    }

    private class Fixture(val records: Records = Records()) {
        var account: String? = "a"
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val gate = AccountOperationGate(records)
        var token: suspend (String) -> String = { "token-$it" }
        var preflight: suspend () -> AccountDeletionPreflight = { readyResult() }
        var delete: suspend () -> AccountDeletionResult = { deletedResult() }
        var cleanup: suspend (String) -> Unit = {}
        var clearSession: suspend (String) -> Unit = { if (account == it) { signedOut += it; switchTo(null) } }
        var deleteCalls = 0
        var preflightCalls = 0
        val cleaned = mutableListOf<String>()
        val signedOut = mutableListOf<String>()
        val controller = AccountDeletionController(scope, { account }, { token(it) },
            { preflightCalls++; preflight() }, { assertEquals("token-a", it); deleteCalls++; delete() },
            gate, records, { cleanup(it); cleaned += it }, { clearSession(it) })
        init { controller.authChanged(account) }
        val phase get() = controller.state.value.phase
        fun switchTo(next: String?) { account = next; controller.authChanged(next) }
        suspend fun ready() { controller.open()!!.join(); assertEquals(AccountDeletionPhase.CONFIRM, phase) }
    }
    private class Records : AccountDeletionRecords {
        val values = mutableMapOf<String, AccountDeletionRecord>()
        var failOn: AccountDeletionRecord? = null
        override fun read(accountId: String) = values[accountId]
        override fun write(accountId: String, record: AccountDeletionRecord?) {
            if (record != null && record == failOn) error("synthetic write failure")
            if (record == null) values.remove(accountId) else values[accountId] = record
        }
    }
    companion object {
        private fun readyResult() = AccountDeletionPreflight("a", true, true)
        private fun deletedResult() = AccountDeletionResult("a", 3, 2)
    }
}
