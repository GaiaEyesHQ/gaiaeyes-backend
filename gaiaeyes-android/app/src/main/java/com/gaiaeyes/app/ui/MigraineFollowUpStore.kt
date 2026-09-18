package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.MigraineFollowUpRepository
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.jsonObject

internal enum class MigraineFollowUpPhase {
    CLOSED, LOADING, EDITING, SAVING, UNCERTAIN, CONFLICT, REVIEWING, REVIEW, REVIEWED, DELETED, UNAVAILABLE, SAVED,
}
internal enum class MigraineFollowUpProblem { INVALID_INPUT, NETWORK, SIGN_IN, INVALID_RESPONSE, REJECTED, CANCELLED }
internal data class MigraineFollowUpState(
    val accountId: String? = null,
    val episodeId: String? = null,
    val promptId: String? = null,
    val phase: MigraineFollowUpPhase = MigraineFollowUpPhase.CLOSED,
    val baseline: MigraineDetail? = null,
    val draft: MigraineFollowUpDraft? = null,
    val pendingRequest: MigraineFollowUpRequest? = null,
    val reviewed: MigraineDetail? = null,
    val saved: MigraineFollowUpResult? = null,
    val problem: MigraineFollowUpProblem? = null,
)

// Confine calls and scope to the owning UI dispatcher, as with MigraineSummaryStore.
// In-memory only. A form must clear on close/account change and explain draft loss.
// No caller can edit a frozen uncertain request or silently rebase its medicine rows.
internal class MigraineFollowUpStore(
    private val scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val repository: MigraineFollowUpRepository,
    private val now: () -> String = { Instant.now().toString() },
) {
    private val mutableState = MutableStateFlow(MigraineFollowUpState())
    val state = mutableState.asStateFlow()
    private var generation = 0L
    private var job: Job? = null

    fun close() {
        generation++
        job?.cancel()
        job = null
        mutableState.value = MigraineFollowUpState()
    }
    fun accountChanged(accountId: String?) { if (state.value.accountId != accountId) close() }

    fun open(accountId: String, episodeId: String, promptId: String) {
        close()
        if (accountId.isBlank() || currentAccountId() != accountId) return
        val episode = runCatching { migraineId(episodeId) }.getOrNull()
        val prompt = runCatching { migraineId(promptId) }.getOrNull()
        if (episode == null || prompt == null) {
            mutableState.value = MigraineFollowUpState(accountId, episodeId, promptId,
                phase = MigraineFollowUpPhase.UNAVAILABLE, problem = MigraineFollowUpProblem.INVALID_INPUT)
            return
        }
        mutableState.value = MigraineFollowUpState(accountId, episode, prompt, MigraineFollowUpPhase.LOADING)
        load(review = false)
    }

    fun retryLoad() {
        if (isCurrent() && state.value.baseline == null && state.value.phase == MigraineFollowUpPhase.UNAVAILABLE) load(false)
    }

    fun setAnswers(answers: MigraineFollowUpAnswers) = edit { it.copy(answers = answers.copy(
        earlySigns = answers.earlySigns?.toList(), contexts = answers.contexts?.toList(),
    )) }
    fun appendMedicine(value: MigraineMedicine) = edit { it.copy(
        medicines = it.medicines + MigraineMedicineDraftRow(UUID.randomUUID().toString(), null, value), medicinesChanged = true,
    ) }
    fun replaceMedicine(rowId: String, value: MigraineMedicine) = edit { draft ->
        require(draft.medicines.any { it.id == rowId })
        draft.copy(medicines = draft.medicines.map { if (it.id == rowId) it.copy(value = value) else it }, medicinesChanged = true)
    }
    fun removeMedicine(rowId: String) = edit { draft ->
        require(draft.medicines.any { it.id == rowId })
        draft.copy(medicines = draft.medicines.filterNot { it.id == rowId }, medicinesChanged = true)
    }
    fun moveMedicine(fromIndex: Int, toIndex: Int) = edit { draft ->
        require(fromIndex in draft.medicines.indices && toIndex in draft.medicines.indices)
        val rows = draft.medicines.toMutableList()
        rows.add(toIndex, rows.removeAt(fromIndex))
        draft.copy(medicines = rows.toList(), medicinesChanged = true)
    }
    private fun edit(change: (MigraineFollowUpDraft) -> MigraineFollowUpDraft) {
        if (!isCurrent() || state.value.phase != MigraineFollowUpPhase.EDITING) return
        val before = state.value
        mutableState.value = try { before.copy(draft = change(requireNotNull(before.draft)), problem = null) }
        catch (_: IllegalArgumentException) { before.copy(problem = MigraineFollowUpProblem.INVALID_INPUT) }
    }

    fun save() {
        if (!isCurrent() || state.value.phase != MigraineFollowUpPhase.EDITING) return
        val before = state.value
        val request = try { requireNotNull(before.draft).request(requireNotNull(before.baseline).revision) }
        catch (_: Exception) {
            mutableState.value = before.copy(problem = MigraineFollowUpProblem.INVALID_INPUT)
            return
        }
        submit(request, alreadyUncertain = false)
    }

    // User action only: replay exactly the same complete replacement and timestamp.
    // The accepted server validates both prompt response and optimistic revision.
    // A loaded response rejected as unavailable keeps its draft and frozen request;
    // do not run retryLoad or rebuild it. Earlier uncertainty stays sticky.
    fun retrySameResponse() {
        if (!isCurrent()) return
        val before = state.value
        val alreadyUncertain = when (before.phase) {
            MigraineFollowUpPhase.UNCERTAIN -> true
            MigraineFollowUpPhase.UNAVAILABLE -> {
                if (before.baseline == null || before.draft == null) return
                false
            }
            else -> return
        }
        submit(before.pendingRequest ?: return, alreadyUncertain = alreadyUncertain)
    }

    fun reviewSavedVersion() {
        if (!isCurrent() || state.value.phase !in setOf(MigraineFollowUpPhase.UNCERTAIN, MigraineFollowUpPhase.CONFLICT)) return
        load(review = true)
    }

    // Explicitly set aside the old request. This is never labelled a successful save.
    // Keep it and its draft for reference; start another response only from refreshed
    // current-symptom/prompt context. Do not append old draft entries to this GET.
    fun useReviewedVersion() {
        if (!isCurrent() || state.value.phase != MigraineFollowUpPhase.REVIEW) return
        mutableState.value = state.value.copy(phase = MigraineFollowUpPhase.REVIEWED, problem = null)
    }

    private fun submit(request: MigraineFollowUpRequest, alreadyUncertain: Boolean) {
        val before = state.value
        val selected = generation
        var dispatched = false
        mutableState.value = before.copy(phase = MigraineFollowUpPhase.SAVING, pendingRequest = request, problem = null)
        job = scope.launch {
            try {
                val saved = repository.save(requireNotNull(before.accountId), requireNotNull(before.episodeId),
                    requireNotNull(before.promptId), request, { requireSelected(selected) }, { dispatched = true })
                requireSelected(selected)
                // The production client checks this too. Keep the state boundary explicit.
                saved.migraineDetail.validateFor(before.episodeId)
                require(sameMigraineId(saved.prompt.id, before.promptId) && sameMigraineId(saved.prompt.episodeId, before.episodeId))
                require(saved.prompt.status == "answered" && saved.prompt.symptomCode == "MIGRAINE")
                require(sameMigraineId(saved.episode.id, before.episodeId) && saved.episode.symptomCode == "MIGRAINE")
                require(saved.episode.currentState == request.state)
                saved.episode.pendingFollowUp?.let { require(!sameMigraineId(it.id, before.promptId)) }
                require(saved.migraineDetail.episode.state == request.state)
                require(migraineEditAcknowledged(request.toJson().getValue("migraine").jsonObject, saved.migraineDetail))
                mutableState.value = state.value.copy(phase = MigraineFollowUpPhase.SAVED, baseline = saved.migraineDetail,
                    draft = null, pendingRequest = null, saved = saved, problem = null)
            } catch (error: Exception) {
                if (!isSelected(selected)) return@launch
                val uncertain = alreadyUncertain || dispatched
                val phase = when (error) {
                    is MigraineEpisodeNotFoundException -> MigraineFollowUpPhase.DELETED
                    is MigraineConflictException -> MigraineFollowUpPhase.CONFLICT
                    is MigraineRejectedException -> if (alreadyUncertain) MigraineFollowUpPhase.CONFLICT else MigraineFollowUpPhase.EDITING
                    is MigraineUnavailableException -> if (alreadyUncertain) MigraineFollowUpPhase.UNCERTAIN else MigraineFollowUpPhase.UNAVAILABLE
                    is ApiUnauthorizedException -> if (alreadyUncertain) MigraineFollowUpPhase.UNCERTAIN else MigraineFollowUpPhase.EDITING
                    else -> if (uncertain) MigraineFollowUpPhase.UNCERTAIN else MigraineFollowUpPhase.EDITING
                }
                mutableState.value = state.value.copy(phase = phase,
                    pendingRequest = if (phase == MigraineFollowUpPhase.EDITING) null else request,
                    problem = problem(error))
            }
        }
    }

    private fun load(review: Boolean) {
        val before = state.value
        val selected = generation
        mutableState.value = before.copy(phase = if (review) MigraineFollowUpPhase.REVIEWING else MigraineFollowUpPhase.LOADING, problem = null)
        job = scope.launch {
            try {
                val detail = repository.detail(requireNotNull(before.accountId), requireNotNull(before.episodeId)) { requireSelected(selected) }
                requireSelected(selected)
                detail.validateFor(before.episodeId)
                if (review) {
                    require(detail.revision >= requireNotNull(before.baseline).revision)
                    mutableState.value = state.value.copy(phase = MigraineFollowUpPhase.REVIEW, reviewed = detail)
                } else {
                    mutableState.value = state.value.copy(phase = MigraineFollowUpPhase.EDITING, baseline = detail,
                        draft = MigraineFollowUpDraft.from(detail, now()))
                }
            } catch (error: Exception) {
                if (!isSelected(selected)) return@launch
                mutableState.value = state.value.copy(phase = if (error is MigraineEpisodeNotFoundException) MigraineFollowUpPhase.DELETED
                    else if (review) before.phase else MigraineFollowUpPhase.UNAVAILABLE, problem = problem(error))
            }
        }
    }

    private fun isCurrent() = isSelected(generation)
    private fun isSelected(expected: Long): Boolean {
        if (generation != expected || state.value.accountId == null) return false
        if (state.value.accountId != currentAccountId()) { close(); return false }
        return true
    }
    private fun requireSelected(expected: Long) {
        if (!isSelected(expected)) throw CancellationException("Follow-up selection changed")
    }
    private fun problem(error: Exception) = when (error) {
        is ApiUnauthorizedException -> MigraineFollowUpProblem.SIGN_IN
        is MigraineRejectedException -> MigraineFollowUpProblem.REJECTED
        is CancellationException -> MigraineFollowUpProblem.CANCELLED
        is MigraineInvalidResponseException, is IllegalArgumentException -> MigraineFollowUpProblem.INVALID_RESPONSE
        else -> MigraineFollowUpProblem.NETWORK
    }
}
