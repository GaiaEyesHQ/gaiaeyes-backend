package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

// Prompt-independent medicine PATCH using the same account/cancellation boundaries
// as the accepted follow-up repository. No SDK startup, cache or automatic retry.
internal class MigraineMedicineRepository(
    private val currentAccountId: () -> String?,
    private val accessToken: suspend () -> String,
    private val read: suspend (String, String) -> MigraineDetail,
    private val patch: suspend (String, String, MigraineStructuredEdit) -> MigraineDetail,
    private val signOut: suspend () -> Unit,
) {
    constructor(auth: AuthRepository, api: GaiaApiClient) : this(
        auth::currentAccountId, auth::accessToken, api::migraineDetail,
        api::updateMigraineDetail, auth::signOut,
    )

    suspend fun detail(accountId: String, episodeId: String, selection: () -> Unit): MigraineDetail =
        authorized(accountId, selection) { read(it, episodeId) }

    suspend fun save(accountId: String, episodeId: String, request: MigraineStructuredEdit,
        selection: () -> Unit, onDispatch: () -> Unit): MigraineDetail = authorized(accountId, selection) {
        onDispatch()
        patch(it, episodeId, request)
    }

    private suspend fun <T> authorized(accountId: String, selection: () -> Unit, operation: suspend (String) -> T): T {
        suspend fun checkScope() {
            currentCoroutineContext().ensureActive()
            selection()
            if (currentAccountId() != accountId) throw CancellationException("Account changed")
        }
        checkScope()
        val token = accessToken()
        checkScope()
        val result = try { operation(token) }
        catch (error: ApiUnauthorizedException) { checkScope(); signOut(); throw error }
        checkScope()
        return result
    }
}
