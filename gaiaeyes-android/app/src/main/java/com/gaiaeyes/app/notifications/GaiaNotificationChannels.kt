package com.gaiaeyes.app.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build

object GaiaNotificationChannels {
    const val ALERTS_CHANNEL_ID = "gaia_alerts"

    fun ensureCreated(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        context.getSystemService(NotificationManager::class.java)
            .createNotificationChannel(
                NotificationChannel(
                    ALERTS_CHANNEL_ID,
                    "Gaia Eyes alerts",
                    NotificationManager.IMPORTANCE_DEFAULT,
                ),
            )
    }
}
