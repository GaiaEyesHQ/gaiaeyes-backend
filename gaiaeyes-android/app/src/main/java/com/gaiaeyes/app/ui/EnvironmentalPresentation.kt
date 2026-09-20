package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.ExploreSnapshot
import com.gaiaeyes.app.data.ExploreSource
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.serialization.json.*

internal data class EnvironmentalReading(
    val title: String,
    val source: String,
    val timestamp: String?,
    val status: String,
    val metrics: List<Pair<String, String>>,
    val note: String? = null,
)
internal data class EnvironmentalChart(
    val title: String,
    val unit: String,
    val source: String,
    val points: List<EnvironmentPoint>,
    val status: String,
    val maxGapMinutes: Long,
)
internal data class EnvironmentalPanel(
    val title: String,
    val explanation: String,
    val readings: List<EnvironmentalReading>,
    val charts: List<EnvironmentalChart>,
) {
    val hasReadings get() = readings.any { it.metrics.isNotEmpty() }
}
internal fun environmentalInstant(raw: String?): Instant? = raw?.let {
    runCatching { Instant.parse(it) }.getOrNull()
        ?: runCatching { OffsetDateTime.parse(it).toInstant() }.getOrNull()
}
internal fun environmentalTime(raw: String?): String = environmentalInstant(raw)?.let {
    DateTimeFormatter.ofPattern("MMM d, yyyy · HH:mm z", Locale.getDefault()).withZone(ZoneId.systemDefault()).format(it)
} ?: "Observation time unavailable"

internal fun environmentalStatus(
    hasValue: Boolean, timestamp: String?, maxAgeMinutes: Long, saved: Boolean,
    failure: String?, now: Instant,
): String {
    if (!hasValue) return when (failure) {
        "sign_in_required" -> "Sign-in required"
        null -> "No readings"
        else -> "Could not refresh"
    }
    val observed = environmentalInstant(timestamp)
    val state = when {
        observed == null -> "Time unknown"
        observed.isAfter(now.plusSeconds(300)) -> "Time unverified"
        observed.isBefore(now.minusSeconds(maxAgeMinutes * 60)) -> "Stale"
        else -> "Current"
    }
    return if (saved || failure != null) "Saved · $state" else state
}
internal fun environmentalNumber(value: Double?, unit: String = "", digits: Int = 2): String? =
    value?.takeIf { it.isFinite() }?.let { String.format(Locale.US, "%.${digits}f", it) + if (unit.isBlank()) "" else " $unit" }

internal fun environmentalPoints(points: List<EnvironmentPoint>): List<EnvironmentPoint> = points
    .filter { environmentalInstant(it.t) != null && it.v?.isFinite() == true }
    .distinctBy { environmentalInstant(it.t) }
    .sortedBy { environmentalInstant(it.t) }

internal fun spaceHistoryPoints(payload: ExplorePayload, key: String): List<EnvironmentPoint> = environmentalPoints(
    payload.spaceHistory?.data?.series24?.get(key).orEmpty().mapNotNull { tuple ->
        if (tuple.size != 2) null else EnvironmentPoint(
            (tuple[0] as? JsonPrimitive)?.contentOrNull,
            (tuple[1] as? JsonPrimitive)?.doubleOrNull,
        )
    },
)

internal fun environmentalPanel(detail: ExploreDetail, snapshot: ExploreSnapshot?, now: Instant = Instant.now()): EnvironmentalPanel {
    val p = snapshot?.payload ?: ExplorePayload()
    val readings = mutableListOf<EnvironmentalReading>()
    val charts = mutableListOf<EnvironmentalChart>()
    fun failed(key: String) = p.sourceErrors[key] ?: if (key in snapshot?.unavailableSources.orEmpty()) "request_failed" else null
    fun status(key: String, has: Boolean, time: String?, age: Long) = environmentalStatus(
        has, time, age, snapshot?.source == ExploreSource.CACHE, failed(key), now,
    )
    fun reading(title: String, source: String, key: String, time: String?, age: Long,
                metrics: List<Pair<String, String>>, note: String? = null) {
        readings += EnvironmentalReading(title, source, time, status(key, metrics.isNotEmpty(), time, age), metrics,
            listOfNotNull(note, failed(key)?.let {
                if (it == "sign_in_required") "Sign in again to refresh this source. Other environmental sources remain available."
                else "Refresh failed. Any readings shown retain their original observation time."
            }).joinToString(" ").ifBlank { null })
    }
    fun chart(title: String, unit: String, source: String, key: String, raw: List<EnvironmentPoint>, age: Long, gap: Long) {
        val points = environmentalPoints(raw)
        charts += EnvironmentalChart(title, unit, source, points, status(key, points.isNotEmpty(), points.lastOrNull()?.t, age), gap)
    }
    fun metric(label: String, value: Double?, unit: String = "", digits: Int = 2) =
        environmentalNumber(value, unit, digits)?.let { label to it }
    when (detail) {
        ExploreDetail.SCHUMANN -> {
            val s = p.schumann
            reading("Cumiana resonance", s?.quality?.primarySource ?: "Cumiana", "Schumann Resonance", s?.generatedAt, 60,
                listOfNotNull(metric("Fundamental", s?.harmonics?.f0 ?: s?.harmonics?.combinedF1, "Hz"),
                    metric("0–20 Hz amplitude proxy", s?.amplitude?.total0To20, "relative units", 3),
                    metric("7–9 Hz band", s?.amplitude?.band7To9, "relative units", 3),
                    metric("13–15 Hz band", s?.amplitude?.band13To15, "relative units", 3),
                    metric("18–20 Hz band", s?.amplitude?.band18To20, "relative units", 3)),
                when (s?.quality?.usable) { false -> "Source quality is limited; interpret these readings cautiously."; else -> "Frequency estimate and relative amplitude from the source spectrogram; amplitude is not a calibrated field-strength measurement." })
            val t = p.tomsk
            reading("Tomsk resonance", "Tomsk", "Tomsk", t?.generatedAt, 90,
                t?.frequencyHz.orEmpty().toSortedMap().mapNotNull { (label, value) -> metric(label, value, "Hz") } +
                    listOfNotNull(metric("A1 amplitude", t?.amplitude?.get("A1"), "source units"), metric("Q1 factor", t?.qFactor?.get("Q1"))),
                if (t?.usable == false) "Tomsk marks this observation as limited quality." else "Tomsk has its own observation time; it may update less often than Cumiana.")
            val rows = p.schumannSeries?.rows.orEmpty().filter { it.quality.usable != false }
            chart("Fundamental history", "Hz", "Cumiana · latest 192 samples", "Schumann history",
                rows.map { EnvironmentPoint(it.ts, it.harmonics.f0) }, 60, 45)
            chart("Amplitude history · 0–20 Hz", "relative units", "Cumiana · latest 192 samples", "Schumann history",
                rows.map { EnvironmentPoint(it.ts, it.amplitude.total0To20) }, 60, 45)
        }
        ExploreDetail.ULF -> {
            val u = p.ulf?.context
            reading("Regional geomagnetic activity", "USGS · ${u?.stations?.joinToString(" / ")?.ifBlank { "observatories" } ?: "observatories"}", "ULF", u?.timestamp, 30,
                listOfNotNull(u?.classification?.let { "Activity" to it }, metric("Intensity percentile", u?.intensity, "/ 100", 1),
                    metric("Station coherence", u?.coherence?.times(100), "%", 1), metric("Persistence", u?.persistence, "%", 1),
                    metric("Confidence", u?.confidence?.times(100), "%", 1)),
                listOfNotNull("Derived from 60-second samples; intensity and persistence are proxies, not true Pc5 spectral power.", ulfQualityNote(u?.qualityFlags.orEmpty())).joinToString(" "))
            p.ulf?.stations.orEmpty().forEach { station ->
                reading("Station ${station.stationId ?: "unknown"}", "USGS · component ${station.component ?: "unspecified"}", "ULF", station.timestamp, 30,
                    listOfNotNull(metric("Field-change RMS", station.dbdtRms, "nT/s", 4), metric("Intensity percentile", station.index, "/ 100", 1)),
                    ulfQualityNote(station.qualityFlags))
            }
            chart("Regional intensity · 48 hours", "percentile / 100", "USGS-derived Gaia Eyes context", "ULF history",
                p.ulfSeries?.series.orEmpty().map { EnvironmentPoint(it.timestamp, it.intensity) }, 30, 15)
        }
        ExploreDetail.SPACE_WEATHER -> {
            val m = p.magnetosphere?.data
            listOf(Triple("Kp index", "kp", ""), Triple("Solar wind speed", "sw", "km/s"), Triple("Bz · north/south field", "bz", "nT")).forEach { (label, key, unit) ->
                val history = spaceHistoryPoints(p, key)
                val latest = history.lastOrNull()
                val current = EnvironmentPoint(m?.ts, when (key) { "kp" -> m?.kpis?.kp; "sw" -> m?.solarWind?.speedKms; else -> m?.solarWind?.bzNt })
                // A fresh sibling response must not date an older channel's value.
                val selected = environmentalPoints(listOfNotNull(current, latest)).lastOrNull()
                    ?: current.takeIf { it.v?.isFinite() == true }
                val sourceKey = if (selected == latest && latest != null) "Space weather history" else "Magnetosphere"
                reading(label, "NOAA/SWPC-derived Gaia Eyes feed", sourceKey, selected?.t, if (key == "kp") 240 else 30,
                    listOfNotNull(metric(label, selected?.v, unit, if (key == "sw") 0 else 2)))
                chart("$label · 24 hours", unit.ifBlank { "Kp (0–9)" }, "NOAA/SWPC-derived Gaia Eyes feed", "Space weather history",
                    history, if (key == "kp") 240 else 30, if (key == "kp") 240 else 30)
            }
            reading("Solar wind density", "NOAA/SWPC-derived Gaia Eyes feed", "Magnetosphere", m?.ts, 30,
                listOfNotNull(metric("Particle density", m?.solarWind?.densityCm3, "cm⁻³")))
        }
        ExploreDetail.MAGNETOSPHERE -> {
            val m = p.magnetosphere?.data
            reading("Modeled boundaries", "Gaia Eyes model · NOAA solar wind / Kp", "Magnetosphere", m?.ts, 30,
                listOfNotNull(metric("Magnetopause standoff", m?.kpis?.standoffDistanceEarthRadii, "Rₑ"),
                    metric("Plasmapause", m?.kpis?.plasmapauseEarthRadii, "Rₑ"), m?.kpis?.geoRisk?.let { "Boundary state" to it },
                    m?.kpis?.storminess?.let { "Geomagnetic context" to it }, m?.kpis?.dbdt?.let { "Field-change proxy" to it },
                    m?.trend?.get("r0")?.let { "Standoff trend" to it }),
                "Rₑ means Earth radii. These boundaries are modeled estimates, not a local field measurement.")
            chart("Standoff history · 24 hours", "Rₑ", "Gaia Eyes magnetosphere model", "Magnetosphere", m?.series?.r0.orEmpty(), 30, 30)
        }
        else -> Unit
    }
    return EnvironmentalPanel(
        when (detail) { ExploreDetail.SCHUMANN -> "Schumann Resonance"; ExploreDetail.ULF -> "ULF Geomagnetic Activity"; ExploreDetail.MAGNETOSPHERE -> "Magnetosphere"; else -> "Space Weather" },
        when (detail) {
            ExploreDetail.SCHUMANN -> "Station observations, source quality and recent resonance trends."
            ExploreDetail.ULF -> "Low-frequency geomagnetic activity from USGS observatories."
            ExploreDetail.MAGNETOSPHERE -> "Follow the modeled boundary of Earth's magnetic environment and its recent changes."
            else -> "Follow solar wind and geomagnetic observations, with separate timestamps for each signal."
        }, readings, charts,
    )
}
private fun ulfQualityNote(flags: List<String>): String? = flags.takeIf { it.isNotEmpty() }?.joinToString(" · ") {
    when (it) { "low_history" -> "Baseline still building"; "missing_samples" -> "Some source samples are missing"; "fallback_component" -> "Alternate field component used"; else -> it.replace('_', ' ') }
}
