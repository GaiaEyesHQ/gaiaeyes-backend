package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.MigraineMedicineRepository
import com.gaiaeyes.app.ui.MigraineFollowUpStoreTest.RecordingEngine
import com.gaiaeyes.app.ui.MigraineFollowUpStoreTest.Reply
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestData
import io.ktor.http.*
import io.ktor.http.content.OutgoingContent
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.*
import java.io.IOException
import java.math.BigDecimal
import java.time.ZoneId
import java.util.Collections
import kotlinx.coroutines.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class MigraineMedicineControllerTest {
    @Test fun onlyLoadedMatchingSelectionCanOpenWithoutPromptIncludingResolved() = runBlocking {
        for (resolved in listOf(false, true)) withHarness { h ->
            h.editor.open(""); assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
            h.summary.open(ACCOUNT, CurrentSymptomItem("legacy", "MIGRAINE"))
            assertFalse(h.editor.canOpen(h.summary.state.value.selectionId))
            if (resolved) h.server.detail = h.server.detail.let { it.copy(episode = it.episode.copy(state = "resolved", end = it.episode.start)) }
            h.load(); val selected = h.summary.state.value
            assertTrue(h.editor.canOpen(selected.selectionId)); assertFalse(h.editor.canOpen("stale"))
            h.editor.open(selected.selectionId)
            assertEquals(h.server.detail, h.state.baseline)
            assertEquals(3L, h.state.baseline!!.revision)
            assertEquals(1, h.server.gets); assertEquals(0, h.tokens)
            h.account = "other"; assertFalse(h.editor.canOpen(selected.selectionId))
            h.actions.save(); assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
            assertTrue(h.server.bodies.isEmpty())
        }
    }

    @Test fun unchangedAndExactEditorRoundTripDoNotAuthenticateOrWrite() = runBlocking { withHarness { h ->
        h.open(); val original = h.state.medicines.map { it.value }
        h.actions.save()
        assertTrue(h.state.message!!.contains("unchanged"))
        for (row in h.state.medicines) { h.actions.edit(row.id); h.actions.apply() }
        assertEquals(original, h.state.medicines.map { it.value }); assertFalse(h.state.hasChanges)
        h.actions.move(2, 0); h.actions.move(0, 2); h.actions.save()
        assertEquals(0, h.tokens); assertEquals(0, h.refreshes); assertTrue(h.server.bodies.isEmpty())
        assertEquals(BigDecimal("0.1000000000000000000001"), original[0].doseAmount)
        assertNull(original[1].doseAmount); assertEquals("none", original[1].reportedRelief)
        h.actions.close(); assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
    } }

    @Test fun addEditRemoveReorderPreserveDuplicatesPrecisionAndOmittedFields() = runBlocking { withHarness { h ->
        h.open(); val original = h.state.baseline!!
        h.actions.edit(h.state.medicines[1].id)
        h.actions.change(h.state.editor!!.copy(notes = "Edited duplicate", relief = "some"))
        h.clock = "2026-09-17T14:15:16.123456Z"; h.actions.apply()
        val edited = h.state.medicines[1].value
        assertEquals(original.episode.medicines[1].takenAt, edited.takenAt)
        assertEquals(h.clock, edited.reliefReportedAt!!.utc); assertEquals("user", edited.reliefReportedAt!!.timezoneSource)
        h.actions.edit(null)
        h.actions.change(h.state.editor!!.copy(name = "Example medicine", amount = "1.00000000000000000000001", unit = "mg", notes = "New duplicate"))
        h.actions.apply(); h.actions.remove(h.state.medicines[2].id); h.actions.move(2, 0)
        val expected = h.state.medicines.map { it.value }; val clocks = h.clockReads
        assertEquals(listOf(null, 0, 1), h.state.medicines.map { it.originalIndex })
        h.clock = "2026-09-18T12:00:00Z"; h.actions.save(); h.await(MigraineMedicinePhase.SAVED)
        assertEquals(setOf("expected_revision", "medicines"), h.server.requests.single().keys)
        assertEquals(expected, h.server.detail.episode.medicines)
        assertEquals(original.episode.copy(medicines = expected, lifecycle = original.episode.lifecycle.copy(revision = 4)), h.server.detail.episode)
        assertEquals(clocks, h.clockReads); assertEquals(1, h.refreshes)
        assertEquals(h.server.detail, h.summary.state.value.detail)
        assertEquals(1, h.server.gets); h.actions.save(); assertEquals(1, h.server.bodies.size)
        h.actions.close(); assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
        assertNotNull(h.summary.state.value.summary)
    } }

    @Test fun missingDoseDoesNotBecomeZeroAndInvalidEditorCannotDispatch() = runBlocking { withHarness { h ->
        h.open(); h.actions.edit(h.state.medicines[2].id)
        h.actions.change(h.state.editor!!.copy(amount = "0", unit = "mg")); h.actions.apply(); h.actions.save()
        assertNotNull(h.state.editor); assertNotNull(h.state.message); assertTrue(h.server.bodies.isEmpty())
        h.actions.change(h.state.editor!!.copy(amount = "", unit = "")); h.actions.apply()
        assertFalse(h.state.hasChanges); assertNull(h.state.medicines[2].value.doseAmount)
    } }

    @Test fun decimalSpellingAloneIsUnchangedWithoutLosingPrecision() = runBlocking { withHarness { h ->
        h.open(); h.actions.edit(h.state.medicines[0].id)
        h.actions.change(h.state.editor!!.copy(amount = "0.1000000000000000000001000")); h.actions.apply()
        assertFalse(h.state.hasChanges); h.actions.save()
        assertTrue(h.server.bodies.isEmpty()); assertEquals(0, h.tokens)
        assertEquals(BigDecimal("0.1000000000000000000001000"), h.state.medicines[0].value.doseAmount)
    } }

    @Test fun emptyArrayExplicitlyClearsAndDiscardRequiresDecision() = runBlocking { withHarness { h ->
        h.open(); h.state.medicines.toList().forEach { h.actions.remove(it.id) }
        h.actions.close(); assertTrue(h.state.confirmDiscard)
        h.actions.save(); assertTrue(h.server.bodies.isEmpty())
        h.actions.keep(); h.actions.save(); h.await(MigraineMedicinePhase.SAVED)
        assertEquals(JsonArray(emptyList()), h.server.requests.single()["medicines"])
        assertTrue(h.summary.state.value.detail!!.episode.medicines.isEmpty())
    } }

    @Test fun unavailableSaveKeepsOrderedDraftAndExactRetry() = runBlocking {
        for (reply in unavailableReplies) withHarness { h ->
            h.open(); h.change(); val draft = h.state.medicines; val baseline = h.state.baseline
            h.server.reply = reply; h.actions.save(); h.await(MigraineMedicinePhase.UNAVAILABLE)
            val request = h.state.pendingRequest!!; val clocks = h.clockReads
            h.actions.edit(null); h.actions.remove(draft[0].id); h.actions.move(0, 1); h.actions.review(); h.actions.save()
            assertSame(draft, h.state.medicines); assertSame(baseline, h.state.baseline)
            assertSame(request, h.state.pendingRequest); assertEquals(1, h.server.gets)
            h.server.reply = null; h.clock = "2026-09-19T12:00:00Z"
            h.actions.retry(); h.await(MigraineMedicinePhase.SAVED)
            assertEquals(2, h.server.bodies.size); assertEquals(1, h.server.bodies.toSet().size)
            assertEquals(clocks, h.clockReads); assertEquals(1, h.server.mutations); assertEquals(1, h.refreshes)
        }
    }

    @Test fun lostAcknowledgementAndUnavailableRetryRemainUncertainUntilMatchingReceipt() = runBlocking {
        for (reply in unavailableReplies) withHarness { h ->
            h.open(); h.change(); h.server.loseReceipt = true
            h.actions.save(); h.await(MigraineMedicinePhase.UNCERTAIN)
            assertEquals(3L, h.summary.state.value.detail!!.revision); assertEquals(0, h.refreshes)
            val pending = h.state.pendingRequest; val draft = h.state.medicines
            h.server.reply = reply; h.actions.retry(); h.await(MigraineMedicinePhase.UNCERTAIN)
            assertSame(pending, h.state.pendingRequest); assertSame(draft, h.state.medicines)
            h.server.reply = null; h.actions.retry(); h.await(MigraineMedicinePhase.SAVED)
            assertEquals(3, h.server.bodies.size); assertEquals(1, h.server.bodies.toSet().size)
            assertEquals(1, h.server.mutations); assertEquals(1, h.refreshes)
        }
    }

    @Test fun conflictReviewIsReadOnlyAndNeverRefreshesSummaryOrClaimsReceipt() = runBlocking { withHarness { h ->
        h.open(); h.change(); val summary = h.summary.state.value
        h.server.reply = Reply(409, "{}"); h.actions.save(); h.await(MigraineMedicinePhase.CONFLICT)
        val pending = h.state.pendingRequest; val draft = h.state.medicines
        h.server.detail = h.server.detail.let { it.copy(revision = 4, episode = it.episode.copy(lifecycle = it.episode.lifecycle.copy(revision = 4))) }
        h.actions.review(); h.await(MigraineMedicinePhase.REVIEW)
        assertSame(summary, h.summary.state.value); assertSame(pending, h.state.pendingRequest)
        assertSame(draft, h.state.medicines); assertNull(h.state.saved); assertEquals(0, h.refreshes)
        h.actions.save(); h.actions.retry(); assertEquals(1, h.server.bodies.size)
        h.actions.useReviewed(); assertEquals(MigraineMedicinePhase.REVIEWED, h.state.phase)
        h.actions.close(); assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
        assertSame(summary, h.summary.state.value)
        h.summary.retry(); h.awaitSummary(); assertEquals(4L, h.summary.state.value.detail!!.revision)
    } }

    @Test fun uncertainGetMatchingDraftIsStillNotAWriteReceipt() = runBlocking { withHarness { h ->
        h.open(); h.change(); h.server.loseReceipt = true; h.actions.save(); h.await(MigraineMedicinePhase.UNCERTAIN)
        h.actions.review(); h.await(MigraineMedicinePhase.REVIEW)
        assertEquals(h.state.medicines.map { it.value }, h.state.reviewed!!.episode.medicines)
        assertNull(h.state.saved); assertEquals(0, h.refreshes); assertEquals(3L, h.summary.state.value.detail!!.revision)
    } }

    @Test fun badWriteReceiptsNeverPublish() = runBlocking {
        for (bad in listOf("episode", "revision", "medicines", "malformed")) withHarness { h ->
            h.open(); h.change(); h.server.badReceipt = bad; h.actions.save(); h.await(MigraineMedicinePhase.UNCERTAIN)
            assertNull(h.state.saved); assertEquals(0, h.refreshes); assertEquals(3L, h.summary.state.value.detail!!.revision)
            assertNotNull(h.state.pendingRequest)
        }
    }

    @Test fun rejectedSaveKeepsEditableDraftAndDeletedSaveKeepsLocalDraft() = runBlocking {
        for (code in listOf(400, 422, 404)) withHarness { h ->
            h.open(); h.change(); val draft = h.state.medicines
            h.server.reply = Reply(code, """{"detail":"Migraine episode not found"}""")
            h.actions.save(); h.await(if (code == 404) MigraineMedicinePhase.DELETED else MigraineMedicinePhase.EDITING)
            assertSame(draft, h.state.medicines); assertEquals(0, h.refreshes)
            h.actions.close(); assertTrue(h.state.confirmDiscard); h.actions.discard()
            assertEquals(MigraineMedicinePhase.CLOSED, h.state.phase)
        }
    }

    @Test fun rejectionAfterUncertaintyDoesNotMakeDraftEditable() = runBlocking { withHarness { h ->
        h.open(); h.change(); h.server.loseReceipt = true; h.actions.save(); h.await(MigraineMedicinePhase.UNCERTAIN)
        h.server.reply = Reply(422, "{}"); h.actions.retry(); h.await(MigraineMedicinePhase.CONFLICT)
        val draft = h.state.medicines; h.actions.edit(null); h.actions.remove(draft[0].id)
        assertSame(draft, h.state.medicines); assertNotNull(h.state.pendingRequest)
    } }

    @Test fun accountCloseReopenAndSelectionChangeDuringAuthPreventDispatch() = runBlocking {
        for (change in listOf("account", "close", "reopen", "summary")) withHarness { h ->
            h.open(); h.change(); val gate = CompletableDeferred<Unit>(); h.tokenGate = gate
            h.actions.save(); assertEquals(MigraineMedicinePhase.SAVING, h.state.phase)
            val job = h.scope.coroutineContext[Job]!!.children.last()
            h.changeSession(change); val after = h.state
            gate.complete(Unit); job.join()
            assertEquals(after, h.state); assertTrue(h.server.bodies.isEmpty()); assertEquals(0, h.refreshes)
        }
    }

    @Test fun lateReceiptAndUnauthorizedCannotUpdateOrSignOutReplacementSession() = runBlocking {
        for (unauthorized in listOf(false, true)) for (change in listOf("account", "close", "reopen", "summary")) withHarness { h ->
            h.open(); h.change(); val gate = CompletableDeferred<Unit>(); h.writeGate = gate; h.lateUnauthorized = unauthorized
            h.actions.save(); h.writeReached.await()
            val job = h.scope.coroutineContext[Job]!!.children.last()
            h.changeSession(change); val after = h.state; val summary = h.summary.state.value
            gate.complete(Unit); job.join()
            assertEquals(after, h.state); assertEquals(summary, h.summary.state.value)
            assertEquals(0, h.refreshes); assertEquals(0, h.signOuts)
        }
    }

    @Test fun lateReadAndOldUiCallbacksCannotPublishIntoReopenedEditor() = runBlocking { withHarness { h ->
        h.open(); val oldActions = h.actions
        oldActions.edit(h.state.medicines[0].id); val oldForm = h.state.editor!!
        oldActions.cancel(); h.actions.edit(h.state.medicines[1].id); val currentForm = h.state.editor
        oldActions.change(oldForm.copy(name = "stale")); assertEquals(currentForm, h.state.editor)
        h.actions.cancel(); h.change(); h.server.reply = Reply(409, "{}"); h.actions.save(); h.await(MigraineMedicinePhase.CONFLICT)
        val gate = CompletableDeferred<Unit>(); h.readGate = gate; h.actions.review(); h.readReached.await()
        val job = h.scope.coroutineContext[Job]!!.children.last()
        h.changeSession("reopen"); val after = h.state
        oldActions.close(); oldActions.discard(); oldActions.edit(null); oldActions.save(); oldActions.change(oldForm)
        gate.complete(Unit); job.join(); assertEquals(after, h.state); assertEquals(0, h.refreshes)
    } }

    @Test fun interruptedDispatchedTransportRemainsUncertain() = runBlocking { withHarness { h ->
        h.open(); h.change(); h.cancelWrite = true; h.actions.save(); h.await(MigraineMedicinePhase.UNCERTAIN)
        assertNotNull(h.state.pendingRequest); assertEquals(0, h.refreshes)
    } }

    @Test fun summaryRequiresMatchingSelectionRevisionAndMedicineOnlyAcknowledgement() = runBlocking { withHarness { h ->
        h.load(); val before = h.summary.state.value; val original = before.detail!!
        val request = MigraineStructuredEdit(original.revision, medicines = emptyList())
        val saved = original.copy(revision = 4, episode = original.episode.copy(medicines = emptyList(), lifecycle = original.episode.lifecycle.copy(revision = 4)))
        assertFalse(h.summary.acceptMedicineEdit("old", request, saved))
        assertFalse(h.summary.acceptMedicineEdit(before.selectionId, request.copy(expectedRevision = 2), saved))
        assertFalse(h.summary.acceptMedicineEdit(before.selectionId, request.copy(notes = MigraineTextChange.Clear), saved))
        assertFalse(h.summary.acceptMedicineEdit(before.selectionId, request, original))
        assertSame(before, h.summary.state.value)
        assertTrue(h.summary.acceptMedicineEdit(before.selectionId, request, saved))
        assertEquals(saved, h.summary.state.value.detail)
        assertFalse(h.summary.acceptMedicineEdit(before.selectionId, request, saved))
    } }

    private suspend fun withHarness(block: suspend (Harness) -> Unit) {
        val h = Harness(); try { withTimeout(10000) { block(h) } } finally { h.close() }
    }
    private class Harness {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        var account: String? = ACCOUNT
        val server = Server()
        val engine = RecordingEngine(server::handle)
        val client = HttpClient(engine) {
            expectSuccess = false; followRedirects = false
            install(HttpTimeout); install(ContentNegotiation) { json(migraineJson) }
            defaultRequest { url("https://example.invalid") }
        }
        val api = GaiaApiClient("https://example.invalid", client, client)
        var tokens = 0; var refreshes = 0; var signOuts = 0; var clockReads = 0
        var clock = "2026-09-17T12:00:00.123456Z"
        var tokenGate: CompletableDeferred<Unit>? = null
        var readGate: CompletableDeferred<Unit>? = null
        var writeGate: CompletableDeferred<Unit>? = null
        val writeReached = CompletableDeferred<Unit>(); val readReached = CompletableDeferred<Unit>()
        var lateUnauthorized = false; var cancelWrite = false
        val summary = MigraineSummaryStore(scope, { account }, { _, id -> api.migraineDetail("synthetic-token", id) })
        val repository = MigraineMedicineRepository({ account }, {
            tokens++; tokenGate?.let { withContext(NonCancellable) { it.await() } }; "synthetic-token"
        }, { token, id ->
            val result = api.migraineDetail(token, id); readReached.complete(Unit)
            readGate?.let { withContext(NonCancellable) { it.await() } }; result
        }, { token, id, request ->
            if (cancelWrite) throw CancellationException("Synthetic cancellation after dispatch")
            val result = api.updateMigraineDetail(token, id, request); writeReached.complete(Unit)
            writeGate?.let { withContext(NonCancellable) { it.await() } }
            if (lateUnauthorized) throw ApiUnauthorizedException()
            result
        }, { signOuts++; account = null })
        val editor = MigraineMedicineController(scope, { account }, summary.state, repository,
            { selection, request, saved -> summary.acceptMedicineEdit(selection, request, saved).also { if (it) refreshes++ } },
            { clockReads++; clock }, { ZoneId.of("America/Chicago") })
        val state get() = editor.state.value
        val actions get() = editor.actions(state.sessionId)
        suspend fun load() { summary.open(ACCOUNT, CurrentSymptomItem(EPISODE_ID, "MIGRAINE")); awaitSummary() }
        suspend fun awaitSummary() { summary.state.first { !it.isLoading }; check(summary.state.value.summary != null) { summary.state.value.toString() } }
        suspend fun open() { load(); editor.open(summary.state.value.selectionId); check(state.phase == MigraineMedicinePhase.EDITING) }
        suspend fun await(phase: MigraineMedicinePhase) { editor.state.first { it.phase == phase } }
        fun change() { actions.edit(state.medicines[0].id); actions.change(state.editor!!.copy(notes = "Synthetic medicine edit")); actions.apply() }
        suspend fun changeSession(change: String) {
            when (change) {
                "account" -> { account = "replacement"; editor.accountChanged(account); summary.accountChanged(account) }
                "close" -> { actions.close(); actions.discard() }
                "reopen" -> { actions.close(); actions.discard(); editor.open(summary.state.value.selectionId) }
                "summary" -> { summary.close(); load() }
            }
        }
        fun close() { editor.clear(); summary.close(); scope.cancel(); client.close(); engine.close() }
    }
    private class Server {
        var detail = fixtureDetail()
        var gets = 0; var mutations = 0
        var reply: Reply? = null; var loseReceipt = false; var badReceipt: String? = null
        val bodies = Collections.synchronizedList(mutableListOf<String>())
        val requests = Collections.synchronizedList(mutableListOf<JsonObject>())
        private var committed: JsonObject? = null
        suspend fun handle(data: HttpRequestData): Reply {
            assertEquals("Bearer synthetic-token", data.headers[HttpHeaders.Authorization])
            assertEquals("/v1/symptoms/current/$EPISODE_ID/migraine-detail", data.url.encodedPath)
            if (data.method == HttpMethod.Get) { gets++; return Reply(body = envelope(detail)) }
            assertEquals(HttpMethod.Patch, data.method)
            val body = when (val b = data.body) {
                is OutgoingContent.ByteArrayContent -> b.bytes().decodeToString()
                is OutgoingContent.ReadChannelContent -> b.readFrom().readRemaining().readText()
                else -> error("Unexpected body")
            }
            val request = migraineJson.parseToJsonElement(body).jsonObject
            bodies += body; requests += request; reply?.let { return it }
            val revision = request.getValue("expected_revision").jsonPrimitive.long
            if (revision == detail.revision) {
                detail = detail.copy(revision = revision + 1, episode = detail.episode.copy(
                    medicines = migraineJson.decodeFromJsonElement(request.getValue("medicines")),
                    lifecycle = detail.episode.lifecycle.copy(revision = revision + 1)))
                mutations++; committed = request
            } else if (committed != request || detail.revision != revision + 1) return Reply(409, "{}")
            if (loseReceipt) { loseReceipt = false; throw IOException("Synthetic acknowledgement lost after commit") }
            val returned = when (badReceipt) {
                "episode" -> detail.copy(episode = detail.episode.copy(episodeId = "44444444-4444-4444-8444-444444444444"))
                "revision" -> detail.copy(revision = detail.revision + 1)
                "medicines" -> detail.copy(episode = detail.episode.copy(medicines = emptyList()))
                else -> detail
            }
            return Reply(body = if (badReceipt == "malformed") "broken" else envelope(returned))
        }
    }
    companion object {
        private const val ACCOUNT = "synthetic-account"
        private val unavailableReplies = listOf(Reply(503, """{"detail":"structured migraine detail storage is not installed"}"""), Reply(404, """{"detail":"Not Found"}"""))
        private fun envelope(detail: MigraineDetail) = buildJsonObject { put("ok", true); put("data", migraineJson.encodeToJsonElement(detail)) }.toString()
    }
}
