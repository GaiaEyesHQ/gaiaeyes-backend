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
import io.ktor.utils.io.*
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class MigraineApiClientTest {
    @Test
    fun readsOnlyRequestedCanonicalEpisodeWithExistingBearerAuth() = runBlocking {
        withClient { api, engine ->
            assertEquals(0, api.migraineDetail(TOKEN, EPISODE_ID).episode.severity)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Get, sent.method)
            assertEquals("/v1/symptoms/current/$EPISODE_ID/migraine-detail", sent.url.encodedPath)
            assertEquals("Bearer $TOKEN", sent.headers[HttpHeaders.Authorization])
        }
    }

    @Test
    fun patchAcknowledgesMatchingNextRevisionAndUsesOneShotBody() = runBlocking {
        withClient { api, engine ->
            val edit = MigraineStructuredEdit(2, medicines = fixtureDetail().episode.medicines)
            assertEquals(3L, api.updateMigraineDetail(TOKEN, EPISODE_ID, edit).revision)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Patch, sent.method)
            assertEquals("/v1/symptoms/current/$EPISODE_ID/migraine-detail", sent.url.encodedPath)
            assertTrue(sent.body is OutgoingContent.ReadChannelContent)
            assertEquals(ContentType.Application.Json, sent.body.contentType)
            assertEquals(edit.toJson(), bodyJson(sent))
            assertEquals("Bearer $TOKEN", sent.headers[HttpHeaders.Authorization])
        }
    }

    @Test
    fun followUpRequiresWholePromptEpisodeAndDetailAcknowledgment() = runBlocking {
        withClient(Reply(body = followUpReply())) { api, engine ->
            val request = followUpRequest()
            val result = api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, request)
            assertEquals("answered", result.prompt.status)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Post, sent.method)
            assertEquals("/v1/symptoms/follow-ups/$PROMPT_ID/respond", sent.url.encodedPath)
            assertEquals(request.toJson(), bodyJson(sent))
        }
    }

    @Test
    fun patchWithNanosecondsConfirmsCanonicalMicrosecondResponseInOneAttempt() = runBlocking {
        withClient { api, engine ->
            val original = fixtureDetail().episode.medicines.map { it.copy(
                takenAt = it.takenAt.copy(utc = "2026-09-15T13:05:06.123456789Z")) }
            val request = MigraineStructuredEdit(2, medicines = original)

            val saved = api.updateMigraineDetail(TOKEN, EPISODE_ID, request)

            assertEquals(3L, saved.revision)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Patch, sent.method)
            assertTrue(sent.body is OutgoingContent.ReadChannelContent)
            assertEquals(edit().toJson(), bodyJson(sent))
            assertEquals(fixtureDetail().episode.medicines, saved.episode.medicines)
            assertEquals("2026-09-15T13:05:06.123456789Z", original[0].takenAt.utc)
        }
    }

    @Test
    fun followUpWithNanosecondsFreezesMicrosecondBodyAndConfirmsOneResponse() = runBlocking {
        withClient(Reply(body = followUpReply())) { api, engine ->
            val original = fixtureDetail().episode.medicines.map { it.copy(
                takenAt = it.takenAt.copy(utc = "2026-09-15T08:05:06.123456789-05:00")) }
            val request = MigraineFollowUpRequest("ongoing", "2026-09-15T09:00:00.123456789-05:00",
                MigraineStructuredEdit(2, medicines = original))

            val saved = api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, request)

            assertEquals("answered", saved.prompt.status)
            assertEquals(3L, saved.migraineDetail.revision)
            val sent = engine.calls.single()
            assertEquals(HttpMethod.Post, sent.method)
            assertTrue(sent.body is OutgoingContent.ReadChannelContent)
            val body = bodyJson(sent)
            assertEquals("2026-09-15T14:00:00.123456Z", body.getValue("ts_utc").jsonPrimitive.content)
            assertEquals(edit().toJson(), body["migraine"])
            assertEquals(fixtureDetail().episode.medicines, saved.migraineDetail.episode.medicines)
            assertEquals("2026-09-15T09:00:00.123456789-05:00", request.timestampUtc)
        }
    }

    @Test
    fun precisionRepairDoesNotConfirmDifferentMicrosecondOrRetryEitherWrite() = runBlocking {
        val good = fixtureDetail()
        val medicines = good.episode.medicines.toMutableList()
        medicines[0] = medicines[0].copy(takenAt = medicines[0].takenAt.copy(utc = "2026-09-15T13:05:06.123457Z"))
        val wrong = good.copy(episode = good.episode.copy(medicines = medicines))
        val request = MigraineStructuredEdit(2, medicines = good.episode.medicines.map { it.copy(
            takenAt = it.takenAt.copy(utc = "2026-09-15T13:05:06.123456789Z")) })
        for (followUp in listOf(false, true)) {
            withClient(Reply(body = if (followUp) followUpReply(wrong) else detailReply(wrong))) { api, engine ->
                expectFailure(MigraineUnconfirmedWriteException::class.java) {
                    if (followUp) api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID,
                        MigraineFollowUpRequest("ongoing", "2026-09-15T14:00:00.123456789Z", request))
                    else api.updateMigraineDetail(TOKEN, EPISODE_ID, request)
                }
                assertEquals(1, engine.calls.size)
            }
        }
    }

    @Test
    fun replayAcknowledgementChangedFalseStillRequiresNextRevision() = runBlocking {
        withClient(Reply(body = fixtureText().replace("\"changed\": true", "\"changed\": false"))) { api, _ ->
            assertFalse(api.updateMigraineDetail(TOKEN, EPISODE_ID, edit()).changed)
        }
    }

    @Test
    fun explicitRejectionsDoNotRetryOrRefreshBehindTheCallersBack() = runBlocking {
        val cases = listOf(
            Triple(401, "not json", ApiUnauthorizedException::class.java),
            Triple(409, "not json", MigraineConflictException::class.java),
            Triple(422, "not json", MigraineRejectedException::class.java),
            Triple(403, "not json", MigraineRejectedException::class.java),
            Triple(404, """{"detail":"Migraine episode not found"}""", MigraineEpisodeNotFoundException::class.java),
            Triple(404, """{"detail":"Not Found"}""", MigraineUnavailableException::class.java),
            Triple(503, """{"detail":"structured migraine detail storage is not installed"}""", MigraineUnavailableException::class.java),
        )
        for ((status, body, error) in cases) withClient(Reply(status, body)) { api, engine ->
            expectFailure(error) { api.updateMigraineDetail(TOKEN, EPISODE_ID, edit()) }
            assertEquals(1, engine.calls.size)
        }
    }

    @Test
    fun malformedEmptyAndFalseSuccessRepliesStayUnconfirmedForBothWrites() = runBlocking {
        for (body in listOf("", "not json", "{}", "{\"ok\":true,\"data\":null}",
            "{\"ok\":false,\"data\":null}", "{\"ok\":true,\"data\":{}}")) {
            for (followUp in listOf(false, true)) withClient(Reply(body = body)) { api, engine ->
                expectFailure(MigraineUnconfirmedWriteException::class.java) {
                    if (followUp) api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, followUpRequest())
                    else api.updateMigraineDetail(TOKEN, EPISODE_ID, edit())
                }
                assertEquals(1, engine.calls.size)
            }
        }
    }

    @Test
    fun wrongEpisodeRevisionAndDroppedMedicineNeverConfirmSave() = runBlocking {
        val original = fixtureDetail()
        val bad = listOf(original.copy(revision = 4, episode = original.episode.copy(lifecycle = original.episode.lifecycle.copy(revision = 4))),
            original.copy(episode = original.episode.copy(episodeId = PROMPT_ID)),
            original.copy(episode = original.episode.copy(medicines = original.episode.medicines.dropLast(1))),
            original.copy(episode = original.episode.copy(medicines = original.episode.medicines.reversed())))
        for (value in bad) withClient(Reply(body = detailReply(value))) { api, engine ->
            expectFailure(MigraineUnconfirmedWriteException::class.java) { api.updateMigraineDetail(TOKEN, EPISODE_ID, edit()) }
            assertEquals(1, engine.calls.size)
        }
    }

    @Test
    fun unansweredWrongOrStillPendingPromptNeverConfirmsFollowUp() = runBlocking {
        val good = followUpReply()
        val invalid = listOf(
            good.replace("\"answered\"", "\"pending\""),
            good.replace("\"id\":\"$PROMPT_ID\"", "\"id\":\"$EPISODE_ID\""),
            good.replace("\"current_state\":\"ongoing\"", "\"current_state\":\"resolved\""),
            good.replace("\"pending_follow_up\":null", "\"pending_follow_up\":{\"id\":\"$PROMPT_ID\"}"),
            """{"ok":true,"data":{"prompt":{"id":"$PROMPT_ID","episode_id":"$EPISODE_ID","symptom_code":"MIGRAINE","status":"answered"},"episode":{"id":"$EPISODE_ID"}}}""",
        )
        for (body in invalid) withClient(Reply(body = body)) { api, engine ->
            expectFailure(MigraineUnconfirmedWriteException::class.java) {
                api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, followUpRequest())
            }
            assertEquals(1, engine.calls.size) // No GET fallback can prove a prompt was answered.
        }
    }

    @Test
    fun transientStatusOrRedirectDoesNotCauseAutomaticResend() = runBlocking {
        for (status in listOf(408, 429, 500, 502, 503, 307)) withClient(Reply(status, "{}",
            headersOf(HttpHeaders.RetryAfter to listOf("0"), HttpHeaders.Location to listOf("https://example.invalid/redirect")))) { api, engine ->
            expectFailure(MigraineUnconfirmedWriteException::class.java) {
                api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, followUpRequest())
            }
            assertEquals(1, engine.calls.size)
        }
    }

    @Test
    fun lostResponseRetainsUncertaintyAndNeverEnqueuesOrResends() = runBlocking {
        withClient(failure = IOException("synthetic connection loss after submit")) { api, engine ->
            val request = followUpRequest()
            val original = request.toJson()
            expectFailure(MigraineUnconfirmedWriteException::class.java) {
                api.respondMigraineFollowUp(TOKEN, EPISODE_ID, PROMPT_ID, request)
            }
            assertEquals(1, engine.calls.size)
            assertEquals(original, bodyJson(engine.calls.single()))
            assertEquals(original, request.toJson())
        }
    }

    @Test
    fun cancellationPropagatesWithoutResendOrFalseConfirmation() = runBlocking {
        withClient(failure = CancellationException("synthetic cancellation")) { api, engine ->
            expectFailure(CancellationException::class.java) { api.updateMigraineDetail(TOKEN, EPISODE_ID, edit()) }
            assertEquals(1, engine.calls.size)
        }
    }

    @Test
    fun invalidInputOrBlankTokenMakesNoTransportCall() = runBlocking {
        withClient { api, engine ->
            expectFailure(IllegalArgumentException::class.java) { api.migraineDetail(" ", EPISODE_ID) }
            expectFailure(IllegalArgumentException::class.java) { api.migraineDetail(TOKEN, "../other") }
            expectFailure(IllegalArgumentException::class.java) { api.updateMigraineDetail(TOKEN, EPISODE_ID, MigraineStructuredEdit(2)) }
            expectFailure(IllegalArgumentException::class.java) { api.updateMigraineDetail(TOKEN, EPISODE_ID, edit().copy(expectedRevision = -1)) }
            expectFailure(IllegalArgumentException::class.java) { api.respondMigraineFollowUp(TOKEN, EPISODE_ID, "bad", followUpRequest()) }
            assertEquals(0, engine.calls.size)
        }
    }

    @Test
    fun invalidReadsAreNotUsableDetailsAndNeverTriggerAWrite() = runBlocking {
        val wrongSchema = fixtureText().replace("\"schema_version\": \"1.0\"", "\"schema_version\": \"9.0\"")
        for (body in listOf("{}", "[]", "not json", wrongSchema,
            fixtureText().replace("\"severity\": 0", "\"severity\": 11"))) withClient(Reply(body = body)) { api, engine ->
            expectFailure(MigraineInvalidResponseException::class.java) { api.migraineDetail(TOKEN, EPISODE_ID) }
            assertEquals(listOf(HttpMethod.Get), engine.calls.map { it.method })
        }
    }

    @Test
    fun existingBasicUpdateKeepsRoutePayloadAndUnauthorizedBehavior() = runBlocking {
        val reply = """{"ok":true,"data":{"id":"legacy-id","symptom_code":"MIGRAINE","severity":0}}"""
        withClient(Reply(body = reply)) { api, engine ->
            val request = CurrentSymptomUpdateRequest(severity = 0, timestampUtc = "2026-09-15T13:00:00Z")
            assertEquals(0, api.updateCurrentSymptom(TOKEN, "legacy-id", request).severity)
            val sent = engine.calls.single()
            assertEquals("/v1/symptoms/current/legacy-id/updates", sent.url.encodedPath)
            assertEquals("Bearer $TOKEN", sent.headers[HttpHeaders.Authorization])
            assertEquals(migraineJson.parseToJsonElement("""{"severity":0,"ts_utc":"2026-09-15T13:00:00Z"}"""), bodyJson(sent))
        }
        withClient(Reply(401, "{}")) { api, engine ->
            expectFailure(ApiUnauthorizedException::class.java) { api.updateCurrentSymptom(TOKEN, "legacy-id", CurrentSymptomUpdateRequest(severity = 0)) }
            assertEquals(1, engine.calls.size)
        }
    }

    private fun edit() = MigraineStructuredEdit(2, medicines = fixtureDetail().episode.medicines)
    private fun followUpRequest() = MigraineFollowUpRequest("ongoing", "2026-09-15T14:00:00Z", edit())
    private fun detailReply(detail: MigraineDetail) = buildJsonObject {
        put("ok", true); put("data", migraineJson.encodeToJsonElement(detail))
    }.toString()
    private fun followUpReply(detail: MigraineDetail = fixtureDetail()) = """{"ok":true,"data":{"prompt":{"id":"$PROMPT_ID","episode_id":"$EPISODE_ID","symptom_code":"MIGRAINE","status":"answered"},"episode":{"id":"$EPISODE_ID","symptom_code":"MIGRAINE","current_state":"ongoing","pending_follow_up":null},"migraine_detail":${migraineJson.encodeToJsonElement(detail)}}}"""

    private suspend fun withClient(
        reply: Reply = Reply(), failure: Exception? = null,
        block: suspend (GaiaApiClient, RecordingEngine) -> Unit,
    ) {
        val engine = RecordingEngine(reply, failure)
        val client = HttpClient(engine) {
            expectSuccess = false
            followRedirects = false
            install(HttpTimeout)
            install(ContentNegotiation) { json(migraineJson) }
            defaultRequest { url("https://example.invalid") }
        }
        try { block(GaiaApiClient("https://example.invalid", client, client), engine) }
        finally { client.close(); engine.close() }
    }

    private suspend fun bodyJson(data: HttpRequestData): JsonObject {
        val bytes = when (val body = data.body) {
            is OutgoingContent.ByteArrayContent -> body.bytes().decodeToString()
            is OutgoingContent.ReadChannelContent -> body.readFrom().readRemaining().readText()
            else -> error("Unexpected request body type")
        }
        return migraineJson.parseToJsonElement(bytes).jsonObject
    }

    private suspend fun expectFailure(expected: Class<out Throwable>, block: suspend () -> Unit) {
        val failure = try { block(); null } catch (error: Throwable) { error }
        assertNotNull("Expected ${expected.simpleName}", failure)
        assertTrue("Expected ${expected.simpleName}, got ${failure?.javaClass?.simpleName}", expected.isInstance(failure))
    }

    private data class Reply(val status: Int = 200, val body: String = fixtureText(), val headers: Headers = Headers.Empty)
    private class RecordingEngine(private val reply: Reply, private val failure: Exception?) : HttpClientEngineBase("synthetic-migraine") {
        override val config = HttpClientEngineConfig()
        override val supportedCapabilities = setOf(HttpTimeoutCapability)
        val calls = mutableListOf<HttpRequestData>()
        @OptIn(InternalAPI::class)
        override suspend fun execute(data: HttpRequestData): HttpResponseData {
            calls += data
            failure?.let { throw it }
            return HttpResponseData(HttpStatusCode.fromValue(reply.status), GMTDate(), Headers.build {
                append(HttpHeaders.ContentType, "application/json")
                appendAll(reply.headers)
            }, HttpProtocolVersion.HTTP_1_1, ByteReadChannel(reply.body), callContext())
        }
    }

    private companion object { const val TOKEN = "synthetic-access-token" }
}
