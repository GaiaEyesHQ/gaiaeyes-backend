package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.DailyCheckInRequest
import com.gaiaeyes.app.core.network.DailyCheckInStatus
import com.gaiaeyes.app.core.network.ExposureCatalogOption
import com.gaiaeyes.app.core.network.ExposureEventRequest
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.SymptomCodeOption
import com.gaiaeyes.app.core.network.SymptomEventRequest
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

class JournalRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
    private val queue: JournalWriteQueue,
) {
    suspend fun symptomCatalog(): List<SymptomCodeOption> =
        authenticatedRequest {
            apiClient.symptomCodes(authRepository.accessToken())
        }

    suspend fun exposureCatalog(): List<ExposureCatalogOption> =
        authenticatedRequest {
            apiClient.exposureCatalog(authRepository.accessToken())
        }

    suspend fun dailyCheckInStatus(): DailyCheckInStatus =
        authenticatedRequest {
            apiClient.dailyCheckInStatus(authRepository.accessToken())
        }

    suspend fun submitSymptom(
        accountId: String,
        symptomCode: String,
        severity: Int,
        note: String?,
    ): JournalWriteResult {
        val request = SymptomEventRequest(
            symptomCode = symptomCode,
            timestampUtc = Instant.now().toString(),
            severity = severity.coerceIn(0, 10),
            note = note.cleaned(),
            tags = listOf("android"),
        )
        queue.enqueue(
            accountId,
            PendingJournalWrite(
                id = UUID.randomUUID().toString(),
                kind = JournalWriteKind.SYMPTOM,
                symptom = request,
                createdAtEpochMillis = System.currentTimeMillis(),
            ),
        )
        return drain(accountId)
    }

    suspend fun submitExposure(
        accountId: String,
        exposureKey: String,
        intensity: Int,
        note: String?,
    ): JournalWriteResult {
        val request = ExposureEventRequest(
            exposureKey = exposureKey,
            intensity = intensity.coerceIn(1, 3),
            timestampUtc = Instant.now().toString(),
            note = note.cleaned(),
        )
        queue.enqueue(
            accountId,
            PendingJournalWrite(
                id = UUID.randomUUID().toString(),
                kind = JournalWriteKind.EXPOSURE,
                exposure = request,
                createdAtEpochMillis = System.currentTimeMillis(),
            ),
        )
        return drain(accountId)
    }

    suspend fun submitDailyCheckIn(
        accountId: String,
        status: DailyCheckInStatus,
        comparedToYesterday: String,
        energyLevel: String,
        usableEnergy: String,
        systemLoad: String,
        painLevel: String,
        moodLevel: String,
        note: String?,
    ): JournalWriteResult {
        val completedAt = Instant.now().toString()
        val request = DailyCheckInRequest(
            promptId = status.prompt?.id?.takeIf(String::isNotBlank),
            day = status.targetDay
                ?.takeIf(String::isNotBlank)
                ?: status.prompt?.day?.takeIf(String::isNotBlank)
                ?: LocalDate.now().toString(),
            comparedToYesterday = comparedToYesterday,
            energyLevel = energyLevel,
            usableEnergy = usableEnergy,
            systemLoad = systemLoad,
            painLevel = painLevel,
            moodLevel = moodLevel,
            note = note.cleaned(),
            completedAt = completedAt,
        )
        queue.enqueue(
            accountId,
            PendingJournalWrite(
                id = UUID.randomUUID().toString(),
                kind = JournalWriteKind.DAILY_CHECK_IN,
                dailyCheckIn = request,
                createdAtEpochMillis = System.currentTimeMillis(),
            ),
        )
        return drain(accountId)
    }

    suspend fun pendingCount(accountId: String): Int = queue.read(accountId).size

    suspend fun drain(accountId: String): JournalWriteResult {
        var delivered = 0
        for (item in queue.read(accountId)) {
            val succeeded = runCatching {
                authenticatedRequest {
                    val token = authRepository.accessToken()
                    when (item.kind) {
                        JournalWriteKind.SYMPTOM ->
                            apiClient.createSymptom(token, requireNotNull(item.symptom))
                        JournalWriteKind.EXPOSURE ->
                            apiClient.createExposure(token, requireNotNull(item.exposure))
                        JournalWriteKind.DAILY_CHECK_IN ->
                            apiClient.submitDailyCheckIn(token, requireNotNull(item.dailyCheckIn))
                    }
                }
            }.fold(
                onSuccess = { true },
                onFailure = { error ->
                    if (error is ApiUnauthorizedException) throw error
                    false
                },
            )
            if (!succeeded) break
            queue.remove(accountId, item.id)
            delivered += 1
        }
        return JournalWriteResult(
            deliveredCount = delivered,
            pendingCount = queue.read(accountId).size,
        )
    }

    suspend fun clear(accountId: String) {
        queue.clear(accountId)
    }

    private suspend fun <T> authenticatedRequest(block: suspend () -> T): T {
        return try {
            block()
        } catch (unauthorized: ApiUnauthorizedException) {
            authRepository.signOut()
            throw unauthorized
        }
    }
}

data class JournalWriteResult(
    val deliveredCount: Int,
    val pendingCount: Int,
)

private fun String?.cleaned(): String? = this?.trim()?.takeIf(String::isNotEmpty)
