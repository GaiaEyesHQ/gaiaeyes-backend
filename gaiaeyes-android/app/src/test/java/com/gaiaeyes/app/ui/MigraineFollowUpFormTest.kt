package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.CurrentSymptomsSnapshot
import com.gaiaeyes.app.data.HomeContextSource
import java.math.BigDecimal
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.junit.Assert.*
import org.junit.Test

class MigraineFollowUpFormTest {
    @Test fun onlyMatchingAccountEpisodeAndCurrentPendingPromptCanOpen() = runBlocking {
        withForm { f ->
            val item = f.item
            val invalid = listOf(item.copy(symptomCode = "HEADACHE"), item.copy(id = "legacy"), item.copy(pendingFollowUp = null),
                item.copy(pendingFollowUp = item.pendingFollowUp!!.copy(episodeId = OTHER)),
                item.copy(pendingFollowUp = item.pendingFollowUp!!.copy(symptomCode = "HEADACHE")),
                item.copy(pendingFollowUp = item.pendingFollowUp!!.copy(id = OTHER)))
            invalid.forEach { f.controller.open(it) }
            assertEquals(MigraineFollowUpPhase.CLOSED, f.controller.state.value.phase)
            assertEquals(0, f.h.tokenReads)
            f.snapshot = f.snapshot.copy(accountId = "another-account")
            f.controller.open(item); assertEquals(0, f.h.tokenReads)
            f.snapshot = f.snapshot.copy(accountId = f.account, symptoms = CurrentSymptomsResponse(items = listOf(item.copy(pendingFollowUp = item.pendingFollowUp!!.copy(status = "answered")))))
            f.controller.open(item); assertEquals(0, f.h.tokenReads)
            f.snapshot = snapshot(f.account, item)
            f.open()
            assertEquals(PROMPT_ID, f.controller.state.value.promptId)
            assertEquals(EPISODE_ID, f.controller.state.value.episodeId)
            assertEquals(item.pendingFollowUp!!.questionText, f.controller.ui.value.selection!!.question)
            assertEquals(1, f.h.server.getCount)
            val draft = f.controller.state.value.draft
            f.controller.open(item) // Double entry tap must not reconstruct a loaded draft.
            assertSame(draft, f.controller.state.value.draft)
            assertEquals(1, f.h.server.getCount)
        }
    }

    @Test fun existingMedicineFieldsRoundTripWithoutDroppingMetadataOrMissingValues() = runBlocking {
        withForm { f ->
            f.open()
            val original = f.controller.state.value.draft!!.medicines
            for (row in original) {
                f.actions().editMedicine(row.id)
                val editor = f.controller.ui.value.medicine!!
                assertEquals(row.value.doseAmount?.toPlainString() ?: "", editor.amount)
                assertEquals(row.value.doseUnit ?: "", editor.unit)
                assertEquals(row.value.reportedRelief, editor.relief)
                f.actions().applyMedicine()
                assertNull(f.controller.ui.value.medicine)
            }
            assertEquals(original, f.controller.state.value.draft!!.medicines)
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.SAVED)
            assertEquals(original.map { it.value }, f.controller.state.value.saved!!.migraineDetail.episode.medicines)
            assertEquals(0, f.controller.state.value.saved!!.migraineDetail.episode.severity)
            assertEquals(listOf(f.account), f.refreshes)
        }
    }

    @Test fun newMedicineSupportsExactDoseReliefAndOrderedDuplicateNames() = runBlocking {
        withForm { f ->
            f.open()
            val rows = f.controller.state.value.draft!!.medicines
            f.actions().editMedicine(null)
            val editor = f.controller.ui.value.medicine!!
            f.actions().medicine(editor.copy(name = rows[0].value.name, amount = "0.1000000000000000000001", unit = "mg", relief = "none", notes = "new note"))
            f.actions().applyMedicine()
            val added = f.controller.state.value.draft!!.medicines.last()
            assertNull(added.originalIndex)
            assertEquals(BigDecimal("0.1000000000000000000001"), added.value.doseAmount)
            assertEquals("none", added.value.reportedRelief)
            assertEquals(NOW, added.value.reliefReportedAt!!.utc)
            f.actions().moveMedicine(3, 1)
            f.actions().removeMedicine(rows[1].id)
            assertEquals(listOf(rows[0].id, added.id, rows[2].id), f.controller.state.value.draft!!.medicines.map { it.id })
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.SAVED)
            assertEquals(3, f.controller.state.value.saved!!.migraineDetail.episode.medicines.size)
            assertEquals(1, f.h.server.mutations)
        }
    }

    @Test fun missingDoseAndZeroAreDistinctAndUnappliedEntryBlocksSave() = runBlocking {
        withForm { f ->
            f.open()
            val row = f.controller.state.value.draft!!.medicines[1]
            f.actions().editMedicine(row.id)
            val originalEditor = f.controller.ui.value.medicine!!
            assertEquals("", originalEditor.amount)
            for ((amount, unit) in listOf("0" to "mg", "1" to "", "bad" to "mg", "-1" to "mg")) {
                f.actions().medicine(originalEditor.copy(amount = amount, unit = unit))
                f.actions().applyMedicine()
                assertNotNull(f.controller.ui.value.message)
                assertNotNull(f.controller.ui.value.medicine)
                assertEquals(row.value, f.controller.state.value.draft!!.medicines[1].value)
                f.actions().action(MigraineFormAction.SAVE)
                assertEquals(0, f.h.server.posts.size)
            }
            f.actions().medicine(originalEditor.copy(amount = "", unit = "")); f.actions().applyMedicine()
            assertNull(f.controller.state.value.draft!!.medicines[1].value.doseAmount)
            assertNull(f.controller.state.value.draft!!.medicines[1].value.doseUnit)
        }
        withForm { f ->
            f.h.server.detail = f.h.server.detail.copy(episode = f.h.server.detail.episode.copy(severity = null))
            f.open(); assertNull(f.controller.state.value.baseline!!.episode.severity)
        }
    }

    @Test fun localDateTimeRequiresRealTimeAndExplicitAmbiguousOffset() {
        val initial = MigraineMedicineForm.from(null, NOW, ZoneId.of("America/Chicago")).copy(name = "Synthetic")
        val gap = initial.copy(takenAt = LocalDateTime.parse("2026-03-08T02:30:00"), offset = null)
        assertThrows(IllegalArgumentException::class.java) { gap.value(NOW) }
        val overlap = initial.copy(takenAt = LocalDateTime.parse("2026-11-01T01:30:00"), offset = null)
        assertThrows(IllegalArgumentException::class.java) { overlap.value(NOW) }
        val first = overlap.copy(offset = ZoneOffset.ofHours(-5)).value(NOW)
        val second = overlap.copy(offset = ZoneOffset.ofHours(-6)).value(NOW)
        assertEquals("2026-11-01T06:30:00Z", first.takenAt.utc)
        assertEquals("2026-11-01T07:30:00Z", second.takenAt.utc)
        assertEquals("America/Chicago", second.takenAt.timezoneName)
        assertEquals(-360, second.takenAt.utcOffsetMinutes)
    }

    @Test fun changedReliefGetsResponseTimeAndOtherEditsPreserveOriginalTimeMetadata() = runBlocking {
        withForm { f ->
            f.open(); val row = f.controller.state.value.draft!!.medicines.first()
            f.actions().editMedicine(row.id)
            val editor = f.controller.ui.value.medicine!!
            f.actions().medicine(editor.copy(notes = "only note changed")); f.actions().applyMedicine()
            val noteEdited = f.controller.state.value.draft!!.medicines.first().value
            assertEquals(row.value.takenAt, noteEdited.takenAt)
            assertEquals(row.value.reliefReportedAt, noteEdited.reliefReportedAt)
            f.actions().editMedicine(row.id)
            f.actions().medicine(f.controller.ui.value.medicine!!.copy(relief = "some")); f.actions().applyMedicine()
            val reliefEdited = f.controller.state.value.draft!!.medicines.first().value
            assertEquals(row.value.takenAt, reliefEdited.takenAt)
            assertEquals(NOW, reliefEdited.reliefReportedAt!!.utc)
        }
    }

    @Test fun editingSignAndContextLabelsPreservesAllAdditionalMetadata() = runBlocking {
        withForm { f ->
            f.open(); val baseline = f.controller.state.value.baseline!!.episode
            f.actions().earlySign(0, "Updated sign"); f.actions().context(0, "Updated context")
            val answers = f.controller.state.value.draft!!.answers
            assertEquals(baseline.earlySigns[0].copy(label = "Updated sign"), answers.earlySigns!![0])
            assertEquals(baseline.contexts[0].copy(label = "Updated context"), answers.contexts!![0])
            f.actions().answers(answers.copy(notes = MigraineTextChange.Clear))
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.SAVED)
            assertNull(f.controller.state.value.saved!!.migraineDetail.episode.notes)
        }
    }

    @Test fun saveActionsAreExplicitSerializedAndRefreshOnlyAfterAuthoritativeAck() = runBlocking {
        withForm { f ->
            f.open(); val gate = CompletableDeferred<Unit>(); f.h.tokenGate = gate
            f.actions().action(MigraineFormAction.SAVE)
            f.actions().action(MigraineFormAction.SAVE)
            assertEquals(MigraineFollowUpPhase.SAVING, f.controller.state.value.phase)
            assertTrue(migraineFormActions(f.controller.state.value).isEmpty())
            assertTrue(f.h.server.posts.isEmpty()); assertTrue(f.refreshes.isEmpty())
            gate.complete(Unit); f.await(MigraineFollowUpPhase.SAVED)
            f.actions().action(MigraineFormAction.SAVE)
            assertEquals(1, f.h.server.posts.size); assertEquals(1, f.refreshes.size)
        }
        withForm { f ->
            f.open(); f.h.server.badReceipt = "prompt"
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.UNCERTAIN)
            assertTrue(f.refreshes.isEmpty()); assertNull(f.controller.state.value.saved)
        }
    }

    @Test fun initialUnavailableAndLoadedUnavailableExposeDifferentRecoveryActions() = runBlocking {
        withForm { f ->
            f.h.server.getReply = MigraineFollowUpStoreTest.Reply(503, """{"detail":"structured migraine detail storage is not installed"}""")
            f.controller.open(f.item); f.await(MigraineFollowUpPhase.UNAVAILABLE)
            assertEquals(listOf(MigraineFormAction.RETRY_LOAD), migraineFormActions(f.controller.state.value))
            f.h.server.getReply = null
            f.actions().action(MigraineFormAction.RETRY_LOAD); f.await(MigraineFollowUpPhase.EDITING)
            assertNotNull(f.controller.state.value.draft)
        }
        for (status in listOf(503, 404)) withForm { f ->
            f.open(); f.actions().answers(f.controller.state.value.draft!!.answers.copy(state = "improving"))
            val draft = f.controller.state.value.draft
            f.h.server.postReply = MigraineFollowUpStoreTest.Reply(status, if (status == 503) """{"detail":"structured migraine detail storage is not installed"}""" else """{"detail":"Not Found"}""")
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.UNAVAILABLE)
            assertEquals(listOf(MigraineFormAction.RETRY_RESPONSE), migraineFormActions(f.controller.state.value))
            f.actions().action(MigraineFormAction.RETRY_LOAD)
            assertSame(draft, f.controller.state.value.draft); assertTrue(f.refreshes.isEmpty())
            f.h.server.postReply = null
            f.actions().action(MigraineFormAction.RETRY_RESPONSE); f.await(MigraineFollowUpPhase.SAVED)
            assertEquals(1, f.h.server.getCount)
            assertEquals(f.h.server.postBodies[0], f.h.server.postBodies[1])
            assertEquals(1, f.h.server.mutations); assertEquals(1, f.refreshes.size)
        }
    }

    @Test fun uncertainAndConflictReviewNeverConfirmOrMergeResponse() = runBlocking {
        for (uncertain in listOf(true, false)) withForm { f ->
            f.open(); val row = f.controller.state.value.draft!!.medicines.first()
            f.actions().editMedicine(null)
            f.actions().medicine(f.controller.ui.value.medicine!!.copy(name = row.value.name))
            f.actions().applyMedicine()
            if (uncertain) f.h.server.loseNextReceipt = true else f.h.server.status = 409
            f.actions().action(MigraineFormAction.SAVE)
            f.await(if (uncertain) MigraineFollowUpPhase.UNCERTAIN else MigraineFollowUpPhase.CONFLICT)
            val draft = f.controller.state.value.draft
            f.actions().answers(MigraineFollowUpAnswers("worse")); f.actions().removeMedicine(row.id)
            assertSame(draft, f.controller.state.value.draft)
            f.h.server.status = null
            f.actions().action(MigraineFormAction.REVIEW); f.await(MigraineFollowUpPhase.REVIEW)
            assertNull(f.controller.state.value.saved); assertTrue(f.refreshes.isEmpty())
            assertSame(draft, f.controller.state.value.draft)
            f.actions().action(MigraineFormAction.USE_REVIEWED)
            assertEquals(MigraineFollowUpPhase.REVIEWED, f.controller.state.value.phase)
            assertTrue(f.refreshes.isEmpty()); assertEquals(1, f.h.server.posts.size)
            f.actions().action(MigraineFormAction.DONE)
            assertEquals(MigraineFollowUpPhase.CLOSED, f.controller.state.value.phase)
        }
    }

    @Test fun deletedEpisodeKeepsDraftAndRequiresExplicitDiscard() = runBlocking {
        withForm { f ->
            f.open(); f.h.server.status = 404
            f.actions().action(MigraineFormAction.SAVE); f.await(MigraineFollowUpPhase.DELETED)
            assertTrue(migraineFormActions(f.controller.state.value).isEmpty())
            assertNotNull(f.controller.state.value.draft)
            f.actions().requestClose(); assertTrue(f.controller.ui.value.confirmDiscard)
            f.actions().discardAndClose(); assertEquals(MigraineFollowUpPhase.CLOSED, f.controller.state.value.phase)
            assertTrue(f.refreshes.isEmpty())
        }
    }

    @Test fun backCloseKeepsDraftUntilConfirmedAndOldFormCallbacksCannotReachReopenedForm() = runBlocking {
        withForm { f ->
            f.open(); val oldActions = f.actions(); val original = f.controller.state.value.draft
            oldActions.editMedicine(null)
            oldActions.medicine(f.controller.ui.value.medicine!!.copy(name = "unsaved input"))
            oldActions.requestClose()
            assertTrue(f.controller.ui.value.confirmDiscard)
            assertEquals("unsaved input", f.controller.ui.value.medicine!!.name)
            oldActions.keepEditing(); assertSame(original, f.controller.state.value.draft)
            oldActions.requestClose(); oldActions.discardAndClose()
            assertEquals(MigraineFollowUpPhase.CLOSED, f.controller.state.value.phase)
            assertNull(f.controller.ui.value.medicine)
            f.open(); val reopened = f.controller.state.value.draft
            oldActions.answers(MigraineFollowUpAnswers("worse")); oldActions.action(MigraineFormAction.SAVE); oldActions.requestClose()
            assertSame(reopened, f.controller.state.value.draft)
            assertFalse(f.controller.ui.value.confirmDiscard); assertTrue(f.h.server.posts.isEmpty())
        }
    }

    @Test fun oldMedicinePickerCannotOverwriteDifferentEditorInSameForm() = runBlocking {
        withForm { f ->
            f.open(); val rows = f.controller.state.value.draft!!.medicines
            f.actions().editMedicine(rows[0].id); val old = f.controller.ui.value.medicine!!
            f.actions().cancelMedicine(); f.actions().editMedicine(rows[1].id)
            val current = f.controller.ui.value.medicine
            f.actions().medicine(old.copy(name = "late old input"))
            assertSame(current, f.controller.ui.value.medicine)
        }
    }

    @Test fun selectingAnotherEpisodeRequiresDiscardAndRevalidatesNewPrompt() = runBlocking {
        withForm { f ->
            f.open(); val next = item(OTHER)
            f.snapshot = f.snapshot.copy(symptoms = CurrentSymptomsResponse(items = listOf(f.item, next)))
            f.controller.open(next)
            assertTrue(f.controller.ui.value.confirmDiscard)
            assertEquals(EPISODE_ID, f.controller.state.value.episodeId)
            f.actions().discardAndClose(); f.await(MigraineFollowUpPhase.EDITING)
            assertEquals(OTHER, f.controller.state.value.episodeId)
        }
    }

    @Test fun logoutDuringAuthPreventsDispatchAndClearsPrivateEditor() = runBlocking {
        withForm { f ->
            f.open(); val gate = CompletableDeferred<Unit>(); f.h.tokenGate = gate
            val priorJobs = f.jobs()
            f.actions().action(MigraineFormAction.SAVE)
            val requests = f.jobs().filterNot { it in priorJobs }
            f.h.account = null; f.controller.accountChanged(null)
            assertNull(f.controller.ui.value.selection); assertNull(f.controller.state.value.draft)
            gate.complete(Unit); requests.joinAll()
            assertTrue(f.h.server.posts.isEmpty()); assertTrue(f.refreshes.isEmpty())
        }
    }

    @Test fun lateCommittedResponseCannotRefreshOrPopulateReplacementAccount() = runBlocking {
        withForm { f ->
            f.open(); val oldActions = f.actions(); val gate = CompletableDeferred<Unit>(); f.h.writeGate = gate
            val priorJobs = f.jobs()
            oldActions.action(MigraineFormAction.SAVE); f.h.writeReached.await()
            val requests = f.jobs().filterNot { it in priorJobs }
            f.h.account = "replacement-account"; f.controller.accountChanged(f.h.account)
            f.snapshot = snapshot(f.h.account!!, f.item)
            f.h.writeGate = null; f.controller.open(f.item); f.await(MigraineFollowUpPhase.EDITING)
            val replacement = f.controller.state.value.draft
            oldActions.answers(MigraineFollowUpAnswers("worse")); oldActions.requestClose()
            gate.complete(Unit); requests.joinAll()
            assertSame(replacement, f.controller.state.value.draft)
            assertNull(f.controller.state.value.saved); assertTrue(f.refreshes.isEmpty())
            assertEquals("replacement-account", f.controller.state.value.accountId)
            assertFalse(f.controller.ui.value.confirmDiscard)
        }
    }

    private suspend fun withForm(block: suspend (FormHarness) -> Unit) {
        val f = FormHarness()
        try { withTimeout(10000) { block(f) } } finally { f.controller.clear(); f.h.close() }
    }
    private class FormHarness {
        val h = MigraineFollowUpStoreTest.Harness()
        val account = h.account!!
        val item = item(EPISODE_ID)
        var snapshot = snapshot(account, item)
        val refreshes = mutableListOf<String>()
        val controller = MigraineFollowUpFormController(h.scope, { h.account }, { snapshot }, h.repository,
            { refreshes += it }, { NOW }, { ZoneId.of("America/Chicago") })
        fun actions() = controller.actions(controller.ui.value.sessionId)
        suspend fun open() { controller.open(item); await(MigraineFollowUpPhase.EDITING) }
        suspend fun await(phase: MigraineFollowUpPhase) { withTimeout(5000) { controller.state.first { it.phase == phase } }; yield() }
        fun jobs() = h.scope.coroutineContext[Job]!!.children.toList()
    }
    companion object {
        private const val NOW = "2026-09-17T12:00:00.123456Z"
        private const val OTHER = "44444444-4444-4444-8444-444444444444"
        private fun item(id: String) = CurrentSymptomItem(id = id, symptomCode = "MIGRAINE", currentState = "ongoing",
            pendingFollowUp = CurrentSymptomPendingFollowUp(PROMPT_ID, id, "MIGRAINE", "How is your migraine now?", "pending"))
        private fun snapshot(account: String, item: CurrentSymptomItem) = CurrentSymptomsSnapshot(account,
            CurrentSymptomsResponse(items = listOf(item)), HomeContextSource.NETWORK, 0)
    }
}
