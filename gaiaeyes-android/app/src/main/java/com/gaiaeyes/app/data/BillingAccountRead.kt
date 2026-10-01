package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.BillingEntitlementsResponse
import java.time.Instant
import kotlinx.coroutines.CancellationException

internal suspend fun readBillingForAccount(
    accountId: String,
    currentAccountId: () -> String?,
    accessToken: suspend () -> String,
    refreshAccessToken: suspend () -> String,
    fetch: suspend (String) -> BillingEntitlementsResponse,
    now: Instant = Instant.now(),
): Boolean {
    fun requireAccount() {
        if (currentAccountId() != accountId) throw CancellationException("Billing account changed")
    }
    suspend fun read(token: String): BillingEntitlementsResponse {
        requireAccount()
        check(token.isNotBlank()) { "Billing session unavailable" }
        return fetch(token).also { requireAccount() }
    }
    requireAccount()
    val response = try {
        read(accessToken())
    } catch (_: ApiUnauthorizedException) {
        requireAccount()
        read(refreshAccessToken())
    }
    check(response.ok && response.userId == accountId) { "Billing response did not match the account" }
    return response.entitlements.any { it.providesPlus(now) }
}
