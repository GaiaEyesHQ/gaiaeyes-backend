package com.gaiaeyes.app.core.network

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class JournalResponsesTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesServerDrivenCatalogsAndDailyTargetDay() {
        val symptomCatalog = json.decodeFromString<SymptomCodeEnvelope>(
            """
            {
              "ok": true,
              "data": [{
                "symptom_code": "MIGRAINE",
                "label": "Migraine",
                "description": "Migraine attack",
                "is_active": true
              }]
            }
            """.trimIndent(),
        )
        val exposureCatalog = json.decodeFromString<ExposureCatalogEnvelope>(
            """
            {
              "ok": true,
              "data": [{
                "exposure_key": "rapid_temperature_change",
                "label": "Rapid temperature change"
              }]
            }
            """.trimIndent(),
        )
        val status = json.decodeFromString<DailyCheckInStatusEnvelope>(
            """
            {
              "ok": true,
              "data": {
                "target_day": "2026-07-30",
                "prompt": {
                  "id": "prompt-1",
                  "day": "2026-07-30",
                  "question_text": "How did today feel?"
                },
                "future_field": "ignored"
              }
            }
            """.trimIndent(),
        )

        assertEquals("MIGRAINE", symptomCatalog.data.single().symptomCode)
        assertEquals(
            "rapid_temperature_change",
            exposureCatalog.data.single().exposureKey,
        )
        assertEquals("2026-07-30", status.data?.targetDay)
        assertEquals("prompt-1", status.data?.prompt?.id)
    }

    @Test
    fun encodesStableClientTimestampsForRetrySafeWrites() {
        val symptom = SymptomEventRequest(
            symptomCode = "MIGRAINE",
            timestampUtc = "2026-07-30T15:00:00Z",
            severity = 6,
            note = "Light sensitivity",
            tags = listOf("android"),
        )
        val exposure = ExposureEventRequest(
            exposureKey = "rapid_temperature_change",
            intensity = 2,
            timestampUtc = "2026-07-30T15:01:00Z",
            note = "Cold room to outdoor heat",
        )

        val symptomJson = json.parseToJsonElement(json.encodeToString(symptom)).jsonObject
        val exposureJson = json.parseToJsonElement(json.encodeToString(exposure)).jsonObject

        assertEquals(
            "2026-07-30T15:00:00Z",
            symptomJson.getValue("ts_utc").jsonPrimitive.content,
        )
        assertEquals(
            "2026-07-30T15:01:00Z",
            exposureJson.getValue("event_ts_utc").jsonPrimitive.content,
        )
        assertEquals("android", symptomJson.getValue("tags").toString().trim('[', ']', '"'))
        assertTrue(exposureJson.containsKey("note_text"))
    }

    @Test
    fun encodesDailyCheckInUsingSharedBackendFieldNames() {
        val request = DailyCheckInRequest(
            promptId = "prompt-1",
            day = "2026-07-30",
            comparedToYesterday = "same",
            energyLevel = "manageable",
            usableEnergy = "enough",
            systemLoad = "moderate",
            painLevel = "a_little",
            moodLevel = "calm",
            note = null,
            completedAt = "2026-07-30T15:02:00Z",
        )

        val encoded = json.parseToJsonElement(json.encodeToString(request)).jsonObject

        assertEquals("same", encoded.getValue("compared_to_yesterday").jsonPrimitive.content)
        assertEquals("manageable", encoded.getValue("energy_level").jsonPrimitive.content)
        assertEquals("enough", encoded.getValue("usable_energy").jsonPrimitive.content)
        assertEquals("moderate", encoded.getValue("system_load").jsonPrimitive.content)
        assertEquals("a_little", encoded.getValue("pain_level").jsonPrimitive.content)
        assertEquals("calm", encoded.getValue("mood_level").jsonPrimitive.content)
    }
}
