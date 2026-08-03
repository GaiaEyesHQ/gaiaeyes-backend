package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.LocalAir
import com.gaiaeyes.app.core.network.LocalCheckResponse
import com.gaiaeyes.app.core.network.LocalWeather
import com.gaiaeyes.app.core.network.ProfileLocation
import com.gaiaeyes.app.data.HomeContextSource
import com.gaiaeyes.app.data.LocalWeatherSnapshot
import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.TimeZone

class LocalWeatherPresentationTest {
    @Test
    fun buildsFriendlyLocalWeatherMetrics() {
        val snapshot = LocalWeatherSnapshot(
            location = ProfileLocation(zip = "78754", label = "Austin, TX"),
            local = LocalCheckResponse(
                weather = LocalWeather(
                    temperatureC = 30.0,
                    temperatureDelta24hC = 2.0,
                    humidityPercent = 72.4,
                    precipitationProbabilityPercent = 35.0,
                    pressureHpa = 1014.6,
                    pressureDelta24hHpa = -3.2,
                    pressureTrend = "falling",
                ),
                air = LocalAir(aqi = 47, category = "Good", pollutant = "O3"),
            ),
            source = HomeContextSource.NETWORK,
            savedAtEpochMillis = 1L,
        )

        val metrics = localWeatherMetrics(snapshot)

        assertEquals("Austin, TX", localWeatherLocationLabel(snapshot))
        assertEquals("Live", localWeatherSourceLabel(snapshot))
        assertEquals("86°F", metrics.first().value)
        assertEquals("+3.6°F in 24h", metrics.first().detail)
        assertEquals("72%", metrics[1].value)
        assertEquals("1015 hPa", metrics[2].value)
        assertEquals("-3.2 hPa in 24h • falling", metrics[2].detail)
        assertEquals("47 AQI", metrics.last().value)
    }

    @Test
    fun fallsBackToZipAndSavedSource() {
        val snapshot = LocalWeatherSnapshot(
            location = ProfileLocation(zip = "78754"),
            local = null,
            source = HomeContextSource.CACHE,
            savedAtEpochMillis = 1L,
        )

        assertEquals("78754", localWeatherLocationLabel(snapshot))
        assertEquals("Saved", localWeatherSourceLabel(snapshot))
        assertEquals(emptyList<LocalWeatherMetric>(), localWeatherMetrics(snapshot))
    }

    @Test
    fun formatsObservationTimeInDeviceTimeZone() {
        val originalTimeZone = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("America/Chicago"))
            val snapshot = LocalWeatherSnapshot(
                location = ProfileLocation(zip = "78754"),
                local = LocalCheckResponse(
                    weather = LocalWeather(observationTime = "2026-08-02T21:35:00Z"),
                ),
                source = HomeContextSource.NETWORK,
                savedAtEpochMillis = 1L,
            )

            assertEquals("Observed Aug 2, 4:35 PM", localWeatherObservedText(snapshot))
        } finally {
            TimeZone.setDefault(originalTimeZone)
        }
    }
}
