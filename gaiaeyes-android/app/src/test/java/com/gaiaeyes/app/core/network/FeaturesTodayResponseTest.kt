package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FeaturesTodayResponseTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesTheExistingFeaturesTodayEnvelope() {
        val envelope = json.decodeFromString<FeaturesTodayEnvelope>(
            """
            {
              "ok": true,
              "data": {
                "day": "2026-07-30",
                "updated_at": "2026-07-30T14:05:00Z",
                "source": "marts.daily_features",
                "sleep_total_minutes": 447,
                "rem_m": 94,
                "core_m": 307,
                "deep_m": 47,
                "awake_m": 14,
                "inbed_m": 461,
                "sleep_efficiency": 0.97,
                "steps_total": 1175,
                "hr_min": 53.0,
                "hr_max": 99.0,
                "hrv_avg": 42.0,
                "hrv_baseline_delta": 9.0,
                "spo2_avg": 0.98,
                "spo2_baseline_delta": 1.0,
                "respiratory_rate_sleep_avg": 13.2,
                "respiratory_rate_baseline_delta": -0.8,
                "temperature_deviation": 0.02,
                "temperature_deviation_baseline_delta": -0.67,
                "temperature_source": "apple_sleeping_wrist_temperature",
                "resting_hr_avg": 64.0,
                "resting_hr_baseline_delta": -3.6,
                "future_field": "ignored"
              }
            }
            """.trimIndent(),
        )

        assertTrue(envelope.ok)
        assertEquals("2026-07-30", envelope.data?.day)
        assertEquals(447, envelope.data?.sleepTotalMinutes)
        assertEquals(0.98, envelope.data?.spo2Average)
        assertEquals(-0.67, envelope.data?.temperatureDeviationBaselineDelta)
        assertEquals(99.0, envelope.data?.heartRateMax)
    }
}
