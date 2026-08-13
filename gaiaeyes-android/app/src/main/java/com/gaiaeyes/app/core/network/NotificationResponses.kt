package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NotificationPreferencesEnvelope(
    val ok: Boolean = false,
    val preferences: NotificationPreferences = NotificationPreferences(),
    val error: String? = null,
)

@Serializable
data class NotificationPreferences(
    val enabled: Boolean = false,
    @SerialName("signal_alerts_enabled") val signalAlertsEnabled: Boolean = true,
    @SerialName("local_condition_alerts_enabled") val localConditionAlertsEnabled: Boolean = true,
    @SerialName("personalized_gauge_alerts_enabled") val personalizedGaugeAlertsEnabled: Boolean = true,
    @SerialName("symptom_followups_enabled") val symptomFollowupsEnabled: Boolean = false,
    @SerialName("symptom_followup_push_enabled") val symptomFollowupPushEnabled: Boolean = false,
    @SerialName("symptom_followup_cadence") val symptomFollowupCadence: String = "balanced",
    @SerialName("symptom_followup_states") val symptomFollowupStates: List<String> = listOf("new", "ongoing", "improving", "worse"),
    @SerialName("symptom_followup_symptom_codes") val symptomFollowupSymptomCodes: List<String> = emptyList(),
    @SerialName("daily_checkins_enabled") val dailyCheckinsEnabled: Boolean = false,
    @SerialName("daily_checkin_push_enabled") val dailyCheckinPushEnabled: Boolean = false,
    @SerialName("daily_checkin_cadence") val dailyCheckinCadence: String = "balanced",
    @SerialName("daily_checkin_reminder_time") val dailyCheckinReminderTime: String = "20:00",
    @SerialName("quiet_hours_enabled") val quietHoursEnabled: Boolean = false,
    @SerialName("quiet_start") val quietStart: String = "22:00",
    @SerialName("quiet_end") val quietEnd: String = "08:00",
    @SerialName("time_zone") val timeZone: String = "UTC",
    val sensitivity: String = "normal",
    val families: Map<String, Boolean> = defaultNotificationFamilies,
) {
    fun asUpdate() = NotificationPreferencesUpdate(
        enabled, signalAlertsEnabled, localConditionAlertsEnabled, personalizedGaugeAlertsEnabled,
        symptomFollowupsEnabled, symptomFollowupPushEnabled, symptomFollowupCadence,
        symptomFollowupStates, symptomFollowupSymptomCodes, dailyCheckinsEnabled,
        dailyCheckinPushEnabled, dailyCheckinCadence, dailyCheckinReminderTime,
        quietHoursEnabled, quietStart, quietEnd, timeZone, sensitivity, families,
    )
}

@Serializable
data class NotificationPreferencesUpdate(
    val enabled: Boolean,
    @SerialName("signal_alerts_enabled") val signalAlertsEnabled: Boolean,
    @SerialName("local_condition_alerts_enabled") val localConditionAlertsEnabled: Boolean,
    @SerialName("personalized_gauge_alerts_enabled") val personalizedGaugeAlertsEnabled: Boolean,
    @SerialName("symptom_followups_enabled") val symptomFollowupsEnabled: Boolean,
    @SerialName("symptom_followup_push_enabled") val symptomFollowupPushEnabled: Boolean,
    @SerialName("symptom_followup_cadence") val symptomFollowupCadence: String,
    @SerialName("symptom_followup_states") val symptomFollowupStates: List<String>,
    @SerialName("symptom_followup_symptom_codes") val symptomFollowupSymptomCodes: List<String>,
    @SerialName("daily_checkins_enabled") val dailyCheckinsEnabled: Boolean,
    @SerialName("daily_checkin_push_enabled") val dailyCheckinPushEnabled: Boolean,
    @SerialName("daily_checkin_cadence") val dailyCheckinCadence: String,
    @SerialName("daily_checkin_reminder_time") val dailyCheckinReminderTime: String,
    @SerialName("quiet_hours_enabled") val quietHoursEnabled: Boolean,
    @SerialName("quiet_start") val quietStart: String,
    @SerialName("quiet_end") val quietEnd: String,
    @SerialName("time_zone") val timeZone: String,
    val sensitivity: String,
    val families: Map<String, Boolean>,
)

@Serializable
data class PushTokenRequest(
    val platform: String = "android",
    @SerialName("device_token") val deviceToken: String,
    @SerialName("app_version") val appVersion: String? = null,
    val environment: String,
    val enabled: Boolean = true,
)

@Serializable
data class PushTokenDisableRequest(@SerialName("device_token") val deviceToken: String)

@Serializable
data class PushTokenEnvelope(val ok: Boolean = false, val error: String? = null)

val defaultNotificationFamilies = mapOf(
    "geomagnetic" to true, "solar_wind" to true, "flare_cme_sep" to true,
    "schumann" to true, "pressure" to true, "aqi" to true, "temp" to true,
    "gauge_spikes" to true, "symptom_followups" to false, "daily_checkins" to false,
)
