package com.gaiaeyes.app.core.di

import android.content.Context
import android.app.Activity
import com.gaiaeyes.app.BuildConfig
import com.gaiaeyes.app.data.AccountDeletionController
import com.gaiaeyes.app.data.AccountDeletionPreferences
import com.gaiaeyes.app.data.AccountOperationGate
import com.gaiaeyes.app.data.clearAccountLocalData
import com.gaiaeyes.app.data.BillingConfig
import com.gaiaeyes.app.data.BillingController
import com.gaiaeyes.app.data.PlusPlan
import com.gaiaeyes.app.data.RevenueCatBillingStore
import com.gaiaeyes.app.data.readBillingForAccount
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.notifications.NotificationNavigationCoordinator
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.data.BodyCache
import com.gaiaeyes.app.data.BodyRepository
import com.gaiaeyes.app.data.DashboardCache
import com.gaiaeyes.app.data.DashboardRepository
import com.gaiaeyes.app.data.DeviceLocationRepository
import com.gaiaeyes.app.data.ExploreCache
import com.gaiaeyes.app.data.ExploreRepository
import com.gaiaeyes.app.data.HealthRepository
import com.gaiaeyes.app.data.HealthConnectRepository
import com.gaiaeyes.app.data.HealthSampleQueue
import com.gaiaeyes.app.data.HomeContextCache
import com.gaiaeyes.app.data.HomeContextRepository
import com.gaiaeyes.app.data.JournalRepository
import com.gaiaeyes.app.data.JournalWriteQueue
import com.gaiaeyes.app.data.NotificationRepository
import com.gaiaeyes.app.data.OutlookCache
import com.gaiaeyes.app.data.OutlookRepository
import com.gaiaeyes.app.data.PatternsCache
import com.gaiaeyes.app.data.PatternsRepository
import com.gaiaeyes.app.data.ProfileRepository
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
    val notificationNavigationCoordinator = NotificationNavigationCoordinator()
    val deviceLocationRepository = DeviceLocationRepository(context.applicationContext)

    private val deletionRecords = AccountDeletionPreferences(context.applicationContext)
    private val accountOperations = AccountOperationGate(deletionRecords)

    val authRepository = AuthRepository(
        context = context,
        supabaseUrl = supabaseUrl,
        supabaseAnonKey = supabaseAnonKey,
        accountOperations = accountOperations,
    )
    private val billingScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val billingConfig = BillingConfig(
        BuildConfig.REVENUECAT_ANDROID_API_KEY,
        mapOf(
            PlusPlan.MONTHLY to BuildConfig.REVENUECAT_PLUS_MONTHLY_PRODUCT_ID,
            PlusPlan.YEARLY to BuildConfig.REVENUECAT_PLUS_YEARLY_PRODUCT_ID,
        ),
    )
    private val billingStore = RevenueCatBillingStore(context, billingConfig)
    val billingController = BillingController(
        config = billingConfig,
        store = billingStore,
        scope = billingScope,
        currentAccountId = authRepository::currentAccountId,
        readBackend = { account ->
            readBillingForAccount(account, authRepository::currentAccountId, authRepository::accessToken,
                authRepository::refreshAccessToken, apiClient::billingEntitlements)
        },
    )

    init {
        billingScope.launch { authRepository.authState.collect(billingController::authChanged) }
    }

    fun purchasePlus(activity: Activity, productId: String) {
        val account = authRepository.currentAccountId() ?: return
        if (accountOperations.isBlocked(account)) return
        billingController.purchase(productId) { billingStore.purchase(activity, productId) }
    }

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
    val exploreRepository = ExploreRepository(
        apiClient = apiClient,
        cache = ExploreCache(context.applicationContext),
        accessToken = authRepository::accessToken,
        currentAccountId = authRepository::currentAccountId,
        trackAccountOperation = authRepository::trackAccountOperation,
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
    val profileRepository = ProfileRepository(
        authRepository = authRepository,
        apiClient = apiClient,
    )
    val notificationRepository = NotificationRepository(
        context = context.applicationContext,
        authRepository = authRepository,
        apiClient = apiClient,
    )

    val accountDeletionController = AccountDeletionController(
        scope = billingScope,
        currentAccountId = authRepository::currentAccountId,
        tokenForAccount = authRepository::tokenForAccountDeletion,
        preflight = apiClient::accountDeletionPreflight,
        delete = apiClient::deleteAccount,
        gate = accountOperations,
        records = deletionRecords,
        clearLocalData = { account ->
            clearAccountLocalData(account, listOf(
                dashboardRepository::clear, bodyRepository::clear, homeContextRepository::clear,
                exploreRepository::clear, journalRepository::clear, healthConnectRepository::clear,
                outlookRepository::clear, patternsRepository::clear,
                { id ->
                    val preferences = context.getSharedPreferences("gaiaeyes_guide", Context.MODE_PRIVATE)
                    val editor = preferences.edit()
                    preferences.all.keys.filter { it.startsWith("$id:") }.forEach(editor::remove)
                    check(editor.commit()) { "Could not clear local Guide answers" }
                },
            ))
            if (authRepository.currentAccountId() == account) {
                notificationRepository.forgetLocalToken()
                quickLogCoordinator.pending.value?.let { quickLogCoordinator.consume(it.id) }
                notificationNavigationCoordinator.pending.value?.let { notificationNavigationCoordinator.consume(it.id) }
            }
        },
        clearSession = authRepository::clearLocalSessionForDeletion,
    )

    init {
        billingScope.launch {
            authRepository.authState.collect {
                accountDeletionController.authChanged(authRepository.currentAccountId())
            }
        }
    }
}
