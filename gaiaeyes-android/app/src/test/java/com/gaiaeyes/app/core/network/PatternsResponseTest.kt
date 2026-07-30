package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PatternsResponseTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesTheExistingPatternsContract() {
        val response = json.decodeFromString<PatternsResponse>(
            """
            {
              "ok": true,
              "partial": false,
              "generatedAt": "2026-07-30T15:00:00Z",
              "disclaimer": "Patterns do not diagnose or prove causes.",
              "strongestPatterns": [{
                "signalKey": "pressure_swing_exposed",
                "signal": "Pressure swings",
                "outcomeKey": "migraine_day",
                "outcome": "Migraine",
                "explanation": "In your history, migraine days overlapped more with pressure swings.",
                "confidence": "Strong",
                "sampleSize": 31,
                "lagHours": 24,
                "lagLabel": "next day",
                "relativeLift": 2.4,
                "exposedRate": 0.48,
                "unexposedRate": 0.20,
                "usedToday": true,
                "usedTodayLabel": "Active now",
                "voiceSemantic": {
                  "interpretation": {
                    "headerSummary": "Pressure swings have overlapped more with migraine days.",
                    "evidenceSummary": "2.4x more common when exposed",
                    "baselineSummary": "When exposed: 48% • When not exposed: 20%",
                    "activeTodaySummary": "Pressure swings are active today."
                  }
                }
              }],
              "emergingPatterns": [],
              "bodySignalsPatterns": [],
              "voiceSemantics": {
                "overview": {
                  "interpretation": {
                    "headerSummary": "1 clearer pattern stands out in your history right now.",
                    "strongestSubtitle": "The clearest repeats in your history so far."
                  }
                }
              },
              "futureField": "ignored"
            }
            """.trimIndent(),
        )

        assertTrue(response.ok)
        assertFalse(response.partial)
        assertEquals("Migraine", response.strongestPatterns.single().outcome)
        assertTrue(response.strongestPatterns.single().usedToday)
        assertEquals(
            "2.4x more common when exposed",
            response.strongestPatterns.single().voiceSemantic?.interpretation?.evidenceSummary,
        )
        assertEquals(
            "1 clearer pattern stands out in your history right now.",
            response.voiceSemantics?.overview?.interpretation?.headerSummary,
        )
    }
}
