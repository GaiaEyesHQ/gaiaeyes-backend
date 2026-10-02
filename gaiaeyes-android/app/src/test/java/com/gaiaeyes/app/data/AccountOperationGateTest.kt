package com.gaiaeyes.app.data

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class AccountOperationGateTest {
    @Test fun pauseCancelsOnlyTargetAccountAndRejectsNewUploads() = runBlocking {
        val records = Records(); val gate = AccountOperationGate(records)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val a = scope.launch { gate.track("a"); awaitCancellation() }
        val b = scope.launch { gate.track("b"); awaitCancellation() }
        gate.pauseAndCancel("a")
        assertTrue(a.isCompleted); assertFalse(b.isCancelled)
        assertTrue(runCatching { gate.track("a") }.exceptionOrNull() is AccountWorkPausedException)
        assertTrue(AccountOperationGate(records).isBlocked("a"))
        scope.cancel()
    }
    @Test fun submittedAndConfirmedRecordsCannotBeResumedAsAnUnsentRequest() {
        for (record in listOf(AccountDeletionRecord.SUBMITTED, AccountDeletionRecord.CONFIRMED, AccountDeletionRecord.COMPLETE)) {
            val records = Records(); records.write("a", record); val gate = AccountOperationGate(records)
            assertTrue(runCatching { gate.resumeBeforeSubmission("a") }.isFailure)
            assertTrue(gate.isBlocked("a")); assertFalse(gate.isBlocked("b"))
        }
    }
    private class Records : AccountDeletionRecords {
        private val records = mutableMapOf<String, AccountDeletionRecord>()
        override fun read(accountId: String) = records[accountId]
        override fun write(accountId: String, record: AccountDeletionRecord?) {
            if (record == null) records.remove(accountId) else records[accountId] = record
        }
    }
}
