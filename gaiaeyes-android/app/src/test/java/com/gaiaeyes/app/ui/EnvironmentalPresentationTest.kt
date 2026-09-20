package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import java.time.Instant
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class EnvironmentalPresentationTest {
    private val json = Json { ignoreUnknownKeys = true }
    private val now = Instant.parse("2026-09-20T16:06:00Z")
    private fun snapshot(payload: ExplorePayload, source: ExploreSource = ExploreSource.NETWORK) = ExploreSnapshot(payload, source, now.toEpochMilli())
    private fun text(name: String) = javaClass.getResource("/environment/$name.json")!!.readText()

    @Test fun realSchumannAndTomskPayloadsKeepSeparateValuesAndTimes() {
        val panel = environmentalPanel(ExploreDetail.SCHUMANN, snapshot(ExplorePayload(
            schumann = json.decodeFromString(text("schumann-latest")), tomsk = json.decodeFromString(text("tomsk-latest")),
        )), now)
        assertEquals("Current", panel.readings[0].status)
        assertEquals("7.89 Hz", panel.readings[0].metrics.first().second)
        assertEquals("Stale", panel.readings[1].status)
        assertEquals("7.75 Hz", panel.readings[1].metrics.first().second)
        assertNotEquals(panel.readings[0].timestamp, panel.readings[1].timestamp)
    }
    @Test fun realUlfPayloadWithoutOkEnvelopeDisplaysBothStationsAndUnits() {
        val panel = environmentalPanel(ExploreDetail.ULF, snapshot(ExplorePayload(ulf = json.decodeFromString(text("ulf-latest")))), now)
        assertEquals(3, panel.readings.size)
        assertEquals("Current", panel.readings.first().status)
        assertTrue(panel.readings.first().metrics.contains("Activity" to "Quiet"))
        assertTrue(panel.readings[1].metrics.any { it.second.endsWith("nT/s") })
        assertTrue(panel.readings.first().source.contains("BOU / CMO"))
    }
    @Test fun emptyResponseNeverSubstitutesNominalFrequencyOrClaimsCurrent() {
        val panel = environmentalPanel(ExploreDetail.SCHUMANN, snapshot(ExplorePayload(schumann = SchumannLatestResponse(ok = true))), now)
        assertFalse(panel.hasReadings)
        assertEquals("No readings", panel.readings.first().status)
        assertTrue(panel.readings.all { it.metrics.isEmpty() })
    }
    @Test fun fusedTomskNumberWithoutItsOwnTimestampIsNotLabeledAsCumiana() {
        val panel = environmentalPanel(ExploreDetail.SCHUMANN, snapshot(ExplorePayload(schumann = SchumannLatestResponse(ok = true, generatedAt = now.toString(), fusion = SchumannFusion(displayF0Hz = 7.9, displayF0Source = "tomsk")))), now)
        assertFalse(panel.hasReadings)
    }
    @Test fun freshnessDoesNotUseNetworkFetchTimeAndSurvivesCacheRoundTrip() {
        val p = ExplorePayload(schumann = SchumannLatestResponse(ok = true, generatedAt = "2026-09-19T12:00:00Z", harmonics = SchumannHarmonics(f0 = 7.8)), sourceErrors = mapOf("Schumann Resonance" to "request_failed"), fetchedAt = mapOf("Schumann Resonance" to now.toEpochMilli()))
        val decoded = json.decodeFromString<ExplorePayload>(json.encodeToString(p))
        assertEquals("Saved · Stale", environmentalPanel(ExploreDetail.SCHUMANN, snapshot(decoded), now).readings.first().status)
    }
    @Test fun missingFutureAndOffsetTimestampsAreNotSilentlyFresh() {
        assertEquals("Time unknown", environmentalStatus(true, null, 30, false, null, now))
        assertEquals("Time unverified", environmentalStatus(true, "2026-09-21T12:00:00Z", 30, false, null, now))
        assertEquals("Current", environmentalStatus(true, "2026-09-20T10:55:00-05:00", 30, false, null, now))
        assertEquals("Saved · Current", environmentalStatus(true, now.toString(), 30, true, null, now))
    }
    @Test fun malformedHistoryPointsAreFilteredZeroValuesPreservedAndSorted() {
        val p = ExplorePayload(spaceHistory = json.decodeFromString("""{"ok":true,"data":{"series24":{"bz":[["bad",8],["2026-09-20T16:05:00Z",0],["2026-09-20T16:00:00Z","-2.3"],["2026-09-20T15:00:00Z",null],["short"]]}}}"""))
        assertEquals(listOf(-2.3, 0.0), spaceHistoryPoints(p, "bz").map { it.v })
    }
    @Test fun historyPopulatesSpaceWeatherWhenMagnetosphereFailsAndEachMetricUsesOwnTime() {
        val history = json.decodeFromString<SpaceHistoryResponse>("""{"ok":true,"data":{"series24":{"kp":[["2026-09-20T15:00:00Z",2.0]],"sw":[["2026-09-20T16:00:00Z",410]],"bz":[["2026-09-19T12:00:00Z",-3.4]]}}}""")
        val panel = environmentalPanel(ExploreDetail.SPACE_WEATHER, snapshot(ExplorePayload(spaceHistory = history, sourceErrors = mapOf("Magnetosphere" to "sign_in_required"))), now)
        assertEquals(listOf("Current", "Current", "Stale", "Sign-in required"), panel.readings.map { it.status })
        assertEquals("410 km/s", panel.readings[1].metrics.single().second)
    }
    @Test fun valueWithoutTimestampRemainsVisibleButNeverCurrent() {
        val panel = environmentalPanel(ExploreDetail.SPACE_WEATHER, snapshot(ExplorePayload(
            magnetosphere = MagnetosphereResponse(true, MagnetosphereData(solarWind = MagnetosphereSolarWind(speedKms = 420.0))),
        )), now)
        assertEquals("420 km/s", panel.readings[1].metrics.single().second)
        assertEquals("Time unknown", panel.readings[1].status)
    }
    @Test fun onePointHistoryAndMissingReadingsAreDistinct() {
        val panel = environmentalPanel(ExploreDetail.SCHUMANN, snapshot(ExplorePayload(schumannSeries = SchumannSeriesResponse(true, listOf(SchumannSeriesRow(now.toString(), SchumannHarmonics(f0 = 7.9)))))), now)
        assertFalse(panel.hasReadings)
        assertEquals(1, panel.charts.first().points.size)
        assertEquals("Current", panel.charts.first().status)
    }
    @Test fun qualityFlagsAreVisibleWithoutHidingProvisionalValues() {
        val panel = environmentalPanel(ExploreDetail.ULF, snapshot(ExplorePayload(ulf = UlfLatestResponse(UlfContext(timestamp = now.toString(), intensity = 0.0, qualityFlags = listOf("low_history", "missing_samples"))))), now)
        assertTrue(panel.hasReadings)
        assertTrue(panel.readings.first().note!!.contains("Baseline still building"))
        assertTrue(panel.readings.first().note!!.contains("missing"))
    }
}
