package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.OutlookResponse
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.outlookDataStore by preferencesDataStore(name = "outlook_cache")

class OutlookCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): CachedOutlook? {
        val encoded = context.outlookDataStore.data.first()[cacheKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedOutlook>(encoded)
        }.getOrNull()
    }

    suspend fun write(
        accountId: String,
        outlook: OutlookResponse,
        savedAtEpochMillis: Long,
    ) {
        context.outlookDataStore.edit { preferences ->
            preferences[cacheKey(accountId)] = json.encodeToString(
                CachedOutlook(
                    outlook = outlook,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.outlookDataStore.edit { preferences ->
            preferences.remove(cacheKey(accountId))
        }
    }

    private fun cacheKey(accountId: String) =
        stringPreferencesKey("outlook_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class CachedOutlook(
    val outlook: OutlookResponse,
    val savedAtEpochMillis: Long,
)
