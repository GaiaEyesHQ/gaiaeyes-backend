package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.*
import io.ktor.client.HttpClient
import io.ktor.client.engine.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.date.GMTDate
import io.ktor.utils.io.*
import java.io.IOException
import java.util.Collections
import kotlinx.coroutines.*
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class ExploreRepositoryTest {
    private class MemoryCache : ExploreCacheStore {
        val rows = mutableMapOf<String, CachedExplore>()
        var writes = 0
        override suspend fun read(accountId: String) = rows[accountId]
        override suspend fun write(accountId: String, payload: ExplorePayload, savedAtEpochMillis: Long) { rows[accountId] = CachedExplore(payload, savedAtEpochMillis); writes++ }
        override suspend fun clear(accountId: String) { rows.remove(accountId) }
    }
    private class Engine : HttpClientEngineBase("environment-fixture") {
        override val config = HttpClientEngineConfig()
        override val supportedCapabilities = setOf(HttpTimeoutCapability)
        val requests = Collections.synchronizedList(mutableListOf<HttpRequestData>())
        var handler: suspend (HttpRequestData) -> Pair<Int, String> = { request ->
            val body = when (request.url.encodedPath) {
                "/v1/earth/schumann/latest" -> """{"ok":true,"generated_at":"2026-09-20T16:00:00Z","harmonics":{"f0":7.89}}"""
                "/v1/earth/ulf/latest" -> """{"latest_context":{"ts_utc":"2026-09-20T16:00:00Z","regional_intensity":20.2},"latest_by_station":[]}"""
                "/v1/space/magnetosphere" -> """{"ok":true,"data":{"ts":"2026-09-20T16:00:00Z","kpis":{"kp":3},"sw":{"v_kms":430},"series":{"r0":[{"t":"2026-09-20T16:00:00Z","v":10.2}]}}}"""
                else -> """{"ok":true}"""
            }
            200 to body
        }
        @OptIn(InternalAPI::class)
        override suspend fun execute(data: HttpRequestData): HttpResponseData {
            check(data.method == HttpMethod.Get && data.url.host == "example.invalid")
            requests += data
            val (status, body) = handler(data)
            return HttpResponseData(HttpStatusCode.fromValue(status), GMTDate(), headersOf(HttpHeaders.ContentType, "application/json"), HttpProtocolVersion.HTTP_1_1, ByteReadChannel(body), callContext())
        }
    }
    private class Harness : AutoCloseable {
        val engine = Engine()
        val client = HttpClient(engine) { install(HttpTimeout); install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }; defaultRequest { url("https://example.invalid") } }
        val cache = MemoryCache()
        var account: String? = "a"
        var token: suspend () -> String = { "fake-session-token" }
        val repo = ExploreRepository(GaiaApiClient("https://example.invalid", client, client), cache, { token() }, { account })
        override fun close() { client.close(); engine.close() }
    }
    @Test fun protectedReadsCarrySessionTokenPublicSignalsDoNotAndHistoryDecodes() = runBlocking {
        Harness().use { h ->
            val p = h.repo.refresh("a").payload
            assertEquals(9, h.engine.requests.size)
            val protected = setOf("/v1/space/magnetosphere", "/v1/space/history", "/v1/quakes/latest")
            h.engine.requests.forEach { r -> assertEquals(if (r.url.encodedPath in protected) "Bearer fake-session-token" else null, r.headers[HttpHeaders.Authorization]) }
            assertEquals(10.2, p.magnetosphere!!.data!!.series.r0.single().v!!, 0.001)
            assertNotNull(p.ulf?.context)
            assertTrue(p.sourceErrors.isEmpty())
        }
    }
    @Test fun failedSourceKeepsOldObservationAndFailureAcrossCacheWhileSiblingsUpdate() = runBlocking {
        Harness().use { h ->
            val first = h.repo.refresh("a")
            val handler = h.engine.handler
            h.engine.handler = { if (it.url.encodedPath.endsWith("schumann/latest")) throw IOException("offline") else handler(it) }
            val next = h.repo.refresh("a")
            assertEquals(first.payload.schumann, next.payload.schumann)
            assertEquals(first.payload.fetchedAt["Schumann Resonance"], next.payload.fetchedAt["Schumann Resonance"])
            assertEquals("request_failed", next.payload.sourceErrors["Schumann Resonance"])
            assertEquals(next.payload.sourceErrors, h.repo.cached("a")!!.payload.sourceErrors)
            assertNotNull(next.payload.ulf)
        }
    }
    @Test fun protected401DoesNotBlockPublicSignalsOrDeleteTheirCache() = runBlocking {
        Harness().use { h ->
            val handler = h.engine.handler
            h.engine.handler = { if (it.url.encodedPath.startsWith("/v1/space/")) 401 to "{}" else handler(it) }
            val p = h.repo.refresh("a").payload
            assertEquals("sign_in_required", p.sourceErrors["Magnetosphere"])
            assertNotNull(p.schumann)
            assertNotNull(p.ulf)
            assertNull(p.magnetosphere)
        }
    }
    @Test fun missingSessionDoesNotBlockPublicSources() = runBlocking {
        Harness().use { h ->
            h.token = { error("no session") }
            val p = h.repo.refresh("a").payload
            assertNotNull(p.ulf)
            assertNotNull(p.schumann)
            assertTrue(h.engine.requests.none { it.url.encodedPath.startsWith("/v1/space/") })
        }
    }
    @Test fun malformedLatestDoesNotDiscardIndependentHistory() = runBlocking {
        Harness().use { h ->
            val handler = h.engine.handler
            h.engine.handler = { if (it.url.encodedPath.endsWith("schumann/latest")) 200 to "not json" else handler(it) }
            val p = h.repo.refresh("a").payload
            assertNull(p.schumann)
            assertNotNull(p.schumannSeries)
            assertEquals("request_failed", p.sourceErrors["Schumann Resonance"])
        }
    }
    @Test fun cancellationAndAccountReplacementDoNotWriteCache() = runBlocking {
        Harness().use { h ->
            h.token = { h.account = "b"; "fake-b" }
            try { h.repo.refresh("a"); fail("expected cancellation") } catch (_: kotlinx.coroutines.CancellationException) { }
            assertEquals(0, h.cache.writes)
            assertTrue(h.engine.requests.none { it.headers[HttpHeaders.Authorization] != null })
        }
    }
}
