package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.PatternsResponse

class PatternsRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val cache: PatternsCache,
) {
    suspend fun cached(accountId: String): PatternsSnapshot? {
        val cached = cache.read(accountId) ?: return null
        return PatternsSnapshot(
            patterns = cached.patterns,
            source = PatternsSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refreshSummary(accountId: String): PatternsSnapshot {
        val summary = authenticatedRequest {
            apiClient.patternsSummary(authRepository.accessToken())
        }
        val current = cache.read(accountId)?.patterns
        val merged = summary.copy(
            emergingPatterns = current?.emergingPatterns.orEmpty(),
            bodySignalsPatterns = current?.bodySignalsPatterns.orEmpty(),
        )
        return save(accountId, merged)
    }

    suspend fun refreshFull(accountId: String): PatternsSnapshot {
        val patterns = authenticatedRequest {
            apiClient.patterns(authRepository.accessToken())
        }
        return save(accountId, patterns)
    }

    suspend fun clear(accountId: String) {
        cache.clear(accountId)
    }

    private suspend fun save(
        accountId: String,
        patterns: PatternsResponse,
    ): PatternsSnapshot {
        val savedAt = System.currentTimeMillis()
        cache.write(accountId, patterns, savedAt)
        return PatternsSnapshot(
            patterns = patterns,
            source = PatternsSource.NETWORK,
            savedAtEpochMillis = savedAt,
        )
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

data class PatternsSnapshot(
    val patterns: PatternsResponse,
    val source: PatternsSource,
    val savedAtEpochMillis: Long,
)

enum class PatternsSource {
    CACHE,
    NETWORK,
}
