package com.gaiaeyes.app.core.di

import android.content.Context
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.data.BodyCache
import com.gaiaeyes.app.data.BodyRepository
import com.gaiaeyes.app.data.DashboardCache
import com.gaiaeyes.app.data.DashboardRepository
import com.gaiaeyes.app.data.HealthRepository
import com.gaiaeyes.app.data.HealthConnectRepository
import com.gaiaeyes.app.data.HealthSampleQueue
import com.gaiaeyes.app.data.HomeContextCache
import com.gaiaeyes.app.data.HomeContextRepository
import com.gaiaeyes.app.data.JournalRepository
import com.gaiaeyes.app.data.JournalWriteQueue
import com.gaiaeyes.app.data.OutlookCache
import com.gaiaeyes.app.data.OutlookRepository
import com.gaiaeyes.app.data.PatternsCache
import com.gaiaeyes.app.data.PatternsRepository
import com.gaiaeyes.app.core.work.JournalDrainScheduler
import com.gaiaeyes.app.core.work.HealthSampleDrainScheduler

class AppContainer(
    context: Context,
    apiBase: String,
    supabaseUrl: String,
    supabaseAnonKey: String,
) {
    private val apiClient = GaiaApiClient(apiBase = apiBase)
    val quickLogCoordinator = QuickLogCoordinator()

    val authRepository = AuthRepository(
        context = context,
        supabaseUrl = supabaseUrl,
        supabaseAnonKey = supabaseAnonKey,
    )
    val healthRepository: HealthRepository = HealthRepository(healthService = apiClient)
    val healthConnectRepository = HealthConnectRepository(
        context = context.applicationContext,
        authRepository = authRepository,
        apiClient = apiClient,
        queue = HealthSampleQueue(context.applicationContext),
        scheduleBackgroundDrain = {
            HealthSampleDrainScheduler.enqueueNow(context.applicationContext)
        },
    )
    val dashboardRepository = DashboardRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        cache = DashboardCache(context.applicationContext),
    )
    val bodyRepository = BodyRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        cache = BodyCache(context.applicationContext),
    )
    val homeContextRepository = HomeContextRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        cache = HomeContextCache(context.applicationContext),
    )
    val patternsRepository = PatternsRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        cache = PatternsCache(context.applicationContext),
    )
    val outlookRepository = OutlookRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        cache = OutlookCache(context.applicationContext),
    )
    val journalRepository = JournalRepository(
        authRepository = authRepository,
        apiClient = apiClient,
        queue = JournalWriteQueue(context.applicationContext),
        scheduleBackgroundDrain = {
            JournalDrainScheduler.enqueueNow(context.applicationContext)
        },
    )
}
