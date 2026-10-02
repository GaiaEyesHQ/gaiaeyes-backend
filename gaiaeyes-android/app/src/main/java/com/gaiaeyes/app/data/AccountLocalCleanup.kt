package com.gaiaeyes.app.data

import kotlinx.coroutines.CancellationException

/** Try every account-scoped store, but never report success if any store failed. Retries are idempotent. */
internal suspend fun clearAccountLocalData(account: String, stores: List<suspend (String) -> Unit>) {
    var failed = false
    for (clear in stores) {
        try {
            clear(account)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            failed = true
        }
    }
    check(!failed) { "Local account cleanup is incomplete" }
}
