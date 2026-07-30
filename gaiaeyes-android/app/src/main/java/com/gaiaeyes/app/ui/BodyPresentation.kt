package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.FeaturesTodayResponse
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

internal data class SleepStageModel(
    val label: String,
    val minutes: Int,
    val progress: Float,
)

internal data class BodyStatModel(
    val label: String,
    val value: String,
    val detail: String,
    val progress: Float,
    val tone: BodyStatTone,
)

internal enum class BodyStatTone {
    LOW,
    MILD,
    ELEVATED,
}

internal fun sleepDurationText(totalMinutes: Int): String {
    if (totalMinutes <= 0) return "—"
    val hours = totalMinutes / 60
    val minutes = totalMinutes % 60
    return "${hours}h ${minutes}m"
}

internal fun sleepEfficiencyPercent(rawEfficiency: Double?): Int? {
    val value = rawEfficiency ?: return null
    val normalized = if (value in 0.0..1.0) value * 100.0 else value
    return normalized.roundToInt().coerceIn(0, 100)
}

internal fun sleepStages(features: FeaturesTodayResponse): List<SleepStageModel> {
    val reference = maxOf(
        features.remMinutes,
        features.coreMinutes,
        features.deepMinutes,
        features.awakeMinutes,
        1,
    ).toFloat()
    return listOf(
        SleepStageModel("REM", features.remMinutes, features.remMinutes / reference),
        SleepStageModel("CORE", features.coreMinutes, features.coreMinutes / reference),
        SleepStageModel("DEEP", features.deepMinutes, features.deepMinutes / reference),
        SleepStageModel("AWAKE", features.awakeMinutes, features.awakeMinutes / reference),
    )
}

internal fun bodyHealthStats(features: FeaturesTodayResponse): List<BodyStatModel> {
    val respiratory = features.respiratoryRateSleepAverage ?: features.respiratoryRateAverage
    val temperatureDelta = features.temperatureDeviationBaselineDelta
        ?: features.temperatureDeviation?.takeUnless {
            features.temperatureSource == "apple_sleeping_wrist_temperature"
        }
    val spo2 = normalizedSpo2(features.spo2Average)

    return listOf(
        BodyStatModel(
            label = "Respiratory",
            value = respiratory?.let { "${oneDecimal(it)} br/min" } ?: "—",
            detail = features.respiratoryRateBaselineDelta?.let {
                baselineDetail(it, "br/min", threshold = 0.2)
            } ?: if (respiratory != null) {
                if (features.respiratoryRateSleepAverage != null) "sleep average" else "daily average"
            } else {
                "waiting for today’s reading"
            },
            progress = deltaProgress(
                features.respiratoryRateBaselineDelta,
                maxAbs = 3.0,
                fallback = respiratory?.div(20.0),
            ),
            tone = BodyStatTone.LOW,
        ),
        BodyStatModel(
            label = "SpO₂",
            value = spo2?.let { "${it.roundToInt()}%" } ?: "—",
            detail = features.spo2BaselineDelta?.let {
                baselineDetail(it, "pp", threshold = 0.2)
            } ?: if (spo2 != null) "daily average" else "waiting for today’s reading",
            progress = deltaProgress(
                features.spo2BaselineDelta,
                maxAbs = 3.0,
                fallback = spo2?.minus(90.0)?.div(10.0),
            ),
            tone = BodyStatTone.MILD,
        ),
        BodyStatModel(
            label = "HRV",
            value = features.hrvAverage?.let { "${it.roundToInt()} ms" } ?: "—",
            detail = features.hrvBaselineDelta?.let {
                baselineDetail(it, "ms", threshold = 1.0)
            } ?: if (features.hrvAverage != null) "daily average" else "waiting for today’s reading",
            progress = deltaProgress(
                features.hrvBaselineDelta,
                maxAbs = 20.0,
                fallback = features.hrvAverage?.div(70.0),
            ),
            tone = BodyStatTone.LOW,
        ),
        BodyStatModel(
            label = "Temp Δ",
            value = temperatureDelta?.let { "${signed(it, decimals = 2)} °F" } ?: "—",
            detail = temperatureDelta?.let {
                directionDetail(it, threshold = 0.35)
            } ?: "waiting for your personal baseline",
            progress = deltaProgress(temperatureDelta, maxAbs = 3.0),
            tone = BodyStatTone.ELEVATED,
        ),
        BodyStatModel(
            label = "Resting HR",
            value = features.restingHeartRateAverage?.let {
                "${it.roundToInt()} bpm"
            } ?: "—",
            detail = features.restingHeartRateBaselineDelta?.let {
                baselineDetail(it, "bpm")
            } ?: if (features.restingHeartRateAverage != null) {
                "daily average"
            } else {
                "waiting for today’s reading"
            },
            progress = deltaProgress(
                features.restingHeartRateBaselineDelta,
                maxAbs = 8.0,
                fallback = features.restingHeartRateAverage?.div(90.0),
            ),
            tone = BodyStatTone.MILD,
        ),
    )
}

internal fun heartRangeText(features: FeaturesTodayResponse): String? {
    val minimum = features.heartRateMin ?: return null
    val maximum = features.heartRateMax ?: return null
    return "${minimum.roundToInt()}-${maximum.roundToInt()} bpm"
}

private fun normalizedSpo2(raw: Double?): Double? {
    val value = raw ?: return null
    val normalized = if (value in 0.0..1.0) value * 100.0 else value
    if (normalized < 60.0) return null
    return normalized.coerceAtMost(100.0)
}

private fun baselineDetail(
    delta: Double,
    unit: String,
    threshold: Double = 0.15,
): String = "${signed(delta)} $unit ${directionDetail(delta, threshold)}"

private fun directionDetail(delta: Double, threshold: Double): String = when {
    delta > threshold -> "above usual"
    delta < -threshold -> "below usual"
    else -> "near usual"
}

private fun deltaProgress(
    delta: Double?,
    maxAbs: Double,
    fallback: Double? = null,
): Float {
    val normalized = delta?.let { abs(it) / maxAbs } ?: fallback ?: 0.14
    return normalized.toFloat().coerceIn(0.08f, 1.0f)
}

private fun signed(value: Double, decimals: Int = 1): String {
    return String.format(Locale.US, "%+.${decimals}f", value)
}

private fun oneDecimal(value: Double): String {
    return String.format(Locale.US, "%.1f", value)
}
