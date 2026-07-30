package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.FeaturesTodayResponse
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.bodyDataStore by preferencesDataStore(name = "body_cache")

class BodyCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): CachedBody? {
        val encoded = context.bodyDataStore.data.first()[cacheKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedBody>(encoded)
        }.getOrNull()
    }

    suspend fun write(
        accountId: String,
        features: FeaturesTodayResponse,
        savedAtEpochMillis: Long,
    ) {
        context.bodyDataStore.edit { preferences ->
            preferences[cacheKey(accountId)] = json.encodeToString(
                CachedBody(
                    features = features,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.bodyDataStore.edit { preferences ->
            preferences.remove(cacheKey(accountId))
        }
    }

    private fun cacheKey(accountId: String) =
        stringPreferencesKey("features_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class CachedBody(
    val features: FeaturesTodayResponse,
    val savedAtEpochMillis: Long,
)
