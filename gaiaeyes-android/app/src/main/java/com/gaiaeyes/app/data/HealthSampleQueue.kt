package com.gaiaeyes.app.data

import android.content.Context
import com.gaiaeyes.app.core.network.HealthSampleUpload
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

class HealthSampleQueue(
    context: Context,
) {
    private val root = File(context.noBackupFilesDir, "health_sample_queue")
    private val mutex = Mutex()
    private val json = Json {
        encodeDefaults = true
        ignoreUnknownKeys = true
    }

    suspend fun enqueue(accountId: String, batch: PendingHealthSampleBatch) = mutex.withLock {
        withContext(Dispatchers.IO) {
            val directory = accountDirectory(accountId).apply { mkdirs() }
            val target = File(directory, "${batch.createdAtEpochMillis}_${batch.id}.json")
            val temporary = File(directory, "${target.name}.pending")
            temporary.writeText(json.encodeToString(batch))
            check(temporary.renameTo(target)) { "Health data could not be queued" }
        }
    }

    suspend fun read(accountId: String): List<PendingHealthSampleBatch> = mutex.withLock {
        withContext(Dispatchers.IO) {
            accountDirectory(accountId)
                .listFiles { file -> file.isFile && file.extension == "json" }
                ?.sortedBy(File::getName)
                ?.mapNotNull { file ->
                    runCatching {
                        json.decodeFromString<PendingHealthSampleBatch>(file.readText())
                    }.getOrNull()
                }
                .orEmpty()
        }
    }

    suspend fun remove(accountId: String, id: String) = mutex.withLock {
        withContext(Dispatchers.IO) {
            accountDirectory(accountId)
                .listFiles { file -> file.isFile && file.name.endsWith("_${id}.json") }
                ?.forEach { file -> check(file.delete()) { "Health data queue could not advance" } }
        }
    }

    suspend fun clear(accountId: String) = mutex.withLock {
        withContext(Dispatchers.IO) {
            accountDirectory(accountId).deleteRecursively()
        }
    }

    private fun accountDirectory(accountId: String): File {
        val safeAccount = accountId.filter(Char::isLetterOrDigit)
        return File(root, safeAccount)
    }
}

@Serializable
data class PendingHealthSampleBatch(
    val id: String,
    val samples: List<HealthSampleUpload>,
    val createdAtEpochMillis: Long,
)
