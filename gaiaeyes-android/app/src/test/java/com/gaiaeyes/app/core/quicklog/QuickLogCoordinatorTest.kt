package com.gaiaeyes.app.core.quicklog

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuickLogCoordinatorTest {
    @Test
    fun parsesMigraineActionAndDeepLink() {
        assertEquals(
            QuickLogKind.MIGRAINE,
            parseQuickLogAction(ACTION_LOG_MIGRAINE, null),
        )
        assertEquals(
            QuickLogKind.MIGRAINE,
            parseQuickLogAction("android.intent.action.VIEW", "gaiaeyes://log/migraine/"),
        )
    }

    @Test
    fun ignoresAuthAndUnknownDeepLinks() {
        assertNull(
            parseQuickLogAction(
                "android.intent.action.VIEW",
                "gaiaeyes://auth/callback",
            ),
        )
        assertNull(parseQuickLogAction("android.intent.action.MAIN", null))
    }

    @Test
    fun suppressesDuplicateDeliveriesForShortWindow() {
        var now = 1_000L
        val coordinator = QuickLogCoordinator(nowEpochMillis = { now })

        assertTrue(coordinator.offer(QuickLogKind.MIGRAINE))
        val first = coordinator.pending.value
        coordinator.consume(requireNotNull(first).id)

        now += 10_000L
        assertFalse(coordinator.offer(QuickLogKind.MIGRAINE))

        now += 6_000L
        assertTrue(coordinator.offer(QuickLogKind.MIGRAINE))
        assertEquals(now, coordinator.pending.value?.requestedAtEpochMillis)
    }
}
