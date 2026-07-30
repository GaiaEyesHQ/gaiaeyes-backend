package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.GaiaApiClient

class DashboardRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: DashboardCache,
) {
    suspend fun cached(accountId: String): DashboardSnapshot? {
        val cached = cache.read(accountId) ?: return null
        return DashboardSnapshot(
            dashboard = cached.dashboard,
            source = DashboardSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refresh(accountId: String): DashboardSnapshot {
        val token = authRepository.accessToken()
        val dashboard = try {
            apiClient.dashboardGauges(token)
        } catch (unauthorized: ApiUnauthorizedException) {
            authRepository.signOut()
            throw unauthorized
        }
        val savedAt = System.currentTimeMillis()
        cache.write(accountId, dashboard, savedAt)
        return DashboardSnapshot(
            dashboard = dashboard,
            source = DashboardSource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
    }

    suspend fun clear(accountId: String) {
        cache.clear(accountId)
    }
}

data class DashboardSnapshot(
    val dashboard: DashboardGaugesResponse,
    val source: DashboardSource,
    val savedAtEpochMillis: Long,
)

enum class DashboardSource {
    CACHE,
    NETWORK,
}
