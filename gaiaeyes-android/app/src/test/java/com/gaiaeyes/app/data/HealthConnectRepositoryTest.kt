package com.gaiaeyes.app.data

import androidx.health.connect.client.records.SleepSessionRecord
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HealthConnectRepositoryTest {
    @Test
    fun mapsCompatibleSleepStagesToSharedBackendVocabulary() {
        assertEquals("awake", healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_AWAKE))
        assertEquals("core", healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_LIGHT))
        assertEquals("deep", healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_DEEP))
        assertEquals("rem", healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_REM))
        assertEquals("asleep", healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_SLEEPING))
        assertNull(healthConnectSleepStage(SleepSessionRecord.STAGE_TYPE_OUT_OF_BED))
    }
}
