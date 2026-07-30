package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.FeaturesTodayResponse
import com.gaiaeyes.app.core.network.GaiaApiClient

class BodyRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: BodyCache,
) {
    suspend fun cached(accountId: String): BodySnapshot? {
        val cached = cache.read(accountId) ?: return null
        return BodySnapshot(
            features = cached.features,
            source = BodySource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refresh(accountId: String): BodySnapshot {
        val features = try {
            apiClient.featuresToday(authRepository.accessToken())
        } catch (unauthorized: ApiUnauthorizedException) {
            authRepository.signOut()
            throw unauthorized
        }
        val savedAt = System.currentTimeMillis()
        cache.write(accountId, features, savedAt)
        return BodySnapshot(
            features = features,
            source = BodySource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
    }

    suspend fun clear(accountId: String) {
        cache.clear(accountId)
    }
}

data class BodySnapshot(
    val features: FeaturesTodayResponse,
    val source: BodySource,
    val savedAtEpochMillis: Long,
)

enum class BodySource {
    CACHE,
    NETWORK,
}
