package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class PollenAvailabilityTest {
    private val now = Instant.parse("2026-09-22T04:00:00Z")
    private val json = Json { ignoreUnknownKeys = true }
    private fun snapshot(local: LocalCheckResponse) = LocalWeatherSnapshot(ProfileLocation(zip="78754"), local, HomeContextSource.NETWORK, 0)
    @Test fun absentAndMetadataOnlyHaveOneExplanationWithoutImpliedZero() {
        listOf(null, LocalAllergens(), LocalAllergens(source="google-pollen:forecast",updatedAt=now.toString()),
            LocalAllergens(overallIndex=9.0,treeIndex=Double.NaN)).forEach {
            val section=localAllergenSection(it,now)
            assertTrue(section.metrics.isEmpty())
            assertTrue(section.detail.contains("Missing data does not mean a low pollen level"))
        }
    }
    @Test fun categoryOnlyRemainsVisibleWithoutInventingIndex() {
        val section=localAllergenSection(LocalAllergens(overallLevel="high",grassLevel="moderate",source="google-pollen:forecast"),now)
        assertEquals("High",section.metrics.first().value)
        assertEquals("Moderate",section.metrics.first{it.label=="Grass"}.value)
        assertFalse(section.metrics.any{it.value.contains("/ 5")})
        assertTrue(section.detail.contains("freshness unverified"))
    }
    @Test fun genuineZeroAndPartialTypesRemainDistinctFromMissing() {
        val section=localAllergenSection(LocalAllergens(overallIndex=0.0,grassIndex=0.0,updatedAt=now.toString()),now)
        assertEquals("0 / 5",section.metrics.first().value)
        assertEquals("Unavailable",section.metrics.first{it.label=="Tree"}.value)
        assertFalse(section.metrics.any{it.label=="Mold"})
    }
    @Test fun staleAndWrongDayAreExplicitlyHistorical() {
        val section=localAllergenSection(LocalAllergens(overallIndex=3.0,forecastDay="2026-09-20",updatedAt="2026-09-20T03:00:00Z"),now)
        assertEquals("Last reported",section.metrics.first().label)
        assertTrue(section.detail.contains("Stale"))
        assertTrue(section.detail.contains("Not today's pollen forecast"))
    }
    @Test fun futureAndInvalidTimesCannotAssertFreshness() {
        for(time in listOf("2026-09-23T04:00:00Z","invalid")) {
            val section=localAllergenSection(LocalAllergens(overallIndex=2.0,updatedAt=time),now)
            assertTrue(section.detail.contains("freshness unverified"))
        }
        val future=localAllergenSection(LocalAllergens(overallIndex=2.0,forecastDay="2026-09-23"),now)
        assertEquals("Forecast",future.metrics.first().label)
        assertTrue(future.detail.contains("Not today's"))
    }
    @Test fun currentForecastDateAndSourceAreIndependentOfWeatherSnapshot() {
        val section=localAllergenSection(LocalAllergens(overallIndex=4.0,forecastDay="2026-09-22",updatedAt="2026-09-22T03:00:00Z",source="google-pollen:forecast"),now)
        assertEquals("Overall",section.metrics.first().label)
        assertFalse(section.detail.contains("Stale"))
        assertTrue(section.detail.contains("2026-09-22 (UTC)"))
    }
    @Test fun dailyForecastDecodesPollenAndDoesNotPromoteItToCurrent() {
        val local=json.decodeFromString<LocalCheckResponse>("""{"allergens":{},"forecast_daily":[{"day":"2026-09-23","temp_high_c":30,"pollen_overall_level":"moderate","pollen_overall_index":3,"pollen_grass_level":"moderate","pollen_grass_index":3,"pollen_weed_index":0,"pollen_source":"google-pollen:forecast","pollen_updated_at":"2026-09-22T02:00:00Z"}]}""")
        assertTrue(localConditionSections(snapshot(local))[3].metrics.isEmpty())
        val forecast=localForecastMetrics(snapshot(local)).single()
        assertTrue(forecast.detail!!.contains("Pollen forecast (2026-09-23 UTC)"))
        assertTrue(forecast.detail!!.contains("Grass 3 / 5"))
        assertTrue(forecast.detail!!.contains("Weed 0 / 5"))
    }
    @Test fun timestampAloneDoesNotAddPollenToDailyForecast() {
        val local=json.decodeFromString<LocalCheckResponse>("""{"weather":{"temp_c":30},"air":{"aqi":47},"allergens":{},"forecast_daily":[{"day":"2026-09-22","pollen_updated_at":"2026-09-22T01:00:00Z","pollen_overall_index":null}]}""")
        assertFalse(localForecastMetrics(snapshot(local)).single().detail!!.contains("Pollen forecast"))
        assertEquals("86°F",localWeatherMetrics(snapshot(local)).first().value)
        assertEquals("47 AQI",localWeatherMetrics(snapshot(local)).last().value)
    }
}
