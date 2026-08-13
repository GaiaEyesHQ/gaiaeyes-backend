package com.gaiaeyes.app.core.notifications

import android.content.Intent
import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class NotificationNavigationCoordinator {
    private val _pending = MutableStateFlow<NotificationNavigationRequest?>(null)
    val pending: StateFlow<NotificationNavigationRequest?> = _pending.asStateFlow()

    fun handleIntent(intent: Intent): Boolean {
        val destination = parseNotificationDestination(intent.dataString) ?: return false
        _pending.value = NotificationNavigationRequest(
            id = UUID.randomUUID().toString(),
            destination = destination,
        )
        return true
    }

    fun consume(requestId: String) {
        if (_pending.value?.id == requestId) {
            _pending.value = null
        }
    }
}

data class NotificationNavigationRequest(
    val id: String,
    val destination: NotificationDestination,
)

enum class NotificationDestination {
    HOME,
    CURRENT_SYMPTOMS,
    DAILY_CHECK_IN,
    EXPLORE,
}

internal fun parseNotificationDestination(data: String?): NotificationDestination? {
    val uri = runCatching { URI(data?.trim().orEmpty()) }.getOrNull() ?: return null
    if (uri.scheme?.lowercase() != "gaiaeyes" || uri.host?.lowercase() != "mission-control") {
        return null
    }
    val family = uri.rawQuery
        ?.split('&')
        ?.firstOrNull { it.substringBefore('=') == "family" }
        ?.substringAfter('=', "")
        ?.let { URLDecoder.decode(it, StandardCharsets.UTF_8.name()) }
        ?.lowercase()

    return when (family) {
        "symptom_followups" -> NotificationDestination.CURRENT_SYMPTOMS
        "daily_checkins" -> NotificationDestination.DAILY_CHECK_IN
        "geomagnetic", "solar_wind", "flare_cme_sep", "schumann", "pressure", "aqi", "temp" ->
            NotificationDestination.EXPLORE
        else -> NotificationDestination.HOME
    }
}
