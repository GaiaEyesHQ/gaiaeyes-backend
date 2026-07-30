package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class OutlookResponse(
    val ok: Boolean = false,
    @SerialName("generated_at")
    val generatedAt: String? = null,
    @SerialName("available_windows")
    val availableWindows: List<String> = emptyList(),
    @SerialName("daily_outlook")
    val dailyOutlook: List<OutlookDay> = emptyList(),
    @SerialName("forecast_data_ready")
    val forecastDataReady: OutlookDataReadiness? = null,
    @SerialName("next_24h")
    val next24h: OutlookWindow? = null,
    @SerialName("next_72h")
    val next72h: OutlookWindow? = null,
    @SerialName("next_7d")
    val next7d: OutlookWindow? = null,
    @SerialName("voice_semantics")
    val voiceSemantics: OutlookVoiceSemantics? = null,
)

@Serializable
data class OutlookDay(
    val day: String = "",
    val label: String = "",
    @SerialName("likely_elevated_domains")
    val likelyElevatedDomains: List<OutlookDomain> = emptyList(),
    @SerialName("top_drivers")
    val topDrivers: List<OutlookDriver> = emptyList(),
    val summary: String? = null,
    @SerialName("support_line")
    val supportLine: String? = null,
    @SerialName("primary_state")
    val primaryState: String? = null,
    @SerialName("voice_semantic")
    val voiceSemantic: OutlookWindowSemantic? = null,
)

@Serializable
data class OutlookWindow(
    @SerialName("window_hours")
    val windowHours: Int = 0,
    @SerialName("likely_elevated_domains")
    val likelyElevatedDomains: List<OutlookDomain> = emptyList(),
    @SerialName("top_drivers")
    val topDrivers: List<OutlookDriver> = emptyList(),
    val summary: String? = null,
    @SerialName("support_line")
    val supportLine: String? = null,
    @SerialName("voice_semantic")
    val voiceSemantic: OutlookWindowSemantic? = null,
)

@Serializable
data class OutlookDomain(
    val key: String = "",
    val label: String = "",
    val likelihood: String = "",
    @SerialName("current_gauge")
    val currentGauge: Double? = null,
    val explanation: String? = null,
    @SerialName("top_driver_key")
    val topDriverKey: String? = null,
    @SerialName("top_driver_label")
    val topDriverLabel: String? = null,
    @SerialName("top_outcome_key")
    val topOutcomeKey: String? = null,
    @SerialName("top_outcome_label")
    val topOutcomeLabel: String? = null,
)

@Serializable
data class OutlookDriver(
    val key: String = "",
    val label: String = "",
    val severity: String? = null,
    val value: Double? = null,
    val unit: String? = null,
    val day: String? = null,
    val detail: String? = null,
    @SerialName("signal_key")
    val signalKey: String? = null,
)

@Serializable
data class OutlookDataReadiness(
    @SerialName("location_found")
    val locationFound: Boolean = false,
    @SerialName("local_forecast_daily")
    val localForecastDaily: Boolean = false,
    @SerialName("local_forecast_days")
    val localForecastDays: Int = 0,
    @SerialName("space_forecast_daily")
    val spaceForecastDaily: Boolean = false,
    @SerialName("space_forecast_days")
    val spaceForecastDays: Int = 0,
    @SerialName("next_24h")
    val next24h: Boolean = false,
    @SerialName("next_72h")
    val next72h: Boolean = false,
    @SerialName("next_7d")
    val next7d: Boolean = false,
)

@Serializable
data class OutlookVoiceSemantics(
    val overview: OutlookOverviewSemantic? = null,
)

@Serializable
data class OutlookOverviewSemantic(
    val interpretation: OutlookOverviewInterpretation? = null,
)

@Serializable
data class OutlookOverviewInterpretation(
    @SerialName("header_summary")
    val headerSummary: String? = null,
    @SerialName("availability_summary")
    val availabilitySummary: String? = null,
    @SerialName("empty_state")
    val emptyState: String? = null,
    @SerialName("seven_day_pending")
    val sevenDayPending: String? = null,
)

@Serializable
data class OutlookWindowSemantic(
    val interpretation: OutlookWindowInterpretation? = null,
)

@Serializable
data class OutlookWindowInterpretation(
    @SerialName("header_summary")
    val headerSummary: String? = null,
    @SerialName("leading_signal_summary")
    val leadingSignalSummary: String? = null,
    @SerialName("domains_summary")
    val domainsSummary: String? = null,
    @SerialName("support_summary")
    val supportSummary: String? = null,
    @SerialName("empty_state")
    val emptyState: String? = null,
)
