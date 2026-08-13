package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.ExplorePayload
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.exploreDataStore by preferencesDataStore(name = "explore_cache")

class ExploreCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): CachedExplore? {
        val encoded = context.exploreDataStore.data.first()[key(accountId)] ?: return null
        return runCatching { json.decodeFromString<CachedExplore>(encoded) }.getOrNull()
    }

    suspend fun write(accountId: String, payload: ExplorePayload, savedAtEpochMillis: Long) {
        context.exploreDataStore.edit { preferences ->
            preferences[key(accountId)] = json.encodeToString(
                CachedExplore(payload = payload, savedAtEpochMillis = savedAtEpochMillis),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.exploreDataStore.edit { preferences -> preferences.remove(key(accountId)) }
    }

    private fun key(accountId: String) =
        stringPreferencesKey("explore_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class CachedExplore(
    val payload: ExplorePayload,
    val savedAtEpochMillis: Long,
)
