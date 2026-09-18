package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import java.util.UUID

// Local row identity only. The backend stores an ordered array with no medicine IDs.
internal data class MigraineMedicineDraftRow(
    val id: String,
    val originalIndex: Int?,
    val value: MigraineMedicine,
)

internal data class MigraineFollowUpAnswers(
    val state: String,
    val earlySigns: List<MigraineEarlySign>? = null,
    val contexts: List<MigraineContext>? = null,
    val notes: MigraineTextChange = MigraineTextChange.Retain,
    val detailChoice: String? = null,
    val detailText: String? = null,
    val noteText: String? = null,
    val timeBucket: String? = null,
)

internal data class MigraineFollowUpDraft(
    val responseTimestampUtc: String,
    val answers: MigraineFollowUpAnswers,
    val medicines: List<MigraineMedicineDraftRow>,
    val medicinesChanged: Boolean = false,
) {
    fun request(revision: Long): MigraineFollowUpRequest = MigraineFollowUpRequest(
        state = answers.state,
        timestampUtc = responseTimestampUtc,
        migraine = MigraineStructuredEdit(
            expectedRevision = revision,
            earlySigns = answers.earlySigns?.toList(),
            contexts = answers.contexts?.toList(),
            medicines = if (medicinesChanged) medicines.map { it.value } else null,
            notes = answers.notes,
        ),
        detailChoice = answers.detailChoice, detailText = answers.detailText,
        noteText = answers.noteText, timeBucket = answers.timeBucket,
    ).also { it.toJson() } // Validate before any auth/transport call; never coerce missing into zero.

    companion object {
        fun from(detail: MigraineDetail, timestampUtc: String) = MigraineFollowUpDraft(
            timestampUtc, MigraineFollowUpAnswers(detail.episode.state),
            detail.episode.medicines.mapIndexed { index, value ->
                MigraineMedicineDraftRow(UUID.randomUUID().toString(), index, value)
            },
        )
    }
}
