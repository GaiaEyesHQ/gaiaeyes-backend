package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.MigraineMedicineRepository
import java.time.Instant
import java.time.ZoneId
import java.util.UUID
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

internal enum class MigraineMedicinePhase { CLOSED, EDITING, SAVING, UNAVAILABLE, UNCERTAIN, CONFLICT, REVIEWING, REVIEW, REVIEWED, DELETED, SAVED }
internal data class MigraineMedicineState(
    val sessionId: String = "",
    val summarySelectionId: String = "",
    val accountId: String? = null,
    val episodeId: String? = null,
    val phase: MigraineMedicinePhase = MigraineMedicinePhase.CLOSED,
    val baseline: MigraineDetail? = null,
    val medicines: List<MigraineMedicineDraftRow> = emptyList(),
    val editor: MigraineMedicineForm? = null,
    val pendingRequest: MigraineStructuredEdit? = null,
    val reviewed: MigraineDetail? = null,
    val saved: MigraineDetail? = null,
    val confirmDiscard: Boolean = false,
    val message: String? = null,
) {
    val hasChanges: Boolean get() {
        val original = baseline?.episode?.medicines ?: return false
        return medicines.size != original.size || medicines.zip(original).any { (row, saved) ->
            val sameDose = if (row.value.doseAmount == null) saved.doseAmount == null
                else saved.doseAmount != null && row.value.doseAmount.compareTo(saved.doseAmount) == 0
            !sameDose || row.value.copy(doseAmount = saved.doseAmount) != saved
        }
    }
}

// The scope and all UI calls are confined to the owning main dispatcher.
// A loaded summary supplies the authoritative baseline; no prompt or second initial read.
internal class MigraineMedicineController(
    private val scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val summary: StateFlow<MigraineSummaryState>,
    private val repository: MigraineMedicineRepository,
    private val onSaved: (String, MigraineStructuredEdit, MigraineDetail) -> Boolean,
    private val now: () -> String = { Instant.now().toString() },
    private val zone: () -> ZoneId = { ZoneId.systemDefault() },
) {
    private val mutableState = MutableStateFlow(MigraineMedicineState())
    val state = mutableState.asStateFlow()
    private var job: Job? = null

    init {
        scope.launch { summary.collect { if (state.value.phase != MigraineMedicinePhase.CLOSED && !sameSummary()) clear() } }
    }

    fun canOpen(selectionId: String): Boolean = runCatching {
        val selected = summary.value
        require(selectionId.isNotBlank() && selectionId == selected.selectionId)
        require(selected.accountId != null && selected.accountId == currentAccountId())
        require(!selected.isLoading && selected.problem == null && selected.summary != null)
        requireNotNull(selected.detail).validateFor(requireNotNull(selected.episodeId))
        // All validated episode states, including resolved, are eligible if already selected.
        // This does not introduce a history browser or change episode state/time.
        true
    }.getOrDefault(false)

    fun open(selectionId: String) {
        if (state.value.phase != MigraineMedicinePhase.CLOSED || !canOpen(selectionId)) return
        val selected = summary.value
        val detail = requireNotNull(selected.detail)
        mutableState.value = MigraineMedicineState(UUID.randomUUID().toString(), selectionId,
            selected.accountId, selected.episodeId, MigraineMedicinePhase.EDITING, detail,
            detail.episode.medicines.mapIndexed { index, value -> MigraineMedicineDraftRow(UUID.randomUUID().toString(), index, value) })
    }
    fun clear() { job?.cancel(); job = null; mutableState.value = MigraineMedicineState() }
    fun accountChanged(accountId: String?) { if (state.value.accountId != accountId) clear() }
    private fun sameSummary(): Boolean {
        val before = state.value; val selected = summary.value
        return before.accountId != null && currentAccountId() == before.accountId &&
            selected.accountId == before.accountId && selected.episodeId == before.episodeId &&
            selected.selectionId == before.summarySelectionId && !selected.isLoading && selected.detail != null
    }
    private fun current(sessionId: String = state.value.sessionId): Boolean {
        if (sessionId.isBlank() || state.value.sessionId != sessionId) return false
        if (!sameSummary()) { clear(); return false }
        return true
    }
    private fun requireCurrent(sessionId: String) { if (!current(sessionId)) throw CancellationException("Medicine editor selection changed") }
    private fun editing() = current() && state.value.phase == MigraineMedicinePhase.EDITING && !state.value.confirmDiscard

    fun actions(sessionId: String) = Actions(this) { current(sessionId) }
    internal class Actions(private val owner: MigraineMedicineController, private val current: () -> Boolean) {
        private fun run(action: () -> Unit) { if (current()) action() }
        fun close() = run(owner::requestClose)
        fun keep() = run { owner.mutableState.value = owner.state.value.copy(confirmDiscard = false) }
        fun discard() = run { if (owner.state.value.confirmDiscard) owner.clear() }
        fun edit(rowId: String?) = run { owner.editMedicine(rowId) }
        fun change(value: MigraineMedicineForm) = run { owner.changeMedicine(value) }
        fun apply() = run(owner::applyMedicine)
        fun cancel() = run { if (owner.editing()) owner.mutableState.value = owner.state.value.copy(editor = null, message = null) }
        fun remove(rowId: String) = run { owner.editRows { rows -> rows.filterNot { it.id == rowId } } }
        fun move(from: Int, to: Int) = run { owner.editRows { rows ->
            if (from !in rows.indices || to !in rows.indices) rows else rows.toMutableList().apply { add(to, removeAt(from)) }.toList()
        } }
        fun save() = run(owner::save)
        fun retry() = run(owner::retry)
        fun review() = run(owner::review)
        fun useReviewed() = run {
            if (owner.state.value.phase == MigraineMedicinePhase.REVIEW && !owner.state.value.confirmDiscard)
                owner.mutableState.value = owner.state.value.copy(phase = MigraineMedicinePhase.REVIEWED, message = null)
        }
    }

    private fun requestClose() {
        val before = state.value
        if (before.phase !in setOf(MigraineMedicinePhase.SAVED, MigraineMedicinePhase.REVIEWED) &&
            (before.hasChanges || before.editor != null || before.pendingRequest != null)) {
            mutableState.value = before.copy(confirmDiscard = true)
        } else clear()
    }
    private fun editRows(change: (List<MigraineMedicineDraftRow>) -> List<MigraineMedicineDraftRow>) {
        if (!editing() || state.value.editor != null) return
        mutableState.value = state.value.copy(medicines = change(state.value.medicines).toList(), message = null)
    }
    private fun editMedicine(rowId: String?) {
        if (!editing() || state.value.editor != null) return
        val row = if (rowId == null) null else state.value.medicines.singleOrNull { it.id == rowId } ?: return
        mutableState.value = state.value.copy(editor = MigraineMedicineForm.from(row, now(), zone()), message = null)
    }
    private fun changeMedicine(value: MigraineMedicineForm) {
        if (!editing()) return
        val editor = state.value.editor ?: return
        if (editor.editorId != value.editorId) return
        mutableState.value = state.value.copy(editor = editor.copy(name = value.name, amount = value.amount, unit = value.unit,
            takenAt = value.takenAt, offset = value.offset, relief = value.relief, notes = value.notes), message = null)
    }
    private fun applyMedicine() {
        if (!editing()) return
        val before = state.value; val editor = before.editor ?: return
        try {
            // Changed relief is reported at Apply, not at an invented follow-up response.
            // Its stored timestamp survives later edits, save attempts and frozen retries.
            val value = editor.value(now())
            val rows = if (editor.rowId == null) before.medicines + MigraineMedicineDraftRow(UUID.randomUUID().toString(), null, value)
                else before.medicines.map { if (it.id == editor.rowId) it.copy(value = value) else it }
            mutableState.value = before.copy(medicines = rows, editor = null, message = null)
        } catch (error: IllegalArgumentException) {
            mutableState.value = before.copy(message = error.message?.takeIf { it.startsWith("Enter ") || it.startsWith("This ") }
                ?: "Check the medicine name, dose, time and notes.")
        }
    }
    private fun save() {
        if (!editing() || state.value.editor != null) return
        val before = state.value
        if (!before.hasChanges) {
            mutableState.value = before.copy(message = "Medicine entries are unchanged. Nothing was saved.")
            return
        }
        val request = try {
            MigraineStructuredEdit(requireNotNull(before.baseline).revision, medicines = before.medicines.map { it.value }).also { it.toJson() }
        } catch (_: IllegalArgumentException) {
            mutableState.value = before.copy(message = "Check the medicine entries before saving."); return
        }
        submit(request, alreadyUncertain = false)
    }
    private fun retry() {
        if (!current() || state.value.confirmDiscard) return
        val before = state.value
        if (before.phase !in setOf(MigraineMedicinePhase.UNAVAILABLE, MigraineMedicinePhase.UNCERTAIN)) return
        submit(before.pendingRequest ?: return, alreadyUncertain = before.phase == MigraineMedicinePhase.UNCERTAIN)
    }
    private fun submit(request: MigraineStructuredEdit, alreadyUncertain: Boolean) {
        val before = state.value; val session = before.sessionId
        var dispatched = false
        mutableState.value = before.copy(phase = MigraineMedicinePhase.SAVING, pendingRequest = request, message = null)
        job = scope.launch {
            try {
                val saved = repository.save(requireNotNull(before.accountId), requireNotNull(before.episodeId), request,
                    { requireCurrent(session) }, { dispatched = true })
                requireCurrent(session)
                saved.validateFor(before.episodeId)
                require(migraineEditAcknowledged(request.toJson(), saved))
                // The summary store validates the same selection, revision and receipt again.
                require(onSaved(before.summarySelectionId, request, saved))
                requireCurrent(session)
                mutableState.value = state.value.copy(phase = MigraineMedicinePhase.SAVED, saved = saved,
                    baseline = saved, medicines = emptyList(), pendingRequest = null, message = null)
            } catch (error: Exception) {
                if (!current(session)) return@launch
                val phase = when (error) {
                    is MigraineEpisodeNotFoundException -> MigraineMedicinePhase.DELETED
                    is MigraineConflictException -> MigraineMedicinePhase.CONFLICT
                    is MigraineUnavailableException -> if (alreadyUncertain) MigraineMedicinePhase.UNCERTAIN else MigraineMedicinePhase.UNAVAILABLE
                    is MigraineRejectedException -> if (alreadyUncertain) MigraineMedicinePhase.CONFLICT else MigraineMedicinePhase.EDITING
                    is ApiUnauthorizedException -> if (alreadyUncertain) MigraineMedicinePhase.UNCERTAIN else MigraineMedicinePhase.EDITING
                    else -> if (alreadyUncertain || dispatched) MigraineMedicinePhase.UNCERTAIN else MigraineMedicinePhase.EDITING
                }
                mutableState.value = state.value.copy(phase = phase,
                    pendingRequest = if (phase == MigraineMedicinePhase.EDITING) null else request, message = problem(error))
            }
        }
    }
    private fun review() {
        if (!current() || state.value.confirmDiscard || state.value.phase !in setOf(MigraineMedicinePhase.UNCERTAIN, MigraineMedicinePhase.CONFLICT)) return
        val before = state.value; val session = before.sessionId
        mutableState.value = before.copy(phase = MigraineMedicinePhase.REVIEWING, message = null)
        job = scope.launch {
            try {
                val detail = repository.detail(requireNotNull(before.accountId), requireNotNull(before.episodeId)) { requireCurrent(session) }
                requireCurrent(session); detail.validateFor(before.episodeId)
                require(detail.revision >= requireNotNull(before.baseline).revision)
                mutableState.value = state.value.copy(phase = MigraineMedicinePhase.REVIEW, reviewed = detail)
            } catch (error: Exception) {
                if (!current(session)) return@launch
                mutableState.value = state.value.copy(phase = if (error is MigraineEpisodeNotFoundException) MigraineMedicinePhase.DELETED else before.phase,
                    message = problem(error))
            }
        }
    }
    private fun problem(error: Exception): String? = when (error) {
        is ApiUnauthorizedException -> "Your session needs attention. The save has not been confirmed."
        is MigraineRejectedException -> "The changes were rejected. Review your kept entries."
        is MigraineInvalidResponseException, is IllegalArgumentException -> "The returned medicine details could not be verified."
        is CancellationException -> "The request was interrupted."
        else -> null // The phase supplies the specific recovery explanation.
    }
}
