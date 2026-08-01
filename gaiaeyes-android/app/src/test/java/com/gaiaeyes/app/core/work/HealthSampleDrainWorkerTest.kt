package com.gaiaeyes.app.core.work

import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import org.junit.Assert.assertEquals
import org.junit.Test

class HealthSampleDrainWorkerTest {
    @Test
    fun succeedsWithoutAnAccountOrPendingBatches() {
        assertEquals(
            HealthSampleDrainDisposition.SUCCESS,
            healthSampleDrainDisposition(hasAccount = false),
        )
        assertEquals(
            HealthSampleDrainDisposition.SUCCESS,
            healthSampleDrainDisposition(hasAccount = true, pendingCount = 0),
        )
    }

    @Test
    fun retriesPendingBatchesAndTransientFailures() {
        assertEquals(
            HealthSampleDrainDisposition.RETRY,
            healthSampleDrainDisposition(hasAccount = true, pendingCount = 1),
        )
        assertEquals(
            HealthSampleDrainDisposition.RETRY,
            healthSampleDrainDisposition(
                hasAccount = true,
                error = IllegalStateException("offline"),
            ),
        )
    }

    @Test
    fun doesNotRetryAnExpiredSession() {
        assertEquals(
            HealthSampleDrainDisposition.SUCCESS,
            healthSampleDrainDisposition(
                hasAccount = true,
                error = ApiUnauthorizedException(),
            ),
        )
    }
}
