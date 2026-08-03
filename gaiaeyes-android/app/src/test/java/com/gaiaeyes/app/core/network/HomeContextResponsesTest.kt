package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeContextResponsesTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesCurrentSymptomsEnvelope() {
        val envelope = json.decodeFromString<CurrentSymptomsEnvelope>(
            """
            {
              "ok": true,
              "data": {
                "generated_at": "2026-07-29T14:00:00Z",
                "window_hours": 12,
                "summary": {
                  "active_count": 2,
                  "new_count": 1,
                  "ongoing_count": 1,
                  "improving_count": 0,
                  "worse_count": 0,
                  "last_updated_at": "2026-07-29T13:55:00Z"
                },
                "items": [
                  {
                    "id": "symptom-1",
                    "symptom_code": "migraine",
                    "label": "Migraine",
                    "severity": 5,
                    "current_state": "ongoing",
                    "gauge_keys": ["pain", "focus"],
                    "future_field": "ignored"
                  }
                ]
              }
            }
            """.trimIndent(),
        )

        assertTrue(envelope.ok)
        assertEquals(2, envelope.data?.summary?.activeCount)
        assertEquals("Migraine", envelope.data?.items?.single()?.label)
        assertEquals(listOf("pain", "focus"), envelope.data?.items?.single()?.gaugeKeys)
    }

    @Test
    fun decodesAllDriversResponse() {
        val response = json.decodeFromString<AllDriversResponse>(
            """
            {
              "ok": true,
              "generated_at": "2026-07-29T14:00:00Z",
              "summary": {
                "active_driver_count": 1,
                "total_count": 2,
                "strongest_category": "Space",
                "primary_state": "Watch",
                "note": "Schumann looks most relevant right now.",
                "has_personal_patterns": true
              },
              "drivers": [
                {
                  "id": "schumann",
                  "key": "schumann",
                  "source_key": "schumann",
                  "aliases": ["earth_resonance"],
                  "label": "Schumann",
                  "category": "earth",
                  "category_label": "Earth / Resonance",
                  "role": "leading",
                  "role_label": "Leading now",
                  "state": "watch",
                  "state_label": "Watch",
                  "severity": "moderate",
                  "reading": "0.50 Hz delta",
                  "short_reason": "Variability is elevated.",
                  "personal_reason": "This has lined up with focus shifts in your history.",
                  "current_symptoms": ["Focus shifts"],
                  "pattern_status": "strong",
                  "pattern_status_label": "Strong pattern",
                  "pattern_summary": "Focus shifts have appeared more often during elevated days.",
                  "outlook_summary": "Worth watching today.",
                  "active_now_text": "Variability is elevated right now.",
                  "signal_strength": 0.72,
                  "display_score": 0.88,
                  "is_objectively_active": true
                }
              ]
            }
            """.trimIndent(),
        )

        assertTrue(response.ok)
        assertEquals(1, response.summary.activeDriverCount)
        assertTrue(response.summary.hasPersonalPatterns)
        assertEquals("Schumann", response.drivers.single().label)
        assertEquals("Leading now", response.drivers.single().roleLabel)
        assertEquals("Earth / Resonance", response.drivers.single().categoryLabel)
        assertEquals(listOf("Focus shifts"), response.drivers.single().currentSymptoms)
        assertEquals("Strong pattern", response.drivers.single().patternStatusLabel)
        assertEquals(0.88, response.drivers.single().displayScore ?: 0.0, 0.001)
    }

    @Test
    fun decodesLocalWeatherWhenHealthFlagsAreAnObject() {
        val response = json.decodeFromString<LocalCheckResponse>(
            """
            {
              "ok": true,
              "where": {"zip": "78754", "lat": 30.35, "lon": -97.65},
              "weather": {
                "temp_c": 31.2,
                "temp_delta_24h_c": 1.8,
                "humidity_pct": 62.0,
                "precip_prob_pct": 20.0,
                "pressure_hpa": 1012.4,
                "baro_delta_24h_hpa": -2.3,
                "baro_trend": "falling",
                "obs_time": "2026-08-02T21:35:00Z"
              },
              "air": {"aqi": 42, "category": "Good", "pollutant": "O3"},
              "health": {
                "flags": {
                  "aqi_flag": "good",
                  "pressure_rapid_drop": false,
                  "big_temp_shift_24h": false
                },
                "messages": []
              },
              "asof": "2026-08-02T21:36:00Z"
            }
            """.trimIndent(),
        )

        assertEquals("78754", response.where.zip)
        assertEquals(31.2, response.weather.temperatureC ?: 0.0, 0.001)
        assertEquals(42, response.air.aqi)
    }

    @Test
    fun decodesNullableLocationPreferences() {
        val envelope = json.decodeFromString<ProfileLocationEnvelope>(
            """
            {
              "ok": true,
              "location": {
                "zip": "78754",
                "lat": 30.35,
                "lon": -97.65,
                "is_primary": true,
                "use_gps": null,
                "local_insights_enabled": null
              }
            }
            """.trimIndent(),
        )

        assertEquals("78754", envelope.location?.zip)
        assertEquals(null, envelope.location?.useGps)
        assertEquals(null, envelope.location?.localInsightsEnabled)
    }
}
