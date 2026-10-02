package com.gaiaeyes.app.core.auth

import android.content.Context
import android.content.Intent
import com.gaiaeyes.app.data.AccountOperationGate
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
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

// Open session boundary permits an isolated synthetic implementation without starting the SDK.
open class AuthRepository(
    context: Context,
    supabaseUrl: String,
    supabaseAnonKey: String,
    val accountOperations: AccountOperationGate? = null,
) {
    private val projectUrl = normalizeSupabaseProjectUrl(supabaseUrl)
    private var deletingLocalSessionFor: String? = null

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
                    sessionManager = EncryptedSessionManager(context.applicationContext) {
                        // clearSession suspends while clearing the SDK verifier cache first.
                        // Recheck identity at the actual encrypted-session deletion boundary.
                        deletingLocalSessionFor?.let { expected ->
                            check(currentAccountId() == expected) { "The signed-in account changed" }
                        }
                    }
                }
            }
        }

    open val authState: Flow<AuthState> = client?.auth?.sessionStatus?.map(::mapSessionStatus)
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
        trackAccountOperation(checkNotNull(currentAccountId()))
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

    open suspend fun accessToken(): String {
        val account = checkNotNull(currentAccountId())
        trackAccountOperation(account)
        return tokenForAccountDeletion(account).also { requireActiveAccount(account) }
    }

    // The deletion controller must authenticate while ordinary account operations are paused.
    suspend fun tokenForAccountDeletion(account: String): String {
        check(currentAccountId() == account) { "The signed-in account changed" }
        val auth = requireClient().auth
        var session = auth.currentSessionOrNull()
            ?: error("Sign in before loading private Gaia Eyes data")
        if (session.expiresAt <= Clock.System.now() + REFRESH_WINDOW) {
            auth.refreshCurrentSession()
            session = auth.currentSessionOrNull()
                ?: error("Your Gaia Eyes session could not be refreshed")
        }
        currentCoroutineContext().ensureActive()
        check(currentAccountId() == account && session.user?.id == account) { "The signed-in account changed" }
        return session.accessToken
    }

    open suspend fun refreshAccessToken(): String {
        val account = checkNotNull(currentAccountId())
        trackAccountOperation(account)
        val auth = requireClient().auth
        auth.currentSessionOrNull()
            ?: error("Sign in before refreshing your Gaia Eyes session")
        auth.refreshCurrentSession()
        requireActiveAccount(account)
        return auth.currentSessionOrNull()?.accessToken
            ?: error("Your Gaia Eyes session could not be refreshed")
    }

    open fun currentAccountId(): String? = client?.auth?.currentUserOrNull()?.id

    suspend fun trackAccountOperation(account: String) {
        requireActiveAccount(account)
        accountOperations?.track(account)
        requireActiveAccount(account)
    }

    suspend fun requireActiveAccount(account: String) {
        currentCoroutineContext().ensureActive()
        check(currentAccountId() == account) { "The signed-in account changed" }
        accountOperations?.requireActive(account)
    }

    suspend fun clearLocalSessionForDeletion(account: String) {
        if (currentAccountId() != account) return
        // No network logout: the backend has already removed this Auth user.
        deletingLocalSessionFor = account
        try {
            requireClient().auth.clearSession()
        } finally {
            deletingLocalSessionFor = null
        }
    }

    open suspend fun signOut() {
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
