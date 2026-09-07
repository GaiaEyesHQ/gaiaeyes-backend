package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.ExplorePayload
import com.gaiaeyes.app.core.network.SchumannLatestResponse
import com.gaiaeyes.app.core.network.SchumannQuality
import com.gaiaeyes.app.data.ExploreSnapshot
import com.gaiaeyes.app.data.ExploreSource
import org.junit.Assert.assertEquals
import org.junit.Test

class ExplorePresentationTest {
    @Test
    fun keepsEveryExploreDestinationVisibleWhenOnlyOneSourceLoads() {
        val snapshot = ExploreSnapshot(
            payload = ExplorePayload(
                schumann = SchumannLatestResponse(
                    ok = true,
                    quality = SchumannQuality(usable = true),
                ),
            ),
            source = ExploreSource.NETWORK,
            savedAtEpochMillis = 1L,
        )

        val summaries = exploreSignalSummaries(snapshot)

        assertEquals(
            listOf(
                ExploreDetail.SPACE_WEATHER,
                ExploreDetail.MAGNETOSPHERE,
                ExploreDetail.SCHUMANN,
                ExploreDetail.EARTHQUAKES,
                ExploreDetail.HAZARDS,
            ),
            summaries.map { it.detail },
        )
        assertEquals("Unavailable", summaries.first().status)
        assertEquals("Available", summaries[2].status)
        assertEquals("Unavailable", summaries.last().status)
    }

    @Test
    fun marksReusedSourceAsSavedInsteadOfLive() {
        val snapshot = ExploreSnapshot(
            payload = ExplorePayload(
                schumann = SchumannLatestResponse(
                    ok = true,
                    quality = SchumannQuality(usable = true),
                ),
            ),
            source = ExploreSource.NETWORK,
            savedAtEpochMillis = 1L,
            unavailableSources = listOf("Schumann Resonance"),
        )

        val schumann = exploreSignalSummaries(snapshot)
            .first { it.detail == ExploreDetail.SCHUMANN }

        assertEquals("Saved", schumann.status)
        assertEquals(true, exploreSourceUnavailable(ExploreDetail.SCHUMANN, snapshot))
    }

    @Test
    fun showsUpdatingBeforeMissingSourcesResolve() {
        val summaries = exploreSignalSummaries(snapshot = null, isLoading = true)

        assertEquals(5, summaries.size)
        assertEquals(setOf("Updating"), summaries.map { it.status }.toSet())
    }
}
