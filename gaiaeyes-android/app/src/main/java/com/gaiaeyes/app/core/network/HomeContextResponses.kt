package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class CurrentSymptomsEnvelope(
    val ok: Boolean = false,
    val data: CurrentSymptomsResponse? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class CurrentSymptomsResponse(
    @SerialName("generated_at")
    val generatedAt: String = "",
    @SerialName("window_hours")
    val windowHours: Int = 12,
    val summary: CurrentSymptomsSummary = CurrentSymptomsSummary(),
    val items: List<CurrentSymptomItem> = emptyList(),
)

@Serializable
data class CurrentSymptomsSummary(
    @SerialName("active_count")
    val activeCount: Int = 0,
    @SerialName("new_count")
    val newCount: Int = 0,
    @SerialName("ongoing_count")
    val ongoingCount: Int = 0,
    @SerialName("improving_count")
    val improvingCount: Int = 0,
    @SerialName("worse_count")
    val worseCount: Int = 0,
    @SerialName("last_updated_at")
    val lastUpdatedAt: String? = null,
)

@Serializable
data class CurrentSymptomItem(
    val id: String = "",
    @SerialName("symptom_code")
    val symptomCode: String = "",
    val label: String = "",
    val severity: Int? = null,
    @SerialName("original_severity")
    val originalSeverity: Int? = null,
    @SerialName("logged_at")
    val loggedAt: String? = null,
    @SerialName("last_interaction_at")
    val lastInteractionAt: String? = null,
    @SerialName("current_state")
    val currentState: String = "",
    @SerialName("note_preview")
    val notePreview: String? = null,
    @SerialName("note_count")
    val noteCount: Int = 0,
    @SerialName("gauge_keys")
    val gaugeKeys: List<String> = emptyList(),
    @SerialName("current_context_badge")
    val currentContextBadge: String? = null,
)

@Serializable
data class CurrentSymptomUpdateRequest(
    val state: String? = null,
    val severity: Int? = null,
    @SerialName("note_text")
    val noteText: String? = null,
    @SerialName("ts_utc")
    val timestampUtc: String? = null,
)

@Serializable
data class CurrentSymptomItemEnvelope(
    val ok: Boolean = false,
    val data: CurrentSymptomItem? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class CurrentSymptomDeleteEnvelope(
    val ok: Boolean = false,
    val data: CurrentSymptomDeleteData? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class CurrentSymptomDeleteData(
    @SerialName("episode_id")
    val episodeId: String = "",
    @SerialName("symptom_code")
    val symptomCode: String = "",
    @SerialName("deleted_at")
    val deletedAt: String = "",
)

@Serializable
data class ProfileLocationEnvelope(
    val ok: Boolean = false,
    val location: ProfileLocation? = null,
    val error: String? = null,
)

@Serializable
data class ProfileLocation(
    val zip: String = "",
    val lat: Double? = null,
    val lon: Double? = null,
    val label: String? = null,
    @SerialName("is_primary")
    val isPrimary: Boolean = true,
    @SerialName("use_gps")
    val useGps: Boolean? = null,
    @SerialName("local_insights_enabled")
    val localInsightsEnabled: Boolean? = null,
    @SerialName("updated_at")
    val updatedAt: String? = null,
)

@Serializable
data class LocalCheckResponse(
    val where: LocalCheckWhere = LocalCheckWhere(),
    val weather: LocalWeather = LocalWeather(),
    val air: LocalAir = LocalAir(),
    val health: LocalHealth = LocalHealth(),
    val asof: String? = null,
)

@Serializable
data class LocalCheckWhere(
    val zip: String = "",
    val lat: Double? = null,
    val lon: Double? = null,
)

@Serializable
data class LocalWeather(
    @SerialName("temp_c")
    val temperatureC: Double? = null,
    @SerialName("temp_delta_24h_c")
    val temperatureDelta24hC: Double? = null,
    @SerialName("humidity_pct")
    val humidityPercent: Double? = null,
    @SerialName("precip_prob_pct")
    val precipitationProbabilityPercent: Double? = null,
    @SerialName("pressure_hpa")
    val pressureHpa: Double? = null,
    @SerialName("obs_time")
    val observationTime: String? = null,
    @SerialName("baro_delta_24h_hpa")
    val pressureDelta24hHpa: Double? = null,
    @SerialName("baro_trend")
    val barometricTrend: String? = null,
    @SerialName("pressure_trend")
    val pressureTrend: String? = null,
)

@Serializable
data class LocalAir(
    val aqi: Int? = null,
    val category: String? = null,
    val pollutant: String? = null,
)

@Serializable
data class LocalHealth(
    val flags: JsonElement? = null,
    val messages: List<String> = emptyList(),
)

@Serializable
data class AllDriversResponse(
    val ok: Boolean = false,
    @SerialName("generated_at")
    val generatedAt: String? = null,
    val asof: String? = null,
    val day: String? = null,
    val summary: DriverPageSummary = DriverPageSummary(),
    val drivers: List<DriverItem> = emptyList(),
)

@Serializable
data class DriverPageSummary(
    @SerialName("active_driver_count")
    val activeDriverCount: Int = 0,
    @SerialName("total_count")
    val totalCount: Int = 0,
    @SerialName("strongest_category")
    val strongestCategory: String? = null,
    @SerialName("primary_state")
    val primaryState: String? = null,
    val note: String? = null,
    @SerialName("has_personal_patterns")
    val hasPersonalPatterns: Boolean = false,
)

@Serializable
data class DriverItem(
    val id: String = "",
    val key: String = "",
    @SerialName("source_key")
    val sourceKey: String? = null,
    val aliases: List<String> = emptyList(),
    val label: String = "",
    val category: String = "",
    @SerialName("category_label")
    val categoryLabel: String? = null,
    val role: String = "",
    @SerialName("role_label")
    val roleLabel: String? = null,
    val state: String = "",
    @SerialName("state_label")
    val stateLabel: String? = null,
    val severity: String? = null,
    val reading: String? = null,
    @SerialName("short_reason")
    val shortReason: String = "",
    @SerialName("personal_reason")
    val personalReason: String? = null,
    @SerialName("current_symptoms")
    val currentSymptoms: List<String> = emptyList(),
    @SerialName("pattern_status")
    val patternStatus: String? = null,
    @SerialName("pattern_status_label")
    val patternStatusLabel: String? = null,
    @SerialName("pattern_summary")
    val patternSummary: String? = null,
    @SerialName("outlook_summary")
    val outlookSummary: String? = null,
    @SerialName("active_now_text")
    val activeNowText: String? = null,
    @SerialName("signal_strength")
    val signalStrength: Double? = null,
    @SerialName("display_score")
    val displayScore: Double? = null,
    @SerialName("is_objectively_active")
    val isObjectivelyActive: Boolean? = null,
)
