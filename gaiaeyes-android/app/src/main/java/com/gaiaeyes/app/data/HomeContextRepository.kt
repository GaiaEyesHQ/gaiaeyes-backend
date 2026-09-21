package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import com.gaiaeyes.app.core.network.CurrentSymptomDeleteData
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.CurrentSymptomUpdateRequest
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.MigraineDetail
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

class HomeContextRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: HomeContextCache,
) {
    suspend fun cachedSymptoms(accountId: String): CurrentSymptomsSnapshot? {
        val cached = cache.readSymptoms(accountId) ?: return null
        return CurrentSymptomsSnapshot(
            accountId = accountId,
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
            accountId = accountId,
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
        val drivers = readForAccount(accountId, apiClient::allDrivers)
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
        val location = readForAccount(accountId, apiClient::profileLocation)
        val local = location
            ?.takeUnless { it.localInsightsEnabled == false }
            ?.zip
            ?.trim()
            ?.takeIf(String::isNotEmpty)
            ?.let { apiClient.localCheck(it) }
        requireHomeContextAccount(accountId, authRepository::currentAccountId)
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

    internal fun migraineFollowUpRepository() = MigraineFollowUpRepository(authRepository, apiClient)
    internal fun migraineMedicineRepository() = MigraineMedicineRepository(authRepository, apiClient)

    // Read-only, with no disk cache. Token refresh must not move this read to
    // another account, and an old request must never sign out a new account.
    suspend fun savedMigraineDetail(accountId: String, episodeId: String): MigraineDetail =
        savedMigraineDetailFor(
            accountId, episodeId,
            currentAccountId = authRepository::currentAccountId,
            accessToken = authRepository::accessToken,
            readDetail = apiClient::migraineDetail,
            signOut = authRepository::signOut,
        )

    private suspend fun <T> authenticatedRequest(block: suspend () -> T): T {
        return try {
            block()
        } catch (unauthorized: ApiUnauthorizedException) {
            authRepository.signOut()
            throw unauthorized
        }
    }

    private suspend fun <T> readForAccount(accountId: String, read: suspend (String) -> T): T =
        readHomeContextForAccount(accountId, authRepository::currentAccountId,
            authRepository::accessToken, authRepository::signOut, read)
}

internal suspend fun requireHomeContextAccount(accountId: String, currentAccountId: () -> String?) {
    currentCoroutineContext().ensureActive()
    if (currentAccountId() != accountId) throw CancellationException("Account changed")
}

internal suspend fun <T> readHomeContextForAccount(
    accountId: String,
    currentAccountId: () -> String?,
    accessToken: suspend () -> String,
    signOut: suspend () -> Unit,
    read: suspend (String) -> T,
): T {
    requireHomeContextAccount(accountId, currentAccountId)
    val token = accessToken()
    requireHomeContextAccount(accountId, currentAccountId)
    val result = try { read(token) } catch (unauthorized: ApiUnauthorizedException) {
        currentCoroutineContext().ensureActive()
        if (currentAccountId() == accountId) signOut()
        throw unauthorized
    }
    requireHomeContextAccount(accountId, currentAccountId)
    return result
}

// The production saved-summary boundary, with only its external calls injectable.
// Keeps synthetic tests independent of Android storage, real sessions and network.
internal suspend fun savedMigraineDetailFor(
    accountId: String,
    episodeId: String,
    currentAccountId: () -> String?,
    accessToken: suspend () -> String,
    readDetail: suspend (String, String) -> MigraineDetail,
    signOut: suspend () -> Unit,
): MigraineDetail {
    suspend fun requireAccount() {
        currentCoroutineContext().ensureActive()
        if (currentAccountId() != accountId) throw CancellationException("Account changed")
    }
    requireAccount()
    val token = accessToken()
    requireAccount()
    val detail = try {
        readDetail(token, episodeId)
    } catch (unauthorized: ApiUnauthorizedException) {
        currentCoroutineContext().ensureActive()
        if (currentAccountId() == accountId) signOut()
        throw unauthorized
    }
    requireAccount()
    return detail
}

data class CurrentSymptomsSnapshot(
    val accountId: String,
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
