package com.gaiaeyes.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.gaiaeyes.app.core.network.DailyCheckInRequest
import com.gaiaeyes.app.core.network.ExposureEventRequest
import com.gaiaeyes.app.core.network.SymptomEventRequest
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.journalWriteDataStore by preferencesDataStore(name = "journal_write_queue")

class JournalWriteQueue(
    private val context: Context,
) {
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun read(accountId: String): List<PendingJournalWrite> {
        val encoded = context.journalWriteDataStore.data.first()[queueKey(accountId)]
            ?: return emptyList()
        return runCatching {
            json.decodeFromString<List<PendingJournalWrite>>(encoded)
        }.getOrDefault(emptyList())
    }

    suspend fun enqueue(accountId: String, item: PendingJournalWrite) {
        write(accountId, read(accountId) + item)
    }

    suspend fun remove(accountId: String, id: String) {
        write(accountId, read(accountId).filterNot { it.id == id })
    }

    suspend fun clear(accountId: String) {
        context.journalWriteDataStore.edit { preferences ->
            preferences.remove(queueKey(accountId))
        }
    }

    private suspend fun write(accountId: String, items: List<PendingJournalWrite>) {
        context.journalWriteDataStore.edit { preferences ->
            preferences[queueKey(accountId)] = json.encodeToString(items)
        }
    }

    private fun queueKey(accountId: String) =
        stringPreferencesKey("journal_${accountId.filter(Char::isLetterOrDigit)}")
}

@Serializable
data class PendingJournalWrite(
    val id: String,
    val kind: JournalWriteKind,
    val symptom: SymptomEventRequest? = null,
    val exposure: ExposureEventRequest? = null,
    val dailyCheckIn: DailyCheckInRequest? = null,
    val createdAtEpochMillis: Long,
)

@Serializable
enum class JournalWriteKind {
    SYMPTOM,
    EXPOSURE,
    DAILY_CHECK_IN,
}
