package com.gaiaeyes.app.core.work

import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import org.junit.Assert.assertEquals
import org.junit.Test

class JournalDrainWorkerTest {
    @Test
    fun succeedsWhenThereIsNoSignedInAccount() {
        assertEquals(
            JournalDrainDisposition.SUCCESS,
            journalDrainDisposition(hasAccount = false),
        )
    }

    @Test
    fun succeedsWhenTheQueueIsEmpty() {
        assertEquals(
            JournalDrainDisposition.SUCCESS,
            journalDrainDisposition(hasAccount = true, pendingCount = 0),
        )
    }

    @Test
    fun retriesWhenWritesRemainPending() {
        assertEquals(
            JournalDrainDisposition.RETRY,
            journalDrainDisposition(hasAccount = true, pendingCount = 2),
        )
    }

    @Test
    fun retriesTransientFailures() {
        assertEquals(
            JournalDrainDisposition.RETRY,
            journalDrainDisposition(
                hasAccount = true,
                error = IllegalStateException("offline"),
            ),
        )
    }

    @Test
    fun doesNotRetryAnExpiredSession() {
        assertEquals(
            JournalDrainDisposition.SUCCESS,
            journalDrainDisposition(
                hasAccount = true,
                error = ApiUnauthorizedException(),
            ),
        )
    }
}
