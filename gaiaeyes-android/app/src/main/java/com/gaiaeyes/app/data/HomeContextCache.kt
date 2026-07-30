package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.AllDriversResponse
import com.gaiaeyes.app.core.network.CurrentSymptomsResponse
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.homeContextDataStore by preferencesDataStore(name = "home_context_cache")

class HomeContextCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun readSymptoms(accountId: String): CachedCurrentSymptoms? {
        val encoded = context.homeContextDataStore.data.first()[symptomsKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedCurrentSymptoms>(encoded)
        }.getOrNull()
    }

    suspend fun writeSymptoms(
        accountId: String,
        symptoms: CurrentSymptomsResponse,
        savedAtEpochMillis: Long,
    ) {
        context.homeContextDataStore.edit { preferences ->
            preferences[symptomsKey(accountId)] = json.encodeToString(
                CachedCurrentSymptoms(
                    symptoms = symptoms,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun readDrivers(accountId: String): CachedDrivers? {
        val encoded = context.homeContextDataStore.data.first()[driversKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedDrivers>(encoded)
        }.getOrNull()
    }

    suspend fun writeDrivers(
        accountId: String,
        drivers: AllDriversResponse,
        savedAtEpochMillis: Long,
    ) {
        context.homeContextDataStore.edit { preferences ->
            preferences[driversKey(accountId)] = json.encodeToString(
                CachedDrivers(
                    drivers = drivers,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.homeContextDataStore.edit { preferences ->
            preferences.remove(symptomsKey(accountId))
            preferences.remove(driversKey(accountId))
        }
    }

    private fun symptomsKey(accountId: String) =
        stringPreferencesKey("symptoms_${accountId.cacheSafeKey()}")

    private fun driversKey(accountId: String) =
        stringPreferencesKey("drivers_${accountId.cacheSafeKey()}")
}

private fun String.cacheSafeKey() = filter(Char::isLetterOrDigit)

@Serializable
data class CachedCurrentSymptoms(
    val symptoms: CurrentSymptomsResponse,
    val savedAtEpochMillis: Long,
)

@Serializable
data class CachedDrivers(
    val drivers: AllDriversResponse,
    val savedAtEpochMillis: Long,
)
