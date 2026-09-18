package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.EPISODE_ID
import com.gaiaeyes.app.core.network.MigraineDetail
import com.gaiaeyes.app.core.network.fixtureDetail
import com.gaiaeyes.app.ui.MigraineSummaryState
import com.gaiaeyes.app.ui.MigraineSummaryStore
import java.io.IOException
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class HomeContextRepositorySavedMigraineTest {
    private class Harness {
        var account: String? = "account-a"
        var tokenCalls = 0
        val reads = mutableListOf<Pair<String, String>>()
        val signOutAccounts = mutableListOf<String?>()
        var token: suspend () -> String = { "synthetic-token-a" }
        var response: suspend () -> MigraineDetail = { fixtureDetail() }
        var returned: MigraineDetail? = null
        var failure: Throwable? = null
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)

        suspend fun read(accountId: String = "account-a", episodeId: String = EPISODE_ID) =
            savedMigraineDetailFor(accountId, episodeId,
                currentAccountId = { account },
                accessToken = { tokenCalls++; token() },
                readDetail = { value, id -> reads += value to id; response() },
                signOut = { signOutAccounts += account },
            )

        fun start() = scope.launch {
            try { returned = read() } catch (error: Throwable) { failure = error }
        }

        fun store() = MigraineSummaryStore(scope, { account }, { accountId, episodeId -> read(accountId, episodeId) })
    }

    @Test fun sameAccountPassesExactTokenAndEpisodeToOneRead() {
        val h = Harness()
        try {
            val saved = fixtureDetail()
            h.response = { saved }
            h.start()
            assertSame(saved, h.returned)
            assertEquals(1, h.tokenCalls)
            assertEquals(listOf("synthetic-token-a" to EPISODE_ID), h.reads)
            assertTrue(h.signOutAccounts.isEmpty())
        } finally { h.scope.cancel() }
    }

    @Test fun absentOrReplacedAccountBeforeEntryDoesNotAcquireTokenOrRead() {
        for (current in listOf(null, "account-b")) {
            val h = Harness()
            try {
                h.account = current
                h.start()
                assertTrue(h.failure is CancellationException)
                assertEquals(0, h.tokenCalls)
                assertTrue(h.reads.isEmpty())
                assertTrue(h.signOutAccounts.isEmpty())
            } finally { h.scope.cancel() }
        }
    }

    @Test fun replacementDuringTokenAcquisitionPreventsWrongAccountRead() {
        val h = Harness()
        val token = CompletableDeferred<String>()
        try {
            h.token = { token.await() }
            h.start()
            h.account = "account-b"
            token.complete("synthetic-token-b")
            assertTrue(h.failure is CancellationException)
            assertNull(h.returned)
            assertTrue(h.reads.isEmpty())
            assertTrue(h.signOutAccounts.isEmpty())
        } finally { token.cancel(); h.scope.cancel() }
    }

    @Test fun lateUnauthorizedAfterReplacementNeverSignsOutReplacement() {
        val h = Harness()
        val reply = CompletableDeferred<MigraineDetail>()
        try {
            h.response = { reply.await() }
            h.start()
            h.account = "account-b"
            reply.completeExceptionally(ApiUnauthorizedException())
            assertTrue(h.failure is ApiUnauthorizedException)
            assertTrue(h.signOutAccounts.isEmpty())
            assertNull(h.returned)
            assertEquals(1, h.reads.size)
        } finally { reply.cancel(); h.scope.cancel() }
    }

    @Test fun unauthorizedForStillCurrentAccountRetainsExistingSignOutBehavior() {
        val h = Harness()
        try {
            h.response = { throw ApiUnauthorizedException() }
            h.start()
            assertTrue(h.failure is ApiUnauthorizedException)
            assertEquals(listOf("account-a"), h.signOutAccounts)
            assertEquals(1, h.reads.size)
            assertNull(h.returned)
        } finally { h.scope.cancel() }
    }

    @Test fun accountReplacementDuringReadCannotReturnSavedDetail() {
        val h = Harness()
        val reply = CompletableDeferred<MigraineDetail>()
        try {
            h.response = { reply.await() }
            h.start()
            h.account = "account-b"
            reply.complete(fixtureDetail())
            assertTrue(h.failure is CancellationException)
            assertNull(h.returned)
            assertTrue(h.signOutAccounts.isEmpty())
        } finally { reply.cancel(); h.scope.cancel() }
    }

    @Test fun cancelledReadCannotReturnNonCooperativeTransportSuccess() {
        val h = Harness()
        val reply = CompletableDeferred<MigraineDetail>()
        try {
            h.response = { withContext(NonCancellable) { reply.await() } }
            val job = h.start()
            job.cancel()
            reply.complete(fixtureDetail())
            assertNull(h.returned)
            assertTrue(h.failure is CancellationException)
            assertTrue(h.signOutAccounts.isEmpty())
        } finally { reply.completeExceptionally(CancellationException()); h.scope.cancel() }
    }

    @Test fun cancelledReadCannotSignOutAfterNonCooperativeUnauthorized() {
        val h = Harness()
        val reply = CompletableDeferred<MigraineDetail>()
        try {
            h.response = { withContext(NonCancellable) { reply.await() } }
            val job = h.start()
            job.cancel()
            reply.completeExceptionally(ApiUnauthorizedException())
            assertTrue(h.signOutAccounts.isEmpty())
            assertTrue(h.failure is CancellationException)
            assertNull(h.returned)
        } finally { reply.completeExceptionally(CancellationException()); h.scope.cancel() }
    }

    @Test fun closeDuringNonCooperativeTokenAcquisitionPreventsLaterRead() {
        val h = Harness()
        val token = CompletableDeferred<String>()
        val store = h.store()
        try {
            h.token = { withContext(NonCancellable) { token.await() } }
            store.open("account-a", CurrentSymptomItem(id = EPISODE_ID, symptomCode = "MIGRAINE"))
            assertTrue(store.state.value.isLoading)
            store.close()
            token.complete("synthetic-token-a")
            assertTrue(h.reads.isEmpty())
            assertTrue(h.signOutAccounts.isEmpty())
            assertEquals(MigraineSummaryState(), store.state.value)
        } finally { token.completeExceptionally(CancellationException()); h.scope.cancel() }
    }

    @Test fun storeAccountInvalidationDiscardsLateUnauthorizedWithoutSignOut() {
        val h = Harness()
        val reply = CompletableDeferred<MigraineDetail>()
        val store = h.store()
        try {
            h.response = { withContext(NonCancellable) { reply.await() } }
            store.open("account-a", CurrentSymptomItem(id = EPISODE_ID, symptomCode = "MIGRAINE"))
            h.account = "account-b"
            store.accountChanged(h.account)
            reply.completeExceptionally(ApiUnauthorizedException())
            assertEquals(MigraineSummaryState(), store.state.value)
            assertTrue(h.signOutAccounts.isEmpty())
        } finally { reply.completeExceptionally(CancellationException()); h.scope.cancel() }
    }

    @Test fun ordinaryTokenCancellationAndNetworkFailuresNeverSignOutOrRetry() {
        for (cancelToken in listOf(true, false)) {
            val h = Harness()
            try {
                if (cancelToken) h.token = { throw CancellationException("Synthetic cancellation") }
                else h.response = { throw IOException("Synthetic network failure") }
                h.start()
                assertNull(h.returned)
                assertTrue(if (cancelToken) h.failure is CancellationException else h.failure is IOException)
                assertEquals(if (cancelToken) 0 else 1, h.reads.size)
                assertEquals(1, h.tokenCalls)
                assertTrue(h.signOutAccounts.isEmpty())
            } finally { h.scope.cancel() }
        }
    }
}
