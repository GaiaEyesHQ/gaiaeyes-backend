package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.LocalForecastDay
import com.gaiaeyes.app.core.network.LocalAllergens
import com.gaiaeyes.app.data.HomeContextSource
import com.gaiaeyes.app.data.LocalWeatherSnapshot
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

internal data class LocalWeatherMetric(val label: String, val value: String, val detail: String? = null)
internal data class LocalConditionSection(
    val title: String,
    val metrics: List<LocalWeatherMetric>,
    val detail: String,
)

internal fun localWeatherLocationLabel(snapshot: LocalWeatherSnapshot?): String =
    snapshot?.location?.label.cleanOrNull() ?: snapshot?.location?.zip.cleanOrNull() ?: "Local conditions"

// Retrieval provenance does not assert that all upstream observations are current.
internal fun localWeatherSourceLabel(snapshot: LocalWeatherSnapshot?): String = when (snapshot?.source) {
    HomeContextSource.NETWORK -> "Fetched"
    HomeContextSource.CACHE -> "Saved"
    null -> "Unavailable"
}

internal fun localWeatherMetrics(snapshot: LocalWeatherSnapshot?): List<LocalWeatherMetric> {
    val local = snapshot?.local ?: return emptyList()
    val w = local.weather
    return listOf(
        LocalWeatherMetric("Temperature", w.temperatureC.finite()?.let(::formatTemperatureF) ?: "Unavailable",
            w.temperatureDelta24hC.finite()?.let(::formatTemperatureChangeF)),
        LocalWeatherMetric("Humidity", percent(w.humidityPercent) ?: "Unavailable"),
        LocalWeatherMetric("Pressure", w.pressureHpa.finite()?.takeIf { it > 0 }?.let { "${formatLocalNumber(it)} hPa" } ?: "Unavailable",
            listOfNotNull(w.pressureDelta24hHpa.finite()?.let(::formatPressureChange),
                w.pressureTrend.cleanOrNull() ?: w.barometricTrend.cleanOrNull()).joinToString(" • ").ifBlank { null }),
        LocalWeatherMetric("Rain chance", percent(w.precipitationProbabilityPercent) ?: "Unavailable"),
        LocalWeatherMetric("Air quality", local.air.aqi?.takeIf { it >= 0 }?.let { "$it AQI" } ?: "Unavailable",
            listOfNotNull(local.air.category.cleanOrNull() ?: aqiCategory(local.air.aqi?.toDouble()),
                local.air.pollutant.cleanOrNull()).joinToString(" • ").ifBlank { null }),
    )
}

internal fun localConditionSections(snapshot: LocalWeatherSnapshot?): List<LocalConditionSection> {
    val local = snapshot?.local ?: return emptyList()
    val metrics = localWeatherMetrics(snapshot)
    val observed = localTimestampText(local.weather.observationTime, "Observed") ?: "Observation time unavailable"
    return listOf(
        LocalConditionSection("Weather", listOf(metrics[0], metrics[1], metrics[3]), observed),
        LocalConditionSection("Barometric pressure", listOf(metrics[2]), observed),
        LocalConditionSection("Air quality", listOf(metrics[4]),
            "US AQI • Observation time and source not supplied in this snapshot."),
        localAllergenSection(local.allergens),
    )
}

internal fun localAllergenSection(a: LocalAllergens?, now: Instant = Instant.now()): LocalConditionSection {
    if (!hasPollenReadings(a)) return LocalConditionSection("Allergens", emptyList(),
        "No pollen readings are available for this location in this update. Missing data does not mean a low pollen level.")
    val category = pollenLevel(a?.overallLevel)
    val summary = listOfNotNull(category?.takeIf { validPollenIndex(a?.overallIndex) != null }, a?.overallLabel.cleanOrNull()?.takeUnless { it.equals(category, true) },
        a?.primaryLabel.cleanOrNull()?.let { "Main contributor: $it" }).joinToString(" • ").ifBlank { null }
    val updated = a?.updatedAt.cleanOrNull()?.let { runCatching { OffsetDateTime.parse(it).toInstant() }.getOrNull() }
    val dated = a?.forecastDay.cleanOrNull()?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
    val today = now.atZone(java.time.ZoneOffset.UTC).toLocalDate()
    val old = (updated != null && updated.isBefore(now.minusSeconds(24 * 3600))) || (dated != null && dated.isBefore(today))
    val label = if (old) "Last reported" else if (dated != null && dated.isAfter(today)) "Forecast" else "Overall"
    return LocalConditionSection("Allergens", listOf(
        LocalWeatherMetric(label, pollenValue(a?.overallIndex, a?.overallLevel), summary),
    ) + allergenTypeMetrics(a), listOfNotNull(
        "Pollen index · 0–5; categories can be supplied without a numeric index.",
        a?.source.cleanOrNull()?.let { "Source: $it" } ?: "Source unavailable",
        when {
            updated == null -> "Update time unavailable; freshness unverified"
            updated.isAfter(now) -> "Update time is in the future; freshness unverified"
            else -> localTimestampText(a?.updatedAt, "Updated", now, staleAfterHours = 24)
        },
        dated?.let { "Forecast date: $it (UTC)" },
        if (dated != null && dated != today) "Not today's pollen forecast." else null,
        if (a?.forecastDay != null && dated == null) "Forecast date could not be verified." else null,
        if (a?.source?.contains("forecast", ignoreCase = true) == true) "Forecast, not a direct observation." else null,
    ).joinToString(" • "))
}

private fun allergenTypeMetrics(a: LocalAllergens?) = listOf(
    Triple("Tree", a?.treeIndex, a?.treeLevel), Triple("Grass", a?.grassIndex, a?.grassLevel),
    Triple("Weed", a?.weedIndex, a?.weedLevel), Triple("Mold", a?.moldIndex, a?.moldLevel),
).filter { (name, value, level) -> name != "Mold" || validPollenIndex(value) != null || pollenLevel(level) != null }
    .map { (name, value, level) -> LocalWeatherMetric(name, pollenValue(value, level),
        pollenLevel(level)?.takeUnless { validPollenIndex(value) == null }) }

private fun validPollenIndex(value: Double?): Double? = value.finite()?.takeIf { it in 0.0..5.0 }
private fun pollenLevel(value: String?): String? = value.cleanOrNull()?.lowercase(Locale.US)?.replace(' ', '_')
    ?.takeIf { it in setOf("none", "very_low", "low", "moderate", "high", "very_high") }?.let(::localCategory)
private fun pollenValue(value: Double?, level: String?): String = validPollenIndex(value)
    ?.let { "${formatLocalNumber(it)} / 5" } ?: pollenLevel(level) ?: "Unavailable"
private fun hasPollenReadings(a: LocalAllergens?): Boolean = a != null && (
    listOf(a.overallIndex, a.treeIndex, a.grassIndex, a.weedIndex, a.moldIndex).any { validPollenIndex(it) != null } ||
    listOf(a.overallLevel, a.treeLevel, a.grassLevel, a.weedLevel, a.moldLevel).any { pollenLevel(it) != null })

private fun forecastPollen(day: LocalForecastDay): String? {
    val a = LocalAllergens(overallIndex = day.pollenOverallIndex, overallLevel = day.pollenOverallLevel,
        treeIndex = day.pollenTreeIndex, grassIndex = day.pollenGrassIndex, weedIndex = day.pollenWeedIndex,
        moldIndex = day.pollenMoldIndex, treeLevel = day.pollenTreeLevel, grassLevel = day.pollenGrassLevel,
        weedLevel = day.pollenWeedLevel, moldLevel = day.pollenMoldLevel)
    if (!hasPollenReadings(a)) return null
    val parts = mutableListOf<String>()
    if (validPollenIndex(a.overallIndex) != null || pollenLevel(a.overallLevel) != null)
        parts += pollenValue(a.overallIndex, a.overallLevel)
    allergenTypeMetrics(a).filter { it.value != "Unavailable" }.forEach { parts += "${it.label} ${it.value}" }
    return listOfNotNull("Pollen forecast (${day.day} UTC): ${parts.joinToString(", ")}",
        day.pollenSource.cleanOrNull()?.let { "Source: $it" },
        localTimestampText(day.pollenUpdatedAt, "Pollen updated", staleAfterHours = 24) ?: "Pollen update time unavailable")
        .joinToString(" • ")
}

private fun localCategory(value: String) = value.replace('_', ' ').replaceFirstChar { it.uppercase() }

internal fun localForecastMetrics(snapshot: LocalWeatherSnapshot?): List<LocalWeatherMetric> =
    snapshot?.local?.forecastDaily.orEmpty().mapNotNull { day ->
        val date = runCatching { LocalDate.parse(day.day) }.getOrNull() ?: return@mapNotNull null
        LocalWeatherMetric(date.format(DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)),
            listOfNotNull(day.temperatureHighC.finite()?.let { "High ${formatTemperatureF(it)}" },
                day.temperatureLowC.finite()?.let { "Low ${formatTemperatureF(it)}" }).joinToString(" · ").ifBlank { "Temperature unavailable" },
            listOfNotNull(
                day.shortForecast.cleanOrNull(),
                day.temperatureDeltaFromPriorDayC.finite()?.let {
                    val deltaF = it * 9.0 / 5.0
                    "${if (deltaF > 0) "+" else ""}${formatLocalNumber(deltaF)}°F vs prior day"
                },
                listOfNotNull(
                    percent(day.precipitationProbabilityPercent)?.let { "Rain $it" },
                    percent(day.humidityAverage)?.let { "Humidity $it" },
                    forecastWind("Wind", day.windSpeed, day.source),
                    forecastWind("Gust", day.windGust, day.source),
                    day.aqiForecast.finite()?.takeIf { it >= 0 }?.let { "Forecast AQI ${formatLocalNumber(it)}" },
                ).joinToString(" • ").ifBlank { null },
                forecastPollen(day),
                listOfNotNull(day.source.cleanOrNull()?.let { "Source: $it" },
                    localTimestampText(day.issuedAt, "Issued", staleAfterHours = 24) ?: "Issue time unavailable")
                    .joinToString(" • "),
            ).joinToString("\n"))
    }.take(7)


private fun forecastWind(label: String, value: Double?, source: String?): String? =
    value.finite()?.takeIf { it >= 0 }?.let {
        // Both NWS speed and gust pass through forecast_outlook._parse_wind_value (km/h).
        "$label ${formatLocalNumber(it)} ${if (source?.startsWith("nws:") == true) "km/h" else "(unit unavailable)"}"
    }

internal fun localForecastVisibleCount(available: Int, expanded: Boolean): Int =
    available.coerceIn(0, if (expanded) 7 else 3)

internal fun localWeatherObservedText(snapshot: LocalWeatherSnapshot?): String? =
    localTimestampText(snapshot?.local?.weather?.observationTime, "Observed")

internal fun localTimestampText(
    raw: String?, label: String, now: Instant = Instant.now(), staleAfterHours: Long = 6,
): String? {
    val parsed = raw.cleanOrNull()?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() } ?: return null
    val display = parsed.atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("MMM d, h:mm a", Locale.US))
    val stale = parsed.toInstant().isBefore(now.minusSeconds(staleAfterHours * 3600))
    return "$label $display${if (stale) " · Stale" else ""}"
}

internal fun formatLocalNumber(value: Double): String = if (value == value.toLong().toDouble()) value.toLong().toString()
    else String.format(Locale.US, "%.1f", value)
internal fun formatTemperatureF(celsius: Double): String = "${formatLocalNumber(celsius * 9.0 / 5.0 + 32.0)}°F"
internal fun formatTemperatureChangeF(celsius: Double): String {
    val fahrenheit = celsius * 9.0 / 5.0
    return "${if (fahrenheit > 0) "+" else ""}${String.format(Locale.US, "%.1f", fahrenheit)}°F in 24h"
}
private fun formatPressureChange(value: Double): String =
    "${if (value > 0) "+" else ""}${String.format(Locale.US, "%.1f", value)} hPa in 24h"
private fun percent(value: Double?): String? = value.finite()?.takeIf { it in 0.0..100.0 }?.let { "${it.roundToInt()}%" }
private fun Double?.finite() = this?.takeIf(Double::isFinite)
private fun String?.cleanOrNull(): String? = this?.trim()?.takeIf(String::isNotEmpty)

internal fun localMoonSection(snapshot: LocalWeatherSnapshot?): LocalConditionSection = LocalConditionSection(
    "Moon", listOf(LocalWeatherMetric("Phase", snapshot?.local?.moon?.phase.cleanOrNull() ?: "Unavailable"),
        LocalWeatherMetric("Illumination", snapshot?.local?.moon?.illum.finite()?.takeIf { it in 0.0..1.0 }
            ?.let { "${formatLocalNumber(it * 100)}%" } ?: "Unavailable")),
    "Lunar context supplied with the local snapshot. A separate update time is unavailable.",
)
