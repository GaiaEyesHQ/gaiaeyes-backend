package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class FeaturesTodayEnvelope(
    val ok: Boolean = false,
    val data: FeaturesTodayResponse? = null,
    val error: String? = null,
    @SerialName("friendly_error")
    val friendlyError: String? = null,
)

@Serializable
data class FeaturesTodayResponse(
    val day: String = "",
    @SerialName("updated_at")
    val updatedAt: String? = null,
    val source: String? = null,
    @SerialName("sleep_total_minutes")
    val sleepTotalMinutes: Int = 0,
    @SerialName("rem_m")
    val remMinutes: Int = 0,
    @SerialName("core_m")
    val coreMinutes: Int = 0,
    @SerialName("deep_m")
    val deepMinutes: Int = 0,
    @SerialName("awake_m")
    val awakeMinutes: Int = 0,
    @SerialName("inbed_m")
    val inBedMinutes: Int = 0,
    @SerialName("sleep_efficiency")
    val sleepEfficiency: Double? = null,
    @SerialName("steps_total")
    val stepsTotal: Int = 0,
    @SerialName("hr_min")
    val heartRateMin: Double? = null,
    @SerialName("hr_max")
    val heartRateMax: Double? = null,
    @SerialName("hrv_avg")
    val hrvAverage: Double? = null,
    @SerialName("hrv_baseline_delta")
    val hrvBaselineDelta: Double? = null,
    @SerialName("spo2_avg")
    val spo2Average: Double? = null,
    @SerialName("spo2_baseline_delta")
    val spo2BaselineDelta: Double? = null,
    @SerialName("respiratory_rate_avg")
    val respiratoryRateAverage: Double? = null,
    @SerialName("respiratory_rate_sleep_avg")
    val respiratoryRateSleepAverage: Double? = null,
    @SerialName("respiratory_rate_baseline_delta")
    val respiratoryRateBaselineDelta: Double? = null,
    @SerialName("temperature_deviation")
    val temperatureDeviation: Double? = null,
    @SerialName("temperature_deviation_baseline_delta")
    val temperatureDeviationBaselineDelta: Double? = null,
    @SerialName("temperature_source")
    val temperatureSource: String? = null,
    @SerialName("resting_hr_avg")
    val restingHeartRateAverage: Double? = null,
    @SerialName("resting_hr_baseline_delta")
    val restingHeartRateBaselineDelta: Double? = null,
)
