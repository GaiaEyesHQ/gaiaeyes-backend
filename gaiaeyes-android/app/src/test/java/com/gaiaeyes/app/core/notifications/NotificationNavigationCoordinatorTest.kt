package com.gaiaeyes.app.core.notifications

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NotificationNavigationCoordinatorTest {
    @Test
    fun `routes notification families to relevant surfaces`() {
        assertEquals(
            NotificationDestination.CURRENT_SYMPTOMS,
            parseNotificationDestination("gaiaeyes://mission-control?family=symptom_followups"),
        )
        assertEquals(
            NotificationDestination.DAILY_CHECK_IN,
            parseNotificationDestination("gaiaeyes://mission-control?family=daily_checkins"),
        )
        assertEquals(
            NotificationDestination.EXPLORE,
            parseNotificationDestination("gaiaeyes://mission-control?family=solar_wind"),
        )
        assertEquals(
            NotificationDestination.HOME,
            parseNotificationDestination("gaiaeyes://mission-control?family=recovery"),
        )
    }

    @Test
    fun `ignores non-notification deep links`() {
        assertNull(parseNotificationDestination("gaiaeyes://log/migraine"))
        assertNull(parseNotificationDestination("https://gaiaeyes.com"))
        assertNull(parseNotificationDestination(null))
    }
}
