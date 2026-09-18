package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.MigraineDetail
import com.gaiaeyes.app.core.network.MigraineEpisodeNotFoundException
import com.gaiaeyes.app.core.network.MigraineInvalidResponseException
import com.gaiaeyes.app.core.network.MigraineUnavailableException
import com.gaiaeyes.app.core.network.migraineId
import com.gaiaeyes.app.core.network.MigraineStructuredEdit
import com.gaiaeyes.app.core.network.MigraineTextChange
import com.gaiaeyes.app.core.network.migraineEditAcknowledged
import java.time.ZoneId
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

internal enum class MigraineSummaryProblem(val message: String) {
    LEGACY_ENTRY("Saved summaries aren't available for this older or unsupported entry. Your existing symptom controls are still available."),
    UNAVAILABLE("Saved migraine details are unavailable for this episode or server right now."),
    NETWORK("We couldn't load the saved episode. Check your connection and retry."),
    INVALID_RESPONSE("The saved episode response couldn't be read. Retry to load it again."),
    SIGN_IN("Your session needs attention. Close this summary and sign in again."),
    CANCELLED("Loading was interrupted. Retry to load the saved episode."),
}

internal data class MigraineSummaryState(
    val accountId: String? = null,
    val episodeId: String? = null,
    val isLoading: Boolean = false,
    val summary: SavedMigraineSummary? = null,
    val problem: MigraineSummaryProblem? = null,
    val selectionId: String = "",
    val detail: MigraineDetail? = null,
)

// Visible in-memory state only: no shared/disk cache, no writes, no automatic retry.
// The generation guard also rejects transports that return after cancellation.
internal class MigraineSummaryStore(
    private val scope: CoroutineScope,
    private val currentAccountId: () -> String?,
    private val fetch: suspend (String, String) -> MigraineDetail,
    private val zone: () -> ZoneId = { ZoneId.systemDefault() },
    private val locale: () -> Locale = { Locale.getDefault() },
) {
    private val mutableState = MutableStateFlow(MigraineSummaryState())
    val state = mutableState.asStateFlow()
    private var generation = 0L
    private var job: Job? = null
    private var selection: Pair<String, CurrentSymptomItem>? = null

    fun close() {
        generation++
        job?.cancel()
        job = null
        selection = null
        mutableState.value = MigraineSummaryState()
    }

    fun accountChanged(accountId: String?) {
        if (state.value.accountId != accountId) close()
    }

    fun retry() {
        selection?.let { (account, item) -> open(account, item) }
    }

    // Only a matching PATCH receipt may automatically refresh this selected summary.
    // GET comparison remains separate; retained prompt text is still from Current Symptoms.
    fun acceptMedicineEdit(selectionId: String, request: MigraineStructuredEdit, saved: MigraineDetail): Boolean {
        val before = state.value
        val selected = selection ?: return false
        if (selectionId.isBlank() || before.selectionId != selectionId || before.isLoading ||
            before.summary == null || before.detail == null || before.accountId != currentAccountId()) return false
        return runCatching {
            require(request.medicines != null && request.earlySigns == null && request.contexts == null && request.notes == MigraineTextChange.Retain)
            require(request.expectedRevision == before.detail.revision)
            saved.validateFor(requireNotNull(before.episodeId))
            require(migraineEditAcknowledged(request.toJson(), saved))
            val summary = savedMigraineSummary(saved, before.episodeId, selected.second.pendingFollowUp, zone(), locale())
            mutableState.value = before.copy(summary = summary, detail = saved, problem = null)
            true
        }.getOrDefault(false)
    }

    fun open(accountId: String, item: CurrentSymptomItem) {
        close()
        if (currentAccountId() != accountId) return
        selection = accountId to item
        val id = runCatching { migraineId(item.id) }.getOrNull()
        if (item.symptomCode != "MIGRAINE" || id == null) {
            mutableState.value = MigraineSummaryState(accountId, item.id, problem = MigraineSummaryProblem.LEGACY_ENTRY)
            return
        }
        val requestGeneration = generation
        mutableState.value = MigraineSummaryState(accountId, id, isLoading = true, selectionId = UUID.randomUUID().toString())
        fun stillSelected(): Boolean {
            if (generation != requestGeneration) return false
            if (currentAccountId() != accountId) { close(); return false }
            return true
        }
        job = scope.launch {
            try {
                if (!stillSelected()) return@launch
                val detail = fetch(accountId, id)
                if (!stillSelected()) return@launch
                val summary = savedMigraineSummary(detail, id, item.pendingFollowUp, zone(), locale())
                mutableState.value = state.value.copy(isLoading = false, summary = summary, detail = detail)
            } catch (error: Exception) {
                if (!stillSelected()) return@launch
                val problem = when (error) {
                    is CancellationException -> MigraineSummaryProblem.CANCELLED
                    is MigraineEpisodeNotFoundException -> MigraineSummaryProblem.UNAVAILABLE
                    is MigraineUnavailableException -> {
                        // Coroutine stack-trace recovery can copy this exception
                        // with the original as its cause. Only a different cause
                        // represents the accepted client's transport failure.
                        var cause: Throwable? = error
                        while (cause is MigraineUnavailableException) cause = cause.cause
                        if (cause == null) MigraineSummaryProblem.UNAVAILABLE else MigraineSummaryProblem.NETWORK
                    }
                    is ApiUnauthorizedException -> MigraineSummaryProblem.SIGN_IN
                    is MigraineInvalidResponseException, is IllegalArgumentException -> MigraineSummaryProblem.INVALID_RESPONSE
                    else -> MigraineSummaryProblem.NETWORK
                }
                mutableState.value = state.value.copy(isLoading = false, summary = null, detail = null, problem = problem)
            }
        }
    }
}
