package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.supervisorScope

class ExploreRepository(
    private val apiClient: GaiaApiClient,
    private val cache: ExploreCacheStore,
    private val accessToken: suspend () -> String,
    private val currentAccountId: () -> String?,
) {
    suspend fun cached(accountId: String): ExploreSnapshot? = cache.read(accountId)?.let {
        ExploreSnapshot(it.payload, ExploreSource.CACHE, it.savedAtEpochMillis, it.payload.sourceErrors.keys.toList())
    }

    suspend fun refresh(accountId: String): ExploreSnapshot = supervisorScope {
        fun checkAccount() {
            if (currentAccountId() != accountId) throw CancellationException("Explore account changed")
        }
        checkAccount()
        val previous = cache.read(accountId)?.payload
        // Public sources stay independent even when session acquisition/protected sources fail.
        val token = async { sourceResult { accessToken().also { checkAccount() } } }
        val magnetosphere = async { sourceResult { apiClient.magnetosphere(token.await().getOrThrow()).also { check(it.ok) } } }
        val history = async { sourceResult { apiClient.spaceHistory(token.await().getOrThrow()).also { check(it.ok) } } }
        val schumann = async { sourceResult { apiClient.schumannLatest().also { check(it.ok) } } }
        val schumannSeries = async { sourceResult { apiClient.schumannSeries().also { check(it.ok) } } }
        val tomsk = async { sourceResult { apiClient.tomskLatest().also { check(it.ok) } } }
        val ulf = async { sourceResult { apiClient.ulfLatest() } }
        val ulfSeries = async { sourceResult { apiClient.ulfSeries() } }
        val quakes = async { sourceResult { apiClient.quakesLatest(token.await().getOrThrow()).also { check(it.ok) } } }
        val hazards = async { sourceResult { apiClient.hazards().also { check(it.ok) } } }
        val errors = mutableMapOf<String, String>()
        val fetchedAt = previous?.fetchedAt.orEmpty().toMutableMap()
        val now = System.currentTimeMillis()
        fun <T> merge(name: String, result: Result<T>, old: T?): T? {
            return result.fold(onSuccess = { fetchedAt[name] = now; it }, onFailure = {
                errors[name] = if (it is ApiUnauthorizedException) "sign_in_required" else "request_failed"
                old
            })
        }
        val payload = ExplorePayload(
            magnetosphere = merge("Magnetosphere", magnetosphere.await(), previous?.magnetosphere),
            schumann = merge("Schumann Resonance", schumann.await(), previous?.schumann),
            quakes = merge("Earthquakes", quakes.await(), previous?.quakes),
            hazards = merge("Global Hazards", hazards.await(), previous?.hazards),
            schumannSeries = merge("Schumann history", schumannSeries.await(), previous?.schumannSeries),
            tomsk = merge("Tomsk", tomsk.await(), previous?.tomsk),
            ulf = merge("ULF", ulf.await(), previous?.ulf),
            ulfSeries = merge("ULF history", ulfSeries.await(), previous?.ulfSeries),
            spaceHistory = merge("Space weather history", history.await(), previous?.spaceHistory),
            sourceErrors = errors,
            fetchedAt = fetchedAt,
        )
        checkAccount()
        cache.write(accountId, payload, now)
        checkAccount()
        ExploreSnapshot(payload, ExploreSource.NETWORK, now, errors.keys.toList())
    }

    suspend fun clear(accountId: String) = cache.clear(accountId)
}

private suspend fun <T> sourceResult(block: suspend () -> T): Result<T> = try {
    Result.success(block())
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (failure: Exception) {
    Result.failure(failure)
}

data class ExploreSnapshot(
    val payload: ExplorePayload,
    val source: ExploreSource,
    val savedAtEpochMillis: Long,
    val unavailableSources: List<String> = emptyList(),
)

enum class ExploreSource { CACHE, NETWORK }
