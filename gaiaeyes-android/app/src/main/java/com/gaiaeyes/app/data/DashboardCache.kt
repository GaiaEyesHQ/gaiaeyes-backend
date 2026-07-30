package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.dashboardDataStore by preferencesDataStore(name = "dashboard_cache")

class DashboardCache(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): CachedDashboard? {
        val encoded = context.dashboardDataStore.data.first()[cacheKey(accountId)] ?: return null
        return runCatching {
            json.decodeFromString<CachedDashboard>(encoded)
        }.getOrNull()
    }

    suspend fun write(
        accountId: String,
        dashboard: DashboardGaugesResponse,
        savedAtEpochMillis: Long,
    ) {
        context.dashboardDataStore.edit { preferences ->
            preferences[cacheKey(accountId)] = json.encodeToString(
                CachedDashboard(
                    dashboard = dashboard,
                    savedAtEpochMillis = savedAtEpochMillis,
                ),
            )
        }
    }

    suspend fun clear(accountId: String) {
        context.dashboardDataStore.edit { preferences ->
            preferences.remove(cacheKey(accountId))
        }
    }

    private fun cacheKey(accountId: String) =
        stringPreferencesKey("gauges_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class CachedDashboard(
    val dashboard: DashboardGaugesResponse,
    val savedAtEpochMillis: Long,
)
