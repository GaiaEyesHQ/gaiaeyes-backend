package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.CurrentSymptomsSnapshot
import com.gaiaeyes.app.data.MigraineFollowUpRepository
import java.time.Instant
import java.time.ZoneId
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

internal data class MigraineFollowUpFormUi(
    val sessionId: String = "",
    val selection: MigraineFollowUpSelection? = null,
    val medicine: MigraineMedicineForm? = null,
    val message: String? = null,
    val confirmDiscard: Boolean = false,
)

// Production ViewModel seam. Saving/recovery belongs only to the accepted store;
// this owns form inputs, prompt validation, explicit close and one refresh receipt.
// All calls and the scope are confined to the main UI dispatcher.
internal class MigraineFollowUpFormController(
    scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val snapshot: () -> CurrentSymptomsSnapshot?,
    repository: MigraineFollowUpRepository,
    private val onSaved: (String) -> Unit,
    now: () -> String = { Instant.now().toString() },
    private val zone: () -> ZoneId = { ZoneId.systemDefault() },
) {
    private val store = MigraineFollowUpStore(scope, currentAccountId, repository, now)
    val state = store.state
    private val mutableUi = MutableStateFlow(MigraineFollowUpFormUi())
    val ui = mutableUi.asStateFlow()
    private var pendingSelection: CurrentSymptomItem? = null
    private var refreshed = false

    init {
        scope.launch {
            state.collect { value ->
                if (value.phase == MigraineFollowUpPhase.CLOSED && mutableUi.value.selection != null) {
                    mutableUi.value = MigraineFollowUpFormUi()
                    pendingSelection = null
                }
                if (value.phase == MigraineFollowUpPhase.SAVED && !refreshed && currentAccountId() == value.accountId) {
                    refreshed = true
                    onSaved(requireNotNull(value.accountId))
                }
            }
        }
    }

    // Compose and native-picker callbacks belong to one opened form, even when
    // the same episode is later reopened. Old callbacks cannot edit a new form.
    fun actions(sessionId: String) = Actions(this) { sessionId.isNotEmpty() && ui.value.sessionId == sessionId && current() }
    internal class Actions(private val owner: MigraineFollowUpFormController, private val current: () -> Boolean) {
        private fun run(action: () -> Unit) { if (current()) action() }
        fun requestClose() = run(owner::requestClose)
        fun keepEditing() = run(owner::keepEditing)
        fun discardAndClose() = run(owner::discardAndClose)
        fun answers(value: MigraineFollowUpAnswers) = run { owner.answers(value) }
        fun earlySign(index: Int?, label: String?) = run { owner.earlySign(index, label) }
        fun context(index: Int?, label: String?) = run { owner.context(index, label) }
        fun editMedicine(rowId: String?) = run { owner.editMedicine(rowId) }
        fun medicine(value: MigraineMedicineForm) = run { owner.medicine(value) }
        fun cancelMedicine() = run(owner::cancelMedicine)
        fun applyMedicine() = run(owner::applyMedicine)
        fun removeMedicine(rowId: String) = run { owner.removeMedicine(rowId) }
        fun moveMedicine(from: Int, to: Int) = run { owner.moveMedicine(from, to) }
        fun action(value: MigraineFormAction) = run { owner.action(value) }
    }

    fun open(item: CurrentSymptomItem) {
        val selection = migraineFollowUpSelection(currentAccountId(), snapshot(), item) ?: return
        if (state.value.phase != MigraineFollowUpPhase.CLOSED) {
            if (selection == ui.value.selection) return
            pendingSelection = item
            requestClose()
            return
        }
        refreshed = false
        mutableUi.value = MigraineFollowUpFormUi(sessionId = UUID.randomUUID().toString(), selection = selection)
        store.open(selection.accountId, selection.episodeId, selection.promptId)
    }

    fun accountChanged(accountId: String?) {
        if (ui.value.selection?.accountId != accountId) clear()
    }
    fun clear() {
        pendingSelection = null
        mutableUi.value = MigraineFollowUpFormUi()
        store.close()
    }
    private fun current(): Boolean {
        if (ui.value.selection?.accountId != currentAccountId() || state.value.accountId != currentAccountId()) {
            clear(); return false
        }
        return ui.value.selection != null
    }
    private fun editable() = current() && state.value.phase == MigraineFollowUpPhase.EDITING && !ui.value.confirmDiscard

    fun requestClose() {
        if (!current()) return
        val keptDraft = state.value.draft != null && state.value.phase !in setOf(MigraineFollowUpPhase.SAVED, MigraineFollowUpPhase.REVIEWED)
        if (keptDraft || ui.value.medicine != null) mutableUi.value = ui.value.copy(confirmDiscard = true)
        else finishClose()
    }
    fun keepEditing() { pendingSelection = null; mutableUi.value = ui.value.copy(confirmDiscard = false) }
    fun discardAndClose() { if (current() && ui.value.confirmDiscard) finishClose() }
    private fun finishClose() {
        val next = pendingSelection
        clear()
        next?.let(::open) // Revalidate against the latest account and prompt snapshot.
    }

    fun answers(value: MigraineFollowUpAnswers) {
        if (!editable() || ui.value.medicine != null) return
        store.setAnswers(value)
        mutableUi.value = ui.value.copy(message = null)
    }
    fun earlySign(index: Int?, label: String?) {
        if (!editable()) return
        val current = state.value.draft!!.answers
        val entries = (current.earlySigns ?: state.value.baseline!!.episode.earlySigns).toMutableList()
        if (index == null) entries += MigraineEarlySign(label ?: "")
        else if (index in entries.indices) { if (label == null) entries.removeAt(index) else entries[index] = entries[index].copy(label = label) }
        answers(current.copy(earlySigns = entries))
    }
    fun context(index: Int?, label: String?) {
        if (!editable()) return
        val current = state.value.draft!!.answers
        val entries = (current.contexts ?: state.value.baseline!!.episode.contexts).toMutableList()
        if (index == null) entries += MigraineContext("context", label ?: "", "user_reported")
        else if (index in entries.indices) { if (label == null) entries.removeAt(index) else entries[index] = entries[index].copy(label = label) }
        answers(current.copy(contexts = entries))
    }

    fun editMedicine(rowId: String?) {
        if (!editable() || ui.value.medicine != null) return
        val draft = state.value.draft!!
        val row = if (rowId == null) null else draft.medicines.singleOrNull { it.id == rowId } ?: return
        mutableUi.value = ui.value.copy(medicine = MigraineMedicineForm.from(row, draft.responseTimestampUtc, zone()), message = null)
    }
    fun medicine(value: MigraineMedicineForm) {
        if (!editable() || ui.value.medicine == null) return
        // Only editable fields come from the form. Row/original/time provenance is owned here.
        val current = ui.value.medicine!!
        if (value.editorId != current.editorId) return
        mutableUi.value = ui.value.copy(medicine = current.copy(name = value.name, amount = value.amount, unit = value.unit,
            takenAt = value.takenAt, offset = value.offset, relief = value.relief, notes = value.notes), message = null)
    }
    fun cancelMedicine() { if (editable()) mutableUi.value = ui.value.copy(medicine = null, message = null) }
    fun applyMedicine() {
        if (!editable()) return
        val editor = ui.value.medicine ?: return
        try {
            val value = editor.value(state.value.draft!!.responseTimestampUtc)
            if (editor.rowId == null) store.appendMedicine(value) else store.replaceMedicine(editor.rowId, value)
            mutableUi.value = ui.value.copy(medicine = null, message = null)
        } catch (error: IllegalArgumentException) {
            mutableUi.value = ui.value.copy(message = error.message?.takeIf { it.startsWith("Enter ") || it.startsWith("This ") }
                ?: "Check the medicine name, dose, time and notes.")
        }
    }
    fun removeMedicine(rowId: String) { if (editable() && ui.value.medicine == null) store.removeMedicine(rowId) }
    fun moveMedicine(from: Int, to: Int) { if (editable() && ui.value.medicine == null) store.moveMedicine(from, to) }

    fun action(action: MigraineFormAction) {
        if (!current() || ui.value.confirmDiscard || ui.value.medicine != null || action !in migraineFormActions(state.value)) return
        when (action) {
            MigraineFormAction.SAVE -> store.save()
            MigraineFormAction.RETRY_LOAD -> store.retryLoad()
            MigraineFormAction.RETRY_RESPONSE -> store.retrySameResponse()
            MigraineFormAction.REVIEW -> store.reviewSavedVersion()
            MigraineFormAction.USE_REVIEWED -> store.useReviewedVersion()
            MigraineFormAction.DONE -> requestClose()
        }
    }
}
