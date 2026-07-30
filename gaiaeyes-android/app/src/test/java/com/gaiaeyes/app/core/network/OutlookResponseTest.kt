package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OutlookResponseTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesTheExistingOutlookContract() {
        val response = json.decodeFromString<OutlookResponse>(
            """
            {
              "ok": true,
              "generated_at": "2026-07-30T15:00:00Z",
              "available_windows": ["next_24h", "next_72h", "next_7d"],
              "daily_outlook": [{
                "day": "2026-07-31",
                "label": "Tomorrow",
                "primary_state": "watch",
                "top_drivers": [{
                  "key": "flare_watch",
                  "label": "Flare watch",
                  "severity": "watch",
                  "value": 1.0,
                  "unit": "%"
                }],
                "likely_elevated_domains": [{
                  "key": "energy",
                  "label": "Energy",
                  "likelihood": "watch",
                  "current_gauge": 42.0,
                  "top_outcome_label": "Low energy"
                }],
                "voice_semantic": {
                  "interpretation": {
                    "empty_state": "No strong signal stands out."
                  }
                }
              }],
              "forecast_data_ready": {
                "location_found": true,
                "local_forecast_daily": true,
                "local_forecast_days": 7,
                "space_forecast_daily": true,
                "space_forecast_days": 7,
                "next_24h": true,
                "next_72h": true,
                "next_7d": true
              },
              "voice_semantics": {
                "overview": {
                  "interpretation": {
                    "header_summary": "Your next seven days are ready."
                  }
                }
              },
              "future_field": "ignored"
            }
            """.trimIndent(),
        )

        assertTrue(response.ok)
        assertEquals(listOf("next_24h", "next_72h", "next_7d"), response.availableWindows)
        assertEquals("Tomorrow", response.dailyOutlook.single().label)
        assertEquals("flare_watch", response.dailyOutlook.single().topDrivers.single().key)
        assertEquals(7, response.forecastDataReady?.localForecastDays)
        assertEquals(
            "Your next seven days are ready.",
            response.voiceSemantics?.overview?.interpretation?.headerSummary,
        )
    }
}
