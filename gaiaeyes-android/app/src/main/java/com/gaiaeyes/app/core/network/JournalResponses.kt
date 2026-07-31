package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SymptomCodeEnvelope(
    val ok: Boolean = false,
    val data: List<SymptomCodeOption> = emptyList(),
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class SymptomCodeOption(
    @SerialName("symptom_code")
    val symptomCode: String = "",
    val label: String = "",
    val description: String? = null,
    @SerialName("is_active")
    val isActive: Boolean = true,
)

@Serializable
data class SymptomEventRequest(
    @SerialName("symptom_code")
    val symptomCode: String,
    @SerialName("ts_utc")
    val timestampUtc: String,
    val severity: Int,
    @SerialName("free_text")
    val note: String? = null,
    val tags: List<String>,
)

@Serializable
data class SymptomEventEnvelope(
    val ok: Boolean = false,
    val data: SymptomEventData? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class SymptomEventData(
    val id: String = "",
    @SerialName("ts_utc")
    val timestampUtc: String = "",
)

@Serializable
data class ExposureCatalogEnvelope(
    val ok: Boolean = false,
    val data: List<ExposureCatalogOption> = emptyList(),
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class ExposureCatalogOption(
    @SerialName("exposure_key")
    val exposureKey: String = "",
    val label: String = "",
)

@Serializable
data class ExposureEventRequest(
    @SerialName("exposure_key")
    val exposureKey: String,
    val intensity: Int,
    @SerialName("event_ts_utc")
    val timestampUtc: String,
    val source: String = "manual",
    @SerialName("note_text")
    val note: String? = null,
)

@Serializable
data class ExposureEventEnvelope(
    val ok: Boolean = false,
    val data: ExposureEventData? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class ExposureEventData(
    val id: String = "",
    @SerialName("exposure_key")
    val exposureKey: String = "",
    val intensity: Int = 1,
    @SerialName("event_ts_utc")
    val timestampUtc: String = "",
)

@Serializable
data class DailyCheckInStatusEnvelope(
    val ok: Boolean = false,
    val data: DailyCheckInStatus? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class DailyCheckInStatus(
    val prompt: DailyCheckInPrompt? = null,
    @SerialName("target_day")
    val targetDay: String? = null,
)

@Serializable
data class DailyCheckInPrompt(
    val id: String = "",
    val day: String = "",
    @SerialName("question_text")
    val questionText: String = "",
)

@Serializable
data class DailyCheckInRequest(
    @SerialName("prompt_id")
    val promptId: String? = null,
    val day: String,
    @SerialName("compared_to_yesterday")
    val comparedToYesterday: String,
    @SerialName("energy_level")
    val energyLevel: String,
    @SerialName("usable_energy")
    val usableEnergy: String,
    @SerialName("system_load")
    val systemLoad: String,
    @SerialName("pain_level")
    val painLevel: String,
    @SerialName("mood_level")
    val moodLevel: String,
    @SerialName("note_text")
    val note: String? = null,
    @SerialName("completed_at")
    val completedAt: String,
)

@Serializable
data class DailyCheckInEntryEnvelope(
    val ok: Boolean = false,
    val data: DailyCheckInEntry? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class DailyCheckInEntry(
    val day: String = "",
)
