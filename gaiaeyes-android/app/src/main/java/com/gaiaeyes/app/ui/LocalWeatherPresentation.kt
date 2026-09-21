package com.gaiaeyes.app.ui

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
    val a = local.allergens
    val allergenCategory = a?.overallLevel.cleanOrNull()?.let(::localCategory)
    val allergenSummary = listOfNotNull(
        allergenCategory,
        a?.overallLabel.cleanOrNull()?.takeUnless { it.equals(allergenCategory, true) },
        a?.primaryLabel.cleanOrNull()?.let { "Main contributor: $it" },
    ).joinToString(" • ").ifBlank { null }
    return listOf(
        LocalConditionSection("Weather", listOf(metrics[0], metrics[1], metrics[3]), observed),
        LocalConditionSection("Barometric pressure", listOf(metrics[2]), observed),
        LocalConditionSection("Air quality", listOf(metrics[4]),
            "US AQI • Observation time and source not supplied in this snapshot."),
        LocalConditionSection("Allergens", listOf(
            LocalWeatherMetric("Overall", pollenIndex(a?.overallIndex), allergenSummary),
        ) + allergenTypeMetrics(a), listOfNotNull(
            "Pollen index · 0–5",
            a?.source.cleanOrNull()?.let { "Source: $it" } ?: "Source unavailable",
            localTimestampText(a?.updatedAt, "Updated", staleAfterHours = 24) ?: "Update time unavailable",
            if (a?.source?.contains("forecast", ignoreCase = true) == true) "Forecast, not a direct observation." else null,
        ).joinToString(" • ")),
    )
}

private fun allergenTypeMetrics(a: LocalAllergens?) = listOf(
    Triple("Tree", a?.treeIndex, a?.treeLevel), Triple("Grass", a?.grassIndex, a?.grassLevel),
    Triple("Weed", a?.weedIndex, a?.weedLevel), Triple("Mold", a?.moldIndex, a?.moldLevel),
).map { (name, value, level) -> LocalWeatherMetric(name, pollenIndex(value), level.cleanOrNull()?.let(::localCategory)) }

private fun pollenIndex(value: Double?): String = value.finite()?.takeIf { it in 0.0..5.0 }
    ?.let { "${formatLocalNumber(it)} / 5" } ?: "Unavailable"
private fun localCategory(value: String) = value.replace('_', ' ').replaceFirstChar { it.uppercase() }

internal fun localForecastMetrics(snapshot: LocalWeatherSnapshot?): List<LocalWeatherMetric> =
    snapshot?.local?.forecastDaily.orEmpty().mapNotNull { day ->
        val date = runCatching { LocalDate.parse(day.day) }.getOrNull() ?: return@mapNotNull null
        LocalWeatherMetric(date.format(DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)),
            listOfNotNull(day.temperatureHighC.finite()?.let { "High ${formatTemperatureF(it)}" },
                day.temperatureLowC.finite()?.let { "Low ${formatTemperatureF(it)}" }).joinToString(" · ").ifBlank { "Temperature unavailable" },
            listOfNotNull(day.shortForecast.cleanOrNull(), percent(day.precipitationProbabilityPercent)?.let { "Rain $it" },
                percent(day.humidityAverage)?.let { "Humidity $it" },
                day.windSpeed.finite()?.takeIf { it >= 0 }?.let {
                    // forecast_outlook._parse_wind_value converts NWS mph/knots to km/h.
                    "Wind ${formatLocalNumber(it)} ${if (day.source?.startsWith("nws:") == true) "km/h" else "(unit unavailable)"}"
                },
                day.source.cleanOrNull()?.let { "Source: $it" },
                localTimestampText(day.issuedAt, "Issued", staleAfterHours = 24) ?: "Issue time unavailable").joinToString(" • "))
    }.take(7)

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
