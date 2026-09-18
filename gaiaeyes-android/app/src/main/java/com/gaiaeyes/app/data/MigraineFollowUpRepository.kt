package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

// Injectable external calls; the production constructor uses the accepted client.
// No cache, automatic retry, SDK initialization, or alternate endpoint.
internal class MigraineFollowUpRepository(
    private val currentAccountId: () -> String?,
    private val accessToken: suspend () -> String,
    private val read: suspend (String, String) -> MigraineDetail,
    private val respond: suspend (String, String, String, MigraineFollowUpRequest) -> MigraineFollowUpResult,
    private val signOut: suspend () -> Unit,
) {
    constructor(auth: AuthRepository, api: GaiaApiClient) : this(
        auth::currentAccountId, auth::accessToken, api::migraineDetail,
        api::respondMigraineFollowUp, auth::signOut,
    )

    suspend fun detail(accountId: String, episodeId: String, requireSelection: () -> Unit): MigraineDetail =
        authorized(accountId, requireSelection) { read(it, episodeId) }

    suspend fun save(
        accountId: String, episodeId: String, promptId: String,
        request: MigraineFollowUpRequest, requireSelection: () -> Unit, onDispatch: () -> Unit,
    ): MigraineFollowUpResult = authorized(accountId, requireSelection) {
        onDispatch()
        respond(it, episodeId, promptId, request)
    }

    private suspend fun <T> authorized(
        accountId: String, requireSelection: () -> Unit, operation: suspend (String) -> T,
    ): T {
        suspend fun checkScope() {
            currentCoroutineContext().ensureActive()
            requireSelection()
            if (currentAccountId() != accountId) throw kotlinx.coroutines.CancellationException("Account changed")
        }
        checkScope()
        val token = accessToken()
        checkScope()
        val result = try { operation(token) }
        catch (error: ApiUnauthorizedException) {
            checkScope() // An old/cancelled request must not sign out a new account.
            signOut()
            throw error
        }
        checkScope()
        return result
    }
}
