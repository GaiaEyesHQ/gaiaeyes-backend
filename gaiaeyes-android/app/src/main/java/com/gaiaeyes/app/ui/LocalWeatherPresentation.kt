package com.gaiaeyes.app.ui

import com.gaiaeyes.app.data.HomeContextSource
import com.gaiaeyes.app.data.LocalWeatherSnapshot
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

internal data class LocalWeatherMetric(
    val label: String,
    val value: String,
    val detail: String? = null,
)

internal fun localWeatherLocationLabel(snapshot: LocalWeatherSnapshot?): String {
    val location = snapshot?.location ?: return "Local conditions"
    return location.label
        ?.trim()
        ?.takeIf(String::isNotEmpty)
        ?: location.zip.trim().takeIf(String::isNotEmpty)
        ?: "Local conditions"
}

internal fun localWeatherSourceLabel(snapshot: LocalWeatherSnapshot?): String {
    return when (snapshot?.source) {
        HomeContextSource.NETWORK -> "Live"
        HomeContextSource.CACHE -> "Saved"
        null -> "Not connected"
    }
}

internal fun localWeatherMetrics(snapshot: LocalWeatherSnapshot?): List<LocalWeatherMetric> {
    val local = snapshot?.local ?: return emptyList()
    val weather = local.weather
    return listOfNotNull(
        weather.temperatureC?.let { temperature ->
            LocalWeatherMetric(
                label = "Temperature",
                value = formatTemperatureF(temperature),
                detail = weather.temperatureDelta24hC?.let(::formatTemperatureChangeF),
            )
        },
        weather.humidityPercent?.let { humidity ->
            LocalWeatherMetric(
                label = "Humidity",
                value = "${humidity.roundToInt()}%",
            )
        },
        weather.pressureHpa?.let { pressure ->
            LocalWeatherMetric(
                label = "Pressure",
                value = "${pressure.roundToInt()} hPa",
                detail = listOfNotNull(
                    weather.pressureDelta24hHpa?.let(::formatPressureChange),
                    weather.pressureTrend.cleanOrNull()
                        ?: weather.barometricTrend.cleanOrNull(),
                ).joinToString(" • ").takeIf(String::isNotEmpty),
            )
        },
        weather.precipitationProbabilityPercent?.let { probability ->
            LocalWeatherMetric(
                label = "Rain chance",
                value = "${probability.roundToInt()}%",
            )
        },
        local.air.aqi?.let { aqi ->
            LocalWeatherMetric(
                label = "Air quality",
                value = "$aqi AQI",
                detail = listOfNotNull(
                    local.air.category.cleanOrNull(),
                    local.air.pollutant.cleanOrNull(),
                ).joinToString(" • ").takeIf(String::isNotEmpty),
            )
        },
    )
}

internal fun localWeatherObservedText(snapshot: LocalWeatherSnapshot?): String? {
    val raw = snapshot?.local?.weather?.observationTime.cleanOrNull()
        ?: snapshot?.local?.asof.cleanOrNull()
        ?: return null
    return runCatching {
        val parsed = OffsetDateTime.parse(raw).atZoneSameInstant(ZoneId.systemDefault())
        "Observed ${parsed.format(DateTimeFormatter.ofPattern("MMM d, h:mm a", Locale.US))}"
    }.getOrElse { "Observed $raw" }
}

internal fun formatTemperatureF(celsius: Double): String {
    return "${((celsius * 9.0 / 5.0) + 32.0).roundToInt()}°F"
}

internal fun formatTemperatureChangeF(celsius: Double): String {
    val fahrenheit = celsius * 9.0 / 5.0
    val prefix = if (fahrenheit > 0.0) "+" else ""
    return "$prefix${String.format(Locale.US, "%.1f", fahrenheit)}°F in 24h"
}

private fun formatPressureChange(value: Double): String {
    val prefix = if (value > 0.0) "+" else ""
    return "$prefix${String.format(Locale.US, "%.1f", value)} hPa in 24h"
}

private fun String?.cleanOrNull(): String? = this?.trim()?.takeIf(String::isNotEmpty)
