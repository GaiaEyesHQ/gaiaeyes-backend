package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.DriverItem
import com.gaiaeyes.app.core.network.GaugeMeta
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GaugeDetailPresentationTest {
    @Test
    fun focusDetailUsesSharedGaugeSymptomsAndRelevantDrivers() {
        val model = gaugeDetailModel(
            key = "focus",
            fallbackLabel = "Focus",
            dashboard = DashboardGaugesResponse(
                gauges = mapOf("focus" to 42.4),
                gaugeLabels = mapOf("focus" to "Focus"),
                gaugesMeta = mapOf("focus" to GaugeMeta(label = "Patchy")),
                gaugesDelta = mapOf("focus" to 10),
            ),
            currentSymptoms = CurrentSymptomsResponse(
                items = listOf(
                    CurrentSymptomItem(label = "Brain fog", severity = 6, gaugeKeys = listOf("focus")),
                    CurrentSymptomItem(label = "Nerve pain", severity = 8, gaugeKeys = listOf("pain")),
                ),
            ),
            drivers = AllDriversResponse(
                drivers = listOf(
                    DriverItem(
                        key = "ulf",
                        label = "ULF",
                        stateLabel = "Elevated",
                        isObjectivelyActive = true,
                    ),
                    DriverItem(
                        key = "air_quality",
                        label = "Air quality",
                        state = "active",
                        role = "supporting",
                    ),
                    DriverItem(key = "cme", label = "CME", state = "quiet", role = "background"),
                ),
            ),
        )

        assertEquals("Focus", model.title)
        assertEquals("Patchy", model.status)
        assertEquals(42, model.score)
        assertEquals(10, model.delta)
        assertEquals(listOf("Brain fog"), model.symptoms)
        assertEquals(listOf("AQI is active", "ULF activity is elevated"), model.influencers)
    }

    @Test
    fun healthStatusShowsTopActiveSymptomsAndStrongestDrivers() {
        val model = gaugeDetailModel(
            key = "health_status",
            fallbackLabel = "Health Status",
            dashboard = DashboardGaugesResponse(
                gauges = mapOf("health_status" to 31.0),
                gaugesMeta = mapOf("health_status" to GaugeMeta(label = "Watchful")),
            ),
            currentSymptoms = CurrentSymptomsResponse(
                items = listOf(
                    CurrentSymptomItem(label = "Migraine", severity = 7, gaugeKeys = listOf("pain")),
                    CurrentSymptomItem(label = "Light sensitivity", severity = 5, gaugeKeys = listOf("focus")),
                ),
            ),
            drivers = AllDriversResponse(
                drivers = listOf(
                    DriverItem(
                        key = "humidity",
                        label = "Humidity",
                        stateLabel = "High",
                        displayScore = 0.70,
                        isObjectivelyActive = true,
                    ),
                    DriverItem(
                        key = "schumann",
                        label = "Schumann",
                        stateLabel = "Watch",
                        displayScore = 0.90,
                        isObjectivelyActive = true,
                    ),
                ),
            ),
        )

        assertEquals(listOf("Migraine", "Light sensitivity"), model.symptoms)
        assertEquals(
            listOf("Earth resonance is watch", "Humidity is high"),
            model.influencers,
        )
        assertTrue(model.helpfulTips.isNotEmpty())
    }

    @Test
    fun missingGaugeDataStillProducesAUsefulExplanation() {
        val model = gaugeDetailModel(
            key = "stamina",
            fallbackLabel = "Recovery Load",
            dashboard = null,
            currentSymptoms = null,
            drivers = null,
        )

        assertEquals("Recovery Load", model.title)
        assertEquals("Waiting for today’s data", model.status)
        assertEquals(null, model.score)
        assertEquals(null, model.delta)
        assertTrue(model.influencers.isEmpty())
        assertTrue(model.helpfulTips.isNotEmpty())
    }
}
