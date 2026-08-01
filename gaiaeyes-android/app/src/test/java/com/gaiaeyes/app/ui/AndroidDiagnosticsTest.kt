package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.auth.AuthState
import com.gaiaeyes.app.data.HealthConnectStatus
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidDiagnosticsTest {
    @Test
    fun diagnosticSummaryIncludesOperationalStateWithoutAccountIdentifiers() {
        val state = HomeUiState(
            authState = AuthState.SignedIn(
                accountId = "private-account-id",
                email = "private@example.com",
            ),
            backendAvailable = true,
            healthConnectStatus = HealthConnectStatus.READY,
            pendingJournalWrites = 2,
            pendingHealthSampleBatches = 1,
        )

        val summary = androidDiagnosticsSummary(state)

        assertTrue(summary.contains("Data service: connected"))
        assertTrue(summary.contains("Health Connect: Connected"))
        assertTrue(summary.contains("Pending journal entries: 2"))
        assertTrue(summary.contains("Pending health batches: 1"))
        assertFalse(summary.contains("private-account-id"))
        assertFalse(summary.contains("private@example.com"))
    }
}
