package com.gaiaeyes.app.core.network

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

class HealthSampleResponsesTest {
    @Test
    fun encodesAndroidHealthConnectProvenanceForSharedSampleEndpoint() {
        val sample = HealthSampleUpload(
            user_id = "user-1",
            device_os = "android",
            source = "health_connect",
            type = "spo2",
            start_time = "2026-08-01T12:00:00Z",
            end_time = "2026-08-01T12:00:00Z",
            value = 97.0,
            unit = "%",
        )

        val encoded = Json.parseToJsonElement(Json.encodeToString(sample)).jsonObject

        assertEquals("android", encoded.getValue("device_os").jsonPrimitive.content)
        assertEquals("health_connect", encoded.getValue("source").jsonPrimitive.content)
        assertEquals("spo2", encoded.getValue("type").jsonPrimitive.content)
        assertEquals("%", encoded.getValue("unit").jsonPrimitive.content)
    }
}
