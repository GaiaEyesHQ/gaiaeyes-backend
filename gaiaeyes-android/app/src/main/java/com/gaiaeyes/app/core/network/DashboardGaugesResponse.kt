package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class DashboardGaugesResponse(
    val day: String = "",
    val gauges: Map<String, Double?>? = null,
    val alerts: List<DashboardAlert> = emptyList(),
    val entitled: Boolean? = null,
    @SerialName("gauge_labels")
    val gaugeLabels: Map<String, String> = emptyMap(),
    @SerialName("gauges_meta")
    val gaugesMeta: Map<String, GaugeMeta> = emptyMap(),
    @SerialName("gauges_delta")
    val gaugesDelta: Map<String, Int?> = emptyMap(),
    @SerialName("cache_hit")
    val cacheHit: Boolean = false,
    @SerialName("cache_age_seconds")
    val cacheAgeSeconds: Double? = null,
    val stale: Boolean = false,
)

@Serializable
data class GaugeMeta(
    val zone: String? = null,
    val label: String? = null,
)

@Serializable
data class DashboardAlert(
    val family: String? = null,
    val severity: String? = null,
    val title: String? = null,
    val body: String? = null,
)
