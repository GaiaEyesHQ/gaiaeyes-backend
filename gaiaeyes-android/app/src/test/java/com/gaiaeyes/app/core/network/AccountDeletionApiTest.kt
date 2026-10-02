package com.gaiaeyes.app.core.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngineBase
import io.ktor.client.engine.HttpClientEngineConfig
import io.ktor.client.engine.callContext
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.HttpTimeoutCapability
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.*
import io.ktor.http.content.OutgoingContent
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.date.GMTDate
import io.ktor.utils.io.ByteReadChannel
import io.ktor.utils.io.InternalAPI
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class AccountDeletionApiTest {
    @Test fun preflightIsAuthenticatedReadAndDeleteUsesPinnedTokenAndOneShotBody() = runBlocking {
        withClient(200, """{"ok":true,"data":{"user_id":"a","delete_ready":true,"auth_delete_ready":true,"rows_found":3}}""") { api, engine ->
            assertEquals(AccountDeletionPreflight("a", true, true), api.accountDeletionPreflight("synthetic-a"))
            assertEquals(HttpMethod.Get, engine.calls.single().method)
            assertEquals("/v1/profile/account/preflight", engine.calls.single().url.encodedPath)
            assertEquals("Bearer synthetic-a", engine.calls.single().headers[HttpHeaders.Authorization])
        }
        withClient(200, """{"ok":true,"data":{"deleted_user_id":"a","rows_deleted":3,"tables_touched":2}}""") { api, engine ->
            assertEquals(AccountDeletionResult("a", 3, 2), api.deleteAccount("synthetic-a"))
            val request = engine.calls.single()
            assertEquals(HttpMethod.Delete, request.method)
            assertEquals("/v1/profile/account", request.url.encodedPath)
            assertEquals("Bearer synthetic-a", request.headers[HttpHeaders.Authorization])
            assertTrue(request.body is OutgoingContent.ReadChannelContent)
        }
    }
    @Test fun missingConfirmationMalformedOrPartialSuccessFailsClosed() = runBlocking {
        for (body in listOf("{}", """{"ok":false,"data":{"deleted_user_id":"a","rows_deleted":3,"tables_touched":2}}""",
            """{"ok":true,"data":{"deleted_user_id":"a"}}""", """{"ok":true,"data":null}""", "not-json")) {
            withClient(200, body) { api, engine ->
                assertTrue(runCatching { api.deleteAccount("synthetic-a") }.isFailure)
                assertEquals(1, engine.calls.size)
            }
        }
    }
    @Test fun unauthorizedRedirectServerErrorAndNoContentNeverConfirmOrRetry() = runBlocking {
        for (status in listOf(401, 403, 302, 500, 503, 204)) {
            withClient(status, """{"ok":true,"data":{"deleted_user_id":"a","rows_deleted":3,"tables_touched":2}}""") { api, engine ->
                assertTrue(runCatching { api.deleteAccount("synthetic-a") }.isFailure)
                assertEquals(1, engine.calls.size)
            }
        }
    }
    @Test fun blankTokenDoesNotSendEitherRequest() = runBlocking {
        withClient(200, "{}") { api, engine ->
            assertTrue(runCatching { api.accountDeletionPreflight("") }.isFailure)
            assertTrue(runCatching { api.deleteAccount(" ") }.isFailure)
            assertTrue(engine.calls.isEmpty())
        }
    }
    private suspend fun withClient(status: Int, body: String, block: suspend (GaiaApiClient, Engine) -> Unit) {
        val engine = Engine(status, body)
        val client = HttpClient(engine) {
            followRedirects = false
            install(HttpTimeout)
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            defaultRequest { url("https://example.invalid") }
        }
        try { block(GaiaApiClient("https://example.invalid", client, client, client), engine) }
        finally { client.close(); engine.close() }
    }
    private class Engine(private val status: Int, private val body: String) : HttpClientEngineBase("synthetic-account-deletion") {
        override val config = HttpClientEngineConfig()
        override val supportedCapabilities = setOf(HttpTimeoutCapability)
        val calls = mutableListOf<HttpRequestData>()
        @OptIn(InternalAPI::class)
        override suspend fun execute(data: HttpRequestData): HttpResponseData {
            calls += data
            return HttpResponseData(HttpStatusCode.fromValue(status), GMTDate(),
                headersOf(HttpHeaders.ContentType, "application/json"), HttpProtocolVersion.HTTP_1_1,
                ByteReadChannel(body), callContext())
        }
    }
}
