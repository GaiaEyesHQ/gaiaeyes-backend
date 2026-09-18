package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import java.io.IOException
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class MigraineSummaryStoreTest {
    private val secondId = "99999999-9999-4999-8999-999999999999"
    private fun item(id: String = EPISODE_ID) = CurrentSymptomItem(id = id, symptomCode = "MIGRAINE")
    private fun detail(id: String = EPISODE_ID) = fixtureDetail().let { it.copy(episode = it.episode.copy(episodeId = id)) }
    private class Harness {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        var account: String? = "account-a"
        val requests = mutableListOf<Pair<String, String>>()
        val replies = mutableListOf<CompletableDeferred<MigraineDetail>>()
        val store = MigraineSummaryStore(scope, { account }, { account, id ->
            requests += account to id
            val reply = CompletableDeferred<MigraineDetail>().also { replies += it }
            // Simulate a transport that finishes even after cancellation.
            withContext(NonCancellable) { reply.await() }
        }, { ZoneId.of("UTC") }, { Locale.US })
    }

    @Test fun twoRapidSelectionsKeepOnlyLatestEpisodeDespiteLateReply() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            assertTrue(h.store.state.value.isLoading)
            h.store.open("account-a", item(secondId))
            h.replies[1].complete(detail(secondId))
            assertNotNull(h.store.state.value.summary)
            h.replies[0].complete(detail())
            assertEquals(secondId, h.store.state.value.episodeId)
            assertNotNull(h.store.state.value.summary)
            assertEquals(listOf("account-a" to EPISODE_ID, "account-a" to secondId), h.requests)
        } finally { h.scope.cancel() }
    }

    @Test fun closeIgnoresLateSuccessAndLateFailure() {
        for (fail in listOf(false, true)) {
            val h = Harness()
            try {
                h.store.open("account-a", item())
                h.store.close()
                if (fail) h.replies[0].completeExceptionally(IOException()) else h.replies[0].complete(detail())
                assertEquals(MigraineSummaryState(), h.store.state.value)
                h.store.retry()
                assertEquals(1, h.requests.size)
            } finally { h.scope.cancel() }
        }
    }

    @Test fun logoutAndSameAccountReloginCannotResurrectPriorSession() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.account = null
            h.store.accountChanged(null)
            h.account = "account-a"
            h.store.accountChanged(h.account)
            h.replies[0].complete(detail())
            assertEquals(MigraineSummaryState(), h.store.state.value)
        } finally { h.scope.cancel() }
    }

    @Test fun accountSwitchClearsReadyDataAndDiscardsOldAccountResponse() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.replies[0].complete(detail())
            assertNotNull(h.store.state.value.summary)
            h.store.retry()
            assertNull(h.store.state.value.summary)
            h.account = "account-b"
            h.store.accountChanged(h.account)
            assertEquals(MigraineSummaryState(), h.store.state.value)
            h.store.open("account-b", item(secondId))
            h.replies[1].complete(detail())
            assertTrue(h.store.state.value.isLoading)
            h.replies[2].complete(detail(secondId))
            assertEquals("account-b", h.store.state.value.accountId)
            assertEquals(secondId, h.store.state.value.episodeId)
        } finally { h.scope.cancel() }
    }

    @Test fun actualAccountChangeIsCheckedEvenBeforeAuthCollectorRuns() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.account = "account-b"
            h.replies[0].complete(detail())
            assertEquals(MigraineSummaryState(), h.store.state.value)
            h.store.open("account-a", item())
            assertEquals(1, h.requests.size)
        } finally { h.scope.cancel() }
    }

    @Test fun legacyAndUnsupportedEntriesNeverRequestInventedIds() {
        val h = Harness()
        try {
            for (entry in listOf(item("legacy-synthetic"), item().copy(symptomCode = "OTHER"))) {
                h.store.open("account-a", entry)
                assertEquals(MigraineSummaryProblem.LEGACY_ENTRY, h.store.state.value.problem)
                h.store.retry()
            }
            assertTrue(h.requests.isEmpty())
        } finally { h.scope.cancel() }
    }

    @Test fun unavailableNetworkInvalidAndUnauthorizedHaveDistinctStates() {
        val cases = listOf(
            MigraineUnavailableException() to MigraineSummaryProblem.UNAVAILABLE,
            MigraineEpisodeNotFoundException() to MigraineSummaryProblem.UNAVAILABLE,
            MigraineUnavailableException(IOException()) to MigraineSummaryProblem.NETWORK,
            MigraineInvalidResponseException() to MigraineSummaryProblem.INVALID_RESPONSE,
            ApiUnauthorizedException() to MigraineSummaryProblem.SIGN_IN,
        )
        for ((error, expected) in cases) {
            val h = Harness()
            try {
                h.store.open("account-a", item())
                h.replies[0].completeExceptionally(error)
                assertEquals(expected, h.store.state.value.problem)
                assertFalse(h.store.state.value.isLoading)
                assertNull(h.store.state.value.summary)
                assertEquals(1, h.requests.size) // no automatic retry
            } finally { h.scope.cancel() }
        }
    }

    @Test fun retryMakesOneNewReadAndDoesNotShowPreviousFailure() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.replies[0].completeExceptionally(IOException())
            h.store.retry()
            assertEquals(2, h.requests.size)
            assertTrue(h.store.state.value.isLoading)
            assertNull(h.store.state.value.problem)
            h.replies[1].complete(detail())
            assertNotNull(h.store.state.value.summary)
        } finally { h.scope.cancel() }
    }

    @Test fun wrongEpisodeResponseNeverBecomesVisible() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.replies[0].complete(detail(secondId))
            assertEquals(MigraineSummaryProblem.INVALID_RESPONSE, h.store.state.value.problem)
            assertNull(h.store.state.value.summary)
        } finally { h.scope.cancel() }
    }

    @Test fun readyStateClearsOnCloseAndSameAccountRefreshCanKeepIt() {
        val h = Harness()
        try {
            h.store.open("account-a", item())
            h.replies[0].complete(detail())
            h.store.accountChanged("account-a")
            assertNotNull(h.store.state.value.summary)
            h.store.close()
            assertEquals(MigraineSummaryState(), h.store.state.value)
        } finally { h.scope.cancel() }
    }
}
