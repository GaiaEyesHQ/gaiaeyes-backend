package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class LocalForecastParityTest {
    private val json = Json { ignoreUnknownKeys = true }
    private fun snapshot(vararg days: LocalForecastDay) = LocalWeatherSnapshot(
        ProfileLocation(zip = "78754"), LocalCheckResponse(forecastDaily = days.toList()), HomeContextSource.NETWORK, 0)
    private fun row(day: LocalForecastDay) = localForecastMetrics(snapshot(day)).single()
    @Test fun decodesExistingOptionalFieldsWithoutLosingPollen() {
        val day = json.decodeFromString<LocalForecastDay>("""{"day":"2026-09-22","temp_delta_from_prior_day_c":-2.5,"wind_gust":32.2,"aqi_forecast":52,"pollen_overall_index":0,"future_field":true}""")
        assertEquals(-2.5, day.temperatureDeltaFromPriorDayC!!, 0.0)
        assertEquals(32.2, day.windGust!!, 0.0)
        assertEquals(52.0, day.aqiForecast!!, 0.0)
        assertEquals(0.0, day.pollenOverallIndex!!, 0.0)
    }
    @Test fun missingAndNullNewFieldsStayUnavailable() {
        for (body in listOf("""{"day":"2026-09-22"}""", """{"day":"2026-09-22","temp_delta_from_prior_day_c":null,"wind_gust":null,"aqi_forecast":null}""")) {
            val day = json.decodeFromString<LocalForecastDay>(body)
            assertNull(day.temperatureDeltaFromPriorDayC); assertNull(day.windGust); assertNull(day.aqiForecast)
            val detail = row(day).detail!!
            assertFalse(detail.contains("vs prior day")); assertFalse(detail.contains("Gust")); assertFalse(detail.contains("Forecast AQI"))
        }
    }
    @Test fun temperatureDifferenceKeepsSignAndUsesDifferenceConversion() {
        for ((c, expected) in listOf(2.0 to "+3.6°F", -2.5 to "-4.5°F", 0.0 to "0°F")) {
            val metric = row(LocalForecastDay(day="2026-09-22", temperatureHighC=0.0, temperatureDeltaFromPriorDayC=c))
            assertEquals("High 32°F",metric.value)
            assertTrue(metric.detail!!.contains("$expected vs prior day"))
            assertFalse(metric.detail!!.contains("in 24h"))
        }
    }
    @Test fun nonfiniteOptionalNumbersAreNotRendered() {
        for (value in listOf(Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
            val detail = row(LocalForecastDay(day="2026-09-22",temperatureDeltaFromPriorDayC=value,windGust=value,aqiForecast=value)).detail!!
            assertFalse(detail.contains("vs prior day")); assertFalse(detail.contains("Gust")); assertFalse(detail.contains("Forecast AQI"))
        }
    }
    @Test fun zeroGustAndForecastAqiRemainRealValues() {
        val detail = row(LocalForecastDay(day="2026-09-22", windSpeed=8.0, windGust=0.0, aqiForecast=0.0, source="nws:forecast-hourly")).detail!!
        assertTrue(detail.contains("Wind 8 km/h")); assertTrue(detail.contains("Gust 0 km/h")); assertTrue(detail.contains("Forecast AQI 0"))
        assertFalse(detail.contains("m/s"))
    }
    @Test fun unknownWindUnitsAndNegativeReadingsAreNotInvented() {
        val unknown = row(LocalForecastDay(day="2026-09-22",windSpeed=5.0,windGust=8.0,source="other-provider")).detail!!
        assertTrue(unknown.contains("Wind 5 (unit unavailable)")); assertTrue(unknown.contains("Gust 8 (unit unavailable)"))
        assertFalse(unknown.contains("km/h"))
        val negative = row(LocalForecastDay(day="2026-09-22",windGust=-1.0,aqiForecast=-1.0)).detail!!
        assertFalse(negative.contains("Gust")); assertFalse(negative.contains("Forecast AQI"))
    }
    @Test fun anotherDaysReadingsNeverFillMissingFields() {
        val metrics=localForecastMetrics(snapshot(LocalForecastDay(day="2026-09-22",windGust=15.0,aqiForecast=52.0),LocalForecastDay(day="2026-09-23")))
        assertTrue(metrics[0].detail!!.contains("Forecast AQI 52"))
        assertFalse(metrics[1].detail!!.contains("Forecast AQI")); assertFalse(metrics[1].detail!!.contains("Gust"))
    }
    @Test fun datesKeepCalendarMeaningAndOnlyValidRowsCountTowardSeven() {
        val days=(22..29).map { LocalForecastDay(day="2026-09-$it") }
        val rows=localForecastMetrics(snapshot(LocalForecastDay(day="invalid"),*days.toTypedArray()))
        assertEquals(7,rows.size); assertEquals("Tue, Sep 22",rows.first().label); assertEquals("Mon, Sep 28",rows.last().label)
    }
    @Test fun expansionUsesActualAvailableDaysAndCapsAtSeven() {
        for (count in listOf(0,1,2,3,4,5,6,7,9)) {
            assertEquals(minOf(count,3),localForecastVisibleCount(count,false))
            assertEquals(minOf(count,7),localForecastVisibleCount(count,true))
        }
    }
    @Test fun datedPollenAndWeatherProvenanceSurviveRicherForecast() {
        val metric=row(LocalForecastDay(day="2026-09-23",temperatureDeltaFromPriorDayC=1.0,windGust=20.0,aqiForecast=52.0,
            source="nws:forecast-hourly",issuedAt="2026-01-01T01:00:00Z",pollenOverallIndex=0.0,
            pollenSource="google-pollen:forecast",pollenUpdatedAt="2026-01-02T01:00:00Z"))
        assertTrue(metric.detail!!.contains("Pollen forecast (2026-09-23 UTC): 0 / 5"))
        assertTrue(metric.detail!!.contains("Pollen updated")); assertTrue(metric.detail!!.contains("Issued")); assertTrue(metric.detail!!.contains("Stale"))
    }
}
