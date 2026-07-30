package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.OutlookDay
import com.gaiaeyes.app.core.network.OutlookDomain
import com.gaiaeyes.app.core.network.OutlookDriver
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

fun visibleOutlookDrivers(day: OutlookDay): List<OutlookDriver> {
    return day.topDrivers.filterNot {
        it.key.trim().lowercase() in setOf("radio", "radio_blackout", "radio-blackout")
    }
}

fun outlookDriverLabel(driver: OutlookDriver): String {
    val key = driver.key.trim().lowercase()
    val label = driver.label.trim()
    if (
        key in setOf("flare", "flare_watch", "solar_flare", "solar_flare_watch") ||
        label.lowercase() == "flare watch"
    ) {
        return "Solar Flare Watch"
    }
    return label.ifBlank {
        key.replace('_', ' ').replace('-', ' ').titleCaseWords()
    }.ifBlank { "Forecast signal" }
}

fun outlookDriverValue(driver: OutlookDriver): String {
    val value = driver.value
    val unit = driver.unit.cleanOrNull()
    if (value != null) {
        val formatted = if (value % 1.0 == 0.0) {
            String.format(Locale.US, "%.0f", value)
        } else {
            String.format(Locale.US, "%.1f", value)
        }
        return listOfNotNull(formatted, unit).joinToString(" ")
    }
    return driver.day.cleanOrNull()
        ?: driver.severity.cleanOrNull()?.titleCaseWords()
        ?: "In view"
}

fun outlookDriverProgress(driver: OutlookDriver): Float {
    val value = driver.value
    return when (driver.key.trim().lowercase()) {
        "kp", "geomagnetic" -> ((value ?: 0.0) / 9.0).toFloat()
        "solar_wind", "solar-wind", "wind" ->
            (((value ?: 250.0) - 250.0) / 550.0).toFloat()
        "humidity", "aqi", "precip", "precipitation" ->
            ((value ?: 0.0) / 100.0).toFloat()
        "pollen", "allergen", "allergens" ->
            ((value ?: 0.0) / 5.0).toFloat()
        else -> when (driver.severity?.trim()?.lowercase()) {
            "strong", "high", "elevated", "active" -> 0.82f
            "watch", "moderate", "medium" -> 0.64f
            "mild", "low" -> 0.38f
            else -> 0.28f
        }
    }.coerceIn(0.08f, 1f)
}

fun outlookDayTitle(day: OutlookDay): String {
    return day.label.cleanOrNull()
        ?: formatOutlookDay(day.day, "EEEE")
        ?: "Forecast day"
}

fun outlookDayDate(day: OutlookDay): String {
    return formatOutlookDay(day.day, "MMM d") ?: day.day
}

fun outlookDayState(day: OutlookDay): String {
    return day.primaryState.cleanOrNull()?.titleCaseWords()
        ?: visibleOutlookDrivers(day).firstOrNull()?.severity.cleanOrNull()?.titleCaseWords()
        ?: day.likelyElevatedDomains.firstOrNull()?.likelihood.cleanOrNull()?.titleCaseWords()
        ?: "Quiet"
}

fun outlookDomainLabel(
    domain: OutlookDomain,
    drivers: List<OutlookDriver>,
): String {
    val outcome = domain.topOutcomeLabel.cleanOrNull()
    if (
        domain.key.trim().lowercase() == "energy" &&
        drivers.any { it.key.trim().lowercase() == "humidity" }
    ) {
        return "Energy dip"
    }
    return outcome
        ?: domain.label.cleanOrNull()
        ?: domain.key.replace('_', ' ').titleCaseWords()
}

private fun formatOutlookDay(raw: String, pattern: String): String? {
    return runCatching {
        LocalDate.parse(raw).format(DateTimeFormatter.ofPattern(pattern, Locale.US))
    }.getOrNull()
}

private fun String?.cleanOrNull(): String? = this?.trim()?.takeIf(String::isNotEmpty)

private fun String.titleCaseWords(): String {
    return split(Regex("\\s+"))
        .joinToString(" ") { word ->
            word.replaceFirstChar { char ->
                if (char.isLowerCase()) char.titlecase(Locale.US) else char.toString()
            }
        }
}
