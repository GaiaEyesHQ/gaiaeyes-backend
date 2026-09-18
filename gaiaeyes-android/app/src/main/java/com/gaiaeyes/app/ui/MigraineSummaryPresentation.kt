package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.CurrentSymptomPendingFollowUp
import com.gaiaeyes.app.core.network.MigraineDetail
import com.gaiaeyes.app.core.network.MigraineTimestamp
import com.gaiaeyes.app.core.network.sameMigraineId
import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

internal data class MigraineSummaryEntry(val title: String, val lines: List<String>)
internal data class MigraineSummarySection(
    val title: String,
    val entries: List<MigraineSummaryEntry>,
    val emptyMessage: String = "Not recorded",
)
internal data class SavedMigraineSummary(
    val displayTimezone: String,
    val hasStructuredDetails: Boolean,
    val sections: List<MigraineSummarySection>,
)

// A projection of the validated saved response, never an editor draft or advice.
internal fun savedMigraineSummary(
    detail: MigraineDetail,
    episodeId: String,
    pendingFollowUp: CurrentSymptomPendingFollowUp?,
    zone: ZoneId = ZoneId.systemDefault(),
    locale: Locale = Locale.getDefault(),
): SavedMigraineSummary {
    detail.validateFor(episodeId)
    val episode = detail.episode
    val format = DateTimeFormatter.ofPattern("MMM d, yyyy 'at' h:mm:ss a z", locale)
    fun text(value: String?) = value?.takeIf { it.isNotBlank() } ?: "Not recorded"
    fun time(value: String?) = value?.let {
        runCatching { OffsetDateTime.parse(it).atZoneSameInstant(zone).format(format) }
            .getOrDefault("Time unavailable")
    } ?: "Not recorded"
    fun timestamp(label: String, value: MigraineTimestamp?): List<String> {
        if (value == null) return listOf("$label: Not recorded")
        return listOf(
            "$label: ${time(value.utc)}",
            "$label — saved UTC: ${value.utc}",
            "Original time: ${text(value.originalTime)}",
            "Recorded timezone: ${text(value.timezoneName)}",
            "Recorded UTC offset (minutes): ${value.utcOffsetMinutes?.toString() ?: "Not recorded"}",
            "Timezone source: ${value.timezoneSource.replace('_', ' ')}",
        )
    }
    val duration = episode.end?.let {
        val minutes = Duration.between(OffsetDateTime.parse(episode.start.utc), OffsetDateTime.parse(it.utc)).toMinutes()
        when {
            minutes == 0L -> "Less than a minute"
            minutes < 60 -> "$minutes minute${if (minutes == 1L) "" else "s"}"
            else -> "${minutes / 60} hour${if (minutes / 60 == 1L) "" else "s"}, ${minutes % 60} minute${if (minutes % 60 == 1L) "" else "s"}"
        }
    } ?: "Not available without a recorded end time"
    val timing = listOf(
        MigraineSummaryEntry("Onset", timestamp("Started", episode.start)),
        MigraineSummaryEntry("End", timestamp("Ended", episode.end)),
        MigraineSummaryEntry("Saved state", listOf(episode.state.replaceFirstChar { it.titlecase(locale) })),
        MigraineSummaryEntry("Severity", listOf(episode.severity?.let { "$it/10" } ?: "Not recorded")),
        MigraineSummaryEntry("Duration", listOf(duration)),
    )
    val medicines = episode.medicines.mapIndexed { index, medicine ->
        val relief = when (medicine.reportedRelief) {
            null -> "Not recorded"
            "none" -> "No relief"
            "unknown" -> "Unknown"
            "a_little" -> "A little"
            "some" -> "Some"
            "a_lot" -> "A lot"
            "complete" -> "Complete"
            else -> medicine.reportedRelief
        }
        MigraineSummaryEntry("${index + 1}. ${medicine.name}",
            timestamp("Taken", medicine.takenAt) + listOf(
                "Dose: ${medicine.doseAmount?.let { "${it.toPlainString()} ${medicine.doseUnit}" } ?: "Not recorded"}",
                "Reported relief: $relief",
            ) + timestamp("Relief recorded", medicine.reliefReportedAt) + "Note: ${text(medicine.notes)}")
    }
    val signs = episode.earlySigns.map { sign ->
        MigraineSummaryEntry(sign.label, timestamp("Recorded", sign.reportedAt) + "Note: ${text(sign.notes)}")
    }
    val contexts = episode.contexts.map { context ->
        MigraineSummaryEntry(context.label, listOf(
            "Type: ${context.kind}", "Source: ${context.source.replace('_', ' ')}",
        ) + timestamp("Observed", context.observedAt) + "Note: ${text(context.notes)}")
    }
    val followUpLines = when {
        pendingFollowUp == null -> listOf("Follow-up status was not provided in the Current Symptoms list.")
        pendingFollowUp.symptomCode != "MIGRAINE" ||
            !runCatching { sameMigraineId(pendingFollowUp.episodeId, episodeId) }.getOrDefault(false) ->
            listOf("Follow-up information is unavailable for this episode.")
        else -> listOf(
            "Status: ${pendingFollowUp.status?.takeIf { it.isNotBlank() }?.replace('_', ' ') ?: "Not provided"}",
            "Question: ${text(pendingFollowUp.questionText)}",
            "Scheduled: ${time(pendingFollowUp.scheduledFor)}",
            "Delivered: ${time(pendingFollowUp.deliveredAt)}",
            "From the last Current Symptoms refresh.",
        )
    }
    return SavedMigraineSummary(zone.id, detail.revision > 0, listOf(
        MigraineSummarySection("Episode", timing),
        MigraineSummarySection("Medicines", medicines, "No medicine entries recorded"),
        MigraineSummarySection("Recorded early signs", signs),
        MigraineSummarySection("Recorded context", contexts),
        MigraineSummarySection("Episode notes", listOf(MigraineSummaryEntry("Note", listOf(text(episode.notes))))),
        MigraineSummarySection("Follow-up", listOf(MigraineSummaryEntry("Available follow-up information", followUpLines))),
    ))
}
