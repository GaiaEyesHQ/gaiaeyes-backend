package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class DashboardGaugesResponseTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesTheExistingDashboardGaugeContract() {
        val response = json.decodeFromString<DashboardGaugesResponse>(
            """
            {
              "day": "2026-07-28",
              "gauges": {
                "pain": 24.0,
                "focus": 31.0,
                "heart": 25.0,
                "stamina": 33.0,
                "energy": 51.0,
                "sleep": 31.0,
                "mood": 28.0,
                "health_status": 15.0
              },
              "gauge_labels": {
                "stamina": "Recovery Load",
                "health_status": "Health Status"
              },
              "gauges_meta": {
                "stamina": {
                  "zone": "mild",
                  "label": "Less steady"
                },
                "health_status": {
                  "zone": "low",
                  "label": "Low strain"
                }
              },
              "gauges_delta": {
                "stamina": -7,
                "energy": 4,
                "sleep": -3,
                "mood": 2,
                "health_status": -10
              },
              "cache_hit": false,
              "cache_age_seconds": 0.0,
              "stale": false,
              "future_backend_field": "ignored"
            }
            """.trimIndent(),
        )

        assertEquals("2026-07-28", response.day)
        assertEquals(24.0, response.gauges?.get("pain"))
        assertEquals(51.0, response.gauges?.get("energy"))
        assertEquals(31.0, response.gauges?.get("sleep"))
        assertEquals(28.0, response.gauges?.get("mood"))
        assertEquals(15.0, response.gauges?.get("health_status"))
        assertEquals("Recovery Load", response.gaugeLabels["stamina"])
        assertEquals("Health Status", response.gaugeLabels["health_status"])
        assertEquals("Less steady", response.gaugesMeta["stamina"]?.label)
        assertEquals("Low strain", response.gaugesMeta["health_status"]?.label)
        assertEquals(-7, response.gaugesDelta["stamina"])
        assertEquals(4, response.gaugesDelta["energy"])
        assertEquals(-3, response.gaugesDelta["sleep"])
        assertEquals(2, response.gaugesDelta["mood"])
        assertEquals(-10, response.gaugesDelta["health_status"])
        assertFalse(response.stale)
    }

    @Test
    fun missingGaugeDataRemainsEmptyRatherThanSimulated() {
        val response = json.decodeFromString<DashboardGaugesResponse>(
            """{"day":"2026-07-28","gauges":null}""",
        )

        assertEquals(null, response.gauges)
        assertEquals(emptyMap<String, Int?>(), response.gaugesDelta)
    }
}
