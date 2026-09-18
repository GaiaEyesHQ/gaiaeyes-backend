package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.MigraineFollowUpRepository
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
import java.math.BigDecimal
import java.util.Collections
import kotlinx.coroutines.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class MigraineFollowUpStoreTest {
    @Test fun storageUnavailableFirstSaveCanExplicitlyRecoverSameEditedResponse() = runBlocking {
        checkUnavailableFirstSave(Reply(503, """{"detail":"structured migraine detail storage is not installed"}"""))
    }

    @Test fun routeUnavailableFirstSaveCanExplicitlyRecoverSameEditedResponse() = runBlocking {
        checkUnavailableFirstSave(Reply(404, """{"detail":"Not Found"}"""))
    }

    @Test fun storageUnavailableAfterUncertaintyKeepsSameResponseFrozen() = runBlocking {
        checkUnavailableAfterUncertainty(Reply(503, """{"detail":"structured migraine detail storage is not installed"}"""))
    }

    @Test fun routeUnavailableAfterUncertaintyKeepsSameResponseFrozen() = runBlocking {
        checkUnavailableAfterUncertainty(Reply(404, """{"detail":"Not Found"}"""))
    }

    private suspend fun checkUnavailableFirstSave(unavailable: Reply) = withHarness { h ->
        h.open()
        val baseline = h.store.state.value.baseline!!
        val firstRow = h.store.state.value.draft!!.medicines.first()
        h.store.replaceMedicine(firstRow.id, firstRow.value.copy(notes = "edited existing entry"))
        h.store.appendMedicine(firstRow.value.copy(notes = "ordered new entry"))
        h.store.moveMedicine(3, 1)
        h.store.setAnswers(MigraineFollowUpAnswers("improving", notes = MigraineTextChange.Clear,
            detailChoice = "better", detailText = "synthetic detail", noteText = "synthetic answer", timeBucket = "recent"))
        val draft = h.store.state.value.draft!!
        h.server.postReply = unavailable
        h.store.save(); h.await(MigraineFollowUpPhase.UNAVAILABLE)
        val pending = h.store.state.value.pendingRequest!!
        val tokens = h.tokenReads
        assertSame(baseline, h.store.state.value.baseline)
        assertSame(draft, h.store.state.value.draft)
        assertEquals(3L, pending.migraine.expectedRevision)
        assertEquals(listOf(0, null, 1, 2), draft.medicines.map { it.originalIndex })
        assertEquals(draft.medicines.map { it.value }, pending.migraine.medicines)
        assertEquals(draft.responseTimestampUtc, pending.timestampUtc)
        assertNull(h.store.state.value.saved)
        assertEquals(0, h.server.mutations)
        assertEquals(1, h.server.posts.size)

        // Initial-load retry must not rebuild or replace an already edited draft.
        h.store.retryLoad(); h.store.save(); h.store.reviewSavedVersion()
        h.store.appendMedicine(firstRow.value); h.store.setAnswers(MigraineFollowUpAnswers("worse"))
        assertSame(draft, h.store.state.value.draft)
        assertSame(pending, h.store.state.value.pendingRequest)
        assertEquals(tokens, h.tokenReads)
        assertEquals(1, h.server.getCount)
        assertEquals(1, h.server.posts.size)

        h.server.postReply = null
        h.clock = "2026-09-18T12:00:00Z"
        val gate = CompletableDeferred<Unit>(); h.tokenGate = gate
        try {
            h.store.retrySameResponse()
            assertEquals("Loaded unavailable response must have an explicit retry", MigraineFollowUpPhase.SAVING, h.store.state.value.phase)
            assertSame(draft, h.store.state.value.draft) // Same row objects/IDs, answers and order.
            assertSame(baseline, h.store.state.value.baseline)
            assertSame(pending, h.store.state.value.pendingRequest)
            assertEquals(1, h.server.posts.size) // Still awaiting auth for this explicit action.
        } finally { gate.complete(Unit) }
        h.await(MigraineFollowUpPhase.SAVED)
        assertEquals(2, h.server.posts.size)
        assertEquals(h.server.postBodies[0], h.server.postBodies[1])
        assertEquals(1, h.server.mutations)
        assertEquals(1, h.server.getCount)
        assertEquals(1, h.clockReads)
        val saved = h.store.state.value.saved!!.migraineDetail
        assertEquals(baseline.revision + 1, saved.revision)
        assertEquals(draft.medicines.map { it.value }, saved.episode.medicines)
        assertEquals("improving", saved.episode.state)
        assertNull(saved.episode.notes)
    }

    private suspend fun checkUnavailableAfterUncertainty(unavailable: Reply) = withHarness { h ->
        h.open()
        h.store.appendMedicine(h.server.detail.episode.medicines[0])
        h.store.setAnswers(MigraineFollowUpAnswers("improving", detailChoice = "better", noteText = "retained response"))
        val draft = h.store.state.value.draft!!
        h.server.loseNextReceipt = true
        h.store.save(); h.await(MigraineFollowUpPhase.UNCERTAIN)
        val pending = h.store.state.value.pendingRequest!!
        h.server.postReply = unavailable
        h.store.retrySameResponse(); h.await(MigraineFollowUpPhase.UNCERTAIN)
        assertEquals(2, h.server.posts.size)
        assertEquals(1, h.server.mutations)
        assertSame(pending, h.store.state.value.pendingRequest)
        assertSame(draft, h.store.state.value.draft)
        assertNull(h.store.state.value.saved)
        h.store.setAnswers(MigraineFollowUpAnswers("worse"))
        h.store.removeMedicine(draft.medicines.first().id); h.store.retryLoad(); h.store.save()
        assertSame(draft, h.store.state.value.draft)
        assertEquals(2, h.server.posts.size)
        h.server.postReply = null
        h.store.retrySameResponse(); h.await(MigraineFollowUpPhase.SAVED)
        assertEquals(3, h.server.posts.size)
        assertEquals(1, h.server.postBodies.toSet().size)
        assertEquals(1, h.server.mutations)
        assertEquals(1, h.server.getCount)
        assertEquals(1, h.clockReads)
        assertEquals(draft.medicines.map { it.value }, h.store.state.value.saved!!.migraineDetail.episode.medicines)
    }

    @Test fun canonicalReadPreservesZeroMissingAndOrderedRowOrigins() = runBlocking {
        withHarness { h ->
            h.open()
            val state = h.store.state.value
            assertEquals(0, state.baseline!!.episode.severity)
            assertEquals(listOf(0, 1, 2), state.draft!!.medicines.map { it.originalIndex })
            assertEquals(listOf("unknown", "none", null), state.draft.medicines.map { it.value.reportedRelief })
            assertEquals(3, state.draft.medicines.map { it.id }.toSet().size)
            assertNull(state.draft.medicines[1].value.doseAmount)
            assertEquals(BigDecimal("0.1000000000000000000001"), state.draft.medicines[0].value.doseAmount)
            assertNull(state.draft.request(3).migraine.medicines) // untouched means retain
        }
        withHarness { h ->
            h.server.detail = h.server.detail.copy(episode = h.server.detail.episode.copy(severity = null))
            h.open()
            assertNull(h.store.state.value.baseline!!.episode.severity)
        }
    }

    @Test fun canonicalSaveEditsRemovesAndOrdersEntriesWithoutNameMerging() = runBlocking {
        withHarness { h ->
            h.open()
            val rows = h.store.state.value.draft!!.medicines
            h.store.replaceMedicine(rows[0].id, rows[0].value.copy(notes = "changed only this entry"))
            h.store.removeMedicine(rows[1].id)
            h.store.appendMedicine(rows[0].value.copy(doseAmount = BigDecimal("12.00000000000000000001"), notes = "new entry"))
            h.store.moveMedicine(2, 1)
            val draft = h.store.state.value.draft!!
            assertEquals(listOf(0, null, 2), draft.medicines.map { it.originalIndex })
            h.store.setAnswers(draft.answers.copy(state = "improving", notes = MigraineTextChange.Clear,
                earlySigns = emptyList(), detailChoice = "better", noteText = "response note", timeBucket = "recent"))
            h.store.save()
            h.await(MigraineFollowUpPhase.SAVED)
            val saved = h.store.state.value.saved!!.migraineDetail
            assertEquals(4L, saved.revision)
            assertEquals(0, saved.episode.severity)
            assertEquals(EPISODE_ID, saved.episode.episodeId)
            assertEquals(draft.medicines.map { it.value }, saved.episode.medicines)
            assertEquals(rows[0].value.takenAt, saved.episode.medicines[0].takenAt)
            assertNull(saved.episode.notes)
            assertTrue(saved.episode.earlySigns.isEmpty())
            assertNull(h.store.state.value.draft)
            assertEquals(1, h.server.mutations)
            assertEquals(1, h.server.posts.size)
        }
    }

    @Test fun uncertainWriteFreezesOneRequestAndExplicitRetryDoesNotDuplicateMedicine() = runBlocking {
        withHarness { h ->
            h.open()
            h.store.appendMedicine(h.server.detail.episode.medicines[0])
            h.server.loseNextReceipt = true
            h.store.save()
            h.await(MigraineFollowUpPhase.UNCERTAIN)
            val pending = h.store.state.value.pendingRequest!!
            assertNull(h.store.state.value.saved)
            assertEquals(1, h.server.posts.size)
            h.store.appendMedicine(h.server.detail.episode.medicines[0])
            h.store.setAnswers(MigraineFollowUpAnswers("worse"))
            h.store.save()
            assertSame(pending, h.store.state.value.pendingRequest)
            assertEquals(4, h.store.state.value.draft!!.medicines.size)
            assertEquals(1, h.server.posts.size)
            h.store.retrySameResponse()
            h.await(MigraineFollowUpPhase.SAVED)
            assertEquals(h.server.posts[0], h.server.posts[1])
            assertEquals(1, h.server.mutations)
            assertEquals(4, h.store.state.value.saved!!.migraineDetail.episode.medicines.size)
            assertEquals(1, h.clockReads)
            assertEquals("2026-09-17T12:00:00.123456Z", h.server.posts[0]["ts_utc"]!!.jsonPrimitive.content)
        }
    }

    @Test fun matchingGetIsOnlyReviewAndExplicitUseCannotReplayDraftAdd() = runBlocking {
        withHarness { h ->
            h.open()
            h.store.appendMedicine(h.server.detail.episode.medicines[0])
            h.server.loseNextReceipt = true
            h.store.save(); h.await(MigraineFollowUpPhase.UNCERTAIN)
            val pending = h.store.state.value.pendingRequest
            h.store.reviewSavedVersion(); h.await(MigraineFollowUpPhase.REVIEW)
            assertNull(h.store.state.value.saved)
            assertEquals(4, h.store.state.value.reviewed!!.episode.medicines.size)
            assertSame(pending, h.store.state.value.pendingRequest)
            h.store.useReviewedVersion()
            assertEquals(MigraineFollowUpPhase.REVIEWED, h.store.state.value.phase)
            h.store.save(); h.store.retrySameResponse()
            assertNull(h.store.state.value.saved)
            assertEquals(1, h.server.posts.size)
            assertEquals(4, h.store.state.value.draft!!.medicines.size)
        }
    }

    @Test fun conflictNeverMergesOrRebasesAndReviewKeepsOriginalRequest() = runBlocking {
        withHarness { h ->
            h.open(); h.store.appendMedicine(h.server.detail.episode.medicines[0])
            h.server.status = 409
            h.store.save(); h.await(MigraineFollowUpPhase.CONFLICT)
            val pending = h.store.state.value.pendingRequest!!
            assertEquals(3L, pending.migraine.expectedRevision)
            h.store.retrySameResponse(); h.store.save()
            assertEquals(1, h.server.posts.size)
            h.server.status = null
            h.server.detail = h.server.detail.copy(revision = 5, episode = h.server.detail.episode.copy(
                lifecycle = h.server.detail.episode.lifecycle.copy(revision = 5)))
            h.store.reviewSavedVersion(); h.await(MigraineFollowUpPhase.REVIEW)
            assertEquals(3L, h.store.state.value.baseline!!.revision)
            assertSame(pending, h.store.state.value.pendingRequest)
            assertNull(h.store.state.value.saved)
        }
    }

    @Test fun conflictAfterUncertaintyRetainsExactOriginalInsteadOfFreshAdd() = runBlocking {
        withHarness { h ->
            h.open(); h.server.loseNextReceipt = true
            h.store.appendMedicine(h.server.detail.episode.medicines[0]); h.store.save()
            h.await(MigraineFollowUpPhase.UNCERTAIN)
            val request = h.store.state.value.pendingRequest
            h.server.status = 409
            h.store.retrySameResponse(); h.await(MigraineFollowUpPhase.CONFLICT)
            assertSame(request, h.store.state.value.pendingRequest)
            assertEquals(h.server.posts[0], h.server.posts[1])
            assertEquals(1, h.server.mutations)
            assertNull(h.store.state.value.saved)
        }
    }

    @Test fun deletionIsTerminalAndDoesNotClaimSaveOrResurrectEpisode() = runBlocking {
        withHarness { h ->
            h.open(); h.server.status = 404
            h.store.save(); h.await(MigraineFollowUpPhase.DELETED)
            h.store.save(); h.store.retrySameResponse(); h.store.reviewSavedVersion()
            assertEquals(1, h.server.posts.size)
            assertNotNull(h.store.state.value.draft)
            assertNull(h.store.state.value.saved)
        }
    }

    @Test fun invalidDoseUnitReliefAndTimeNeverReachAuthOrTransport() = runBlocking {
        val valid = fixtureDetail().episode.medicines[0]
        val bad = listOf(valid.copy(name = " "), valid.copy(doseAmount = BigDecimal.ZERO),
            valid.copy(doseAmount = BigDecimal("-1")), valid.copy(doseUnit = null),
            valid.copy(doseAmount = null), valid.copy(takenAt = valid.takenAt.copy(utc = "not a date")),
            valid.copy(takenAt = valid.takenAt.copy(utcOffsetMinutes = 999)),
            valid.copy(reportedRelief = "invented"), valid.copy(reportedRelief = null, reliefReportedAt = valid.takenAt))
        for (medicine in bad) withHarness { h ->
            h.open(); val tokens = h.tokenReads
            h.store.appendMedicine(medicine); h.store.save()
            assertEquals(MigraineFollowUpPhase.EDITING, h.store.state.value.phase)
            assertEquals(MigraineFollowUpProblem.INVALID_INPUT, h.store.state.value.problem)
            assertEquals(tokens, h.tokenReads)
            assertTrue(h.server.posts.isEmpty())
        }
    }

    @Test fun badResponseTimestampAndStateDoNotWrite() = runBlocking {
        withHarness { h ->
            h.clock = "bad time"; h.open(); h.store.save()
            assertEquals(MigraineFollowUpProblem.INVALID_INPUT, h.store.state.value.problem)
            assertTrue(h.server.posts.isEmpty())
        }
        withHarness { h ->
            h.open(); h.store.setAnswers(MigraineFollowUpAnswers("invalid")); h.store.save()
            assertEquals(MigraineFollowUpProblem.INVALID_INPUT, h.store.state.value.problem)
            assertTrue(h.server.posts.isEmpty())
        }
    }

    @Test fun invalidAcknowledgementNeverBecomesSavedSuccess() = runBlocking {
        for (kind in listOf("revision", "episode", "prompt", "medicine", "pending", "malformed")) withHarness { h ->
            h.open(); h.store.appendMedicine(h.server.detail.episode.medicines[0]); h.server.badReceipt = kind
            h.store.save(); h.await(MigraineFollowUpPhase.UNCERTAIN)
            assertNull(h.store.state.value.saved)
            assertNotNull(h.store.state.value.pendingRequest)
            assertEquals(1, h.server.posts.size)
        }
    }

    @Test fun definitiveRejectionKeepsEditableDraftButPriorUncertaintyStaysFrozen() = runBlocking {
        withHarness { h ->
            h.open(); h.server.status = 422; h.store.save(); h.await(MigraineFollowUpPhase.EDITING)
            assertEquals(MigraineFollowUpProblem.REJECTED, h.store.state.value.problem)
            assertNull(h.store.state.value.pendingRequest)
            assertNotNull(h.store.state.value.draft)
        }
        withHarness { h ->
            h.open(); h.server.loseNextReceipt = true; h.store.save(); h.await(MigraineFollowUpPhase.UNCERTAIN)
            h.server.status = 422; h.store.retrySameResponse(); h.await(MigraineFollowUpPhase.CONFLICT)
            assertNotNull(h.store.state.value.pendingRequest)
            assertNull(h.store.state.value.saved)
        }
    }

    @Test fun accountChangeAndCloseDuringNonCooperativeAuthBlockWrite() = runBlocking {
        for (action in listOf("account", "logout", "close", "episode")) withHarness { h ->
            h.open(); val gate = CompletableDeferred<Unit>(); h.tokenGate = gate
            h.store.save(); h.await(MigraineFollowUpPhase.SAVING)
            h.changeSelection(action)
            gate.complete(Unit); h.scope.coroutineContext[Job]!!.children.toList().joinAll()
            assertTrue(h.server.posts.isEmpty())
            assertEquals(0, h.signOuts)
            assertTrue(h.store.state.value.phase != MigraineFollowUpPhase.SAVED)
            if (action == "episode") assertEquals(SECOND_EPISODE, h.store.state.value.episodeId)
        }
    }

    @Test fun staleReadAfterLogoutOrEpisodeChangeCannotEnterNewSelection() = runBlocking {
        for (action in listOf("account", "logout", "close", "episode")) withHarness { h ->
            val gate = CompletableDeferred<Unit>(); h.readGate = gate
            h.store.open(ACCOUNT, EPISODE_ID, PROMPT_ID)
            h.readReached.await()
            h.changeSelection(action)
            gate.complete(Unit); h.scope.coroutineContext[Job]!!.children.toList().joinAll()
            assertNull(h.store.state.value.saved)
            if (action == "episode") assertEquals(SECOND_EPISODE, h.store.state.value.baseline!!.episode.episodeId)
            else assertNull(h.store.state.value.baseline)
        }
    }

    @Test fun staleCommittedWriteAfterAccountOrEpisodeChangeCannotShowSuccess() = runBlocking {
        for (action in listOf("account", "logout", "close", "episode")) withHarness { h ->
            h.open(); val gate = CompletableDeferred<Unit>(); h.writeGate = gate
            h.store.save(); h.writeReached.await()
            h.changeSelection(action)
            gate.complete(Unit); h.scope.coroutineContext[Job]!!.children.toList().joinAll()
            assertEquals(1, h.server.mutations) // Cancellation cannot undo a dispatched server write.
            assertNull(h.store.state.value.saved)
            if (action == "episode") assertEquals(SECOND_EPISODE, h.store.state.value.episodeId)
            else assertEquals(MigraineFollowUpPhase.CLOSED, h.store.state.value.phase)
        }
    }

    @Test fun staleUnauthorizedResponseCannotSignOutReplacementAccount() = runBlocking {
        withHarness { h ->
            h.open(); h.unauthorizedAfterWrite = true
            val gate = CompletableDeferred<Unit>(); h.writeGate = gate
            h.store.save(); h.writeReached.await()
            h.account = "replacement-account" // No observer needed for the request boundary.
            gate.complete(Unit); h.scope.coroutineContext[Job]!!.children.toList().joinAll()
            assertEquals(0, h.signOuts)
            assertEquals(MigraineFollowUpPhase.CLOSED, h.store.state.value.phase)
        }
    }

    @Test fun explicitTransportCancellationIsUncertainAndNotAutomaticallyRetried() = runBlocking {
        withHarness { h ->
            h.open(); h.cancelWrite = true
            h.store.save(); h.await(MigraineFollowUpPhase.UNCERTAIN)
            assertEquals(MigraineFollowUpProblem.CANCELLED, h.store.state.value.problem)
            assertNotNull(h.store.state.value.pendingRequest)
            assertNull(h.store.state.value.saved)
        }
    }

    @Test fun copyingCallerListsPreventsChangesDuringAuthFromChangingFrozenPayload() = runBlocking {
        withHarness { h ->
            h.open()
            val signs = mutableListOf(MigraineEarlySign("one"))
            h.store.setAnswers(MigraineFollowUpAnswers("ongoing", earlySigns = signs))
            signs.add(MigraineEarlySign("before save"))
            val gate = CompletableDeferred<Unit>(); h.tokenGate = gate
            h.store.save(); signs.add(MigraineEarlySign("during auth")); gate.complete(Unit)
            h.await(MigraineFollowUpPhase.SAVED)
            assertEquals(listOf("one"), h.store.state.value.saved!!.migraineDetail.episode.earlySigns.map { it.label })
        }
    }

    private suspend fun withHarness(block: suspend (Harness) -> Unit) {
        val h = Harness()
        try { withTimeout(10000) { block(h) } } finally { h.close() }
    }
    internal class Harness {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        var account: String? = ACCOUNT
        val server = SyntheticServer()
        val engine = RecordingEngine(server::handle)
        val client = HttpClient(engine) {
            expectSuccess = false; followRedirects = false
            install(HttpTimeout)
            install(ContentNegotiation) { json(migraineJson) }
            defaultRequest { url("https://example.invalid") }
        }
        val api = GaiaApiClient("https://example.invalid", client, client)
        var tokenGate: CompletableDeferred<Unit>? = null
        var readGate: CompletableDeferred<Unit>? = null
        var writeGate: CompletableDeferred<Unit>? = null
        val readReached = CompletableDeferred<Unit>()
        val writeReached = CompletableDeferred<Unit>()
        var unauthorizedAfterWrite = false
        var cancelWrite = false
        var signOuts = 0
        var tokenReads = 0
        var clockReads = 0
        var clock = "2026-09-17T12:00:00.123456789Z"
        val repository = MigraineFollowUpRepository(
            currentAccountId = { account },
            accessToken = { tokenReads++; tokenGate?.let { withContext(NonCancellable) { it.await() } }; "synthetic-token" },
            read = { token, id ->
                val result = api.migraineDetail(token, id)
                val gate = readGate
                readReached.complete(Unit)
                gate?.let { withContext(NonCancellable) { it.await() } }
                result
            },
            respond = { token, id, prompt, request ->
                if (cancelWrite) throw CancellationException("synthetic transport cancelled")
                val result = api.respondMigraineFollowUp(token, id, prompt, request)
                val gate = writeGate
                writeReached.complete(Unit)
                gate?.let { withContext(NonCancellable) { it.await() } }
                if (unauthorizedAfterWrite) throw ApiUnauthorizedException()
                result
            },
            signOut = { signOuts++; account = null },
        )
        val store = MigraineFollowUpStore(scope, { account }, repository) { clockReads++; clock }
        suspend fun open() { store.open(ACCOUNT, EPISODE_ID, PROMPT_ID); await(MigraineFollowUpPhase.EDITING) }
        suspend fun await(phase: MigraineFollowUpPhase) { withTimeout(5000) { store.state.first { it.phase == phase } } }
        fun changeSelection(action: String) {
            when (action) {
                "account" -> { account = "replacement-account"; store.accountChanged(account) }
                "logout" -> { account = null; store.accountChanged(null) }
                "close" -> store.close()
                "episode" -> {
                    tokenGate = null; readGate = null; writeGate = null
                    store.open(ACCOUNT, SECOND_EPISODE, PROMPT_ID)
                }
            }
        }
        fun close() { store.close(); scope.cancel(); client.close(); engine.close() }
    }

    internal class SyntheticServer {
        var detail = fixtureDetail()
        var status: Int? = null
        var postReply: Reply? = null
        var getReply: Reply? = null
        var getCount = 0
        var badReceipt: String? = null
        var loseNextReceipt = false
        var mutations = 0
        val posts = Collections.synchronizedList(mutableListOf<JsonObject>())
        val postBodies = Collections.synchronizedList(mutableListOf<String>())
        private var committedRequest: JsonObject? = null
        suspend fun handle(data: HttpRequestData): Reply {
            assertEquals("Bearer synthetic-token", data.headers[HttpHeaders.Authorization])
            if (data.method == HttpMethod.Get) {
                getCount++
                getReply?.let { return it }
                val id = data.url.encodedPath.split('/').dropLast(1).last()
                return Reply(body = envelope(detail.copy(episode = detail.episode.copy(episodeId = id))))
            }
            assertEquals(HttpMethod.Post, data.method)
            assertEquals("/v1/symptoms/follow-ups/$PROMPT_ID/respond", data.url.encodedPath)
            val text = when (val body = data.body) {
                is OutgoingContent.ByteArrayContent -> body.bytes().decodeToString()
                is OutgoingContent.ReadChannelContent -> body.readFrom().readRemaining().readText()
                else -> error("Unexpected synthetic request body type")
            }
            val request = migraineJson.parseToJsonElement(text).jsonObject
            posts += request
            postBodies += text
            postReply?.let { return it }
            status?.let { return Reply(it, """{"detail":"Migraine episode not found"}""") }
            val edit = request.getValue("migraine").jsonObject
            val revision = edit.getValue("expected_revision").jsonPrimitive.long
            if (detail.revision == revision) {
                val previous = detail.episode
                val saved = previous.copy(
                    state = request.getValue("state").jsonPrimitive.content,
                    medicines = edit["medicines"]?.let { migraineJson.decodeFromJsonElement<List<MigraineMedicine>>(it) } ?: previous.medicines,
                    earlySigns = edit["early_signs"]?.let { migraineJson.decodeFromJsonElement<List<MigraineEarlySign>>(it) } ?: previous.earlySigns,
                    contexts = edit["contexts"]?.let { migraineJson.decodeFromJsonElement<List<MigraineContext>>(it) } ?: previous.contexts,
                    notes = if (edit.containsKey("notes")) edit["notes"]?.jsonPrimitive?.contentOrNull else previous.notes,
                    lifecycle = previous.lifecycle.copy(revision = revision + 1),
                )
                detail = detail.copy(revision = revision + 1, episode = saved)
                mutations++; committedRequest = request
            } else if (committedRequest != request || detail.revision != revision + 1) return Reply(409, "{}")
            if (loseNextReceipt) { loseNextReceipt = false; throw IOException("synthetic lost acknowledgement after commit") }
            var returnedDetail = detail
            if (badReceipt == "revision") returnedDetail = detail.copy(revision = detail.revision + 1)
            if (badReceipt == "episode") returnedDetail = detail.copy(episode = detail.episode.copy(episodeId = SECOND_EPISODE))
            if (badReceipt == "medicine") returnedDetail = detail.copy(episode = detail.episode.copy(medicines = emptyList()))
            val prompt = if (badReceipt == "prompt") SECOND_EPISODE else PROMPT_ID
            val pending = if (badReceipt == "pending") """{"id":"$PROMPT_ID","episode_id":"$EPISODE_ID","symptom_code":"MIGRAINE","question_text":"synthetic"}""" else "null"
            if (badReceipt == "malformed") return Reply(body = "not json")
            return Reply(body = """{"ok":true,"data":{"prompt":{"id":"$prompt","episode_id":"$EPISODE_ID","symptom_code":"MIGRAINE","status":"answered"},"episode":{"id":"$EPISODE_ID","symptom_code":"MIGRAINE","current_state":"${detail.episode.state}","pending_follow_up":$pending},"migraine_detail":${migraineJson.encodeToJsonElement(returnedDetail)}}}""")
        }
    }
    internal data class Reply(val status: Int = 200, val body: String)
    internal class RecordingEngine(private val handle: suspend (HttpRequestData) -> Reply) : HttpClientEngineBase("synthetic-follow-up") {
        override val config = HttpClientEngineConfig()
        override val supportedCapabilities = setOf(HttpTimeoutCapability)
        @OptIn(InternalAPI::class)
        override suspend fun execute(data: HttpRequestData): HttpResponseData {
            val reply = handle(data)
            return HttpResponseData(HttpStatusCode.fromValue(reply.status), GMTDate(),
                Headers.build { append(HttpHeaders.ContentType, "application/json") },
                HttpProtocolVersion.HTTP_1_1, ByteReadChannel(reply.body), callContext())
        }
    }
    companion object {
        private const val ACCOUNT = "synthetic-account"
        private const val SECOND_EPISODE = "44444444-4444-4444-8444-444444444444"
        private fun envelope(detail: MigraineDetail) = buildJsonObject {
            put("ok", true); put("data", migraineJson.encodeToJsonElement(detail))
        }.toString()
    }
}
