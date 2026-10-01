package com.gaiaeyes.app.core.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngineBase
import io.ktor.client.engine.HttpClientEngineConfig
import io.ktor.client.engine.callContext
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.date.GMTDate
import io.ktor.utils.io.ByteReadChannel
import io.ktor.utils.io.InternalAPI
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class BillingApiClientTest {
    @Test fun usesAuthenticatedReadAndIgnoresUnneededPrivateFields() = runBlocking {
        withClient(200) { api, engine ->
            val response = api.billingEntitlements("synthetic-token")
            assertTrue(response.ok)
            assertEquals("a", response.userId)
            assertEquals("plus", response.entitlements.single().key)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Get, sent.method)
            assertEquals("/v1/billing/entitlements", sent.url.encodedPath)
            assertEquals("Bearer synthetic-token", sent.headers[HttpHeaders.Authorization])
        }
    }
    @Test fun unauthorizedAndServerFailureDoNotProduceMembership() = runBlocking {
        withClient(401) { api, _ ->
            assertTrue(runCatching { api.billingEntitlements("token") }.exceptionOrNull() is ApiUnauthorizedException)
        }
        withClient(503) { api, _ -> assertTrue(runCatching { api.billingEntitlements("token") }.isFailure) }
        withClient(200) { api, engine ->
            assertTrue(runCatching { api.billingEntitlements("") }.isFailure)
            assertTrue(engine.calls.isEmpty())
        }
    }
    private suspend fun withClient(status: Int, block: suspend (GaiaApiClient, Engine) -> Unit) {
        val engine = Engine(status)
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            defaultRequest { url("https://example.invalid") }
        }
        try { block(GaiaApiClient("https://example.invalid", client, client), engine) }
        finally { client.close(); engine.close() }
    }
    private class Engine(private val status: Int) : HttpClientEngineBase("synthetic-billing") {
        override val config = HttpClientEngineConfig()
        val calls = mutableListOf<HttpRequestData>()
        @OptIn(InternalAPI::class)
        override suspend fun execute(data: HttpRequestData): HttpResponseData {
            calls += data
            return HttpResponseData(HttpStatusCode.fromValue(status), GMTDate(),
                headersOf(HttpHeaders.ContentType, "application/json"), HttpProtocolVersion.HTTP_1_1,
                ByteReadChannel("""{"ok":true,"user_id":"a","email":"ignored@example.invalid","entitlements":[{"key":"plus","is_active":true,"expires_at":null,"term":"monthly"}]}"""), callContext())
        }
    }
}
