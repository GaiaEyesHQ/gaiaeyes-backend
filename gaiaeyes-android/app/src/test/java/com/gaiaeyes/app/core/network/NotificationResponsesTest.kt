package com.gaiaeyes.app.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationResponsesTest {
    @Test
    fun preferenceUpdatePreservesAndroidAlertChoices() {
        val preferences = NotificationPreferences(
            enabled = true,
            signalAlertsEnabled = false,
            localConditionAlertsEnabled = true,
            personalizedGaugeAlertsEnabled = false,
            symptomFollowupsEnabled = true,
            symptomFollowupPushEnabled = true,
            dailyCheckinsEnabled = true,
            dailyCheckinPushEnabled = true,
            timeZone = "America/Chicago",
            families = defaultNotificationFamilies +
                mapOf("symptom_followups" to true, "daily_checkins" to true),
        )

        val update = preferences.asUpdate()

        assertTrue(update.enabled)
        assertFalse(update.signalAlertsEnabled)
        assertTrue(update.localConditionAlertsEnabled)
        assertFalse(update.personalizedGaugeAlertsEnabled)
        assertTrue(update.symptomFollowupsEnabled)
        assertTrue(update.dailyCheckinsEnabled)
        assertEquals("America/Chicago", update.timeZone)
        assertTrue(update.families.getValue("symptom_followups"))
        assertTrue(update.families.getValue("daily_checkins"))
    }
}
