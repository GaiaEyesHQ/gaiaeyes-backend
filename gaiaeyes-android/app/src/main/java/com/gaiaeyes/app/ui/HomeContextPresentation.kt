package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.DriverItem

internal data class PossibleSymptom(
    val label: String,
    val isMatched: Boolean,
)

internal fun derivePossibleSymptoms(
    dashboard: DashboardGaugesResponse?,
    drivers: AllDriversResponse?,
    activeLabels: List<String>,
    limit: Int = 6,
): List<PossibleSymptom> {
    val candidates = buildList {
        relevantDrivers(drivers).forEach { driver ->
            addAll(possibleSymptomsForDriver(driver))
        }
        dashboard?.gauges.orEmpty().forEach { (key, _) ->
            val meta = dashboard?.gaugesMeta?.get(key)
            if (showsSymptomAffordance(meta?.zone, meta?.label)) {
                addAll(possibleSymptomsForGauge(key))
            }
        }
    }

    val activeKeys = activeLabels
        .map(::normalizedSymptomKey)
        .filter(String::isNotEmpty)
        .toSet()
    val seen = mutableSetOf<String>()
    val matched = mutableListOf<PossibleSymptom>()
    val unmatched = mutableListOf<PossibleSymptom>()

    candidates.forEach { raw ->
        val label = canonicalSymptomLabel(raw)
        val key = normalizedSymptomKey(label)
        if (label.isEmpty() || !seen.add(key)) return@forEach
        val symptom = PossibleSymptom(
            label = label,
            isMatched = key in activeKeys,
        )
        if (symptom.isMatched) matched += symptom else unmatched += symptom
    }

    return (matched + unmatched).take(limit.coerceAtLeast(0))
}

internal fun relevantDrivers(response: AllDriversResponse?): List<DriverItem> {
    val drivers = response?.drivers.orEmpty()
    val relevant = drivers.filter { driver ->
        driver.isObjectivelyActive == true ||
            driver.role.equals("leading", ignoreCase = true) ||
            driver.role.equals("supporting", ignoreCase = true)
    }
    return (relevant.ifEmpty { drivers }).take(5)
}

internal data class DriverRoleCounts(
    val leading: Int,
    val supporting: Int,
)

internal fun exploreDrivers(response: AllDriversResponse?): List<DriverItem> {
    return response?.drivers.orEmpty()
}

internal fun driverRoleCounts(response: AllDriversResponse?): DriverRoleCounts {
    val drivers = exploreDrivers(response)
    return DriverRoleCounts(
        leading = drivers.count { it.role.equals("leading", ignoreCase = true) },
        supporting = drivers.count { it.role.equals("supporting", ignoreCase = true) },
    )
}

internal fun driverDisplayReason(driver: DriverItem): String {
    return driver.personalReason
        ?.trim()
        ?.takeIf(String::isNotEmpty)
        ?: driver.shortReason.trim().takeIf(String::isNotEmpty)
        ?: driver.activeNowText?.trim().orEmpty()
}

internal fun driverSignalProgress(driver: DriverItem): Float {
    val score = driver.displayScore ?: driver.signalStrength
    if (score != null) return score.toFloat().coerceIn(0.08f, 1f)

    return when (
        driver.severity?.trim()?.lowercase()
            ?: driver.state.trim().lowercase()
    ) {
        "strong", "high", "elevated", "active" -> 0.82f
        "watch", "moderate", "medium" -> 0.64f
        "mild", "low" -> 0.38f
        else -> 0.22f
    }
}

private fun possibleSymptomsForDriver(driver: DriverItem): List<String> {
    val keys = buildList {
        add(driver.key)
        driver.sourceKey?.let { add(it) }
        addAll(driver.aliases)
    }.map(::normalizedDriverKey)

    return when {
        keys.any { it in setOf("allergens", "aqi") } ->
            listOf("Head / sinus pressure", "Migraine", "Headache", "Irritation")
        "humidity" in keys ->
            listOf("Sinus pressure", "Headache", "Migraine", "Fatigue")
        "pressure" in keys ->
            listOf("Migraine", "Headache", "Energy dip", "Body aches")
        "temp" in keys ->
            listOf("Energy dip", "Poor sleep")
        keys.any { it in setOf("schumann", "ulf") } ->
            listOf("Focus shifts", "Restlessness")
        keys.any { it in setOf("kp", "bz", "solar_wind", "cme") } ->
            listOf("Focus shifts", "Body tension")
        keys.any { it in setOf("sleep", "less_sleep", "sleep_debt") } ->
            listOf("Poor sleep", "Fatigue")
        else -> emptyList()
    }
}

private fun possibleSymptomsForGauge(rawKey: String): List<String> {
    return when (normalizedDriverKey(rawKey)) {
        "pain" -> listOf("Pain flare", "Migraine", "Headache")
        "focus" -> listOf("Brain fog", "Focus shifts")
        "energy", "stamina" -> listOf("Fatigue", "Energy dip")
        "sleep" -> listOf("Poor sleep", "Fatigue")
        "mood" -> listOf("Irritation")
        "heart", "health_status" -> listOf("HRV dips", "Body strain")
        else -> emptyList()
    }
}

private fun showsSymptomAffordance(zone: String?, label: String?): Boolean {
    val normalizedZone = zone.orEmpty().trim().lowercase()
    if (normalizedZone == "elevated" || normalizedZone == "high") return true
    val normalizedLabel = label.orEmpty().trim().lowercase()
    return normalizedLabel.contains("elevated") ||
        normalizedLabel.contains("high") ||
        normalizedLabel.contains("watch")
}

private fun normalizedDriverKey(raw: String): String {
    return raw.trim().lowercase().replace("-", "_")
}

private fun normalizedSymptomKey(raw: String): String {
    return when (raw.trim().lowercase()) {
        "tired" -> "low energy"
        "poor sleep", "restless sleep" -> "restless sleep"
        else -> raw.trim().lowercase()
    }
}

private fun canonicalSymptomLabel(raw: String): String {
    return when (normalizedSymptomKey(raw)) {
        "low energy" -> "Low energy"
        "restless sleep" -> "Restless sleep"
        else -> raw.trim()
    }
}
