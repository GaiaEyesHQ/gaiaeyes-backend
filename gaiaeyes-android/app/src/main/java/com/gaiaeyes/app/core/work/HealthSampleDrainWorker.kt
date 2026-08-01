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

class HealthSampleDrainWorker(
    applicationContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(applicationContext, workerParameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? GaiaEyesApplication ?: return Result.failure()
        val accountId = app.container.authRepository.currentAccountId()
            ?: return Result.success()
        val disposition = try {
            healthSampleDrainDisposition(
                hasAccount = true,
                pendingCount = app.container.healthConnectRepository.drain(accountId).pendingCount,
            )
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: Throwable) {
            healthSampleDrainDisposition(hasAccount = true, error = error)
        }
        return when (disposition) {
            HealthSampleDrainDisposition.SUCCESS -> Result.success()
            HealthSampleDrainDisposition.RETRY -> Result.retry()
        }
    }
}

object HealthSampleDrainScheduler {
    private const val PERIODIC_WORK_NAME = "gaiaeyes-health-sample-drain"
    private const val IMMEDIATE_WORK_NAME = "gaiaeyes-health-sample-drain-now"
    private const val REPEAT_INTERVAL_MINUTES = 15L
    private const val BACKOFF_SECONDS = 30L

    private val connectedConstraint = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<HealthSampleDrainWorker>(
            REPEAT_INTERVAL_MINUTES,
            TimeUnit.MINUTES,
        )
            .setConstraints(connectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, BACKOFF_SECONDS, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    fun enqueueNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<HealthSampleDrainWorker>()
            .setConstraints(connectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, BACKOFF_SECONDS, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}

internal enum class HealthSampleDrainDisposition {
    SUCCESS,
    RETRY,
}

internal fun healthSampleDrainDisposition(
    hasAccount: Boolean,
    pendingCount: Int? = null,
    error: Throwable? = null,
): HealthSampleDrainDisposition {
    if (!hasAccount || error is ApiUnauthorizedException) {
        return HealthSampleDrainDisposition.SUCCESS
    }
    if (error != null || pendingCount != 0) {
        return HealthSampleDrainDisposition.RETRY
    }
    return HealthSampleDrainDisposition.SUCCESS
}
