package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.*
import io.ktor.client.HttpClient
import io.ktor.client.engine.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.util.date.GMTDate
import io.ktor.utils.io.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class AccountDeletionExploreTest {
    @Test fun deletingCancelsSiblingRequestsAfterTokenChildCompletedAndPreventsCacheWrite() = runBlocking {
        val requestsStarted = CompletableDeferred<Unit>()
        val engine = object : HttpClientEngineBase("synthetic-deletion-explore") {
            override val config = HttpClientEngineConfig()
            override val supportedCapabilities = setOf(HttpTimeoutCapability)
            @OptIn(InternalAPI::class)
            override suspend fun execute(data: HttpRequestData): HttpResponseData {
                requestsStarted.complete(Unit)
                awaitCancellation()
            }
        }
        val client = HttpClient(engine) { defaultRequest { url("https://example.invalid") } }
        var cacheWritten = false
        val cache = object : ExploreCacheStore {
            override suspend fun read(accountId: String): CachedExplore? = null
            override suspend fun write(accountId: String, payload: ExplorePayload, savedAtEpochMillis: Long) { cacheWritten = true }
            override suspend fun clear(accountId: String) {}
        }
        var record: AccountDeletionRecord? = null
        val gate = AccountOperationGate(object : AccountDeletionRecords {
            override fun read(accountId: String) = record
            override fun write(accountId: String, next: AccountDeletionRecord?) { record = next }
        })
        val repo = ExploreRepository(GaiaApiClient("https://example.invalid", client, client), cache,
            { gate.track("a"); "synthetic-a" }, { "a" }, gate::track)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val refresh = scope.launch { repo.refresh("a") }
            withTimeout(2_000) { requestsStarted.await() }
            gate.pauseAndCancel("a")
            assertTrue(refresh.isCompleted); assertTrue(refresh.isCancelled); assertFalse(cacheWritten)
            assertTrue(runCatching { repo.refresh("a") }.exceptionOrNull() is AccountWorkPausedException)
        } finally { scope.cancel(); client.close(); engine.close() }
    }
}
