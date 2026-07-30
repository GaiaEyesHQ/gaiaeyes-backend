package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.OutlookResponse

class OutlookRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: OutlookCache,
) {
    suspend fun cached(accountId: String): OutlookSnapshot? {
        val cached = cache.read(accountId) ?: return null
        return OutlookSnapshot(
            outlook = cached.outlook,
            source = OutlookSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refresh(accountId: String): OutlookSnapshot {
        val outlook = authenticatedRequest {
            apiClient.userOutlook(authRepository.accessToken())
        }
        val savedAt = System.currentTimeMillis()
        cache.write(accountId, outlook, savedAt)
        return OutlookSnapshot(
            outlook = outlook,
            source = OutlookSource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
    }

    suspend fun clear(accountId: String) {
        cache.clear(accountId)
    }

    private suspend fun <T> authenticatedRequest(block: suspend () -> T): T {
        return try {
            block()
        } catch (unauthorized: ApiUnauthorizedException) {
            authRepository.signOut()
            throw unauthorized
        }
    }
}

data class OutlookSnapshot(
    val outlook: OutlookResponse,
    val source: OutlookSource,
    val savedAtEpochMillis: Long,
)

enum class OutlookSource {
    CACHE,
    NETWORK,
}
