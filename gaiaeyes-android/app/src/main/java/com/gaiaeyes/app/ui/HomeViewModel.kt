package com.gaiaeyes.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.auth.AuthState
import com.gaiaeyes.app.core.network.DailyCheckInStatus
import com.gaiaeyes.app.core.network.ExposureCatalogOption
import com.gaiaeyes.app.core.network.CurrentSymptomUpdateRequest
import com.gaiaeyes.app.core.network.ProfileLocation
import com.gaiaeyes.app.core.network.SymptomCodeOption
import com.gaiaeyes.app.core.network.ProfileLocationUpdate
import com.gaiaeyes.app.core.network.ProfilePreferencesUpdate
import com.gaiaeyes.app.core.network.ProfileTagOption
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.core.quicklog.QuickLogRequest
import com.gaiaeyes.app.data.BodyRepository
import com.gaiaeyes.app.data.BodySnapshot
import com.gaiaeyes.app.data.DashboardRepository
import com.gaiaeyes.app.data.DashboardSnapshot
import com.gaiaeyes.app.data.DeviceLocationRepository
import com.gaiaeyes.app.data.DriversSnapshot
import com.gaiaeyes.app.data.HealthRepository
import com.gaiaeyes.app.data.HealthConnectRepository
import com.gaiaeyes.app.data.HealthConnectStatus
import com.gaiaeyes.app.data.HomeContextRepository
import com.gaiaeyes.app.data.CurrentSymptomsSnapshot
import com.gaiaeyes.app.data.LocalWeatherSnapshot
import com.gaiaeyes.app.data.JournalRepository
import com.gaiaeyes.app.data.OutlookRepository
import com.gaiaeyes.app.data.OutlookSnapshot
import com.gaiaeyes.app.data.PatternsRepository
import com.gaiaeyes.app.data.PatternsSnapshot
import com.gaiaeyes.app.data.ProfileRepository
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
    private val deviceLocationRepository: DeviceLocationRepository,
    private val healthRepository: HealthRepository,
    private val healthConnectRepository: HealthConnectRepository,
    private val homeContextRepository: HomeContextRepository,
    private val journalRepository: JournalRepository,
    private val outlookRepository: OutlookRepository,
    private val patternsRepository: PatternsRepository,
    private val profileRepository: ProfileRepository,
    private val quickLogCoordinator: QuickLogCoordinator,
) : ViewModel() {
    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    private var dashboardJob: Job? = null
    private var bodyJob: Job? = null
    private var homeContextJob: Job? = null
    private var localWeatherJob: Job? = null
    private var outlookJob: Job? = null
    private var patternsJob: Job? = null
    private var onboardingJob: Job? = null
    private var locationJob: Job? = null
    private var loadedAccountId: String? = null
    private var processingQuickLogId: String? = null
    private var lastForegroundLocationRefreshAt = 0L

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
            emailUpgradeSent = false,
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
        if (_uiState.value.isSendingMagicLink || _uiState.value.isStartingGuest) return

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

    fun continueWithoutEmail() {
        if (_uiState.value.isStartingGuest || _uiState.value.isSendingMagicLink) return

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isStartingGuest = true,
                authMessage = null,
                magicLinkSent = false,
            )
            runCatching {
                authRepository.signInAnonymously()
            }.onSuccess {
                _uiState.value = _uiState.value.copy(
                    isStartingGuest = false,
                    authMessage = null,
                )
            }.onFailure {
                _uiState.value = _uiState.value.copy(
                    isStartingGuest = false,
                    authMessage = "We couldn't start your Gaia Eyes account. Check your connection and try again.",
                )
            }
        }
    }

    fun addEmailToCurrentAccount() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (!account.isAnonymous) return
        val email = _uiState.value.email.trim()
        if (!email.looksLikeEmail()) {
            _uiState.value = _uiState.value.copy(
                authMessage = "Enter a valid email address to protect this account.",
            )
            return
        }
        if (_uiState.value.isAddingEmail) return

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isAddingEmail = true,
                emailUpgradeSent = false,
                authMessage = null,
            )
            runCatching {
                authRepository.addEmailToCurrentAccount(email)
            }.onSuccess {
                _uiState.value = _uiState.value.copy(
                    isAddingEmail = false,
                    emailUpgradeSent = true,
                    authMessage = "Check your email and open the secure link to protect your Gaia Eyes account.",
                )
            }.onFailure {
                _uiState.value = _uiState.value.copy(
                    isAddingEmail = false,
                    authMessage = "We couldn't add that email. If it already has a Gaia Eyes account, use that account's sign-in link instead.",
                )
            }
        }
    }

    fun refresh() {
        refreshHealth()
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.onboardingStatus != OnboardingStatus.COMPLETE) {
            loadOnboarding(account.accountId)
            return
        }
        retryJournalWrites(account.accountId, showSuccessMessage = false)
        when (_uiState.value.selectedPage) {
            SignedInPage.HOME -> {
                loadDashboard(account.accountId, showCachedFirst = false)
                loadHomeContext(account.accountId, showCachedFirst = false)
            }
            SignedInPage.BODY -> {
                loadBody(account.accountId, showCachedFirst = false)
                loadHomeContext(account.accountId, showCachedFirst = false)
            }
            SignedInPage.PATTERNS -> loadPatterns(account.accountId, showCachedFirst = false)
            SignedInPage.OUTLOOK -> loadOutlook(account.accountId, showCachedFirst = false)
            SignedInPage.EXPLORE -> {
                loadHomeContext(account.accountId, showCachedFirst = false)
                refreshLocalWeather()
            }
        }
    }

    fun onOnboardingModeChanged(value: String) {
        _uiState.value = _uiState.value.copy(onboardingMode = value, onboardingMessage = null)
    }

    fun onOnboardingToneChanged(value: String) {
        _uiState.value = _uiState.value.copy(onboardingTone = value, onboardingMessage = null)
    }

    fun onOnboardingTemperatureUnitChanged(value: String) {
        _uiState.value = _uiState.value.copy(onboardingTemperatureUnit = value, onboardingMessage = null)
    }

    fun toggleOnboardingTag(tagKey: String) {
        val next = _uiState.value.onboardingSelectedTags.toMutableSet().apply {
            if (!add(tagKey)) remove(tagKey)
        }
        _uiState.value = _uiState.value.copy(
            onboardingSelectedTags = next,
            onboardingMessage = null,
        )
    }

    fun onOnboardingLocalInsightsChanged(enabled: Boolean) {
        _uiState.value = _uiState.value.copy(
            onboardingLocalInsightsEnabled = enabled,
            onboardingMessage = null,
        )
    }

    fun onOnboardingZipChanged(value: String) {
        _uiState.value = _uiState.value.copy(
            onboardingZip = value.filter(Char::isDigit).take(5),
            onboardingUseGps = false,
            onboardingLatitude = null,
            onboardingLongitude = null,
            onboardingMessage = null,
        )
    }

    fun onLocationLocalInsightsChanged(enabled: Boolean) {
        _uiState.value = _uiState.value.copy(
            locationLocalInsightsEnabled = enabled,
            locationSettingsMessage = null,
        )
    }

    fun onLocationZipChanged(value: String) {
        _uiState.value = _uiState.value.copy(
            locationZip = value.filter(Char::isDigit).take(5),
            locationUseGps = false,
            locationLatitude = null,
            locationLongitude = null,
            locationSettingsMessage = null,
        )
    }

    fun onLocationPermissionDenied(forOnboarding: Boolean) {
        val message = "Location access wasn't granted. You can still use a saved ZIP code."
        _uiState.value = if (forOnboarding) {
            _uiState.value.copy(onboardingMessage = message)
        } else {
            _uiState.value.copy(locationSettingsMessage = message)
        }
    }

    fun useCurrentDeviceLocation(forOnboarding: Boolean) {
        updateFromDeviceLocation(forOnboarding = forOnboarding, showMessage = true)
    }

    fun saveLocationSettings() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        val state = _uiState.value
        if (state.isSavingLocation || state.isLocatingDevice) return
        if (state.locationLocalInsightsEnabled && !isValidOnboardingZip(state.locationZip)) {
            _uiState.value = state.copy(
                locationSettingsMessage = "Enter a 5-digit ZIP code or use your current location.",
            )
            return
        }

        locationJob?.cancel()
        locationJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isSavingLocation = true,
                locationSettingsMessage = null,
            )
            runCatching {
                profileRepository.saveLocation(
                    ProfileLocationUpdate(
                        zip = state.locationZip.takeIf { state.locationLocalInsightsEnabled },
                        lat = state.locationLatitude.takeIf { state.locationLocalInsightsEnabled },
                        lon = state.locationLongitude.takeIf { state.locationLocalInsightsEnabled },
                        useGps = state.locationUseGps && state.locationLocalInsightsEnabled,
                        localInsightsEnabled = state.locationLocalInsightsEnabled,
                    ),
                )
            }.onSuccess { location ->
                if (!isCurrentAccount(account.accountId)) return@onSuccess
                hydrateLocationSettings(location)
                _uiState.value = _uiState.value.copy(
                    isSavingLocation = false,
                    locationSettingsMessage = if (state.locationLocalInsightsEnabled) {
                        "Local conditions updated for ZIP ${state.locationZip}."
                    } else {
                        "Local conditions are turned off."
                    },
                )
                loadLocalWeather(account.accountId, showCachedFirst = false)
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isSavingLocation = false,
                        locationSettingsMessage = "Your local settings couldn't be saved. Check your connection and try again.",
                    )
                }
            }
        }
    }

    fun refreshLocalWeather() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (
            _uiState.value.locationUseGps &&
            _uiState.value.locationLocalInsightsEnabled &&
            deviceLocationRepository.hasPermission()
        ) {
            updateFromDeviceLocation(forOnboarding = false, showMessage = false)
        } else {
            loadLocalWeather(account.accountId, showCachedFirst = false)
        }
    }

    fun refreshForegroundLocation() {
        val state = _uiState.value
        if (
            state.onboardingStatus != OnboardingStatus.COMPLETE ||
            !state.locationSettingsLoaded ||
            !state.locationUseGps ||
            !state.locationLocalInsightsEnabled ||
            !deviceLocationRepository.hasPermission() ||
            state.isLocatingDevice
        ) return
        val now = System.currentTimeMillis()
        if (now - lastForegroundLocationRefreshAt < FOREGROUND_LOCATION_REFRESH_INTERVAL_MS) return
        lastForegroundLocationRefreshAt = now
        updateFromDeviceLocation(forOnboarding = false, showMessage = false)
    }

    fun previousOnboardingStep() {
        val previous = when (_uiState.value.onboardingStep) {
            OnboardingStep.WELCOME -> OnboardingStep.WELCOME
            OnboardingStep.PREFERENCES -> OnboardingStep.WELCOME
            OnboardingStep.HEALTH_CONTEXT -> OnboardingStep.PREFERENCES
            OnboardingStep.LOCATION -> OnboardingStep.HEALTH_CONTEXT
            OnboardingStep.HEALTH_CONNECT -> OnboardingStep.LOCATION
            OnboardingStep.READY -> OnboardingStep.HEALTH_CONNECT
        }
        _uiState.value = _uiState.value.copy(onboardingStep = previous, onboardingMessage = null)
    }

    fun continueOnboarding() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isSavingOnboarding) return
        val state = _uiState.value
        if (
            state.onboardingStep == OnboardingStep.LOCATION &&
            state.onboardingLocalInsightsEnabled &&
            !isValidOnboardingZip(state.onboardingZip)
        ) {
            _uiState.value = state.copy(
                onboardingMessage = "Enter a 5-digit ZIP code, use your current location, or choose Not now.",
            )
            return
        }

        onboardingJob?.cancel()
        onboardingJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSavingOnboarding = true, onboardingMessage = null)
            runCatching {
                when (state.onboardingStep) {
                    OnboardingStep.WELCOME -> {
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(onboardingStep = "mode"),
                        )
                        OnboardingStep.PREFERENCES
                    }
                    OnboardingStep.PREFERENCES -> {
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(
                                mode = state.onboardingMode,
                                guide = "cat",
                                tone = state.onboardingTone,
                                tempUnit = state.onboardingTemperatureUnit,
                                onboardingStep = "health_context",
                            ),
                        )
                        OnboardingStep.HEALTH_CONTEXT
                    }
                    OnboardingStep.HEALTH_CONTEXT -> {
                        profileRepository.saveTags(state.onboardingSelectedTags)
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(onboardingStep = "location"),
                        )
                        OnboardingStep.LOCATION
                    }
                    OnboardingStep.LOCATION -> {
                        profileRepository.saveLocation(
                            ProfileLocationUpdate(
                                zip = state.onboardingZip.takeIf {
                                    state.onboardingLocalInsightsEnabled
                                },
                                lat = state.onboardingLatitude.takeIf {
                                    state.onboardingLocalInsightsEnabled
                                },
                                lon = state.onboardingLongitude.takeIf {
                                    state.onboardingLocalInsightsEnabled
                                },
                                useGps = state.onboardingUseGps &&
                                    state.onboardingLocalInsightsEnabled,
                                localInsightsEnabled = state.onboardingLocalInsightsEnabled,
                            ),
                        )
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(onboardingStep = "healthkit"),
                        )
                        OnboardingStep.HEALTH_CONNECT
                    }
                    OnboardingStep.HEALTH_CONNECT -> {
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(onboardingStep = "activation"),
                        )
                        OnboardingStep.READY
                    }
                    OnboardingStep.READY -> {
                        profileRepository.savePreferences(
                            ProfilePreferencesUpdate(
                                onboardingStep = "activation",
                                onboardingCompleted = true,
                            ),
                        )
                        null
                    }
                }
            }.onSuccess { nextStep ->
                if (!isCurrentAccount(account.accountId)) return@onSuccess
                if (nextStep == null) {
                    _uiState.value = _uiState.value.copy(
                        onboardingStatus = OnboardingStatus.COMPLETE,
                        isSavingOnboarding = false,
                        onboardingMessage = null,
                    )
                    loadSignedInContent(account.accountId)
                } else {
                    _uiState.value = _uiState.value.copy(
                        onboardingStep = nextStep,
                        isSavingOnboarding = false,
                    )
                }
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isSavingOnboarding = false,
                        onboardingMessage = "That choice couldn't be saved. Check your connection and try again.",
                    )
                }
            }
        }
    }

    fun refreshHealthConnect() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                healthConnectStatus = HealthConnectStatus.CHECKING,
                healthConnectMessage = null,
            )
            runCatching {
                val status = healthConnectRepository.status()
                val pending = healthConnectRepository.pendingCount(account.accountId)
                status to pending
            }.onSuccess { (status, pending) ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        healthConnectStatus = status,
                        pendingHealthSampleBatches = pending,
                    )
                }
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        healthConnectStatus = HealthConnectStatus.UNAVAILABLE,
                        healthConnectMessage = "Health Connect couldn't be checked on this device.",
                    )
                }
            }
        }
    }

    fun importHealthConnect() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isImportingHealthConnect) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isImportingHealthConnect = true,
                healthConnectMessage = null,
            )
            runCatching {
                healthConnectRepository.importRecent(account.accountId)
            }.onSuccess { result ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isImportingHealthConnect = false,
                        healthConnectImportedCount = result.importedSampleCount,
                        pendingHealthSampleBatches = result.pendingBatchCount,
                        healthConnectMessage = if (result.pendingBatchCount == 0) {
                            "Imported ${result.importedSampleCount} Health Connect readings."
                        } else {
                            "Imported ${result.importedSampleCount} readings. Saved batches will retry automatically."
                        },
                    )
                    loadBody(account.accountId, showCachedFirst = false)
                }
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isImportingHealthConnect = false,
                        healthConnectMessage = "Health data couldn't import. Check Health Connect access and try again.",
                    )
                }
            }
        }
    }

    fun selectPage(page: SignedInPage) {
        _uiState.value = _uiState.value.copy(selectedPage = page)
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        when (page) {
            SignedInPage.HOME -> Unit
            SignedInPage.BODY -> {
                if (_uiState.value.body == null) {
                    loadBody(account.accountId, showCachedFirst = true)
                }
                if (_uiState.value.currentSymptoms == null) {
                    loadHomeContext(account.accountId, showCachedFirst = true)
                }
            }
            SignedInPage.PATTERNS -> if (_uiState.value.patterns == null) {
                loadPatterns(account.accountId, showCachedFirst = true)
            }
            SignedInPage.OUTLOOK -> if (_uiState.value.outlook == null) {
                loadOutlook(account.accountId, showCachedFirst = true)
            }
            SignedInPage.EXPLORE -> {
                if (_uiState.value.drivers == null) {
                    loadHomeContext(account.accountId, showCachedFirst = true)
                }
                if (!_uiState.value.locationSettingsLoaded) {
                    loadLocationSettings(account.accountId)
                }
                if (_uiState.value.localWeather == null) {
                    loadLocalWeather(account.accountId, showCachedFirst = true)
                }
            }
        }
    }

    fun signOut() {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isSigningOut) return
        if (account.isAnonymous) {
            _uiState.value = _uiState.value.copy(
                authMessage = "Add an email before signing out so you don't lose access to this account.",
            )
            return
        }

        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isSigningOut = true, authMessage = null)
            runCatching {
                dashboardRepository.clear(account.accountId)
                bodyRepository.clear(account.accountId)
                homeContextRepository.clear(account.accountId)
                journalRepository.clear(account.accountId)
                healthConnectRepository.clear(account.accountId)
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
            healthConnectMessage = null,
            localWeatherMessage = null,
            symptomActionMessage = null,
        )
    }

    fun updateCurrentSymptom(
        episodeId: String,
        state: String? = null,
        severity: Int? = null,
        note: String? = null,
    ) {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isUpdatingSymptoms || episodeId.isBlank()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isUpdatingSymptoms = true,
                journalMessage = null,
                symptomActionMessage = null,
            )
            runCatching {
                homeContextRepository.updateCurrentSymptom(
                    accountId = account.accountId,
                    episodeId = episodeId,
                    request = CurrentSymptomUpdateRequest(
                        state = state,
                        severity = severity,
                        noteText = note?.trim()?.takeIf(String::isNotEmpty),
                        timestampUtc = Instant.now().toString(),
                    ),
                )
            }.onSuccess { (_, symptoms) ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        currentSymptoms = symptoms,
                        isUpdatingSymptoms = false,
                        symptomActionMessage = when (state) {
                            "resolved" -> "Symptom marked resolved."
                            "improving" -> "Symptom marked improving."
                            "worse" -> "Symptom update saved."
                            else -> "Symptom details updated."
                        },
                    )
                    loadDashboard(account.accountId, showCachedFirst = false)
                    loadHomeContext(account.accountId, showCachedFirst = false)
                }
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isUpdatingSymptoms = false,
                        symptomActionMessage = "That symptom couldn't be updated. Check your connection and try again.",
                    )
                }
            }
        }
    }

    fun deleteCurrentSymptom(episodeId: String) {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isUpdatingSymptoms || episodeId.isBlank()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isUpdatingSymptoms = true,
                journalMessage = null,
                symptomActionMessage = null,
            )
            runCatching {
                homeContextRepository.deleteCurrentSymptom(account.accountId, episodeId)
            }.onSuccess { (_, symptoms) ->
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        currentSymptoms = symptoms,
                        isUpdatingSymptoms = false,
                        symptomActionMessage = "Symptom entry deleted.",
                    )
                    loadDashboard(account.accountId, showCachedFirst = false)
                    loadHomeContext(account.accountId, showCachedFirst = false)
                }
            }.onFailure {
                if (isCurrentAccount(account.accountId)) {
                    _uiState.value = _uiState.value.copy(
                        isUpdatingSymptoms = false,
                        symptomActionMessage = "That symptom couldn't be deleted. Check your connection and try again.",
                    )
                }
            }
        }
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
            isStartingGuest = false,
        )

        if (authState is AuthState.SignedIn) {
            _uiState.value = _uiState.value.copy(
                email = authState.email ?: _uiState.value.email,
                emailUpgradeSent = if (authState.isAnonymous) {
                    _uiState.value.emailUpgradeSent
                } else {
                    false
                },
            )
            if (loadedAccountId != authState.accountId) {
                loadedAccountId = authState.accountId
                loadOnboarding(authState.accountId)
            }
            if (_uiState.value.onboardingStatus == OnboardingStatus.COMPLETE) {
                maybeHandleQuickLog(quickLogCoordinator.pending.value)
            }
            return
        }

        dashboardJob?.cancel()
        dashboardJob = null
        bodyJob?.cancel()
        bodyJob = null
        homeContextJob?.cancel()
        homeContextJob = null
        localWeatherJob?.cancel()
        localWeatherJob = null
        patternsJob?.cancel()
        patternsJob = null
        outlookJob?.cancel()
        outlookJob = null
        onboardingJob?.cancel()
        onboardingJob = null
        locationJob?.cancel()
        locationJob = null
        lastForegroundLocationRefreshAt = 0L
        loadedAccountId = null
        _uiState.value = _uiState.value.copy(
            dashboard = null,
            isLoadingDashboard = false,
            dashboardMessage = null,
            body = null,
            isLoadingBody = false,
            bodyMessage = null,
            selectedPage = SignedInPage.HOME,
            onboardingStatus = OnboardingStatus.CHECKING,
            onboardingStep = OnboardingStep.WELCOME,
            onboardingUseGps = false,
            onboardingLatitude = null,
            onboardingLongitude = null,
            isSavingOnboarding = false,
            onboardingMessage = null,
            currentSymptoms = null,
            drivers = null,
            isLoadingHomeContext = false,
            homeContextMessage = null,
            localWeather = null,
            isLoadingLocalWeather = false,
            localWeatherMessage = null,
            locationLocalInsightsEnabled = true,
            locationZip = "",
            locationUseGps = false,
            locationLatitude = null,
            locationLongitude = null,
            locationSettingsLoaded = false,
            isLocatingDevice = false,
            isSavingLocation = false,
            locationSettingsMessage = null,
            isUpdatingSymptoms = false,
            symptomActionMessage = null,
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
            healthConnectStatus = HealthConnectStatus.CHECKING,
            isImportingHealthConnect = false,
            healthConnectMessage = null,
            healthConnectImportedCount = 0,
            pendingHealthSampleBatches = 0,
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
        if (_uiState.value.onboardingStatus != OnboardingStatus.COMPLETE) return

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

    private fun loadOnboarding(accountId: String) {
        onboardingJob?.cancel()
        onboardingJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                onboardingStatus = OnboardingStatus.CHECKING,
                onboardingMessage = null,
            )
            runCatching { profileRepository.load() }
                .onSuccess { profile ->
                    if (!isCurrentAccount(accountId)) return@onSuccess
                    if (profile.preferences.onboardingCompleted) {
                        _uiState.value = _uiState.value.copy(
                            onboardingStatus = OnboardingStatus.COMPLETE,
                            onboardingMessage = null,
                        )
                        loadSignedInContent(accountId)
                    } else {
                        _uiState.value = _uiState.value.copy(
                            onboardingStatus = OnboardingStatus.REQUIRED,
                            onboardingStep = onboardingStepFor(profile.preferences.onboardingStep),
                            onboardingMode = profile.preferences.mode,
                            onboardingTone = profile.preferences.tone,
                            onboardingTemperatureUnit = profile.preferences.tempUnit ?: "F",
                            onboardingTagCatalog = profile.tagCatalog,
                            onboardingSelectedTags = profile.selectedTags,
                            onboardingLocalInsightsEnabled =
                                profile.location?.localInsightsEnabled != false,
                            onboardingZip = profile.location?.zip.orEmpty(),
                            onboardingUseGps = profile.location?.useGps == true,
                            onboardingLatitude = profile.location?.lat,
                            onboardingLongitude = profile.location?.lon,
                            onboardingMessage = null,
                        )
                        hydrateLocationSettings(profile.location)
                        refreshHealthConnect()
                    }
                }
                .onFailure {
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(
                            onboardingStatus = OnboardingStatus.REQUIRED,
                            onboardingStep = OnboardingStep.WELCOME,
                            onboardingMessage = "Setup couldn't load. Check your connection and try again.",
                        )
                    }
                }
        }
    }

    private fun loadSignedInContent(accountId: String) {
        loadDashboard(accountId, showCachedFirst = true)
        loadHomeContext(accountId, showCachedFirst = true)
        loadLocationSettings(accountId)
        refreshHealthConnect()
        if (quickLogCoordinator.pending.value == null) {
            retryJournalWrites(accountId, showSuccessMessage = false)
        }
        maybeHandleQuickLog(quickLogCoordinator.pending.value)
    }

    private fun loadLocationSettings(accountId: String) {
        locationJob?.cancel()
        locationJob = viewModelScope.launch {
            runCatching { profileRepository.loadLocation() }
                .onSuccess { location ->
                    if (isCurrentAccount(accountId)) {
                        hydrateLocationSettings(location)
                    }
                }
                .onFailure {
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(
                            locationSettingsLoaded = true,
                            locationSettingsMessage = "Your saved location couldn't load. You can try again from Settings.",
                        )
                    }
                }
        }
    }

    private fun updateFromDeviceLocation(forOnboarding: Boolean, showMessage: Boolean) {
        val account = _uiState.value.authState as? AuthState.SignedIn ?: return
        if (_uiState.value.isLocatingDevice || _uiState.value.isSavingLocation) return
        if (!deviceLocationRepository.hasPermission()) {
            onLocationPermissionDenied(forOnboarding)
            return
        }

        locationJob?.cancel()
        locationJob = viewModelScope.launch {
            _uiState.value = if (forOnboarding) {
                _uiState.value.copy(isLocatingDevice = true, onboardingMessage = null)
            } else {
                _uiState.value.copy(isLocatingDevice = true, locationSettingsMessage = null)
            }

            runCatching { deviceLocationRepository.currentPostalLocation() }
                .onSuccess { deviceLocation ->
                    if (!isCurrentAccount(account.accountId)) return@onSuccess
                    if (forOnboarding) {
                        _uiState.value = _uiState.value.copy(
                            onboardingLocalInsightsEnabled = true,
                            onboardingZip = deviceLocation.zip,
                            onboardingUseGps = true,
                            onboardingLatitude = deviceLocation.latitude,
                            onboardingLongitude = deviceLocation.longitude,
                            isLocatingDevice = false,
                            onboardingMessage = "Current location found. ZIP ${deviceLocation.zip} will remain your fallback.",
                        )
                    } else {
                        runCatching {
                            profileRepository.saveLocation(
                                ProfileLocationUpdate(
                                    zip = deviceLocation.zip,
                                    lat = deviceLocation.latitude,
                                    lon = deviceLocation.longitude,
                                    useGps = true,
                                    localInsightsEnabled = true,
                                ),
                            )
                        }.onSuccess saveLocationSuccess@{ savedLocation ->
                            if (!isCurrentAccount(account.accountId)) return@saveLocationSuccess
                            hydrateLocationSettings(
                                savedLocation ?: ProfileLocation(
                                    zip = deviceLocation.zip,
                                    lat = deviceLocation.latitude,
                                    lon = deviceLocation.longitude,
                                    useGps = true,
                                    localInsightsEnabled = true,
                                ),
                            )
                            _uiState.value = _uiState.value.copy(
                                isLocatingDevice = false,
                                locationSettingsMessage = if (showMessage) {
                                    "Using your current location. ZIP ${deviceLocation.zip} is saved as a fallback."
                                } else {
                                    null
                                },
                            )
                            loadLocalWeather(account.accountId, showCachedFirst = false)
                        }.onFailure {
                            if (isCurrentAccount(account.accountId)) {
                                _uiState.value = _uiState.value.copy(
                                    isLocatingDevice = false,
                                    locationSettingsMessage = "Your current location was found, but it couldn't be saved. Try again shortly.",
                                )
                            }
                        }
                    }
                }
                .onFailure { error ->
                    if (!isCurrentAccount(account.accountId)) return@onFailure
                    val message = error.message
                        ?: "Your current location couldn't be found. Try again or enter a ZIP code."
                    _uiState.value = if (forOnboarding) {
                        _uiState.value.copy(isLocatingDevice = false, onboardingMessage = message)
                    } else {
                        _uiState.value.copy(isLocatingDevice = false, locationSettingsMessage = message)
                    }
                    if (!forOnboarding && !showMessage) {
                        loadLocalWeather(account.accountId, showCachedFirst = false)
                    }
                }
        }
    }

    private fun hydrateLocationSettings(location: ProfileLocation?) {
        _uiState.value = _uiState.value.copy(
            locationLocalInsightsEnabled = location?.localInsightsEnabled != false,
            locationZip = location?.zip.orEmpty(),
            locationUseGps = location?.useGps == true,
            locationLatitude = location?.lat,
            locationLongitude = location?.lon,
            locationSettingsLoaded = true,
        )
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

    private fun loadLocalWeather(accountId: String, showCachedFirst: Boolean) {
        localWeatherJob?.cancel()
        localWeatherJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                isLoadingLocalWeather = true,
                localWeatherMessage = null,
            )

            if (showCachedFirst) {
                homeContextRepository.cachedLocal(accountId)?.let { cached ->
                    if (isCurrentAccount(accountId)) {
                        _uiState.value = _uiState.value.copy(localWeather = cached)
                    }
                }
            }

            runCatching {
                homeContextRepository.refreshLocal(accountId)
            }.onSuccess { localWeather ->
                if (isCurrentAccount(accountId)) {
                    hydrateLocationSettings(localWeather.location)
                    _uiState.value = _uiState.value.copy(
                        localWeather = localWeather,
                        isLoadingLocalWeather = false,
                        localWeatherMessage = when {
                            localWeather.location == null -> "Add a ZIP code in Gaia Eyes to see local conditions."
                            localWeather.location.localInsightsEnabled == false -> "Local conditions are turned off in your Gaia Eyes profile."
                            localWeather.local == null -> "Local conditions aren't available for this location yet."
                            else -> null
                        },
                    )
                }
            }.onFailure {
                if (isCurrentAccount(accountId)) {
                    val hasCachedLocal = _uiState.value.localWeather?.local != null
                    _uiState.value = _uiState.value.copy(
                        isLoadingLocalWeather = false,
                        localWeatherMessage = if (hasCachedLocal) {
                            "Showing saved local conditions while live data reconnects."
                        } else {
                            "Local conditions couldn't load. Check your connection and try again."
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
        private val deviceLocationRepository: DeviceLocationRepository,
        private val healthRepository: HealthRepository,
        private val healthConnectRepository: HealthConnectRepository,
        private val homeContextRepository: HomeContextRepository,
        private val journalRepository: JournalRepository,
        private val outlookRepository: OutlookRepository,
        private val patternsRepository: PatternsRepository,
        private val profileRepository: ProfileRepository,
        private val quickLogCoordinator: QuickLogCoordinator,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(HomeViewModel::class.java))
            return HomeViewModel(
                authRepository = authRepository,
                bodyRepository = bodyRepository,
                dashboardRepository = dashboardRepository,
                deviceLocationRepository = deviceLocationRepository,
                healthRepository = healthRepository,
                healthConnectRepository = healthConnectRepository,
                homeContextRepository = homeContextRepository,
                journalRepository = journalRepository,
                outlookRepository = outlookRepository,
                patternsRepository = patternsRepository,
                profileRepository = profileRepository,
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
    val isStartingGuest: Boolean = false,
    val isAddingEmail: Boolean = false,
    val emailUpgradeSent: Boolean = false,
    val authMessage: String? = null,
    val isSigningOut: Boolean = false,
    val selectedPage: SignedInPage = SignedInPage.HOME,
    val onboardingStatus: OnboardingStatus = OnboardingStatus.CHECKING,
    val onboardingStep: OnboardingStep = OnboardingStep.WELCOME,
    val onboardingMode: String = "scientific",
    val onboardingTone: String = "balanced",
    val onboardingTemperatureUnit: String = "F",
    val onboardingTagCatalog: List<ProfileTagOption> = emptyList(),
    val onboardingSelectedTags: Set<String> = emptySet(),
    val onboardingLocalInsightsEnabled: Boolean = true,
    val onboardingZip: String = "",
    val onboardingUseGps: Boolean = false,
    val onboardingLatitude: Double? = null,
    val onboardingLongitude: Double? = null,
    val isSavingOnboarding: Boolean = false,
    val onboardingMessage: String? = null,
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
    val localWeather: LocalWeatherSnapshot? = null,
    val isLoadingLocalWeather: Boolean = false,
    val localWeatherMessage: String? = null,
    val locationLocalInsightsEnabled: Boolean = true,
    val locationZip: String = "",
    val locationUseGps: Boolean = false,
    val locationLatitude: Double? = null,
    val locationLongitude: Double? = null,
    val locationSettingsLoaded: Boolean = false,
    val isLocatingDevice: Boolean = false,
    val isSavingLocation: Boolean = false,
    val locationSettingsMessage: String? = null,
    val isUpdatingSymptoms: Boolean = false,
    val symptomActionMessage: String? = null,
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
    val healthConnectStatus: HealthConnectStatus = HealthConnectStatus.CHECKING,
    val isImportingHealthConnect: Boolean = false,
    val healthConnectMessage: String? = null,
    val healthConnectImportedCount: Int = 0,
    val pendingHealthSampleBatches: Int = 0,
    val isCheckingBackend: Boolean = false,
    val backendAvailable: Boolean? = null,
    val backendDetail: String = "Checking the Gaia Eyes data service",
)

enum class OnboardingStatus {
    CHECKING,
    REQUIRED,
    COMPLETE,
}

enum class OnboardingStep {
    WELCOME,
    PREFERENCES,
    HEALTH_CONTEXT,
    LOCATION,
    HEALTH_CONNECT,
    READY,
}

internal fun onboardingStepFor(value: String): OnboardingStep = when (value) {
    "mode", "guide", "tone", "temperature_unit", "sensitivities" -> OnboardingStep.PREFERENCES
    "health_context" -> OnboardingStep.HEALTH_CONTEXT
    "location" -> OnboardingStep.LOCATION
    "healthkit", "backfill", "notifications" -> OnboardingStep.HEALTH_CONNECT
    "activation" -> OnboardingStep.READY
    else -> OnboardingStep.WELCOME
}

internal fun isValidOnboardingZip(value: String): Boolean =
    value.length == 5 && value.all(Char::isDigit)

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

private const val FOREGROUND_LOCATION_REFRESH_INTERVAL_MS = 5 * 60 * 1_000L
