package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.DriverItem
import com.gaiaeyes.app.core.network.GaugeMeta
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeContextPresentationTest {
    @Test
    fun deduplicatesRelatedSleepLabelsAndMarksActiveMatch() {
        val result = derivePossibleSymptoms(
            dashboard = DashboardGaugesResponse(
                gauges = mapOf("sleep" to 62.0),
                gaugesMeta = mapOf(
                    "sleep" to GaugeMeta(
                        zone = "elevated",
                        label = "Disrupted",
                    ),
                ),
            ),
            drivers = AllDriversResponse(
                ok = true,
                drivers = listOf(
                    DriverItem(
                        key = "sleep_debt",
                        label = "Sleep debt",
                        role = "supporting",
                    ),
                ),
            ),
            activeLabels = listOf("Restless sleep"),
        )

        assertEquals(1, result.count { it.label == "Restless sleep" })
        assertTrue(result.first { it.label == "Restless sleep" }.isMatched)
    }

    @Test
    fun usesDriverAndGaugeContextWithoutDuplicatingSymptoms() {
        val result = derivePossibleSymptoms(
            dashboard = DashboardGaugesResponse(
                gauges = mapOf("focus" to 55.0),
                gaugesMeta = mapOf(
                    "focus" to GaugeMeta(
                        zone = "elevated",
                        label = "Patchy",
                    ),
                ),
            ),
            drivers = AllDriversResponse(
                ok = true,
                drivers = listOf(
                    DriverItem(
                        key = "ulf",
                        label = "ULF activity",
                        role = "leading",
                        isObjectivelyActive = true,
                    ),
                ),
            ),
            activeLabels = emptyList(),
        )

        assertEquals(1, result.count { it.label == "Focus shifts" })
        assertTrue(result.any { it.label == "Brain fog" })
        assertFalse(result.any { it.isMatched })
    }

    @Test
    fun relevantDriversPreferActiveAndPersonalRows() {
        val response = AllDriversResponse(
            ok = true,
            drivers = listOf(
                DriverItem(key = "kp", label = "Kp", role = "background"),
                DriverItem(key = "aqi", label = "Air quality", role = "supporting"),
                DriverItem(
                    key = "schumann",
                    label = "Schumann",
                    role = "background",
                    isObjectivelyActive = true,
                ),
            ),
        )

        assertEquals(
            listOf("Air quality", "Schumann"),
            relevantDrivers(response).map { it.label },
        )
    }

    @Test
    fun exploreDriversPreserveTheCompleteServerOrder() {
        val response = AllDriversResponse(
            ok = true,
            drivers = (1..6).map { index ->
                DriverItem(
                    key = "driver_$index",
                    label = "Driver $index",
                    role = when (index) {
                        1 -> "leading"
                        2, 3 -> "supporting"
                        else -> "background"
                    },
                )
            },
        )

        assertEquals(
            listOf("Driver 1", "Driver 2", "Driver 3", "Driver 4", "Driver 5", "Driver 6"),
            exploreDrivers(response).map { it.label },
        )
        assertEquals(
            DriverRoleCounts(leading = 1, supporting = 2),
            driverRoleCounts(response),
        )
    }

    @Test
    fun driverPresentationPrefersPersonalContextAndDisplayScore() {
        val driver = DriverItem(
            key = "schumann",
            label = "Schumann",
            shortReason = "Variability is elevated.",
            personalReason = "This has lined up with focus shifts in your history.",
            activeNowText = "Active right now.",
            signalStrength = 0.72,
            displayScore = 0.88,
        )

        assertEquals(
            "This has lined up with focus shifts in your history.",
            driverDisplayReason(driver),
        )
        assertEquals(0.88f, driverSignalProgress(driver), 0.001f)
    }

    @Test
    fun driverPresentationFallsBackToActiveContext() {
        val driver = DriverItem(
            key = "temperature",
            label = "Temperature swing",
            activeNowText = "A rapid temperature change is active.",
        )

        assertEquals(
            "A rapid temperature change is active.",
            driverDisplayReason(driver),
        )
    }
}
