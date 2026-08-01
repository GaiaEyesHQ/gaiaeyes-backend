package com.gaiaeyes.app.data

import android.content.Context
import androidx.activity.result.contract.ActivityResultContract
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.HealthSampleUpload
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class HealthConnectRepository(
    context: Context,
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val queue: HealthSampleQueue,
    private val scheduleBackgroundDrain: () -> Unit = {},
) {
    private val applicationContext = context.applicationContext
    private val drainMutex = Mutex()

    val requiredPermissions: Set<String> = setOf(
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(RestingHeartRateRecord::class),
        HealthPermission.getReadPermission(RespiratoryRateRecord::class),
        HealthPermission.getReadPermission(OxygenSaturationRecord::class),
    )

    fun permissionContract(): ActivityResultContract<Set<String>, Set<String>> =
        PermissionController.createRequestPermissionResultContract()

    suspend fun status(): HealthConnectStatus {
        return when (HealthConnectClient.getSdkStatus(applicationContext)) {
            HealthConnectClient.SDK_UNAVAILABLE -> HealthConnectStatus.UNAVAILABLE
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED ->
                HealthConnectStatus.UPDATE_REQUIRED
            else -> {
                val granted = client().permissionController.getGrantedPermissions()
                if (granted.containsAll(requiredPermissions)) {
                    HealthConnectStatus.READY
                } else {
                    HealthConnectStatus.PERMISSIONS_REQUIRED
                }
            }
        }
    }

    suspend fun importRecent(accountId: String, days: Long = IMPORT_DAYS): HealthConnectImportResult {
        check(status() == HealthConnectStatus.READY) {
            "Connect Health Connect before importing health data"
        }
        val end = Instant.now()
        val start = end.minus(days, ChronoUnit.DAYS)
        val range = TimeRangeFilter.between(start, end)
        val healthClient = client()
        val samples = buildList {
            addAll(readSleepSamples(healthClient, range, accountId))
            addAll(readStepSamples(healthClient, range, accountId))
            addAll(readHeartRateSamples(healthClient, range, accountId))
            addAll(readRestingHeartRateSamples(healthClient, range, accountId))
            addAll(readRespiratoryRateSamples(healthClient, range, accountId))
            addAll(readOxygenSaturationSamples(healthClient, range, accountId))
        }.sortedBy(HealthSampleUpload::start_time)

        samples.chunked(BATCH_SIZE).forEachIndexed { index, batch ->
            queue.enqueue(
                accountId,
                PendingHealthSampleBatch(
                    id = UUID.randomUUID().toString(),
                    samples = batch,
                    createdAtEpochMillis = System.currentTimeMillis() + index,
                ),
            )
        }
        val drain = drain(accountId)
        if (drain.pendingCount > 0) scheduleBackgroundDrain()
        return HealthConnectImportResult(
            importedSampleCount = samples.size,
            deliveredBatchCount = drain.deliveredCount,
            pendingBatchCount = drain.pendingCount,
        )
    }

    suspend fun drain(accountId: String): HealthSampleDrainResult = drainMutex.withLock {
        var delivered = 0
        for (batch in queue.read(accountId)) {
            try {
                apiClient.uploadHealthSamples(
                    accessToken = authRepository.accessToken(),
                    samples = batch.samples,
                )
            } catch (cancellation: CancellationException) {
                throw cancellation
            } catch (unauthorized: ApiUnauthorizedException) {
                authRepository.signOut()
                throw unauthorized
            } catch (_: Throwable) {
                break
            }
            queue.remove(accountId, batch.id)
            delivered += 1
        }
        HealthSampleDrainResult(
            deliveredCount = delivered,
            pendingCount = queue.read(accountId).size,
        )
    }

    suspend fun pendingCount(accountId: String): Int = queue.read(accountId).size

    suspend fun clear(accountId: String) {
        queue.clear(accountId)
    }

    private fun client(): HealthConnectClient = HealthConnectClient.getOrCreate(applicationContext)

    private suspend fun readSleepSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<SleepSessionRecord>(healthClient, range).flatMap { session ->
        buildList {
            add(
                sample(
                    accountId = accountId,
                    type = "sleep_stage",
                    start = session.startTime,
                    end = session.endTime,
                    valueText = "inBed",
                ),
            )
            if (session.stages.isEmpty()) {
                add(
                    sample(
                        accountId = accountId,
                        type = "sleep_stage",
                        start = session.startTime,
                        end = session.endTime,
                        valueText = "asleep",
                    ),
                )
            } else {
                session.stages.mapNotNullTo(this) { stage ->
                    healthConnectSleepStage(stage.stage)?.let { valueText ->
                        sample(
                            accountId = accountId,
                            type = "sleep_stage",
                            start = stage.startTime,
                            end = stage.endTime,
                            valueText = valueText,
                        )
                    }
                }
            }
        }
    }

    private suspend fun readStepSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<StepsRecord>(healthClient, range).mapNotNull { record ->
        record.count.takeIf { it >= 0 }?.let { count ->
            sample(accountId, "step_count", record.startTime, record.endTime, count.toDouble(), "count")
        }
    }

    private suspend fun readHeartRateSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<HeartRateRecord>(healthClient, range).flatMap { record ->
        record.samples.mapNotNull { reading ->
            reading.beatsPerMinute.takeIf { it in 20..250 }?.let { bpm ->
                sample(accountId, "heart_rate", reading.time, reading.time, bpm.toDouble(), "bpm")
            }
        }
    }

    private suspend fun readRestingHeartRateSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<RestingHeartRateRecord>(healthClient, range).mapNotNull { record ->
        record.beatsPerMinute.takeIf { it in 20..180 }?.let { bpm ->
            sample(accountId, "resting_heart_rate", record.time, record.time, bpm.toDouble(), "bpm")
        }
    }

    private suspend fun readRespiratoryRateSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<RespiratoryRateRecord>(healthClient, range).mapNotNull { record ->
        record.rate.takeIf { it in 4.0..80.0 }?.let { rate ->
            sample(accountId, "respiratory_rate", record.time, record.time, rate, "br/min")
        }
    }

    private suspend fun readOxygenSaturationSamples(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
        accountId: String,
    ): List<HealthSampleUpload> = readAll<OxygenSaturationRecord>(healthClient, range).mapNotNull { record ->
        record.percentage.value.takeIf { it in 50.0..100.0 }?.let { percent ->
            sample(accountId, "spo2", record.time, record.time, percent, "%")
        }
    }

    private suspend inline fun <reified T : Record> readAll(
        healthClient: HealthConnectClient,
        range: TimeRangeFilter,
    ): List<T> {
        val records = mutableListOf<T>()
        var pageToken: String? = null
        do {
            val response = healthClient.readRecords(
                ReadRecordsRequest<T>(
                    timeRangeFilter = range,
                    pageSize = PAGE_SIZE,
                    pageToken = pageToken,
                ),
            )
            records += response.records
            pageToken = response.pageToken
        } while (pageToken != null)
        return records
    }

    private fun sample(
        accountId: String,
        type: String,
        start: Instant,
        end: Instant,
        value: Double? = null,
        unit: String? = null,
        valueText: String? = null,
    ) = HealthSampleUpload(
        user_id = accountId,
        device_os = "android",
        source = "health_connect",
        type = type,
        start_time = start.toString(),
        end_time = end.toString(),
        value = value,
        unit = unit,
        value_text = valueText,
    )

    private companion object {
        const val IMPORT_DAYS = 30L
        const val BATCH_SIZE = 500
        const val PAGE_SIZE = 1000
    }
}

enum class HealthConnectStatus {
    CHECKING,
    UNAVAILABLE,
    UPDATE_REQUIRED,
    PERMISSIONS_REQUIRED,
    READY,
}

data class HealthConnectImportResult(
    val importedSampleCount: Int,
    val deliveredBatchCount: Int,
    val pendingBatchCount: Int,
)

data class HealthSampleDrainResult(
    val deliveredCount: Int,
    val pendingCount: Int,
)

internal fun healthConnectSleepStage(stage: Int): String? = when (stage) {
    SleepSessionRecord.STAGE_TYPE_AWAKE,
    SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> "awake"
    SleepSessionRecord.STAGE_TYPE_SLEEPING,
    SleepSessionRecord.STAGE_TYPE_UNKNOWN -> "asleep"
    SleepSessionRecord.STAGE_TYPE_LIGHT -> "core"
    SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
    SleepSessionRecord.STAGE_TYPE_REM -> "rem"
    SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> null
    else -> null
}
