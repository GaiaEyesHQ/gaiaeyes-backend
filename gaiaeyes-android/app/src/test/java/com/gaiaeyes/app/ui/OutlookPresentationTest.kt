package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.OutlookDay
import com.gaiaeyes.app.core.network.OutlookDomain
import com.gaiaeyes.app.core.network.OutlookDriver
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OutlookPresentationTest {
    @Test
    fun normalizesSolarFlareAndFiltersRadioBlackoutDrivers() {
        val day = OutlookDay(
            topDrivers = listOf(
                OutlookDriver(
                    key = "flare_watch",
                    label = "Flare watch",
                    severity = "watch",
                ),
                OutlookDriver(
                    key = "radio_blackout",
                    label = "Radio blackout",
                    severity = "watch",
                ),
            ),
        )

        val visible = visibleOutlookDrivers(day)

        assertEquals(1, visible.size)
        assertEquals("Solar Flare Watch", outlookDriverLabel(visible.single()))
        assertFalse(visible.any { it.key == "radio_blackout" })
    }

    @Test
    fun formatsDayStateAndDriverValues() {
        val day = OutlookDay(
            day = "2026-07-31",
            label = "Tomorrow",
            primaryState = "watch",
        )
        val driver = OutlookDriver(
            key = "humidity",
            label = "Humidity",
            value = 84.0,
            unit = "%",
        )

        assertEquals("Tomorrow", outlookDayTitle(day))
        assertEquals("Jul 31", outlookDayDate(day))
        assertEquals("Watch", outlookDayState(day))
        assertEquals("84 %", outlookDriverValue(driver))
        assertEquals(0.84f, outlookDriverProgress(driver), 0.001f)
    }

    @Test
    fun labelsEnergyAsDipWhenHumidityIsInView() {
        val label = outlookDomainLabel(
            domain = OutlookDomain(
                key = "energy",
                label = "Energy",
                topOutcomeLabel = "Low energy",
            ),
            drivers = listOf(OutlookDriver(key = "humidity")),
        )

        assertEquals("Energy dip", label)
    }

    @Test
    fun progressAlwaysStaysVisibleAndBounded() {
        assertTrue(
            outlookDriverProgress(
                OutlookDriver(key = "solar_wind", value = 200.0),
            ) >= 0.08f,
        )
        assertTrue(
            outlookDriverProgress(
                OutlookDriver(key = "kp", value = 12.0),
            ) <= 1f,
        )
    }
}
