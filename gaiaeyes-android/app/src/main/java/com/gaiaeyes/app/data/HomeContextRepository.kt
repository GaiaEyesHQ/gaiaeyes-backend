package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import com.gaiaeyes.app.core.network.CurrentSymptomDeleteData
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.CurrentSymptomUpdateRequest
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

    suspend fun cachedLocal(accountId: String): LocalWeatherSnapshot? {
        val cached = cache.readLocal(accountId) ?: return null
        return LocalWeatherSnapshot(
            location = cached.location,
            local = cached.local,
            source = HomeContextSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refreshLocal(accountId: String): LocalWeatherSnapshot {
        val location = authenticatedRequest {
            apiClient.profileLocation(authRepository.accessToken())
        }
        val local = location
            ?.takeUnless { it.localInsightsEnabled == false }
            ?.zip
            ?.trim()
            ?.takeIf(String::isNotEmpty)
            ?.let { apiClient.localCheck(it) }
        val savedAt = System.currentTimeMillis()
        cache.writeLocal(accountId, location, local, savedAt)
        return LocalWeatherSnapshot(
            location = location,
            local = local,
            source = HomeContextSource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
    }

    suspend fun updateCurrentSymptom(
        accountId: String,
        episodeId: String,
        request: CurrentSymptomUpdateRequest,
    ): Pair<CurrentSymptomItem, CurrentSymptomsSnapshot> {
        val item = authenticatedRequest {
            apiClient.updateCurrentSymptom(authRepository.accessToken(), episodeId, request)
        }
        return item to refreshSymptoms(accountId)
    }

    suspend fun deleteCurrentSymptom(
        accountId: String,
        episodeId: String,
    ): Pair<CurrentSymptomDeleteData, CurrentSymptomsSnapshot> {
        val result = authenticatedRequest {
            apiClient.deleteCurrentSymptom(authRepository.accessToken(), episodeId)
        }
        return result to refreshSymptoms(accountId)
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

data class LocalWeatherSnapshot(
    val location: com.gaiaeyes.app.core.network.ProfileLocation?,
    val local: com.gaiaeyes.app.core.network.LocalCheckResponse?,
    val source: HomeContextSource,
    val savedAtEpochMillis: Long,
)

enum class HomeContextSource {
    CACHE,
    NETWORK,
}
