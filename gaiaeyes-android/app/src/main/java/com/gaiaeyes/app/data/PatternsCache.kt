package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.PatternsResponse
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.patternsDataStore by preferencesDataStore(name = "patterns_cache")

class PatternsCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): CachedPatterns? {
        val encoded = context.patternsDataStore.data.first()[cacheKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedPatterns>(encoded)
        }.getOrNull()
    }

    suspend fun write(
        accountId: String,
        patterns: PatternsResponse,
        savedAtEpochMillis: Long,
    ) {
        context.patternsDataStore.edit { preferences ->
            preferences[cacheKey(accountId)] = json.encodeToString(
                CachedPatterns(
                    patterns = patterns,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.patternsDataStore.edit { preferences ->
            preferences.remove(cacheKey(accountId))
        }
    }

    private fun cacheKey(accountId: String) =
        stringPreferencesKey("patterns_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class CachedPatterns(
    val patterns: PatternsResponse,
    val savedAtEpochMillis: Long,
)
