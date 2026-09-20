package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class MagnetosphereResponse(
    val ok: Boolean = false,
    val data: MagnetosphereData? = null,
    val error: String? = null,
)

@Serializable
data class MagnetosphereData(
    val ts: String? = null,
    val kpis: MagnetosphereKpis = MagnetosphereKpis(),
    @SerialName("sw") val solarWind: MagnetosphereSolarWind = MagnetosphereSolarWind(),
    val series: MagnetosphereSeries = MagnetosphereSeries(),
    val trend: Map<String, String?> = emptyMap(),
)

@Serializable
data class MagnetosphereKpis(
    @SerialName("r0_re") val standoffDistanceEarthRadii: Double? = null,
    @SerialName("geo_risk") val geoRisk: String? = null,
    val storminess: String? = null,
    val dbdt: String? = null,
    @SerialName("lpp_re") val plasmapauseEarthRadii: Double? = null,
    val kp: Double? = null,
)

@Serializable
data class MagnetosphereSolarWind(
    @SerialName("n_cm3") val densityCm3: Double? = null,
    @SerialName("v_kms") val speedKms: Double? = null,
    @SerialName("bz_nt") val bzNt: Double? = null,
)

@Serializable
data class SchumannLatestResponse(
    val ok: Boolean = false,
    @SerialName("generated_at") val generatedAt: String? = null,
    val harmonics: SchumannHarmonics = SchumannHarmonics(),
    val amplitude: SchumannAmplitude = SchumannAmplitude(),
    val quality: SchumannQuality = SchumannQuality(),
    val fusion: SchumannFusion = SchumannFusion(),
)

@Serializable
data class SchumannHarmonics(
    val f0: Double? = null,
    val f1: Double? = null,
    val f2: Double? = null,
    val f3: Double? = null,
    val f4: Double? = null,
    val f5: Double? = null,
    @SerialName("combined_f1") val combinedF1: Double? = null,
)

@Serializable
data class SchumannAmplitude(
    @SerialName("sr_total_0_20") val total0To20: Double? = null,
    @SerialName("band_7_9") val band7To9: Double? = null,
    @SerialName("band_13_15") val band13To15: Double? = null,
    @SerialName("band_18_20") val band18To20: Double? = null,
)

@Serializable
data class SchumannQuality(
    @SerialName("primary_source") val primarySource: String? = null,
    val usable: Boolean? = null,
    @SerialName("quality_score") val qualityScore: Double? = null,
)

@Serializable
data class SchumannFusion(
    val enabled: Boolean = false,
    @SerialName("tomsk_usable") val tomskUsable: Boolean = false,
    @SerialName("display_f0_hz") val displayF0Hz: Double? = null,
    @SerialName("display_f0_source") val displayF0Source: String? = null,
    @SerialName("secondary_f0_hz") val secondaryF0Hz: Double? = null,
    @SerialName("secondary_f0_source") val secondaryF0Source: String? = null,
    val coherence: JsonElement? = null,
    @SerialName("tomsk_quality_score") val tomskQualityScore: Double? = null,
)

@Serializable
data class QuakesLatestResponse(
    val ok: Boolean = false,
    val item: QuakesLatestItem? = null,
)

@Serializable
data class QuakesLatestItem(
    val day: String? = null,
    @SerialName("all_quakes") val allQuakes: Int? = null,
    @SerialName("m4p") val magnitude4Plus: Int? = null,
    @SerialName("m5p") val magnitude5Plus: Int? = null,
    @SerialName("m6p") val magnitude6Plus: Int? = null,
    @SerialName("m7p") val magnitude7Plus: Int? = null,
)

@Serializable
data class HazardsResponse(
    val ok: Boolean = false,
    @SerialName("generated_at") val generatedAt: String? = null,
    val items: List<HazardItem> = emptyList(),
)

@Serializable
data class HazardItem(
    val id: String? = null,
    val title: String? = null,
    val url: String? = null,
    val source: String? = null,
    val kind: String? = null,
    val location: String? = null,
    val severity: String? = null,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("ended_at") val endedAt: String? = null,
    @SerialName("ingested_at") val ingestedAt: String? = null,
    val details: JsonElement? = null,
    val lat: Double? = null,
    val lon: Double? = null,
)

@Serializable
data class ExplorePayload(
    val magnetosphere: MagnetosphereResponse? = null,
    val schumann: SchumannLatestResponse? = null,
    val quakes: QuakesLatestResponse? = null,
    val hazards: HazardsResponse? = null,
    val schumannSeries: SchumannSeriesResponse? = null,
    val tomsk: TomskLatestResponse? = null,
    val ulf: UlfLatestResponse? = null,
    val ulfSeries: UlfSeriesResponse? = null,
    val spaceHistory: SpaceHistoryResponse? = null,
    // Per-source request failures survive cache round trips; a successful sibling cannot mark them live.
    val sourceErrors: Map<String, String> = emptyMap(),
    val fetchedAt: Map<String, Long> = emptyMap(),
)

@Serializable
data class MagnetosphereSeries(val r0: List<EnvironmentPoint> = emptyList())

@Serializable
data class EnvironmentPoint(val t: String? = null, val v: Double? = null)

@Serializable
data class SpaceHistoryResponse(val ok: Boolean = false, val data: SpaceHistoryData? = null)

@Serializable
data class SpaceHistoryData(val series24: Map<String, List<List<JsonElement>>> = emptyMap())

@Serializable
data class SchumannSeriesResponse(val ok: Boolean = false, val rows: List<SchumannSeriesRow> = emptyList())

@Serializable
data class SchumannSeriesRow(
    val ts: String? = null,
    val harmonics: SchumannHarmonics = SchumannHarmonics(),
    val amplitude: SchumannAmplitude = SchumannAmplitude(),
    val quality: SchumannQuality = SchumannQuality(),
)

@Serializable
data class TomskLatestResponse(
    val ok: Boolean = false,
    @SerialName("generated_at") val generatedAt: String? = null,
    @SerialName("station_id") val stationId: String? = null,
    val usable: Boolean? = null,
    @SerialName("quality_score") val qualityScore: Double? = null,
    @SerialName("frequency_hz") val frequencyHz: Map<String, Double?> = emptyMap(),
    val amplitude: Map<String, Double?> = emptyMap(),
    @SerialName("q_factor") val qFactor: Map<String, Double?> = emptyMap(),
)

// ULF endpoints intentionally have no `ok` envelope.
@Serializable
data class UlfLatestResponse(
    @SerialName("latest_context") val context: UlfContext? = null,
    @SerialName("latest_by_station") val stations: List<UlfStation> = emptyList(),
)

@Serializable
data class UlfContext(
    @SerialName("ts_utc") val timestamp: String? = null,
    @SerialName("stations_used") val stations: List<String> = emptyList(),
    @SerialName("regional_intensity") val intensity: Double? = null,
    @SerialName("regional_coherence") val coherence: Double? = null,
    @SerialName("regional_persistence") val persistence: Double? = null,
    @SerialName("context_class") val classification: String? = null,
    @SerialName("confidence_score") val confidence: Double? = null,
    @SerialName("quality_flags") val qualityFlags: List<String> = emptyList(),
)

@Serializable
data class UlfStation(
    @SerialName("station_id") val stationId: String? = null,
    @SerialName("ts_utc") val timestamp: String? = null,
    @SerialName("component_used") val component: String? = null,
    @SerialName("dbdt_rms") val dbdtRms: Double? = null,
    @SerialName("ulf_band_proxy") val bandProxy: Double? = null,
    @SerialName("ulf_index_station") val index: Double? = null,
    @SerialName("quality_flags") val qualityFlags: List<String> = emptyList(),
)

@Serializable
data class UlfSeriesResponse(val series: List<UlfContext> = emptyList())
