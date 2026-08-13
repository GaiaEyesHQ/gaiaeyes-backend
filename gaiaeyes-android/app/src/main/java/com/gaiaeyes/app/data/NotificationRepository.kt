package com.gaiaeyes.app.data

import android.content.Context
import com.gaiaeyes.app.BuildConfig
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.NotificationPreferences
import com.gaiaeyes.app.core.network.NotificationPreferencesUpdate
import com.gaiaeyes.app.core.network.PushTokenDisableRequest
import com.gaiaeyes.app.core.network.PushTokenRequest
import com.gaiaeyes.app.notifications.FirebaseConfiguration
import com.google.firebase.messaging.FirebaseMessaging
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine

class NotificationRepository(
    context: Context,
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
) {
    private val preferences = context.getSharedPreferences("gaia_notifications", Context.MODE_PRIVATE)

    suspend fun loadPreferences(): NotificationPreferences = authenticatedRequest {
        apiClient.notificationPreferences(authRepository.accessToken())
    }

    suspend fun savePreferences(update: NotificationPreferencesUpdate): NotificationPreferences =
        authenticatedRequest {
            apiClient.updateNotificationPreferences(authRepository.accessToken(), update)
        }

    suspend fun registerCurrentToken(): Boolean {
        if (!FirebaseConfiguration.isConfigured) return false
        val token = firebaseToken()
        registerToken(token)
        return true
    }

    suspend fun registerToken(token: String) = authenticatedRequest {
        apiClient.registerPushToken(
            authRepository.accessToken(),
            PushTokenRequest(
                deviceToken = token,
                appVersion = BuildConfig.VERSION_NAME,
                environment = if (BuildConfig.DEBUG) "dev" else "prod",
            ),
        )
        preferences.edit().putString(TOKEN_KEY, token).apply()
    }

    suspend fun disableCurrentToken() {
        val token = preferences.getString(TOKEN_KEY, null) ?: return
        authenticatedRequest {
            apiClient.disablePushToken(authRepository.accessToken(), PushTokenDisableRequest(token))
        }
        preferences.edit().remove(TOKEN_KEY).apply()
    }

    private suspend fun firebaseToken(): String = suspendCancellableCoroutine { continuation ->
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { if (continuation.isActive) continuation.resume(it) }
            .addOnFailureListener { if (continuation.isActive) continuation.resumeWithException(it) }
    }

    private suspend fun <T> authenticatedRequest(block: suspend () -> T): T = try {
        block()
    } catch (unauthorized: ApiUnauthorizedException) {
        authRepository.signOut()
        throw unauthorized
    }

    private companion object {
        const val TOKEN_KEY = "fcm_device_token"
    }
}
