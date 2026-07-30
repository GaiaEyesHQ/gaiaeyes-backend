package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import com.gaiaeyes.app.core.network.GaiaApiClient

class HomeContextRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: HomeContextCache,
) {
    suspend fun cachedSymptoms(accountId: String): CurrentSymptomsSnapshot? {
        val cached = cache.readSymptoms(accountId) ?: return null
        return CurrentSymptomsSnapshot(
            symptoms = cached.symptoms,
            source = HomeContextSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refreshSymptoms(accountId: String): CurrentSymptomsSnapshot {
        val symptoms = authenticatedRequest {
            apiClient.currentSymptoms(authRepository.accessToken())
        }
        val savedAt = System.currentTimeMillis()
        cache.writeSymptoms(accountId, symptoms, savedAt)
        return CurrentSymptomsSnapshot(
            symptoms = symptoms,
            source = HomeContextSource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
    }

    suspend fun cachedDrivers(accountId: String): DriversSnapshot? {
        val cached = cache.readDrivers(accountId) ?: return null
        return DriversSnapshot(
            drivers = cached.drivers,
            source = HomeContextSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refreshDrivers(accountId: String): DriversSnapshot {
        val drivers = authenticatedRequest {
            apiClient.allDrivers(authRepository.accessToken())
        }
        val savedAt = System.currentTimeMillis()
        cache.writeDrivers(accountId, drivers, savedAt)
        return DriversSnapshot(
            drivers = drivers,
            source = HomeContextSource.NETWORK,
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

data class CurrentSymptomsSnapshot(
    val symptoms: CurrentSymptomsResponse,
    val source: HomeContextSource,
    val savedAtEpochMillis: Long,
)

data class DriversSnapshot(
    val drivers: AllDriversResponse,
    val source: HomeContextSource,
    val savedAtEpochMillis: Long,
)

enum class HomeContextSource {
    CACHE,
    NETWORK,
}
