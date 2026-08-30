package com.gaiaeyes.app.core.auth

import android.content.Context
import android.content.Intent
import io.github.jan.supabase.SupabaseClient
import io.github.jan.supabase.auth.Auth
import io.github.jan.supabase.auth.FlowType
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.auth.handleDeeplinks
import io.github.jan.supabase.auth.providers.builtin.OTP
import io.github.jan.supabase.auth.status.SessionStatus
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.logging.LogLevel
import kotlin.time.Clock
import kotlin.time.Duration.Companion.minutes
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map

class AuthRepository(
    context: Context,
    supabaseUrl: String,
    supabaseAnonKey: String,
) {
    private val projectUrl = normalizeSupabaseProjectUrl(supabaseUrl)

    private val client: SupabaseClient? =
        if (projectUrl.isBlank() || supabaseAnonKey.isBlank()) {
            null
        } else {
            createSupabaseClient(projectUrl, supabaseAnonKey) {
                defaultLogLevel = LogLevel.NONE
                install(Auth) {
                    scheme = DEEP_LINK_SCHEME
                    host = DEEP_LINK_HOST
                    defaultRedirectUrl = MAGIC_LINK_REDIRECT
                    flowType = FlowType.IMPLICIT
                    alwaysAutoRefresh = true
                    autoLoadFromStorage = true
                    autoSaveToStorage = true
                    sessionManager = EncryptedSessionManager(context.applicationContext)
                }
            }
        }

    val authState: Flow<AuthState> = client?.auth?.sessionStatus?.map(::mapSessionStatus)
        ?: flowOf(AuthState.Unavailable)

    private val _deepLinkError = MutableStateFlow<String?>(null)
    val deepLinkError: StateFlow<String?> = _deepLinkError.asStateFlow()

    val isConfigured: Boolean
        get() = client != null

    suspend fun sendMagicLink(email: String) {
        val authClient = requireClient()
        authClient.auth.signInWith(
            provider = OTP,
            redirectUrl = MAGIC_LINK_REDIRECT,
        ) {
            this.email = email.trim()
            createUser = true
        }
    }

    suspend fun signInAnonymously() {
        requireClient().auth.signInAnonymously()
    }

    suspend fun addEmailToCurrentAccount(email: String) {
        requireClient().auth.updateUser(
            redirectUrl = MAGIC_LINK_REDIRECT,
        ) {
            this.email = email.trim()
        }
    }

    fun handleDeepLink(intent: Intent) {
        _deepLinkError.value = null
        client?.handleDeeplinks(
            intent = intent,
            onError = { error ->
                _deepLinkError.value =
                    error.message ?: "The sign-in link could not be completed"
            },
        )
    }

    fun clearDeepLinkError() {
        _deepLinkError.value = null
    }

    suspend fun accessToken(): String {
        val auth = requireClient().auth
        var session = auth.currentSessionOrNull()
            ?: error("Sign in before loading private Gaia Eyes data")
        if (session.expiresAt <= Clock.System.now() + REFRESH_WINDOW) {
            auth.refreshCurrentSession()
            session = auth.currentSessionOrNull()
                ?: error("Your Gaia Eyes session could not be refreshed")
        }
        return session.accessToken
    }

    suspend fun refreshAccessToken(): String {
        val auth = requireClient().auth
        auth.currentSessionOrNull()
            ?: error("Sign in before refreshing your Gaia Eyes session")
        auth.refreshCurrentSession()
        return auth.currentSessionOrNull()?.accessToken
            ?: error("Your Gaia Eyes session could not be refreshed")
    }

    fun currentAccountId(): String? = client?.auth?.currentUserOrNull()?.id

    suspend fun signOut() {
        client?.auth?.signOut()
    }

    private fun requireClient(): SupabaseClient {
        return client ?: error("Supabase is not configured for this Android build")
    }

    private fun mapSessionStatus(status: SessionStatus): AuthState {
        return when (status) {
            SessionStatus.Initializing -> AuthState.Initializing
            is SessionStatus.NotAuthenticated -> AuthState.SignedOut
            is SessionStatus.RefreshFailure -> AuthState.SessionProblem(
                "Your session needs attention. Check your connection and try again.",
            )
            is SessionStatus.Authenticated -> {
                val user = status.session.user
                if (user == null) {
                    AuthState.Initializing
                } else {
                    AuthState.SignedIn(
                        accountId = user.id,
                        email = user.email,
                        isAnonymous = isAnonymousAccountEmail(user.email),
                    )
                }
            }
        }
    }

    private companion object {
        const val DEEP_LINK_SCHEME = "gaiaeyes"
        const val DEEP_LINK_HOST = "auth"
        const val MAGIC_LINK_REDIRECT = "gaiaeyes://auth/callback"
        val REFRESH_WINDOW = 2.minutes
    }
}

internal fun normalizeSupabaseProjectUrl(value: String): String {
    return value
        .trim()
        .trimEnd('/')
        .removeSuffix("/rest/v1")
        .trimEnd('/')
}

internal fun isAnonymousAccountEmail(email: String?): Boolean = email.isNullOrBlank()

sealed interface AuthState {
    data object Initializing : AuthState
    data object SignedOut : AuthState
    data object Unavailable : AuthState
    data class SessionProblem(val message: String) : AuthState
    data class SignedIn(
        val accountId: String,
        val email: String?,
        val isAnonymous: Boolean = false,
    ) : AuthState
}
