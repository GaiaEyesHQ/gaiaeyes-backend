package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ExploreResponsesTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun decodesMagnetosphereAndSolarWindReadings() {
        val response = json.decodeFromString<MagnetosphereResponse>(
            """
            {
              "ok": true,
              "data": {
                "ts": "2026-08-11T14:20:00Z",
                "kpis": {
                  "r0_re": 10.4,
                  "geo_risk": "quiet",
                  "storminess": "watch",
                  "lpp_re": 5.2,
                  "kp": 2.7
                },
                "sw": {"n_cm3": 6.8, "v_kms": 442.0, "bz_nt": -3.1}
              }
            }
            """.trimIndent(),
        )

        assertTrue(response.ok)
        assertEquals(2.7, response.data?.kpis?.kp ?: 0.0, 0.001)
        assertEquals(442.0, response.data?.solarWind?.speedKms ?: 0.0, 0.001)
        assertEquals(6.8, response.data?.solarWind?.densityCm3 ?: 0.0, 0.001)
    }

    @Test
    fun decodesSchumannQuakeAndHazardContracts() {
        val schumann = json.decodeFromString<SchumannLatestResponse>(
            """
            {
              "ok": true,
              "generated_at": "2026-08-11T14:20:00Z",
              "harmonics": {"f0": 7.83},
              "amplitude": {"sr_total_0_20": 11.2},
              "quality": {"primary_source": "tomsk", "usable": true, "quality_score": 0.91},
              "fusion": {"enabled": true, "display_f0_hz": 7.81, "display_f0_source": "fusion"}
            }
            """.trimIndent(),
        )
        val quakes = json.decodeFromString<QuakesLatestResponse>(
            """{"ok":true,"item":{"day":"2026-08-11","all_quakes":221,"m4p":18,"m5p":3}}""",
        )
        val hazards = json.decodeFromString<HazardsResponse>(
            """
            {
              "ok": true,
              "generated_at": "2026-08-11T14:20:00Z",
              "items": [{"id":"event-1","title":"Flooding","kind":"flood","location":"Region","severity":"severe"}]
            }
            """.trimIndent(),
        )

        assertEquals(7.81, schumann.fusion.displayF0Hz ?: 0.0, 0.001)
        assertEquals(18, quakes.item?.magnitude4Plus)
        assertEquals("Flooding", hazards.items.single().title)
    }
}
