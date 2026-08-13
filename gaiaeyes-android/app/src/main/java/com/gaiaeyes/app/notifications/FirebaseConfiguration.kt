package com.gaiaeyes.app.notifications

import android.content.Context
import com.gaiaeyes.app.BuildConfig
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

object FirebaseConfiguration {
    val isConfigured: Boolean
        get() = listOf(
            BuildConfig.FIREBASE_PROJECT_ID,
            BuildConfig.FIREBASE_APPLICATION_ID,
            BuildConfig.FIREBASE_API_KEY,
            BuildConfig.FIREBASE_GCM_SENDER_ID,
        ).all(String::isNotBlank)

    fun initialize(context: Context): Boolean {
        if (!isConfigured) return false
        if (FirebaseApp.getApps(context).isEmpty()) {
            FirebaseApp.initializeApp(
                context,
                FirebaseOptions.Builder()
                    .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                    .setApplicationId(BuildConfig.FIREBASE_APPLICATION_ID)
                    .setApiKey(BuildConfig.FIREBASE_API_KEY)
                    .setGcmSenderId(BuildConfig.FIREBASE_GCM_SENDER_ID)
                    .build(),
            )
        }
        return FirebaseApp.getApps(context).isNotEmpty()
    }
}
