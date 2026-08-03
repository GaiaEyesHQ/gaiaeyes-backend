package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.DriverItem
import kotlin.math.roundToInt

internal data class GaugeDetailModel(
    val key: String,
    val title: String,
    val status: String,
    val score: Int?,
    val delta: Int?,
    val symptoms: List<String>,
    val influencers: List<String>,
    val helpfulTips: List<String>,
)

internal fun gaugeDetailModel(
    key: String,
    fallbackLabel: String,
    dashboard: DashboardGaugesResponse?,
    currentSymptoms: CurrentSymptomsResponse?,
    drivers: AllDriversResponse?,
): GaugeDetailModel {
    val normalizedGauge = normalizedGaugeKey(key)
    val symptoms = currentSymptoms?.items.orEmpty()
        .asSequence()
        .filter { item ->
            normalizedGauge == "health_status" ||
                item.gaugeKeys.any { normalizedGaugeKey(it) == normalizedGauge }
        }
        .filter { it.label.isNotBlank() }
        .sortedByDescending { it.severity ?: 0 }
        .distinctBy { it.label.trim().lowercase() }
        .take(3)
        .map { it.label.trim() }
        .toList()

    return GaugeDetailModel(
        key = normalizedGauge,
        title = dashboard?.gaugeLabels?.get(key)?.trim().takeUnless { it.isNullOrEmpty() }
            ?: fallbackLabel,
        status = dashboard?.gaugesMeta?.get(key)?.label?.trim().takeUnless { it.isNullOrEmpty() }
            ?: if (dashboard?.gauges?.get(key) == null) "Waiting for today’s data" else "Current",
        score = dashboard?.gauges?.get(key)?.roundToInt(),
        delta = dashboard?.gaugesDelta?.get(key),
        symptoms = symptoms,
        influencers = gaugeInfluencers(normalizedGauge, drivers),
        helpfulTips = helpfulTipsForGauge(normalizedGauge),
    )
}

internal const val gaugeScoreExplanation =
    "This score brings together your recent body signals, symptoms, and relevant conditions. " +
        "Higher scores mean more estimated load. It is context, not a diagnosis."

internal const val gaugeDeltaExplanation =
    "This compares today’s gauge score with yesterday. Higher scores mean more estimated load; " +
        "lower scores mean less."

private fun gaugeInfluencers(
    gaugeKey: String,
    response: AllDriversResponse?,
): List<String> {
    val active = response?.drivers.orEmpty()
        .filter(::isActiveGaugeDriver)
        .distinctBy { driverCanonicalKey(it) }

    val priorities = gaugeDriverPriorities[gaugeKey].orEmpty()
    val prioritized = priorities.mapNotNull { preferred ->
        active.firstOrNull { preferred in driverKeys(it) }
    }
    val remaining = active
        .filterNot { it in prioritized }
        .sortedByDescending { it.displayScore ?: it.signalStrength ?: 0.0 }

    return (prioritized + remaining)
        .distinctBy { driverCanonicalKey(it) }
        .take(4)
        .map(::driverInfluencerText)
}

private fun isActiveGaugeDriver(driver: DriverItem): Boolean {
    if (driver.isObjectivelyActive == true) return true
    if (driver.role.equals("leading", ignoreCase = true) ||
        driver.role.equals("supporting", ignoreCase = true)
    ) return true

    val activeTokens = setOf(
        "active", "elevated", "high", "strong", "watch", "mild", "moderate", "storm",
    )
    return driver.state.trim().lowercase() in activeTokens ||
        driver.severity?.trim()?.lowercase() in activeTokens
}

private fun driverInfluencerText(driver: DriverItem): String {
    val key = driverCanonicalKey(driver)
    if (key == "allergen_exposure") return "Recent allergen exposure may be contributing"
    if (key == "overexertion") return "Recent heavy activity may be contributing"

    val label = friendlyDriverLabel(key, driver.label)
    val state = driver.stateLabel?.trim().takeUnless { it.isNullOrEmpty() }
        ?: driver.severity?.trim().takeUnless { it.isNullOrEmpty() }
        ?: driver.state.trim().takeIf(String::isNotEmpty)
    return if (state == null || state.equals("unknown", ignoreCase = true)) {
        label
    } else {
        "$label is ${state.replaceFirstChar(Char::lowercase)}"
    }
}

private fun friendlyDriverLabel(key: String, fallback: String): String = when (key) {
    "aqi" -> "AQI"
    "pressure" -> "Pressure change"
    "temp" -> "Temperature swing"
    "humidity" -> "Humidity"
    "schumann" -> "Earth resonance"
    "ulf" -> "ULF activity"
    "kp" -> "Geomagnetic conditions"
    "bz" -> "Bz coupling"
    "sw" -> "Solar wind"
    "allergens" -> "Allergens"
    else -> fallback.trim().ifEmpty { key.replace('_', ' ') }
}

private fun driverKeys(driver: DriverItem): Set<String> = buildSet {
    add(canonicalDriverKey(driver.key))
    driver.sourceKey?.let { add(canonicalDriverKey(it)) }
    driver.aliases.forEach { add(canonicalDriverKey(it)) }
}

private fun driverCanonicalKey(driver: DriverItem): String =
    driverKeys(driver).firstOrNull().orEmpty()

private fun canonicalDriverKey(raw: String): String = when (
    raw.trim().lowercase().replace('-', '_')
) {
    "temperature" -> "temp"
    "resonance", "earth_resonance" -> "schumann"
    "solar_wind", "solarwind" -> "sw"
    "geomagnetic", "geomagnetic_activity" -> "kp"
    "air_quality" -> "aqi"
    else -> raw.trim().lowercase().replace('-', '_')
}

private fun normalizedGaugeKey(raw: String): String = when (
    raw.trim().lowercase().replace('-', '_')
) {
    "recovery_load", "recovery", "stamina" -> "stamina"
    "health", "health_status" -> "health_status"
    else -> raw.trim().lowercase().replace('-', '_')
}

private val gaugeDriverPriorities = mapOf(
    "pain" to listOf("allergen_exposure", "overexertion", "allergens", "pressure", "temp", "aqi"),
    "focus" to listOf("allergen_exposure", "allergens", "pressure", "aqi", "ulf", "schumann"),
    "heart" to listOf("overexertion", "allergen_exposure", "kp", "bz", "sw", "pressure", "schumann", "ulf"),
    "stamina" to listOf("overexertion", "temp", "pressure", "aqi", "schumann", "ulf"),
    "energy" to listOf("overexertion", "allergen_exposure", "temp", "aqi", "allergens", "schumann", "ulf"),
    "sleep" to listOf("overexertion", "allergen_exposure", "pressure", "temp", "schumann"),
    "mood" to listOf("pressure", "schumann", "aqi"),
)

private fun helpfulTipsForGauge(key: String): List<String> = when (key) {
    "pain" -> listOf(
        "Keep effort steadier today.",
        "Shorter exposure windows may help.",
        "Keep hydration and meals steady.",
    )
    "focus" -> listOf(
        "Use shorter work blocks.",
        "Reduce stimulation where you can.",
        "Take quick resets between tasks.",
    )
    "heart" -> listOf(
        "Keep effort smooth and steady.",
        "Keep hydration steady.",
        "Reduce stimulation if your system feels reactive.",
    )
    "stamina" -> listOf(
        "Favor steadier effort over spikes.",
        "Choose lower-friction routines where you can.",
        "Protect recovery time tonight.",
    )
    "energy" -> listOf(
        "Pace earlier to avoid a later crash.",
        "Keep meals and hydration steady.",
        "Save optional tasks for later if needed.",
    )
    "sleep" -> listOf(
        "Protect your wind-down tonight.",
        "Keep tonight as predictable as you can.",
        "Lower stimulation before bed.",
    )
    "mood" -> listOf(
        "Keep the day steadier where you can.",
        "Lower stimulation if you feel reactive.",
        "Add short resets between demands.",
    )
    else -> listOf(
        "Keep the day a little lighter if needed.",
        "Favor steady effort over pushing.",
        "Protect your wind-down tonight.",
    )
}
