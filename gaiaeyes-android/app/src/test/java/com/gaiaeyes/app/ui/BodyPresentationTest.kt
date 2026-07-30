package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.FeaturesTodayResponse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BodyPresentationTest {
    @Test
    fun formatsSleepSummaryAndEfficiency() {
        assertEquals("7h 27m", sleepDurationText(447))
        assertEquals("—", sleepDurationText(0))
        assertEquals(97, sleepEfficiencyPercent(0.97))
        assertEquals(97, sleepEfficiencyPercent(97.2))
        assertNull(sleepEfficiencyPercent(null))
    }

    @Test
    fun buildsHealthStatsWithNormalizedSpo2AndBaselineDetails() {
        val stats = bodyHealthStats(
            FeaturesTodayResponse(
                respiratoryRateSleepAverage = 13.2,
                respiratoryRateBaselineDelta = -0.8,
                spo2Average = 0.98,
                spo2BaselineDelta = 1.0,
                hrvAverage = 42.0,
                hrvBaselineDelta = 9.0,
                temperatureDeviationBaselineDelta = -0.67,
                restingHeartRateAverage = 64.0,
                restingHeartRateBaselineDelta = -3.6,
            ),
        ).associateBy { it.label }

        assertEquals("13.2 br/min", stats.getValue("Respiratory").value)
        assertEquals("-0.8 br/min below usual", stats.getValue("Respiratory").detail)
        assertEquals("98%", stats.getValue("SpO₂").value)
        assertEquals("+1.0 pp above usual", stats.getValue("SpO₂").detail)
        assertEquals("42 ms", stats.getValue("HRV").value)
        assertEquals("+9.0 ms above usual", stats.getValue("HRV").detail)
        assertEquals("-0.67 °F", stats.getValue("Temp Δ").value)
        assertEquals("below usual", stats.getValue("Temp Δ").detail)
        assertEquals("64 bpm", stats.getValue("Resting HR").value)
    }

    @Test
    fun doesNotTreatAppleWristTemperatureAsAnAbsoluteTemperatureDelta() {
        val temperature = bodyHealthStats(
            FeaturesTodayResponse(
                temperatureDeviation = 0.02,
                temperatureSource = "apple_sleeping_wrist_temperature",
            ),
        ).first { it.label == "Temp Δ" }

        assertEquals("—", temperature.value)
        assertEquals("waiting for your personal baseline", temperature.detail)
    }

    @Test
    fun formatsHeartRangeOnlyWhenBothBoundsExist() {
        assertEquals(
            "53-99 bpm",
            heartRangeText(
                FeaturesTodayResponse(
                    heartRateMin = 53.0,
                    heartRateMax = 99.0,
                ),
            ),
        )
        assertNull(heartRangeText(FeaturesTodayResponse(heartRateMin = 53.0)))
    }
}
