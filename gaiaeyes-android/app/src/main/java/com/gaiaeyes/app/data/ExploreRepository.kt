package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.ExplorePayload
import com.gaiaeyes.app.core.network.GaiaApiClient
import kotlinx.coroutines.async
import kotlinx.coroutines.supervisorScope

class ExploreRepository(
    private val apiClient: GaiaApiClient,
    private val cache: ExploreCache,
) {
    suspend fun cached(accountId: String): ExploreSnapshot? {
        val cached = cache.read(accountId) ?: return null
        return ExploreSnapshot(
            payload = cached.payload,
            source = ExploreSource.CACHE,
            savedAtEpochMillis = cached.savedAtEpochMillis,
        )
    }

    suspend fun refresh(accountId: String): ExploreSnapshot = supervisorScope {
        val previous = cache.read(accountId)?.payload
        val magnetosphere = async { runCatching { apiClient.magnetosphere() } }
        val schumann = async { runCatching { apiClient.schumannLatest() } }
        val quakes = async { runCatching { apiClient.quakesLatest() } }
        val hazards = async { runCatching { apiClient.hazards() } }

        val magnetosphereResult = magnetosphere.await()
        val schumannResult = schumann.await()
        val quakesResult = quakes.await()
        val hazardsResult = hazards.await()
        val failures = buildList {
            if (magnetosphereResult.isFailure) add("magnetosphere")
            if (schumannResult.isFailure) add("Schumann Resonance")
            if (quakesResult.isFailure) add("earthquakes")
            if (hazardsResult.isFailure) add("hazards")
        }
        val payload = ExplorePayload(
            magnetosphere = magnetosphereResult.getOrNull()?.takeIf { it.ok }
                ?: previous?.magnetosphere,
            schumann = schumannResult.getOrNull()?.takeIf { it.ok }
                ?: previous?.schumann,
            quakes = quakesResult.getOrNull()?.takeIf { it.ok }
                ?: previous?.quakes,
            hazards = hazardsResult.getOrNull()?.takeIf { it.ok }
                ?: previous?.hazards,
        )
        check(
            payload.magnetosphere != null || payload.schumann != null ||
                payload.quakes != null || payload.hazards != null,
        ) { "Explore data was unavailable" }

        val savedAt = System.currentTimeMillis()
        cache.write(accountId, payload, savedAt)
        ExploreSnapshot(
            payload = payload,
            source = ExploreSource.NETWORK,
            savedAtEpochMillis = savedAt,
            unavailableSources = failures,
        )
    }

    suspend fun clear(accountId: String) = cache.clear(accountId)
}

data class ExploreSnapshot(
    val payload: ExplorePayload,
    val source: ExploreSource,
    val savedAtEpochMillis: Long,
    val unavailableSources: List<String> = emptyList(),
)

enum class ExploreSource {
    CACHE,
    NETWORK,
}
