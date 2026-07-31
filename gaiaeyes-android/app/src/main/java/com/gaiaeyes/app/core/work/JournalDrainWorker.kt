package com.gaiaeyes.app.core.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.gaiaeyes.app.GaiaEyesApplication
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException

class JournalDrainWorker(
    applicationContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(applicationContext, workerParameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? GaiaEyesApplication
            ?: return Result.failure()
        val accountId = app.container.authRepository.currentAccountId()
        if (accountId == null) {
            return Result.success()
        }

        val disposition = try {
            val result = app.container.journalRepository.drain(accountId)
            journalDrainDisposition(
                hasAccount = true,
                pendingCount = result.pendingCount,
            )
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: Throwable) {
            journalDrainDisposition(
                hasAccount = true,
                error = error,
            )
        }

        return when (disposition) {
            JournalDrainDisposition.SUCCESS -> Result.success()
            JournalDrainDisposition.RETRY -> Result.retry()
        }
    }
}

object JournalDrainScheduler {
    private const val PERIODIC_WORK_NAME = "gaiaeyes-journal-drain"
    private const val IMMEDIATE_WORK_NAME = "gaiaeyes-journal-drain-now"
    private const val REPEAT_INTERVAL_MINUTES = 15L
    private const val BACKOFF_SECONDS = 30L

    private val connectedConstraint = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<JournalDrainWorker>(
            REPEAT_INTERVAL_MINUTES,
            TimeUnit.MINUTES,
        )
            .setConstraints(connectedConstraint)
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                BACKOFF_SECONDS,
                TimeUnit.SECONDS,
            )
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    fun enqueueNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<JournalDrainWorker>()
            .setConstraints(connectedConstraint)
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                BACKOFF_SECONDS,
                TimeUnit.SECONDS,
            )
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}

internal enum class JournalDrainDisposition {
    SUCCESS,
    RETRY,
}

internal fun journalDrainDisposition(
    hasAccount: Boolean,
    pendingCount: Int? = null,
    error: Throwable? = null,
): JournalDrainDisposition {
    if (!hasAccount || error is ApiUnauthorizedException) {
        return JournalDrainDisposition.SUCCESS
    }
    if (error != null || pendingCount != 0) {
        return JournalDrainDisposition.RETRY
    }
    return JournalDrainDisposition.SUCCESS
}
