package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.CurrentSymptomsSnapshot
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.UUID

internal data class MigraineFollowUpSelection(val accountId: String, val episodeId: String, val promptId: String, val question: String)

// Used both to display the entry and again on click with the current account snapshot.
internal fun migraineFollowUpSelection(accountId: String?, snapshot: CurrentSymptomsSnapshot?, item: CurrentSymptomItem): MigraineFollowUpSelection? = runCatching {
    require(!accountId.isNullOrBlank() && snapshot?.accountId == accountId)
    val id = migraineId(item.id)
    require(item.symptomCode == "MIGRAINE")
    val current = requireNotNull(snapshot).symptoms.items.singleOrNull { runCatching { sameMigraineId(it.id, id) }.getOrDefault(false) }
    require(current?.symptomCode == "MIGRAINE")
    val prompt = requireNotNull(current.pendingFollowUp)
    val displayed = requireNotNull(item.pendingFollowUp)
    require(prompt.symptomCode == "MIGRAINE" && displayed.symptomCode == "MIGRAINE")
    require(sameMigraineId(prompt.episodeId, id) && sameMigraineId(displayed.episodeId, id))
    require(sameMigraineId(prompt.id, displayed.id))
    require(prompt.status == null || prompt.status in setOf("pending", "snoozed"))
    MigraineFollowUpSelection(requireNotNull(accountId), id, migraineId(prompt.id), prompt.questionText)
}.getOrNull()

internal enum class MigraineFormAction(val label: String) {
    SAVE("Save follow-up"), RETRY_LOAD("Retry loading"), RETRY_RESPONSE("Retry same response"),
    REVIEW("Review saved version"), USE_REVIEWED("Use reviewed version"), DONE("Done"),
}
internal fun migraineFormActions(state: MigraineFollowUpState): List<MigraineFormAction> = when (state.phase) {
    MigraineFollowUpPhase.EDITING -> listOf(MigraineFormAction.SAVE)
    MigraineFollowUpPhase.UNCERTAIN -> listOf(MigraineFormAction.RETRY_RESPONSE, MigraineFormAction.REVIEW)
    MigraineFollowUpPhase.CONFLICT -> listOf(MigraineFormAction.REVIEW)
    MigraineFollowUpPhase.REVIEW -> listOf(MigraineFormAction.USE_REVIEWED)
    MigraineFollowUpPhase.UNAVAILABLE -> when {
        state.baseline == null -> listOf(MigraineFormAction.RETRY_LOAD)
        state.draft != null && state.pendingRequest != null -> listOf(MigraineFormAction.RETRY_RESPONSE)
        else -> emptyList()
    }
    MigraineFollowUpPhase.SAVED, MigraineFollowUpPhase.REVIEWED -> listOf(MigraineFormAction.DONE)
    else -> emptyList()
}

internal fun migraineFormStatus(state: MigraineFollowUpState): String = when (state.phase) {
    MigraineFollowUpPhase.CLOSED -> ""
    MigraineFollowUpPhase.LOADING -> "Loading your saved episode…"
    MigraineFollowUpPhase.EDITING -> "Update what changed. Extra details are optional."
    MigraineFollowUpPhase.SAVING -> "Saving your response…"
    MigraineFollowUpPhase.UNCERTAIN -> "We couldn't confirm the save. Your response is kept. Retry sends the same response."
    MigraineFollowUpPhase.CONFLICT -> "This episode changed. Your response is kept; review the saved version before deciding."
    MigraineFollowUpPhase.REVIEWING -> "Loading the saved version for comparison…"
    MigraineFollowUpPhase.REVIEW -> "Compare the saved version below with your kept response. This check does not confirm your earlier save."
    MigraineFollowUpPhase.REVIEWED -> "You chose the reviewed version. The earlier response was set aside, not confirmed as saved. Close and refresh Current Symptoms before another follow-up."
    MigraineFollowUpPhase.SAVED -> "Follow-up saved."
    MigraineFollowUpPhase.DELETED -> "This episode is no longer available. Any draft is kept here until you close it."
    MigraineFollowUpPhase.UNAVAILABLE -> if (state.draft == null) "Saved details are unavailable. Try loading again."
        else "Follow-up saving is unavailable. Your response is kept; retry sends the same response."
}

internal data class MigraineMedicineForm(
    val rowId: String?,
    val original: MigraineMedicine?,
    val name: String,
    val amount: String,
    val unit: String,
    val takenAt: LocalDateTime,
    val zoneId: String,
    val offset: ZoneOffset?,
    val relief: String?,
    val notes: String,
    val initialTime: LocalDateTime,
    val editorId: String = UUID.randomUUID().toString(),
) {
    fun value(responseTimestamp: String): MigraineMedicine {
        val dose = amount.trim()
        val doseUnit = unit.trim()
        require(name.trim().isNotEmpty()) { "Enter a medicine name." }
        require(dose.isEmpty() == doseUnit.isEmpty()) { "Enter both dose and unit, or leave both blank." }
        val decimal = if (dose.isEmpty()) null else dose.toBigDecimalOrNull()
        require(dose.isEmpty() || decimal != null && decimal.signum() > 0) { "Enter a dose greater than zero." }
        val time = if (original != null && takenAt == initialTime && offset == OffsetDateTime.parse(original.takenAt.utc).atZoneSameInstant(ZoneId.of(zoneId)).offset) {
            original.takenAt
        } else {
            val zone = ZoneId.of(zoneId)
            val offsets = zone.rules.getValidOffsets(takenAt)
            require(offsets.isNotEmpty()) { "This local time does not exist because the clocks change. Choose another time." }
            val chosen = offsets.singleOrNull() ?: offset?.takeIf { it in offsets }
            require(chosen != null) { "This time occurs twice. Choose its UTC offset." }
            MigraineTimestamp(takenAt.toInstant(chosen).toString(), "user", takenAt.toString(), zone.id, chosen.totalSeconds / 60)
        }
        val reliefTime = if (relief == original?.reportedRelief) original?.reliefReportedAt
            else if (relief == null) null else MigraineTimestamp(responseTimestamp, "user")
        return MigraineMedicine(
            name = if (name == original?.name) name else name.trim(),
            takenAt = time,
            doseAmount = if (amount == original?.doseAmount?.toPlainString()) original.doseAmount else decimal,
            doseUnit = if (unit == (original?.doseUnit ?: "")) original?.doseUnit else doseUnit.takeIf { it.isNotEmpty() },
            reportedRelief = relief, reliefReportedAt = reliefTime,
            notes = if (notes == (original?.notes ?: "")) original?.notes else notes.trim().takeIf { it.isNotEmpty() },
        ).also { it.validate() }
    }

    companion object {
        fun from(row: MigraineMedicineDraftRow?, timestamp: String, zone: ZoneId): MigraineMedicineForm {
            val original = row?.value
            val instant = OffsetDateTime.parse(original?.takenAt?.utc ?: timestamp).atZoneSameInstant(zone)
            return MigraineMedicineForm(row?.id, original, original?.name ?: "", original?.doseAmount?.toPlainString() ?: "",
                original?.doseUnit ?: "", instant.toLocalDateTime(), zone.id, instant.offset,
                original?.reportedRelief, original?.notes ?: "", instant.toLocalDateTime())
        }
    }
}
