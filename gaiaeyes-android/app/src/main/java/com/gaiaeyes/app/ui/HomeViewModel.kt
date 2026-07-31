package com.gaiaeyes.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.auth.AuthState
import com.gaiaeyes.app.core.network.DailyCheckInStatus
import com.gaiaeyes.app.core.network.ExposureCatalogOption
import com.gaiaeyes.app.core.network.SymptomCodeOption
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.core.quicklog.QuickLogRequest
import com.gaiaeyes.app.data.BodyRepository
import com.gaiaeyes.app.data.BodySnapshot
import com.gaiaeyes.app.data.DashboardRepository
import com.gaiaeyes.app.data.DashboardSnapshot
import com.gaiaeyes.app.data.DriversSnapshot
import com.gaiaeyes.app.data.HealthRepository
import com.gaiaeyes.app.data.HomeContextRepository
import com.gaiaeyes.app.data.CurrentSymptomsSnapshot
import com.gaiaeyes.app.data.JournalRepository
import com.gaiaeyes.app.data.OutlookRepository
import com.gaiaeyes.app.data.OutlookSnapshot
import com.gaiaeyes.app.data.PatternsRepository
import com.gaiaeyes.app.data.PatternsSnapshot
import java.time.Instant
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class HomeViewModel(
    private val authRepository: AuthRepository,
    private val bodyRepository: BodyRepository,
    private val dashboardRepository: DashboardRepository,
    private val healthRepository: HealthRepository,
    private val homeContextRepository: HomeContextRepository,
    private val journalRepository: JournalRepository,
    private val outlookRepository: OutlookRepository,
    private val patternsRepository: PatternsRepository,
    private val quickLogCoordinator: QuickLogCoordinator,
) : ViewModel() {
    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    private var dashboardJob: Job? = null
    private var bodyJob: Job? = null
    private var homeContextJob: Job? = null
    private var outlookJob: Job? = null
    private var patternsJob: Job? = null
    private var loadedAccountId: String? = null
    private var processingQuickLogId: String? = null

    init {
        refreshHealth()
        viewModelScope.launch {
            authRepository.authState.collect(::handleAuthState)
        }
        viewModelScope.launch {
            authRepository.deepLinkError.collect { message ->
                if (message != null) {
                    _uiState.value = _uiState.value.copy(authMessage = message)
                }
            }
        }
        viewModelScope.launch {
            quickLogCoordinator.pending.collect(::maybeHandleQuickLog)
        }
    }

    fun onEmailChanged(email: String) {
        _uiState.value = _uiState.value.copy(
            email = email,
            authMessage = null,
            magicLinkSent = false,
        )
    }

    fun sendMagicLink() {
        val email = _uiState.value.email.trim()
        if (!email.looksLikeEmail()) {
            _uiState.value = _uiState.value.copy(
                authMessage = "Enter the email address you use for Gaia Eyes.",
            )
            return
        }
        if (_uiState.value.isSendingMagicLink) return

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isSendingMagicLink = true,
                authMessage = null,
                magicLinkSent = false,
            )
            runCatching {
                authRepository.sendMagicLink(email)
            }.onSuccess {
                _uiState.value = _uiState.value.copy(
                    isSendingMagicLink = false,
                    magicLinkSent = true,
                    authMessage = "Check your email and open the secure Gaia Eyes sign-in link.",
                )
            }.onFailure {
                _uiState.value = _uiState.value.copy(
                    isSendingMagicLink = false,
                    authMessage = "We couldn't send the sign-in link. Check your connection and try again.",
                )
            }
        }
    }

    fun refresh() {
        refreshHealth()
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        retryJournalWrites(account.accountId, showSuccessMessage = false)
        when (_uiState.value.selectedPage) {
            SignedInPage.HOME -> {
                loadDashboard(account.accountId, showCachedFirst = false)
                loadHomeContext(account.accountId, showCachedFirst = false)
            }
            SignedInPage.BODY -> loadBody(account.accountId, showCachedFirst = false)
            SignedInPage.PATTERNS -> loadPatterns(account.accountId, showCachedFirst = false)
            SignedInPage.OUTLOOK -> loadOutlook(account.accountId, showCachedFirst = false)
            SignedInPage.EXPLORE -> loadHomeContext(account.accountId, showCachedFirst = false)
        }
    }

    fun selectPage(page: SignedInPage) {
        _uiState.value = _uiState.value.copy(selectedPage = page)
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        when (page) {
            SignedInPage.HOME -> Unit
            SignedInPage.BODY -> if (_uiState.value.body == null) {
                loadBody(account.accountId, showCachedFirst = true)
            }
            SignedInPage.PATTERNS -> if (_uiState.value.patterns == null) {
                loadPatterns(account.accountId, showCachedFirst = true)
            }
            SignedInPage.OUTLOOK -> if (_uiState.value.outlook == null) {
                loadOutlook(account.accountId, showCachedFirst = true)
            }
            SignedInPage.EXPLORE -> if (_uiState.value.drivers == null) {
                loadHomeContext(account.accountId, showCachedFirst = true)
            }
        }
    }

    fun signOut() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isSigningOut) return

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSigningOut = true, authMessage = null)
            runCatching {
                dashboardRepository.clear(account.accountId)
                bodyRepository.clear(account.accountId)
                homeContextRepository.clear(account.accountId)
                journalRepository.clear(account.accountId)
                outlookRepository.clear(account.accountId)
                patternsRepository.clear(account.accountId)
                authRepository.signOut()
            }.onFailure {
                _uiState.value = _uiState.value.copy(
                    isSigningOut = false,
                    authMessage = "We couldn't sign you out. Check your connection and try again.",
                )
            }
        }
    }

    fun dismissMessage() {
        authRepository.clearDeepLinkError()
        _uiState.value = _uiState.value.copy(
            authMessage = null,
            dashboardMessage = null,
            bodyMessage = null,
            homeContextMessage = null,
            outlookMessage = null,
            patternsMessage = null,
            journalMessage = null,
        )
    }

    fun openSymptomLog() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        _uiState.value = _uiState.value.copy(
            journalDialog = JournalDialog.SYMPTOM,
            journalMessage = null,
        )
        if (_uiState.value.symptomCatalog.isEmpty()) {
            viewModelScope.launch {
                _uiState.value = _uiState.value.copy(isLoadingJournal = true)
                runCatching {
                    journalRepository.symptomCatalog()
                }.onSuccess { catalog ->
                    if (isCurrentAccount(account.accountId)) {
                        _uiState.value = _uiState.value.copy(
                            symptomCatalog = catalog.sortedBy { it.label.lowercase() },
                            isLoadingJournal = false,
                        )
                    }
                }.onFailure {
                    journalLoadFailed(account.accountId, "Symptom choices couldn't load.")
                }
            }
        }
    }

    fun openExposureLog() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        _uiState.value = _uiState.value.copy(
            journalDialog = JournalDialog.EXPOSURE,
            journalMessage = null,
        )
        if (_uiState.value.exposureCatalog.isEmpty()) {
            viewModelScope.launch {
                _uiState.value = _uiState.value.copy(isLoadingJournal = true)
                runCatching {
                    journalRepository.exposureCatalog()
                }.onSuccess { catalog ->
                    if (isCurrentAccount(account.accountId)) {
                        _uiState.value = _uiState.value.copy(
                            exposureCatalog = catalog.sortedBy { it.label.lowercase() },
                            isLoadingJournal = false,
                        )
                    }
                }.onFailure {
                    journalLoadFailed(account.accountId, "Exposure choices couldn't load.")
                }
            }
        }
    }

    fun openDailyCheckIn() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        _uiState.value = _uiState.value.copy(
            journalDialog = JournalDialog.DAILY_CHECK_IN,
            journalMessage = null,
            isLoadingJournal = true,
        )
        viewModelScope.launch {
            runCatching {
                journalRepository.dailyCheckInStatus()
            }.onSuccess { status ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        dailyCheckInStatus = status,
                        isLoadingJournal = false,
                    )
                }
            }.onFailure {
                journalLoadFailed(account.accountId, "Today's check-in couldn't load.")
            }
        }
    }

    fun dismissJournal() {
        if (_uiState.value.isSubmittingJournal) return
        _uiState.value = _uiState.value.copy(
            journalDialog = null,
            isLoadingJournal = false,
        )
    }

    fun submitSymptom(symptomCode: String, severity: Int, note: String?) {
        submitJournalWrite("Symptom saved.") { accountId ->
            journalRepository.submitSymptom(accountId, symptomCode, severity, note)
        }
    }

    fun submitExposure(exposureKey: String, intensity: Int, note: String?) {
        submitJournalWrite("Exposure saved.") { accountId ->
            journalRepository.submitExposure(accountId, exposureKey, intensity, note)
        }
    }

    fun submitDailyCheckIn(
        comparedToYesterday: String,
        energyLevel: String,
        usableEnergy: String,
        systemLoad: String,
        painLevel: String,
        moodLevel: String,
        note: String?,
    ) {
        val status = _uiState.value.dailyCheckInStatus ?: return
        submitJournalWrite("Daily check-in saved.") { accountId ->
            journalRepository.submitDailyCheckIn(
                accountId = accountId,
                status = status,
                comparedToYesterday = comparedToYesterday,
                energyLevel = energyLevel,
                usableEnergy = usableEnergy,
                systemLoad = systemLoad,
                painLevel = painLevel,
                moodLevel = moodLevel,
                note = note,
            )
        }
    }

    private fun handleAuthState(authState: AuthState) {
        _uiState.value = _uiState.value.copy(
            authState = authState,
            isSigningOut = false,
        )

        if (authState is AuthState.SignedIn) {
            if (loadedAccountId != authState.accountId) {
                loadedAccountId = authState.accountId
                loadDashboard(authState.accountId, showCachedFirst = true)
                loadHomeContext(authState.accountId, showCachedFirst = true)
                if (quickLogCoordinator.pending.value == null) {
                    retryJournalWrites(authState.accountId, showSuccessMessage = false)
                }
            }
            maybeHandleQuickLog(quickLogCoordinator.pending.value)
            return
        }

        dashboardJob?.cancel()
        dashboardJob = null
        bodyJob?.cancel()
        bodyJob = null
        homeContextJob?.cancel()
        homeContextJob = null
        patternsJob?.cancel()
        patternsJob = null
        outlookJob?.cancel()
        outlookJob = null
        loadedAccountId = null
        _uiState.value = _uiState.value.copy(
            dashboard = null,
            isLoadingDashboard = false,
            dashboardMessage = null,
            body = null,
            isLoadingBody = false,
            bodyMessage = null,
            selectedPage = SignedInPage.HOME,
            currentSymptoms = null,
            drivers = null,
            isLoadingHomeContext = false,
            homeContextMessage = null,
            patterns = null,
            isLoadingPatterns = false,
            patternsMessage = null,
            outlook = null,
            isLoadingOutlook = false,
            outlookMessage = null,
            journalDialog = null,
            isLoadingJournal = false,
            isSubmittingJournal = false,
            journalMessage = null,
            pendingJournalWrites = 0,
            authMessage = if (
                authState is AuthState.SignedOut &&
                quickLogCoordinator.pending.value != null
            ) {
                "Sign in to log your migraine hands-free."
            } else {
                _uiState.value.authMessage
            },
        )
    }

    private fun maybeHandleQuickLog(request: QuickLogRequest?) {
        request ?: return
        if (processingQuickLogId == request.id || _uiState.value.isSubmittingJournal) return

        val account = _uiState.value.authState as? AuthState.SignedIn
        if (account == null) {
            if (_uiState.value.authState is AuthState.SignedOut) {
                _uiState.value = _uiState.value.copy(
                    authMessage = "Sign in to log your migraine hands-free.",
                )
            }
            return
        }

        processingQuickLogId = request.id
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                selectedPage = SignedInPage.HOME,
                isSubmittingJournal = true,
                journalDialog = null,
                journalMessage = null,
            )
            runCatching {
                journalRepository.submitSymptom(
                    accountId = account.accountId,
                    symptomCode = request.kind.symptomCode,
                    severity = request.kind.defaultSeverity,
                    note = null,
                    timestampUtc = Instant.ofEpochMilli(request.requestedAtEpochMillis).toString(),
                    sourceTag = "assistant",
                )
            }.onSuccess { result ->
                quickLogCoordinator.consume(request.id)
                processingQuickLogId = null
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isSubmittingJournal = false,
                        pendingJournalWrites = result.pendingCount,
                        journalMessage = if (result.pendingCount == 0) {
                            "Migraine logged. Rest—you can add details later."
                        } else {
                            "Migraine saved on this device. Gaia Eyes will sync it when your connection returns."
                        },
                    )
                    loadDashboard(account.accountId, showCachedFirst = false)
                    loadHomeContext(account.accountId, showCachedFirst = false)
                }
            }.onFailure {
                val pending = journalRepository.pendingCount(account.accountId)
                if (pending > 0) {
                    quickLogCoordinator.consume(request.id)
                }
                processingQuickLogId = null
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isSubmittingJournal = false,
                        pendingJournalWrites = pending,
                        journalMessage = if (pending > 0) {
                            "Migraine saved on this device. Gaia Eyes will sync it when your connection returns."
                        } else {
                            "Your migraine wasn't logged. Open Gaia Eyes and try again."
                        },
                    )
                }
            }
        }
    }

    private fun submitJournalWrite(
        successMessage: String,
        write: suspend (String) -> com.gaiaeyes.app.data.JournalWriteResult,
    ) {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isSubmittingJournal) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isSubmittingJournal = true,
                journalMessage = null,
            )
            runCatching {
                write(account.accountId)
            }.onSuccess { result ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        journalDialog = null,
                        isSubmittingJournal = false,
                        pendingJournalWrites = result.pendingCount,
                        journalMessage = if (result.pendingCount == 0) {
                            successMessage
                        } else {
                            "Saved securely on this device. Gaia Eyes will retry when your connection returns."
                        },
                    )
                    loadDashboard(account.accountId, showCachedFirst = false)
                    loadHomeContext(account.accountId, showCachedFirst = false)
                }
                maybeHandleQuickLog(quickLogCoordinator.pending.value)
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    viewModelScope.launch {
                        val pending = journalRepository.pendingCount(account.accountId)
                        _uiState.value = _uiState.value.copy(
                            journalDialog = null,
                            isSubmittingJournal = false,
                            pendingJournalWrites = pending,
                            journalMessage = if (pending > 0) {
                                "Saved securely on this device. Gaia Eyes will retry when your connection returns."
                            } else {
                                "That entry couldn't be saved. Check your connection and try again."
                            },
                        )
                        maybeHandleQuickLog(quickLogCoordinator.pending.value)
                    }
                }
            }
        }
    }

    private fun retryJournalWrites(accountId: String, showSuccessMessage: Boolean) {
        viewModelScope.launch {
            runCatching {
                journalRepository.drain(accountId)
            }.onSuccess { result ->
                if (isCurrentAccount(accountId)) {
                    val previouslyPending = _uiState.value.pendingJournalWrites
                    _uiState.value = _uiState.value.copy(
                        pendingJournalWrites = result.pendingCount,
                        journalMessage = when {
                            showSuccessMessage && result.deliveredCount > 0 -> "Saved entries are now up to date."
                            previouslyPending > 0 && result.pendingCount == 0 -> "Saved entries are now up to date."
                            else -> _uiState.value.journalMessage
                        },
                    )
                    if (result.deliveredCount > 0) {
                        loadDashboard(accountId, showCachedFirst = false)
                        loadHomeContext(accountId, showCachedFirst = false)
                    }
                }
            }.onFailure {
                if (isCurrentAccount(accountId)) {
                    val pending = journalRepository.pendingCount(accountId)
                    _uiState.value = _uiState.value.copy(pendingJournalWrites = pending)
                }
            }
        }
    }

    private fun journalLoadFailed(accountId: String, message: String) {
        if (!isCurrentAccount(accountId)) return
        _uiState.value = _uiState.value.copy(
            journalDialog = null,
            isLoadingJournal = false,
            journalMessage = message,
        )
    }

    private fun loadDashboard(accountId: String, showCachedFirst: Boolean) {
        dashboardJob?.cancel()
        dashboardJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingDashboard = true,
                dashboardMessage = null,
            )

            if (showCachedFirst) {
                dashboardRepository.cached(accountId)?.let { cached ->
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(dashboard = cached)
                    }
                }
            }

            runCatching {
                dashboardRepository.refresh(accountId)
            }.onSuccess { dashboard ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(
                        dashboard = dashboard,
                        isLoadingDashboard = false,
                        dashboardMessage = null,
                    )
                }
            }.onFailure {
                if (isCurrentAccount(accountId)) {
                    val hasCachedDashboard = _uiState.value.dashboard != null
                    _uiState.value = _uiState.value.copy(
                        isLoadingDashboard = false,
                        dashboardMessage = if (hasCachedDashboard) {
                            "Showing your saved dashboard while live data reconnects."
                        } else {
                            "Your dashboard couldn't load. Check your connection and try again."
                        },
                    )
                }
            }
        }
    }

    private fun loadHomeContext(accountId: String, showCachedFirst: Boolean) {
        homeContextJob?.cancel()
        homeContextJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingHomeContext = true,
                homeContextMessage = null,
            )

            if (showCachedFirst) {
                val cachedSymptoms = homeContextRepository.cachedSymptoms(accountId)
                val cachedDrivers = homeContextRepository.cachedDrivers(accountId)
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(
                        currentSymptoms = cachedSymptoms ?: _uiState.value.currentSymptoms,
                        drivers = cachedDrivers ?: _uiState.value.drivers,
                    )
                }
            }

            var failures = 0
            runCatching {
                homeContextRepository.refreshSymptoms(accountId)
            }.onSuccess { symptoms ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(currentSymptoms = symptoms)
                }
            }.onFailure {
                failures += 1
            }

            runCatching {
                homeContextRepository.refreshDrivers(accountId)
            }.onSuccess { drivers ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(drivers = drivers)
                }
            }.onFailure {
                failures += 1
            }

            if (isCurrentAccount(accountId)) {
                val hasSavedContext =
                    _uiState.value.currentSymptoms != null || _uiState.value.drivers != null
                _uiState.value = _uiState.value.copy(
                    isLoadingHomeContext = false,
                    homeContextMessage = when {
                        failures == 0 -> null
                        hasSavedContext -> "Showing saved context while live details reconnect."
                        else -> "Today’s context couldn’t load. Check your connection and try again."
                    },
                )
            }
        }
    }

    private fun loadBody(accountId: String, showCachedFirst: Boolean) {
        bodyJob?.cancel()
        bodyJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingBody = true,
                bodyMessage = null,
            )

            if (showCachedFirst) {
                bodyRepository.cached(accountId)?.let { cached ->
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(body = cached)
                    }
                }
            }

            runCatching {
                bodyRepository.refresh(accountId)
            }.onSuccess { body ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(
                        body = body,
                        isLoadingBody = false,
                        bodyMessage = null,
                    )
                }
            }.onFailure {
                if (isCurrentAccount(accountId)) {
                    val hasCachedBody = _uiState.value.body != null
                    _uiState.value = _uiState.value.copy(
                        isLoadingBody = false,
                        bodyMessage = if (hasCachedBody) {
                            "Showing saved Body data while live details reconnect."
                        } else {
                            "Your Body data couldn't load. Check your connection and try again."
                        },
                    )
                }
            }
        }
    }

    private fun loadPatterns(accountId: String, showCachedFirst: Boolean) {
        patternsJob?.cancel()
        patternsJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingPatterns = true,
                patternsMessage = null,
            )

            if (showCachedFirst) {
                patternsRepository.cached(accountId)?.let { cached ->
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(patterns = cached)
                    }
                }
            }

            var failures = 0
            runCatching {
                patternsRepository.refreshSummary(accountId)
            }.onSuccess { summary ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(patterns = summary)
                }
            }.onFailure {
                failures += 1
            }

            runCatching {
                patternsRepository.refreshFull(accountId)
            }.onSuccess { patterns ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(patterns = patterns)
                }
            }.onFailure {
                failures += 1
            }

            if (isCurrentAccount(accountId)) {
                val hasSavedPatterns = _uiState.value.patterns != null
                _uiState.value = _uiState.value.copy(
                    isLoadingPatterns = false,
                    patternsMessage = when {
                        failures == 0 -> null
                        hasSavedPatterns -> "Showing saved patterns while live details reconnect."
                        else -> "Your patterns couldn't load. Check your connection and try again."
                    },
                )
            }
        }
    }

    private fun loadOutlook(accountId: String, showCachedFirst: Boolean) {
        outlookJob?.cancel()
        outlookJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingOutlook = true,
                outlookMessage = null,
            )

            if (showCachedFirst) {
                outlookRepository.cached(accountId)?.let { cached ->
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(outlook = cached)
                    }
                }
            }

            runCatching {
                outlookRepository.refresh(accountId)
            }.onSuccess { outlook ->
                if (isCurrentAccount(accountId)) {
                    _uiState.value = _uiState.value.copy(
                        outlook = outlook,
                        isLoadingOutlook = false,
                        outlookMessage = null,
                    )
                }
            }.onFailure {
                if (isCurrentAccount(accountId)) {
                    val hasSavedOutlook = _uiState.value.outlook != null
                    _uiState.value = _uiState.value.copy(
                        isLoadingOutlook = false,
                        outlookMessage = if (hasSavedOutlook) {
                            "Showing your saved Outlook while live details reconnect."
                        } else {
                            "Your Outlook couldn't load. Check your connection and try again."
                        },
                    )
                }
            }
        }
    }

    private fun refreshHealth() {
        if (_uiState.value.isCheckingBackend) return

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isCheckingBackend = true)
            val health = healthRepository.check()
            _uiState.value = _uiState.value.copy(
                isCheckingBackend = false,
                backendAvailable = health.isAvailable,
                backendDetail = health.detail,
            )
        }
    }

    private fun isCurrentAccount(accountId: String): Boolean {
        val signedIn = _uiState.value.authState as? AuthState.SignedIn
        return signedIn?.accountId == accountId
    }

    class Factory(
        private val authRepository: AuthRepository,
        private val bodyRepository: BodyRepository,
        private val dashboardRepository: DashboardRepository,
        private val healthRepository: HealthRepository,
        private val homeContextRepository: HomeContextRepository,
        private val journalRepository: JournalRepository,
        private val outlookRepository: OutlookRepository,
        private val patternsRepository: PatternsRepository,
        private val quickLogCoordinator: QuickLogCoordinator,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(HomeViewModel::class.java))
            return HomeViewModel(
                authRepository = authRepository,
                bodyRepository = bodyRepository,
                dashboardRepository = dashboardRepository,
                healthRepository = healthRepository,
                homeContextRepository = homeContextRepository,
                journalRepository = journalRepository,
                outlookRepository = outlookRepository,
                patternsRepository = patternsRepository,
                quickLogCoordinator = quickLogCoordinator,
            ) as T
        }
    }
}

data class HomeUiState(
    val authState: AuthState = AuthState.Initializing,
    val email: String = "",
    val isSendingMagicLink: Boolean = false,
    val magicLinkSent: Boolean = false,
    val authMessage: String? = null,
    val isSigningOut: Boolean = false,
    val selectedPage: SignedInPage = SignedInPage.HOME,
    val dashboard: DashboardSnapshot? = null,
    val isLoadingDashboard: Boolean = false,
    val dashboardMessage: String? = null,
    val body: BodySnapshot? = null,
    val isLoadingBody: Boolean = false,
    val bodyMessage: String? = null,
    val currentSymptoms: CurrentSymptomsSnapshot? = null,
    val drivers: DriversSnapshot? = null,
    val isLoadingHomeContext: Boolean = false,
    val homeContextMessage: String? = null,
    val patterns: PatternsSnapshot? = null,
    val isLoadingPatterns: Boolean = false,
    val patternsMessage: String? = null,
    val outlook: OutlookSnapshot? = null,
    val isLoadingOutlook: Boolean = false,
    val outlookMessage: String? = null,
    val journalDialog: JournalDialog? = null,
    val symptomCatalog: List<SymptomCodeOption> = emptyList(),
    val exposureCatalog: List<ExposureCatalogOption> = emptyList(),
    val dailyCheckInStatus: DailyCheckInStatus? = null,
    val isLoadingJournal: Boolean = false,
    val isSubmittingJournal: Boolean = false,
    val journalMessage: String? = null,
    val pendingJournalWrites: Int = 0,
    val isCheckingBackend: Boolean = false,
    val backendAvailable: Boolean? = null,
    val backendDetail: String = "Checking the Gaia Eyes data service",
)

enum class JournalDialog {
    SYMPTOM,
    EXPOSURE,
    DAILY_CHECK_IN,
}

enum class SignedInPage {
    HOME,
    BODY,
    PATTERNS,
    OUTLOOK,
    EXPLORE,
}

private fun String.looksLikeEmail(): Boolean {
    val separator = indexOf('@')
    return separator > 0 && separator < lastIndex && substring(separator + 1).contains('.')
}
