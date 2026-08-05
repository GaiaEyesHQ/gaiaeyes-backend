package com.gaiaeyes.app.core.network

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileResponsesTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesSharedOnboardingPreferences() {
        val envelope = json.decodeFromString<ProfilePreferencesEnvelope>(
            """
            {
              "ok": true,
              "preferences": {
                "mode": "scientific",
                "guide": "cat",
                "tone": "balanced",
                "temp_unit": "F",
                "onboarding_step": "location",
                "onboarding_completed": false
              }
            }
            """.trimIndent(),
        )

        assertTrue(envelope.ok)
        assertEquals("scientific", envelope.preferences.mode)
        assertEquals("F", envelope.preferences.tempUnit)
        assertEquals("location", envelope.preferences.onboardingStep)
        assertFalse(envelope.preferences.onboardingCompleted)
    }

    @Test
    fun decodesHealthContextCatalogAndIgnoresFutureFields() {
        val envelope = json.decodeFromString<ProfileTagCatalogEnvelope>(
            """
            {
              "ok": true,
              "items": [
                {
                  "tag_key": "migraine",
                  "label": "Migraine",
                  "description": "Diagnosed or suspected migraine.",
                  "section": "health_context",
                  "is_active": true,
                  "future_field": "ignored"
                }
              ]
            }
            """.trimIndent(),
        )

        assertTrue(envelope.ok)
        assertEquals("migraine", envelope.items.single().tagKey)
        assertEquals("Migraine", envelope.items.single().label)
        assertEquals("health_context", envelope.items.single().section)
        assertTrue(envelope.items.single().isActive)
    }

    @Test
    fun decodesSelectedSharedProfileTags() {
        val envelope = json.decodeFromString<ProfileTagsEnvelope>(
            """{"ok":true,"tags":["migraine","fibromyalgia"]}""",
        )

        assertEquals(listOf("migraine", "fibromyalgia"), envelope.tags)
    }

    @Test
    fun encodesDeviceLocationForSharedProfile() {
        val encoded = json.encodeToJsonElement(
            ProfileLocationUpdate.serializer(),
            ProfileLocationUpdate(
                zip = "78754",
                lat = 30.35,
                lon = -97.65,
                useGps = true,
                localInsightsEnabled = true,
            ),
        ).jsonObject

        assertEquals("78754", encoded.getValue("zip").jsonPrimitive.content)
        assertEquals("30.35", encoded.getValue("lat").jsonPrimitive.content)
        assertEquals("-97.65", encoded.getValue("lon").jsonPrimitive.content)
        assertEquals("true", encoded.getValue("use_gps").jsonPrimitive.content)
        assertEquals("true", encoded.getValue("local_insights_enabled").jsonPrimitive.content)
    }
}
