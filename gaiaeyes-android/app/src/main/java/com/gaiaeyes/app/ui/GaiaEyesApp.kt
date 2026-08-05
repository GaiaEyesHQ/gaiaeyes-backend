package com.gaiaeyes.app.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaiaeyes.app.BuildConfig
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.core.auth.AuthState
import com.gaiaeyes.app.core.network.DashboardGaugesResponse
import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.DriverItem
import com.gaiaeyes.app.core.network.FeaturesTodayResponse
import com.gaiaeyes.app.core.network.OutlookDay
import com.gaiaeyes.app.core.network.OutlookDomain
import com.gaiaeyes.app.core.network.OutlookDriver
import com.gaiaeyes.app.core.network.PatternCard
import com.gaiaeyes.app.data.BodyRepository
import com.gaiaeyes.app.data.BodySource
import com.gaiaeyes.app.data.DashboardRepository
import com.gaiaeyes.app.data.DashboardSource
import com.gaiaeyes.app.data.DeviceLocationRepository
import com.gaiaeyes.app.data.HealthRepository
import com.gaiaeyes.app.data.HealthConnectRepository
import com.gaiaeyes.app.data.HealthConnectStatus
import com.gaiaeyes.app.data.HomeContextRepository
import com.gaiaeyes.app.data.HomeContextSource
import com.gaiaeyes.app.data.JournalRepository
import com.gaiaeyes.app.data.LocalWeatherSnapshot
import com.gaiaeyes.app.data.OutlookRepository
import com.gaiaeyes.app.data.OutlookSource
import com.gaiaeyes.app.data.PatternsRepository
import com.gaiaeyes.app.data.PatternsSource
import com.gaiaeyes.app.data.ProfileRepository
import com.gaiaeyes.app.ui.theme.GaiaAmber
import com.gaiaeyes.app.ui.theme.GaiaBlue
import com.gaiaeyes.app.ui.theme.GaiaGreen
import com.gaiaeyes.app.ui.theme.GaiaNavy
import com.gaiaeyes.app.ui.theme.GaiaPanel
import com.gaiaeyes.app.ui.theme.GaiaRose
import kotlin.math.roundToInt

@Composable
fun GaiaEyesApp(
    authRepository: AuthRepository,
    bodyRepository: BodyRepository,
    dashboardRepository: DashboardRepository,
    deviceLocationRepository: DeviceLocationRepository,
    healthRepository: HealthRepository,
    healthConnectRepository: HealthConnectRepository,
    homeContextRepository: HomeContextRepository,
    journalRepository: JournalRepository,
    outlookRepository: OutlookRepository,
    patternsRepository: PatternsRepository,
    profileRepository: ProfileRepository,
    quickLogCoordinator: QuickLogCoordinator,
    modifier: Modifier = Modifier,
) {
    val viewModel: HomeViewModel = viewModel(
        factory = HomeViewModel.Factory(
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
        ),
    )
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    var showSettings by rememberSaveable { mutableStateOf(false) }
    var showCurrentSymptoms by rememberSaveable { mutableStateOf(false) }
    var showLocalWeather by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    var locationRequestForOnboarding by rememberSaveable { mutableStateOf(false) }
    val healthConnectPermissionLauncher = rememberLauncherForActivityResult(
        contract = healthConnectRepository.permissionContract(),
        onResult = { viewModel.refreshHealthConnect() },
    )
    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            viewModel.useCurrentDeviceLocation(locationRequestForOnboarding)
        } else {
            viewModel.onLocationPermissionDenied(locationRequestForOnboarding)
        }
    }
    val requestCurrentLocation: (Boolean) -> Unit = { forOnboarding ->
        locationRequestForOnboarding = forOnboarding
        if (
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            viewModel.useCurrentDeviceLocation(forOnboarding)
        } else {
            locationPermissionLauncher.launch(Manifest.permission.ACCESS_COARSE_LOCATION)
        }
    }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        viewModel.refreshForegroundLocation()
    }

    when (val authState = uiState.authState) {
        AuthState.Initializing -> LoadingScreen(modifier)
        AuthState.Unavailable -> ConfigurationScreen(
            modifier = modifier,
        )
        AuthState.SignedOut -> SignInScreen(
            uiState = uiState,
            onEmailChanged = viewModel::onEmailChanged,
            onSendMagicLink = viewModel::sendMagicLink,
            onContinueWithoutEmail = viewModel::continueWithoutEmail,
            onDismissMessage = viewModel::dismissMessage,
            onRetry = viewModel::refresh,
            modifier = modifier,
        )
        is AuthState.SessionProblem -> SignInScreen(
            uiState = uiState.copy(authMessage = uiState.authMessage ?: authState.message),
            onEmailChanged = viewModel::onEmailChanged,
            onSendMagicLink = viewModel::sendMagicLink,
            onContinueWithoutEmail = viewModel::continueWithoutEmail,
            onDismissMessage = viewModel::dismissMessage,
            onRetry = viewModel::refresh,
            modifier = modifier,
        )
        is AuthState.SignedIn -> if (uiState.onboardingStatus == OnboardingStatus.CHECKING) {
            LoadingScreen(modifier)
        } else if (uiState.onboardingStatus == OnboardingStatus.REQUIRED) {
            OnboardingScreen(
                uiState = uiState,
                onModeChanged = viewModel::onOnboardingModeChanged,
                onToneChanged = viewModel::onOnboardingToneChanged,
                onTemperatureUnitChanged = viewModel::onOnboardingTemperatureUnitChanged,
                onToggleTag = viewModel::toggleOnboardingTag,
                onLocalInsightsChanged = viewModel::onOnboardingLocalInsightsChanged,
                onZipChanged = viewModel::onOnboardingZipChanged,
                onUseDeviceLocation = { requestCurrentLocation(true) },
                onBack = viewModel::previousOnboardingStep,
                onContinue = viewModel::continueOnboarding,
                onConnectHealth = {
                    healthConnectPermissionLauncher.launch(healthConnectRepository.requiredPermissions)
                },
                onRetry = viewModel::refresh,
                onSignOut = viewModel::signOut,
                modifier = modifier,
            )
        } else if (showSettings) {
            SettingsScreen(
                uiState = uiState,
                account = authState,
                onBack = { showSettings = false },
                onRefresh = viewModel::refresh,
                onEmailChanged = viewModel::onEmailChanged,
                onAddEmail = viewModel::addEmailToCurrentAccount,
                onLocalInsightsChanged = viewModel::onLocationLocalInsightsChanged,
                onZipChanged = viewModel::onLocationZipChanged,
                onUseDeviceLocation = { requestCurrentLocation(false) },
                onSaveLocation = viewModel::saveLocationSettings,
                onDismissMessage = viewModel::dismissMessage,
                onSignOut = {
                    showSettings = false
                    showCurrentSymptoms = false
                    showLocalWeather = false
                    viewModel.signOut()
                },
                modifier = modifier,
            )
        } else if (showCurrentSymptoms) {
            CurrentSymptomsScreen(
                uiState = uiState,
                onClose = { showCurrentSymptoms = false },
                onRefresh = viewModel::refresh,
                onLogSymptom = viewModel::openSymptomLog,
                onUpdateSymptom = viewModel::updateCurrentSymptom,
                onDeleteSymptom = viewModel::deleteCurrentSymptom,
                onDismissMessage = viewModel::dismissMessage,
                modifier = modifier,
            )
        } else if (showLocalWeather) {
            LocalWeatherScreen(
                uiState = uiState,
                onClose = { showLocalWeather = false },
                onRefresh = viewModel::refreshLocalWeather,
                onLocalInsightsChanged = viewModel::onLocationLocalInsightsChanged,
                onZipChanged = viewModel::onLocationZipChanged,
                onUseDeviceLocation = { requestCurrentLocation(false) },
                onSaveLocation = viewModel::saveLocationSettings,
                onDismissMessage = viewModel::dismissMessage,
                modifier = modifier,
            )
        } else when (uiState.selectedPage) {
            SignedInPage.HOME -> HomeScreen(
                uiState = uiState,
                account = authState,
                onRefresh = viewModel::refresh,
                onOpenSettings = { showSettings = true },
                onDismissMessage = viewModel::dismissMessage,
                onSelectPage = viewModel::selectPage,
                onLogSymptom = viewModel::openSymptomLog,
                onLogExposure = viewModel::openExposureLog,
                onDailyCheckIn = viewModel::openDailyCheckIn,
                onOpenCurrentSymptoms = { showCurrentSymptoms = true },
                modifier = modifier,
            )
            SignedInPage.BODY -> BodyScreen(
                uiState = uiState,
                account = authState,
                onRefresh = viewModel::refresh,
                onOpenSettings = { showSettings = true },
                onDismissMessage = viewModel::dismissMessage,
                onSelectPage = viewModel::selectPage,
                onConnectHealth = {
                    healthConnectPermissionLauncher.launch(healthConnectRepository.requiredPermissions)
                },
                onImportHealth = viewModel::importHealthConnect,
                onOpenCurrentSymptoms = { showCurrentSymptoms = true },
                modifier = modifier,
            )
            SignedInPage.PATTERNS -> PatternsScreen(
                uiState = uiState,
                account = authState,
                onRefresh = viewModel::refresh,
                onOpenSettings = { showSettings = true },
                onDismissMessage = viewModel::dismissMessage,
                onSelectPage = viewModel::selectPage,
                modifier = modifier,
            )
            SignedInPage.OUTLOOK -> OutlookScreen(
                uiState = uiState,
                account = authState,
                onRefresh = viewModel::refresh,
                onOpenSettings = { showSettings = true },
                onDismissMessage = viewModel::dismissMessage,
                onSelectPage = viewModel::selectPage,
                modifier = modifier,
            )
            SignedInPage.EXPLORE -> ExploreScreen(
                uiState = uiState,
                account = authState,
                onRefresh = viewModel::refresh,
                onOpenSettings = { showSettings = true },
                onDismissMessage = viewModel::dismissMessage,
                onSelectPage = viewModel::selectPage,
                onOpenLocalWeather = { showLocalWeather = true },
                modifier = modifier,
            )
        }
    }

    JournalDialogHost(
        uiState = uiState,
        onDismiss = viewModel::dismissJournal,
        onSubmitSymptom = viewModel::submitSymptom,
        onSubmitExposure = viewModel::submitExposure,
        onSubmitDailyCheckIn = viewModel::submitDailyCheckIn,
    )
}

@Composable
private fun OnboardingScreen(
    uiState: HomeUiState,
    onModeChanged: (String) -> Unit,
    onToneChanged: (String) -> Unit,
    onTemperatureUnitChanged: (String) -> Unit,
    onToggleTag: (String) -> Unit,
    onLocalInsightsChanged: (Boolean) -> Unit,
    onZipChanged: (String) -> Unit,
    onUseDeviceLocation: () -> Unit,
    onBack: () -> Unit,
    onContinue: () -> Unit,
    onConnectHealth: () -> Unit,
    onRetry: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(enabled = uiState.onboardingStep != OnboardingStep.WELCOME, onBack = onBack)
    val stepNumber = uiState.onboardingStep.ordinal + 1
    ScreenFrame(modifier = modifier) {
        ContentColumn(bottomPadding = 32.dp) {
            Header(
                subtitle = "A calm, useful setup",
                trailing = {
                    TextButton(onClick = onSignOut) {
                        Text("Sign out", color = Color(0xFF9BA6B4))
                    }
                },
            )
            Spacer(Modifier.height(24.dp))
            Text(
                text = "Step $stepNumber of ${OnboardingStep.entries.size}",
                color = GaiaBlue,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(
                progress = { stepNumber.toFloat() / OnboardingStep.entries.size.toFloat() },
                color = GaiaBlue,
                trackColor = Color.White.copy(alpha = 0.10f),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(24.dp))

            when (uiState.onboardingStep) {
                OnboardingStep.WELCOME -> OnboardingWelcome()
                OnboardingStep.PREFERENCES -> OnboardingPreferences(
                    uiState = uiState,
                    onModeChanged = onModeChanged,
                    onToneChanged = onToneChanged,
                    onTemperatureUnitChanged = onTemperatureUnitChanged,
                )
                OnboardingStep.HEALTH_CONTEXT -> OnboardingHealthContext(
                    uiState = uiState,
                    onToggleTag = onToggleTag,
                )
                OnboardingStep.LOCATION -> OnboardingLocation(
                    uiState = uiState,
                    onLocalInsightsChanged = onLocalInsightsChanged,
                    onZipChanged = onZipChanged,
                    onUseDeviceLocation = onUseDeviceLocation,
                )
                OnboardingStep.HEALTH_CONNECT -> OnboardingHealthConnect(
                    uiState = uiState,
                    onConnectHealth = onConnectHealth,
                )
                OnboardingStep.READY -> OnboardingReady(uiState)
            }

            uiState.onboardingMessage?.let { message ->
                Spacer(Modifier.height(16.dp))
                Text(message, color = GaiaRose, fontSize = 14.sp)
                if (uiState.onboardingStep == OnboardingStep.WELCOME) {
                    TextButton(onClick = onRetry) { Text("Try again", color = GaiaBlue) }
                }
            }
            Spacer(Modifier.height(24.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (uiState.onboardingStep != OnboardingStep.WELCOME) {
                    TextButton(onClick = onBack, enabled = !uiState.isSavingOnboarding) {
                        Text("Back", color = Color(0xFF9BA6B4))
                    }
                }
                Button(
                    onClick = onContinue,
                    enabled = !uiState.isSavingOnboarding,
                    colors = ButtonDefaults.buttonColors(containerColor = GaiaBlue),
                    modifier = Modifier.weight(1f),
                ) {
                    if (uiState.isSavingOnboarding) {
                        CircularProgressIndicator(
                            color = GaiaNavy,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(18.dp),
                        )
                    } else {
                        Text(
                            if (uiState.onboardingStep == OnboardingStep.READY) "Open Gaia Eyes" else "Continue",
                            color = GaiaNavy,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun OnboardingWelcome() {
    OnboardingTitle(
        title = "Make Gaia Eyes yours",
        body = "Choose the context Gaia Eyes should pay attention to. Your selections help organize the dashboard; they do not diagnose a condition or predict a health event.",
    )
    OnboardingInfoCard(
        "We'll set your display style, health context, local conditions, and optional Health Connect access. You can skip any optional choice.",
    )
}

@Composable
private fun OnboardingPreferences(
    uiState: HomeUiState,
    onModeChanged: (String) -> Unit,
    onToneChanged: (String) -> Unit,
    onTemperatureUnitChanged: (String) -> Unit,
) {
    OnboardingTitle("Choose your view", "These choices change presentation, not the underlying data.")
    OnboardingSectionLabel("Style")
    ChoiceRow("Scientific", uiState.onboardingMode == "scientific") { onModeChanged("scientific") }
    ChoiceRow("Mystical", uiState.onboardingMode == "mystical") { onModeChanged("mystical") }
    OnboardingSectionLabel("Language")
    ChoiceRow("Straightforward", uiState.onboardingTone == "straight") { onToneChanged("straight") }
    ChoiceRow("Balanced", uiState.onboardingTone == "balanced") { onToneChanged("balanced") }
    ChoiceRow("A little playful", uiState.onboardingTone == "humorous") { onToneChanged("humorous") }
    OnboardingSectionLabel("Temperature")
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        ChoiceChip("°F", uiState.onboardingTemperatureUnit == "F") { onTemperatureUnitChanged("F") }
        ChoiceChip("°C", uiState.onboardingTemperatureUnit == "C") { onTemperatureUnitChanged("C") }
    }
}

@Composable
private fun OnboardingHealthContext(uiState: HomeUiState, onToggleTag: (String) -> Unit) {
    OnboardingTitle(
        "What is relevant to your health?",
        "Optional. This helps Gaia Eyes prioritize useful symptoms and context. Choose diagnosed or suspected areas that matter to you.",
    )
    if (uiState.onboardingTagCatalog.isEmpty()) {
        OnboardingInfoCard("No health context choices are available right now. You can continue without selecting one.")
    } else {
        uiState.onboardingTagCatalog.forEach { option ->
            ChoiceRow(
                label = option.label,
                selected = option.tagKey in uiState.onboardingSelectedTags,
                detail = option.description,
            ) { onToggleTag(option.tagKey) }
        }
    }
}

@Composable
private fun OnboardingLocation(
    uiState: HomeUiState,
    onLocalInsightsChanged: (Boolean) -> Unit,
    onZipChanged: (String) -> Unit,
    onUseDeviceLocation: () -> Unit,
) {
    OnboardingTitle(
        "Add local conditions",
        "Use your current location or a saved ZIP code so Gaia Eyes can compare nearby weather, pressure, and air quality with your day.",
    )
    ChoiceRow("Use local insights", uiState.onboardingLocalInsightsEnabled) {
        onLocalInsightsChanged(true)
    }
    ChoiceRow("Not now", !uiState.onboardingLocalInsightsEnabled) {
        onLocalInsightsChanged(false)
    }
    if (uiState.onboardingLocalInsightsEnabled) {
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onUseDeviceLocation,
            enabled = !uiState.isLocatingDevice,
            colors = ButtonDefaults.buttonColors(
                containerColor = GaiaGreen,
                contentColor = GaiaNavy,
            ),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (uiState.isLocatingDevice) {
                CircularProgressIndicator(
                    color = GaiaNavy,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(18.dp),
                )
            } else {
                Text("Use current location", fontWeight = FontWeight.Bold)
            }
        }
        Text(
            text = when {
                uiState.onboardingUseGps && uiState.onboardingZip.isNotBlank() ->
                    "Using your current area. ZIP ${uiState.onboardingZip} is saved as a fallback."
                uiState.onboardingZip.isNotBlank() -> "Using saved ZIP ${uiState.onboardingZip}."
                else -> "Choose your current location or enter a ZIP code."
            },
            color = Color(0xFF9BA6B4),
            fontSize = 13.sp,
            lineHeight = 19.sp,
        )
        OutlinedTextField(
            value = uiState.onboardingZip,
            onValueChange = onZipChanged,
            label = { Text("ZIP code") },
            supportingText = { Text("You can use this instead of device location.") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            "Gaia Eyes requests approximate location only while you use the app. It saves a ZIP fallback and does not track you in the background.",
            color = Color(0xFF8F9AA9),
            fontSize = 12.sp,
            lineHeight = 18.sp,
        )
    }
}

@Composable
private fun OnboardingHealthConnect(uiState: HomeUiState, onConnectHealth: () -> Unit) {
    OnboardingTitle(
        "Connect your health data",
        "Optional. Health Connect can add sleep, steps, heart rate, resting heart rate, respiratory rate, and SpO₂ when your device makes them available.",
    )
    val statusText = when (uiState.healthConnectStatus) {
        HealthConnectStatus.READY -> "Health Connect is ready."
        HealthConnectStatus.PERMISSIONS_REQUIRED -> "Choose Connect to review Health Connect permissions."
        HealthConnectStatus.UNAVAILABLE -> "Health Connect is not available on this device. You can continue."
        HealthConnectStatus.UPDATE_REQUIRED -> "Health Connect needs an update. You can continue for now."
        HealthConnectStatus.CHECKING -> "Checking Health Connect…"
    }
    OnboardingInfoCard(statusText)
    if (uiState.healthConnectStatus == HealthConnectStatus.PERMISSIONS_REQUIRED) {
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onConnectHealth,
            colors = ButtonDefaults.buttonColors(containerColor = GaiaGreen),
        ) {
            Text("Connect Health Connect", color = GaiaNavy, fontWeight = FontWeight.Bold)
        }
    }
    Text(
        "Continue works even if you prefer to connect later.",
        color = Color(0xFF8F9AA9),
        fontSize = 13.sp,
        modifier = Modifier.padding(top = 12.dp),
    )
}

@Composable
private fun OnboardingReady(uiState: HomeUiState) {
    OnboardingTitle("You're ready", "Gaia Eyes will begin with the information available now and become more personal as you add context.")
    OnboardingInfoCard(
        if (uiState.onboardingLocalInsightsEnabled) {
            if (uiState.onboardingUseGps) {
                "Local conditions will follow your approximate location while Gaia Eyes is open. ZIP ${uiState.onboardingZip} remains saved as a fallback. Health and pattern sections may take a little time to fill in."
            } else {
                "Local conditions are set for ZIP ${uiState.onboardingZip}. Health and pattern sections may take a little time to fill in."
            }
        } else {
            "Local insights are off for now. Health and pattern sections may take a little time to fill in."
        },
    )
}

@Composable
private fun OnboardingTitle(title: String, body: String) {
    Text(title, color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
    Text(
        body,
        color = Color(0xFF9BA6B4),
        fontSize = 16.sp,
        lineHeight = 23.sp,
        modifier = Modifier.padding(top = 10.dp, bottom = 20.dp),
    )
}

@Composable
private fun OnboardingSectionLabel(label: String) {
    Text(
        label.uppercase(),
        color = GaiaBlue,
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(top = 14.dp, bottom = 8.dp),
    )
}

@Composable
private fun ChoiceRow(
    label: String,
    selected: Boolean,
    detail: String? = null,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(
            containerColor = if (selected) GaiaBlue.copy(alpha = 0.20f) else GaiaPanel,
        ),
        border = BorderStroke(1.dp, if (selected) GaiaBlue else Color.White.copy(alpha = 0.08f)),
        modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(label, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                detail?.takeIf(String::isNotBlank)?.let {
                    Text(it, color = Color(0xFF8F9AA9), fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
                }
            }
            Text(if (selected) "✓" else "", color = GaiaBlue, fontSize = 20.sp)
        }
    }
}

@Composable
private fun RowScope.ChoiceChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (selected) GaiaBlue else GaiaPanel,
        ),
        modifier = Modifier.weight(1f),
    ) {
        Text(label, color = if (selected) GaiaNavy else Color.White)
    }
}

@Composable
private fun OnboardingInfoCard(text: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.08f)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text,
            color = Color(0xFFC2CBD6),
            fontSize = 15.sp,
            lineHeight = 22.sp,
            modifier = Modifier.padding(18.dp),
        )
    }
}

@Composable
private fun LoadingScreen(modifier: Modifier = Modifier) {
    ScreenFrame(modifier = modifier) {
        Column(
            modifier = Modifier
                .align(Alignment.Center)
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            GaiaMark()
            CircularProgressIndicator(color = GaiaBlue)
            Text(
                text = "Opening Gaia Eyes",
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun ConfigurationScreen(
    modifier: Modifier = Modifier,
) {
    val uriHandler = LocalUriHandler.current

    ScreenFrame(modifier = modifier) {
        ContentColumn {
            Header(subtitle = "Secure account access")
            Spacer(modifier = Modifier.height(34.dp))
            Text(
                text = "Sign-in is temporarily unavailable",
                color = Color.White,
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Secure sign-in isn’t available in this app version. Please update Gaia Eyes. If you still need help, contact support.",
                color = Color(0xFFADB7C5),
                fontSize = 17.sp,
                lineHeight = 25.sp,
                modifier = Modifier.padding(top = 12.dp),
            )
            Spacer(modifier = Modifier.height(22.dp))
            Button(
                onClick = { uriHandler.openUri("https://gaiaeyes.com/support/") },
                colors = ButtonDefaults.buttonColors(
                    containerColor = GaiaBlue,
                    contentColor = GaiaNavy,
                ),
            ) {
                Text(
                    text = "Open support",
                    color = GaiaNavy,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun SignInScreen(
    uiState: HomeUiState,
    onEmailChanged: (String) -> Unit,
    onSendMagicLink: () -> Unit,
    onContinueWithoutEmail: () -> Unit,
    onDismissMessage: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var showGuestConfirmation by rememberSaveable { mutableStateOf(false) }

    ScreenFrame(modifier = modifier) {
        ContentColumn {
            Header(subtitle = "Secure account access")
            Spacer(modifier = Modifier.height(34.dp))
            Text(
                text = "Sign in or create your account.",
                color = Color.White,
                fontSize = 34.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Enter your email and we’ll send a secure link. If you’re new, your account will be created when you open it.",
                color = Color(0xFFADB7C5),
                fontSize = 17.sp,
                lineHeight = 25.sp,
                modifier = Modifier.padding(top = 10.dp),
            )
            Spacer(modifier = Modifier.height(24.dp))
            Card(
                colors = CardDefaults.cardColors(containerColor = GaiaPanel),
                shape = RoundedCornerShape(26.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    modifier = Modifier.padding(22.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    OutlinedTextField(
                        value = uiState.email,
                        onValueChange = onEmailChanged,
                        label = { Text("Email") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = onSendMagicLink,
                        enabled = !uiState.isSendingMagicLink && !uiState.isStartingGuest,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = GaiaBlue,
                            contentColor = GaiaNavy,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (uiState.isSendingMagicLink) {
                            CircularProgressIndicator(
                                color = GaiaNavy,
                                strokeWidth = 2.dp,
                                modifier = Modifier.size(20.dp),
                            )
                        } else {
                            Text(
                                text = if (uiState.magicLinkSent) "Send another link" else "Continue with email",
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        HorizontalDivider(modifier = Modifier.weight(1f))
                        Text("or", color = Color(0xFF8994A3), fontSize = 13.sp)
                        HorizontalDivider(modifier = Modifier.weight(1f))
                    }
                    TextButton(
                        onClick = { showGuestConfirmation = true },
                        enabled = !uiState.isSendingMagicLink && !uiState.isStartingGuest,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (uiState.isStartingGuest) {
                            CircularProgressIndicator(
                                color = GaiaBlue,
                                strokeWidth = 2.dp,
                                modifier = Modifier.size(20.dp),
                            )
                        } else {
                            Text(
                                text = "Continue without email",
                                color = GaiaBlue,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Text(
                        text = "Try Gaia Eyes now and add an email later to protect your history and use it on another device.",
                        color = Color(0xFF8994A3),
                        fontSize = 13.sp,
                        lineHeight = 19.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    uiState.authMessage?.let { message ->
                        MessageCard(
                            message = message,
                            positive = uiState.magicLinkSent,
                            onDismiss = onDismissMessage,
                        )
                    }
                }
            }
            Spacer(modifier = Modifier.height(18.dp))
            BackendCard(uiState = uiState, onRetry = onRetry)
        }
    }

    if (showGuestConfirmation) {
        AlertDialog(
            onDismissRequest = { showGuestConfirmation = false },
            title = { Text("Continue without an email?") },
            text = {
                Text(
                    "This guest account stays on this device. Add an email before signing out, reinstalling, clearing app data, or moving to another device so you can recover it.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showGuestConfirmation = false
                        onContinueWithoutEmail()
                    },
                ) {
                    Text("Continue as guest")
                }
            },
            dismissButton = {
                TextButton(onClick = { showGuestConfirmation = false }) {
                    Text("Use email")
                }
            },
        )
    }
}

@Composable
private fun SettingsScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onEmailChanged: (String) -> Unit,
    onAddEmail: () -> Unit,
    onLocalInsightsChanged: (Boolean) -> Unit,
    onZipChanged: (String) -> Unit,
    onUseDeviceLocation: () -> Unit,
    onSaveLocation: () -> Unit,
    onDismissMessage: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val diagnostics = androidDiagnosticsSummary(uiState)

    ScreenFrame(modifier = modifier) {
        ContentColumn {
            Header(
                subtitle = "Settings and diagnostics",
                trailing = {
                    TextButton(onClick = onBack) {
                        Text("Back")
                    }
                },
            )
            Spacer(modifier = Modifier.height(24.dp))
            Text(
                text = "Settings",
                color = Color.White,
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Manage your account, local conditions, connections, and support information.",
                color = Color(0xFF9BA6B4),
                fontSize = 15.sp,
                lineHeight = 22.sp,
                modifier = Modifier.padding(top = 6.dp),
            )

            Spacer(modifier = Modifier.height(18.dp))
            SettingsSectionCard(title = "Account") {
                if (account.isAnonymous) {
                    SettingsStatusRow(
                        label = "Account",
                        value = "Guest account",
                        positive = true,
                    )
                    Text(
                        text = "Add an email to protect your history and use Gaia Eyes on another device.",
                        color = Color(0xFF9BA6B4),
                        fontSize = 14.sp,
                        lineHeight = 20.sp,
                    )
                    OutlinedTextField(
                        value = uiState.email,
                        onValueChange = onEmailChanged,
                        label = { Text("Email") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = onAddEmail,
                        enabled = !uiState.isAddingEmail,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = GaiaBlue,
                            contentColor = GaiaNavy,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (uiState.isAddingEmail) {
                            CircularProgressIndicator(
                                color = GaiaNavy,
                                strokeWidth = 2.dp,
                                modifier = Modifier.size(20.dp),
                            )
                        } else {
                            Text("Add recovery email", fontWeight = FontWeight.Bold)
                        }
                    }
                    uiState.authMessage?.let { message ->
                        MessageCard(
                            message = message,
                            positive = uiState.emailUpgradeSent,
                            onDismiss = onDismissMessage,
                        )
                    }
                    Text(
                        text = "Sign out is unavailable until you add an email, so this account can’t be lost by accident.",
                        color = Color(0xFF8994A3),
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                    )
                } else {
                    SettingsStatusRow(
                        label = "Signed in as",
                        value = account.email ?: "Gaia Eyes account",
                        positive = true,
                    )
                    TextButton(
                        onClick = onSignOut,
                        enabled = !uiState.isSigningOut,
                        modifier = Modifier.align(Alignment.End),
                    ) {
                        Text(if (uiState.isSigningOut) "Signing out…" else "Sign out")
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            LocalConditionsSettingsCard(
                uiState = uiState,
                onLocalInsightsChanged = onLocalInsightsChanged,
                onZipChanged = onZipChanged,
                onUseDeviceLocation = onUseDeviceLocation,
                onSaveLocation = onSaveLocation,
            )

            Spacer(modifier = Modifier.height(16.dp))
            SettingsSectionCard(title = "Connections") {
                SettingsStatusRow(
                    label = "Gaia Eyes data service",
                    value = when (uiState.backendAvailable) {
                        true -> "Connected"
                        false -> "Needs attention"
                        null -> "Checking"
                    },
                    positive = uiState.backendAvailable == true,
                )
                SettingsStatusRow(
                    label = "Health Connect",
                    value = healthConnectStatusLabel(uiState.healthConnectStatus),
                    positive = uiState.healthConnectStatus == HealthConnectStatus.READY,
                )
                SettingsStatusRow(
                    label = "Saved entries waiting to sync",
                    value = uiState.pendingJournalWrites.toString(),
                    positive = uiState.pendingJournalWrites == 0,
                )
                SettingsStatusRow(
                    label = "Health batches waiting to sync",
                    value = uiState.pendingHealthSampleBatches.toString(),
                    positive = uiState.pendingHealthSampleBatches == 0,
                )
                TextButton(
                    onClick = onRefresh,
                    enabled = !uiState.isCheckingBackend,
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Text(if (uiState.isCheckingBackend) "Checking…" else "Refresh status")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            SettingsSectionCard(title = "Privacy and support") {
                SettingsLink(label = "Help and support") {
                    uriHandler.openUri("https://gaiaeyes.com/support/")
                }
                SettingsLink(label = "Privacy policy") {
                    uriHandler.openUri("https://gaiaeyes.com/privacy-policy/")
                }
                SettingsLink(label = "Terms of use") {
                    uriHandler.openUri("https://gaiaeyes.com/terms/")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            SettingsSectionCard(title = "Diagnostics") {
                Text(
                    text = "Share a status summary with support. It excludes your email, account ID, access credentials, and health readings.",
                    color = Color(0xFFB7C0CC),
                    fontSize = 15.sp,
                    lineHeight = 21.sp,
                )
                Button(
                    onClick = {
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_SUBJECT, "Gaia Eyes Android diagnostics")
                            putExtra(Intent.EXTRA_TEXT, diagnostics)
                        }
                        context.startActivity(
                            Intent.createChooser(intent, "Share Gaia Eyes diagnostics"),
                        )
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = GaiaBlue,
                        contentColor = GaiaNavy,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Share diagnostics", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun LocalConditionsSettingsCard(
    uiState: HomeUiState,
    onLocalInsightsChanged: (Boolean) -> Unit,
    onZipChanged: (String) -> Unit,
    onUseDeviceLocation: () -> Unit,
    onSaveLocation: () -> Unit,
) {
    SettingsSectionCard(title = "Local conditions") {
        Text(
            text = "Use your current area as you travel, or keep conditions tied to one saved ZIP code.",
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            lineHeight = 21.sp,
        )
        ChoiceRow("Use local conditions", uiState.locationLocalInsightsEnabled) {
            onLocalInsightsChanged(true)
        }
        ChoiceRow("Not now", !uiState.locationLocalInsightsEnabled) {
            onLocalInsightsChanged(false)
        }
        if (uiState.locationLocalInsightsEnabled) {
            Button(
                onClick = onUseDeviceLocation,
                enabled = !uiState.isLocatingDevice && !uiState.isSavingLocation,
                colors = ButtonDefaults.buttonColors(
                    containerColor = GaiaGreen,
                    contentColor = GaiaNavy,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (uiState.isLocatingDevice) {
                    CircularProgressIndicator(
                        color = GaiaNavy,
                        strokeWidth = 2.dp,
                        modifier = Modifier.size(18.dp),
                    )
                } else {
                    Text("Use current location", fontWeight = FontWeight.Bold)
                }
            }
            Text(
                text = when {
                    uiState.locationUseGps && uiState.locationZip.isNotBlank() ->
                        "Following your approximate location. ZIP ${uiState.locationZip} is the fallback."
                    uiState.locationZip.isNotBlank() -> "Using saved ZIP ${uiState.locationZip}."
                    else -> "Choose your current location or enter a ZIP code."
                },
                color = Color(0xFF9BA6B4),
                fontSize = 13.sp,
                lineHeight = 19.sp,
            )
            OutlinedTextField(
                value = uiState.locationZip,
                onValueChange = onZipChanged,
                label = { Text("ZIP code") },
                supportingText = { Text("Entering a ZIP turns off device-location updates.") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                text = "Approximate location is checked only while Gaia Eyes is in use. Background location is not requested.",
                color = Color(0xFF8994A3),
                fontSize = 12.sp,
                lineHeight = 18.sp,
            )
        }
        Button(
            onClick = onSaveLocation,
            enabled = !uiState.isSavingLocation && !uiState.isLocatingDevice,
            colors = ButtonDefaults.buttonColors(
                containerColor = GaiaBlue,
                contentColor = GaiaNavy,
            ),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (uiState.isSavingLocation) {
                CircularProgressIndicator(
                    color = GaiaNavy,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(18.dp),
                )
            } else {
                Text("Save local settings", fontWeight = FontWeight.Bold)
            }
        }
        uiState.locationSettingsMessage?.let { message ->
            Text(
                text = message,
                color = if (
                    message.startsWith("Using") ||
                    message.startsWith("Local conditions updated") ||
                    message.startsWith("Local conditions are turned off")
                ) {
                    GaiaGreen
                } else {
                    GaiaRose
                },
                fontSize = 13.sp,
                lineHeight = 19.sp,
            )
        }
    }
}

@Composable
private fun SettingsSectionCard(
    title: String,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = title,
                color = Color.White,
                fontSize = 21.sp,
                fontWeight = FontWeight.Bold,
            )
            content()
        }
    }
}

@Composable
private fun SettingsStatusRow(
    label: String,
    value: String,
    positive: Boolean,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = label,
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = value,
            color = if (positive) GaiaGreen else GaiaAmber,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.End,
            modifier = Modifier
                .weight(1f)
                .padding(start = 12.dp),
        )
    }
}

@Composable
private fun SettingsLink(
    label: String,
    onClick: () -> Unit,
) {
    Text(
        text = "$label  ›",
        color = GaiaBlue,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 4.dp),
    )
}

@Composable
private fun SettingsButton(onClick: () -> Unit) {
    TextButton(onClick = onClick) {
        Text("Settings")
    }
}

internal fun androidDiagnosticsSummary(uiState: HomeUiState): String {
    fun loaded(value: Any?): String = if (value == null) "no" else "yes"

    return buildString {
        appendLine("Gaia Eyes Android diagnostics")
        appendLine("App version: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        appendLine("Data service: ${when (uiState.backendAvailable) {
            true -> "connected"
            false -> "needs attention"
            null -> "checking"
        }}")
        appendLine("Health Connect: ${healthConnectStatusLabel(uiState.healthConnectStatus)}")
        appendLine("Pending journal entries: ${uiState.pendingJournalWrites}")
        appendLine("Pending health batches: ${uiState.pendingHealthSampleBatches}")
        appendLine("Dashboard loaded: ${loaded(uiState.dashboard)}")
        appendLine("Body loaded: ${loaded(uiState.body)}")
        appendLine("Current symptoms loaded: ${loaded(uiState.currentSymptoms)}")
        appendLine("Drivers loaded: ${loaded(uiState.drivers)}")
        appendLine("Patterns loaded: ${loaded(uiState.patterns)}")
        appendLine("Outlook loaded: ${loaded(uiState.outlook)}")
    }.trim()
}

internal fun healthConnectStatusLabel(status: HealthConnectStatus): String {
    return when (status) {
        HealthConnectStatus.CHECKING -> "Checking"
        HealthConnectStatus.UNAVAILABLE -> "Unavailable"
        HealthConnectStatus.UPDATE_REQUIRED -> "Update required"
        HealthConnectStatus.PERMISSIONS_REQUIRED -> "Permission required"
        HealthConnectStatus.READY -> "Connected"
    }
}

@Composable
private fun HomeScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onDismissMessage: () -> Unit,
    onSelectPage: (SignedInPage) -> Unit,
    onLogSymptom: () -> Unit,
    onLogExposure: () -> Unit,
    onDailyCheckIn: () -> Unit,
    onOpenCurrentSymptoms: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var showAllGauges by rememberSaveable { mutableStateOf(false) }
    var selectedGaugeKey by rememberSaveable { mutableStateOf<String?>(null) }

    val selectedGauge = allGaugeDefinitions.firstOrNull { it.key == selectedGaugeKey }
    if (selectedGauge != null) {
        GaugeDetailScreen(
            model = gaugeDetailModel(
                key = selectedGauge.key,
                fallbackLabel = selectedGauge.fallbackLabel,
                dashboard = uiState.dashboard?.dashboard,
                currentSymptoms = uiState.currentSymptoms?.symptoms,
                drivers = uiState.drivers?.drivers,
            ),
            color = selectedGauge.color,
            onClose = { selectedGaugeKey = null },
            onViewBody = {
                selectedGaugeKey = null
                onSelectPage(SignedInPage.BODY)
            },
            onViewDrivers = {
                selectedGaugeKey = null
                onSelectPage(SignedInPage.EXPLORE)
            },
            onLogSymptom = {
                selectedGaugeKey = null
                onLogSymptom()
            },
            modifier = modifier,
        )
        return
    }

    ScreenFrame(modifier = modifier) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val columns = if (maxWidth > 660.dp) 4 else 2
            ContentColumn(bottomPadding = 104.dp) {
                Header(
                    subtitle = account.email ?: "Signed in",
                    trailing = { SettingsButton(onClick = onOpenSettings) },
                )
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Your body, in context.",
                            color = Color.White,
                            fontSize = 30.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = dashboardFreshnessText(uiState),
                            color = dashboardFreshnessColor(uiState),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                    }
                    TextButton(
                        onClick = onRefresh,
                        enabled = !uiState.isLoadingDashboard,
                    ) {
                        Text(if (uiState.isLoadingDashboard) "Refreshing…" else "Refresh")
                    }
                }
                Spacer(modifier = Modifier.height(18.dp))
                GaugeGrid(
                    dashboard = uiState.dashboard?.dashboard,
                    columns = columns,
                    showAll = showAllGauges,
                    onGaugeClick = { selectedGaugeKey = it.key },
                )
                TextButton(
                    onClick = { showAllGauges = !showAllGauges },
                    modifier = Modifier.align(Alignment.CenterHorizontally),
                ) {
                    Text(
                        text = if (showAllGauges) "Show fewer gauges ↑" else "Show all 8 gauges ↓",
                        color = GaiaBlue,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                uiState.dashboardMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.dashboard != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.homeContextMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.currentSymptoms != null || uiState.drivers != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.authMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = false,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.journalMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = !message.contains("couldn't"),
                        onDismiss = onDismissMessage,
                    )
                }
                Spacer(modifier = Modifier.height(18.dp))
                TodayReadCard(
                    uiState = uiState,
                    columns = if (columns == 4) 3 else 2,
                    onLogSymptom = onLogSymptom,
                    onLogExposure = onLogExposure,
                    onDailyCheckIn = onDailyCheckIn,
                    onOpenCurrentSymptoms = onOpenCurrentSymptoms,
                )
                Spacer(modifier = Modifier.height(18.dp))
                SignalsToWatchCard(
                    uiState = uiState,
                    onClick = { onSelectPage(SignedInPage.EXPLORE) },
                )
                Spacer(modifier = Modifier.height(18.dp))
                BackendCard(uiState = uiState, onRetry = onRefresh)
            }
            SignedInNavigation(
                selectedPage = SignedInPage.HOME,
                onSelectPage = onSelectPage,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun BodyScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onDismissMessage: () -> Unit,
    onSelectPage: (SignedInPage) -> Unit,
    onConnectHealth: () -> Unit,
    onImportHealth: () -> Unit,
    onOpenCurrentSymptoms: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenFrame(modifier = modifier) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val wide = maxWidth > 660.dp
            ContentColumn(bottomPadding = 104.dp) {
                Header(
                    subtitle = account.email ?: "Signed in",
                    trailing = { SettingsButton(onClick = onOpenSettings) },
                )
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Body",
                            color = Color.White,
                            fontSize = 30.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = bodyFreshnessText(uiState),
                            color = bodyFreshnessColor(uiState),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                    }
                    TextButton(
                        onClick = onRefresh,
                        enabled = !uiState.isLoadingBody,
                    ) {
                        Text(if (uiState.isLoadingBody) "Refreshing…" else "Refresh")
                    }
                }

                uiState.bodyMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.body != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.authMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = false,
                        onDismiss = onDismissMessage,
                    )
                }

                Spacer(modifier = Modifier.height(18.dp))
                val features = uiState.body?.features
                when {
                    features != null -> {
                        SleepSummaryCard(features = features, wide = wide)
                        Spacer(modifier = Modifier.height(18.dp))
                        HealthStatsCard(features = features, wide = wide)
                    }
                    uiState.isLoadingBody -> BodyLoadingCard()
                    else -> BodyEmptyCard()
                }
                Spacer(modifier = Modifier.height(18.dp))
                CurrentSymptomsSummaryCard(
                    uiState = uiState,
                    onClick = onOpenCurrentSymptoms,
                )
                Spacer(modifier = Modifier.height(18.dp))
                HealthConnectCard(
                    uiState = uiState,
                    onConnect = onConnectHealth,
                    onImport = onImportHealth,
                )
                Spacer(modifier = Modifier.height(18.dp))
                BackendCard(uiState = uiState, onRetry = onRefresh)
            }
            SignedInNavigation(
                selectedPage = SignedInPage.BODY,
                onSelectPage = onSelectPage,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun CurrentSymptomsSummaryCard(
    uiState: HomeUiState,
    onClick: () -> Unit,
) {
    val symptoms = uiState.currentSymptoms?.symptoms?.items.orEmpty()
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaRose.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, GaiaRose.copy(alpha = 0.28f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Current Symptoms",
                    color = Color.White,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = if (symptoms.isEmpty()) "Open ›" else "${symptoms.size} active ›",
                    color = GaiaRose,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                text = when {
                    symptoms.isNotEmpty() -> symptoms
                        .take(3)
                        .joinToString(" • ") { it.label.ifBlank { "Symptom" } }
                    uiState.isLoadingHomeContext -> "Checking your recent symptom logs…"
                    else -> "Nothing is active right now. Open this page to log or review symptoms."
                },
                color = Color(0xFFB7C0CC),
                fontSize = 15.sp,
                lineHeight = 21.sp,
            )
        }
    }
}

@Composable
private fun CurrentSymptomsScreen(
    uiState: HomeUiState,
    onClose: () -> Unit,
    onRefresh: () -> Unit,
    onLogSymptom: () -> Unit,
    onUpdateSymptom: (String, String?, Int?, String?) -> Unit,
    onDeleteSymptom: (String) -> Unit,
    onDismissMessage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var editingItem by remember { mutableStateOf<CurrentSymptomItem?>(null) }
    var deletingItem by remember { mutableStateOf<CurrentSymptomItem?>(null) }
    val symptoms = uiState.currentSymptoms?.symptoms?.items.orEmpty()

    BackHandler(onBack = onClose)
    ScreenFrame(modifier = modifier) {
        ContentColumn(bottomPadding = 36.dp) {
            Header(
                subtitle = "Body context",
                trailing = {
                    TextButton(onClick = onClose) {
                        Text("Close", color = GaiaRose)
                    }
                },
            )
            Spacer(modifier = Modifier.height(24.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Current Symptoms",
                        color = Color.White,
                        fontSize = 30.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Review what is active, add an update, or remove an accidental entry.",
                        color = Color(0xFF9BA6B4),
                        fontSize = 15.sp,
                        lineHeight = 22.sp,
                        modifier = Modifier.padding(top = 6.dp),
                    )
                }
                TextButton(
                    onClick = onRefresh,
                    enabled = !uiState.isLoadingHomeContext && !uiState.isUpdatingSymptoms,
                ) {
                    Text(if (uiState.isLoadingHomeContext) "Refreshing…" else "Refresh")
                }
            }

            uiState.symptomActionMessage?.let { message ->
                Spacer(modifier = Modifier.height(14.dp))
                MessageCard(
                    message = message,
                    positive = !message.contains("couldn't"),
                    onDismiss = onDismissMessage,
                )
            }
            uiState.homeContextMessage?.let { message ->
                Spacer(modifier = Modifier.height(14.dp))
                MessageCard(
                    message = message,
                    positive = uiState.currentSymptoms != null,
                    onDismiss = onDismissMessage,
                )
            }

            Spacer(modifier = Modifier.height(18.dp))
            when {
                symptoms.isNotEmpty() -> symptoms.forEach { item ->
                    CurrentSymptomEditorCard(
                        item = item,
                        isUpdating = uiState.isUpdatingSymptoms,
                        onStateChange = { state ->
                            onUpdateSymptom(item.id, state, item.severity, null)
                        },
                        onEdit = { editingItem = item },
                        onDelete = { deletingItem = item },
                    )
                    Spacer(modifier = Modifier.height(14.dp))
                }
                uiState.isLoadingHomeContext -> ContextLoadingRow("Checking recent symptoms…")
                else -> Card(
                    colors = CardDefaults.cardColors(containerColor = GaiaPanel),
                    shape = RoundedCornerShape(24.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = "Nothing is active right now. If something changes, one quick log is enough to start a timeline.",
                        color = Color(0xFFB7C0CC),
                        fontSize = 16.sp,
                        lineHeight = 23.sp,
                        modifier = Modifier.padding(20.dp),
                    )
                }
            }

            Button(
                onClick = onLogSymptom,
                colors = ButtonDefaults.buttonColors(
                    containerColor = GaiaRose,
                    contentColor = GaiaNavy,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Log a symptom", fontWeight = FontWeight.Bold)
            }
        }
    }

    editingItem?.let { item ->
        SymptomEditDialog(
            item = item,
            onDismiss = { editingItem = null },
            onSave = { severity, note ->
                editingItem = null
                onUpdateSymptom(item.id, item.currentState.ifBlank { "ongoing" }, severity, note)
            },
        )
    }
    deletingItem?.let { item ->
        AlertDialog(
            onDismissRequest = { deletingItem = null },
            title = { Text("Delete ${item.label.ifBlank { "symptom" }}?") },
            text = { Text("This removes the symptom episode and its updates. This cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        deletingItem = null
                        onDeleteSymptom(item.id)
                    },
                ) {
                    Text("Delete", color = GaiaRose, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { deletingItem = null }) {
                    Text("Cancel")
                }
            },
        )
    }
}

@Composable
private fun CurrentSymptomEditorCard(
    item: CurrentSymptomItem,
    isUpdating: Boolean,
    onStateChange: (String) -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaRose.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, GaiaRose.copy(alpha = 0.24f)),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = item.label.ifBlank { "Symptom" },
                        color = Color.White,
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = buildString {
                            item.severity?.let { append("Severity $it/10") }
                            if (isNotEmpty()) append(" • ")
                            append(symptomStateLabel(item.currentState))
                        },
                        color = Color(0xFFADB7C5),
                        fontSize = 14.sp,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                item.currentContextBadge?.trim()?.takeIf(String::isNotEmpty)?.let { badge ->
                    PatternPill(label = badge, color = GaiaBlue)
                }
            }
            item.notePreview?.trim()?.takeIf(String::isNotEmpty)?.let { note ->
                Text(
                    text = note,
                    color = Color(0xFFC4CCD7),
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SymptomUpdateButton(
                    label = "Still active",
                    enabled = !isUpdating,
                    onClick = { onStateChange("ongoing") },
                    modifier = Modifier.weight(1f),
                )
                SymptomUpdateButton(
                    label = "Improving",
                    enabled = !isUpdating,
                    onClick = { onStateChange("improving") },
                    modifier = Modifier.weight(1f),
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SymptomUpdateButton(
                    label = "Worse",
                    enabled = !isUpdating,
                    onClick = { onStateChange("worse") },
                    modifier = Modifier.weight(1f),
                )
                SymptomUpdateButton(
                    label = "Resolved",
                    enabled = !isUpdating,
                    onClick = { onStateChange("resolved") },
                    modifier = Modifier.weight(1f),
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                TextButton(onClick = onEdit, enabled = !isUpdating) {
                    Text("Edit details", color = GaiaRose)
                }
                TextButton(onClick = onDelete, enabled = !isUpdating) {
                    Text("Delete", color = Color(0xFFADB7C5))
                }
            }
        }
    }
}

@Composable
private fun SymptomUpdateButton(
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(
            containerColor = GaiaRose.copy(alpha = 0.15f),
            contentColor = GaiaRose,
        ),
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 10.dp),
        modifier = modifier,
    ) {
        Text(label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun SymptomEditDialog(
    item: CurrentSymptomItem,
    onDismiss: () -> Unit,
    onSave: (Int?, String?) -> Unit,
) {
    var severityText by rememberSaveable(item.id) {
        mutableStateOf(item.severity?.toString().orEmpty())
    }
    var noteText by rememberSaveable(item.id) {
        mutableStateOf(item.notePreview.orEmpty())
    }
    val severity = severityText.toIntOrNull()?.takeIf { it in 0..10 }
    val severityIsValid = severityText.isBlank() || severity != null

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit ${item.label.ifBlank { "symptom" }}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = severityText,
                    onValueChange = { severityText = it.filter(Char::isDigit).take(2) },
                    label = { Text("Severity (0–10)") },
                    isError = !severityIsValid,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = noteText,
                    onValueChange = { noteText = it.take(500) },
                    label = { Text("Note (optional)") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(severity, noteText.trim().takeIf(String::isNotEmpty)) },
                enabled = severityIsValid,
            ) {
                Text("Save", color = GaiaRose, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        },
    )
}

private fun symptomStateLabel(state: String): String {
    return when (state.lowercase()) {
        "new" -> "New"
        "ongoing" -> "Still active"
        "improving" -> "Improving"
        "worse" -> "Worse"
        "resolved" -> "Resolved"
        else -> "Active"
    }
}

@Composable
private fun PatternsScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onDismissMessage: () -> Unit,
    onSelectPage: (SignedInPage) -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenFrame(modifier = modifier) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val columns = if (maxWidth > 660.dp) 2 else 1
            ContentColumn(bottomPadding = 104.dp) {
                Header(
                    subtitle = account.email ?: "Signed in",
                    trailing = { SettingsButton(onClick = onOpenSettings) },
                )
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Patterns",
                            color = Color.White,
                            fontSize = 30.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = patternsFreshnessText(uiState),
                            color = patternsFreshnessColor(uiState),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                    }
                    TextButton(
                        onClick = onRefresh,
                        enabled = !uiState.isLoadingPatterns,
                    ) {
                        Text(if (uiState.isLoadingPatterns) "Refreshing…" else "Refresh")
                    }
                }

                uiState.patternsMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.patterns != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.authMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = false,
                        onDismiss = onDismissMessage,
                    )
                }

                Spacer(modifier = Modifier.height(18.dp))
                val patterns = uiState.patterns?.patterns
                when {
                    patterns != null -> {
                        PatternsOverviewCard(
                            overview = patternOverviewText(patterns),
                            isPartial = patterns.partial,
                        )
                        patternSections(patterns).forEach { section ->
                            Spacer(modifier = Modifier.height(18.dp))
                            PatternSectionCard(
                                section = section,
                                columns = columns,
                            )
                        }
                        Spacer(modifier = Modifier.height(18.dp))
                        Text(
                            text = patterns.disclaimer
                                ?.trim()
                                ?.takeIf(String::isNotEmpty)
                                ?: "Patterns show associations in your history. They do not diagnose conditions or prove causes.",
                            color = Color(0xFF8994A3),
                            fontSize = 13.sp,
                            lineHeight = 19.sp,
                            modifier = Modifier.padding(horizontal = 4.dp),
                        )
                    }
                    uiState.isLoadingPatterns -> PatternsLoadingCard()
                    else -> PatternsEmptyCard()
                }
                Spacer(modifier = Modifier.height(18.dp))
                BackendCard(uiState = uiState, onRetry = onRefresh)
            }
            SignedInNavigation(
                selectedPage = SignedInPage.PATTERNS,
                onSelectPage = onSelectPage,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun PatternsOverviewCard(
    overview: String,
    isPartial: Boolean,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaBlue.copy(alpha = 0.10f)),
        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.30f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "What your history is showing",
                color = Color.White,
                fontSize = 21.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = overview,
                color = Color(0xFFC4CCD7),
                fontSize = 16.sp,
                lineHeight = 23.sp,
            )
            if (isPartial) {
                Text(
                    text = "Loading the rest of your pattern details…",
                    color = GaiaAmber,
                    fontSize = 13.sp,
                )
            }
        }
    }
}

@Composable
private fun PatternSectionCard(
    section: PatternSectionModel,
    columns: Int,
) {
    var showsAll by rememberSaveable(section.title) { mutableStateOf(false) }
    val visibleCards = visiblePatternCards(section.cards, showsAll)
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = section.title,
                color = Color.White,
                fontSize = 23.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = section.subtitle,
                color = Color(0xFF9BA6B4),
                fontSize = 14.sp,
                lineHeight = 20.sp,
            )
            if (section.cards.isEmpty()) {
                Text(
                    text = section.emptyMessage,
                    color = Color(0xFFB7C0CC),
                    fontSize = 15.sp,
                    lineHeight = 21.sp,
                    modifier = Modifier.padding(vertical = 6.dp),
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    visibleCards.chunked(columns).forEachIndexed { rowIndex, cards ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            cards.forEachIndexed { columnIndex, card ->
                                val cardIndex = (rowIndex * columns) + columnIndex
                                PatternResultCard(
                                    card = card,
                                    accentColor = patternCardAccent(cardIndex),
                                    modifier = Modifier.weight(1f),
                                )
                            }
                            repeat(columns - cards.size) {
                                Spacer(modifier = Modifier.weight(1f))
                            }
                        }
                    }
                    if (section.cards.size > 3) {
                        TextButton(
                            onClick = { showsAll = !showsAll },
                            modifier = Modifier.align(Alignment.End),
                        ) {
                            Text(
                                text = if (showsAll) "Show fewer" else "Show all (${section.cards.size})",
                                color = GaiaBlue,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PatternResultCard(
    card: PatternCard,
    accentColor: Color,
    modifier: Modifier = Modifier,
) {
    val confidenceColor = patternConfidenceColor(card.confidence)
    Card(
        colors = CardDefaults.cardColors(
            containerColor = accentColor.copy(alpha = 0.08f),
        ),
        border = BorderStroke(1.dp, accentColor.copy(alpha = 0.30f)),
        shape = RoundedCornerShape(22.dp),
        modifier = modifier.heightIn(min = 220.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = card.outcome.ifBlank { "Personal pattern" },
                        color = Color.White,
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    if (card.signal.isNotBlank()) {
                        Text(
                            text = card.signal,
                            color = Color(0xFF9BA6B4),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 3.dp),
                        )
                    }
                }
                card.confidence?.trim()?.takeIf(String::isNotEmpty)?.let { confidence ->
                    PatternPill(
                        label = confidence,
                        color = confidenceColor,
                    )
                }
            }

            if (card.usedToday) {
                PatternPill(
                    label = card.usedTodayLabel?.trim()?.takeIf(String::isNotEmpty)
                        ?: "Active now",
                    color = GaiaGreen,
                )
            }

            Text(
                text = patternExplanation(card),
                color = Color(0xFFC4CCD7),
                fontSize = 15.sp,
                lineHeight = 21.sp,
            )
            Text(
                text = patternEvidence(card),
                color = confidenceColor,
                fontSize = 13.sp,
                lineHeight = 18.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = patternBaseline(card),
                color = Color(0xFF8994A3),
                fontSize = 12.sp,
                lineHeight = 17.sp,
            )
            if (card.usedToday) {
                card.voiceSemantic
                    ?.interpretation
                    ?.activeTodaySummary
                    ?.trim()
                    ?.takeIf(String::isNotEmpty)
                    ?.let { activeSummary ->
                        Text(
                            text = activeSummary,
                            color = GaiaGreen,
                            fontSize = 13.sp,
                            lineHeight = 18.sp,
                        )
                    }
            }
        }
    }
}

@Composable
private fun PatternPill(
    label: String,
    color: Color,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.16f)),
        shape = RoundedCornerShape(18.dp),
    ) {
        Text(
            text = label,
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
        )
    }
}

@Composable
private fun PatternsLoadingCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(modifier = Modifier.padding(20.dp)) {
            ContextLoadingRow(message = "Comparing your saved history…")
        }
    }
}

@Composable
private fun PatternsEmptyCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Patterns will appear as Gaia Eyes finds enough overlap in your history.",
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            lineHeight = 21.sp,
            modifier = Modifier.padding(20.dp),
        )
    }
}

@Composable
private fun OutlookScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onDismissMessage: () -> Unit,
    onSelectPage: (SignedInPage) -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenFrame(modifier = modifier) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val columns = if (maxWidth > 660.dp) 2 else 1
            ContentColumn(bottomPadding = 104.dp) {
                Header(
                    subtitle = account.email ?: "Signed in",
                    trailing = { SettingsButton(onClick = onOpenSettings) },
                )
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Outlook",
                            color = Color.White,
                            fontSize = 30.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = outlookFreshnessText(uiState),
                            color = outlookFreshnessColor(uiState),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                    }
                    TextButton(
                        onClick = onRefresh,
                        enabled = !uiState.isLoadingOutlook,
                    ) {
                        Text(if (uiState.isLoadingOutlook) "Refreshing…" else "Refresh")
                    }
                }

                uiState.outlookMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.outlook != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.authMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = false,
                        onDismiss = onDismissMessage,
                    )
                }

                Spacer(modifier = Modifier.height(18.dp))
                Text(
                    text = "7-Day Forecast",
                    color = Color.White,
                    fontSize = 26.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "Signals that may be useful to keep in view.",
                    color = Color(0xFF9BA6B4),
                    fontSize = 14.sp,
                    modifier = Modifier.padding(top = 5.dp),
                )
                Spacer(modifier = Modifier.height(14.dp))

                val outlook = uiState.outlook?.outlook
                when {
                    outlook?.dailyOutlook?.isNotEmpty() == true -> {
                        OutlookDayGrid(
                            days = outlook.dailyOutlook,
                            columns = columns,
                        )
                    }
                    uiState.isLoadingOutlook -> OutlookLoadingCard()
                    else -> OutlookEmptyCard(
                        message = outlook
                            ?.voiceSemantics
                            ?.overview
                            ?.interpretation
                            ?.emptyState,
                    )
                }
                Spacer(modifier = Modifier.height(18.dp))
                Text(
                    text = "Outlook highlights context to watch. It does not diagnose symptoms or predict a medical event.",
                    color = Color(0xFF8994A3),
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
                Spacer(modifier = Modifier.height(18.dp))
                BackendCard(uiState = uiState, onRetry = onRefresh)
            }
            SignedInNavigation(
                selectedPage = SignedInPage.OUTLOOK,
                onSelectPage = onSelectPage,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun ExploreScreen(
    uiState: HomeUiState,
    account: AuthState.SignedIn,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onDismissMessage: () -> Unit,
    onSelectPage: (SignedInPage) -> Unit,
    onOpenLocalWeather: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenFrame(modifier = modifier) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val columns = if (maxWidth > 660.dp) 2 else 1
            ContentColumn(bottomPadding = 104.dp) {
                Header(
                    subtitle = account.email ?: "Signed in",
                    trailing = { SettingsButton(onClick = onOpenSettings) },
                )
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Explore",
                            color = Color.White,
                            fontSize = 30.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = exploreFreshnessText(uiState),
                            color = exploreFreshnessColor(uiState),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                    }
                    TextButton(
                        onClick = onRefresh,
                        enabled = !uiState.isLoadingHomeContext && !uiState.isLoadingLocalWeather,
                    ) {
                        Text(
                            if (uiState.isLoadingHomeContext || uiState.isLoadingLocalWeather) {
                                "Refreshing…"
                            } else {
                                "Refresh"
                            },
                        )
                    }
                }

                uiState.homeContextMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.drivers != null,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.authMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = false,
                        onDismiss = onDismissMessage,
                    )
                }
                uiState.localWeatherMessage?.let { message ->
                    Spacer(modifier = Modifier.height(14.dp))
                    MessageCard(
                        message = message,
                        positive = uiState.localWeather != null,
                        onDismiss = onDismissMessage,
                    )
                }

                Spacer(modifier = Modifier.height(18.dp))
                Text(
                    text = "Explore the signals around you.",
                    color = Color.White,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "See the local, Earth, space, and body-context signals Gaia Eyes is comparing for you right now.",
                    color = Color(0xFF9BA6B4),
                    fontSize = 15.sp,
                    lineHeight = 22.sp,
                    modifier = Modifier.padding(top = 7.dp),
                )
                Spacer(modifier = Modifier.height(18.dp))

                LocalConditionsSummaryCard(
                    snapshot = uiState.localWeather,
                    isLoading = uiState.isLoadingLocalWeather,
                    onClick = onOpenLocalWeather,
                )
                Spacer(modifier = Modifier.height(18.dp))

                val response = uiState.drivers?.drivers
                when {
                    response?.drivers?.isNotEmpty() == true -> {
                        ExploreSummaryCard(response = response)
                        Spacer(modifier = Modifier.height(18.dp))
                        Text(
                            text = "All Drivers",
                            color = Color.White,
                            fontSize = 26.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "Shown in Gaia Eyes’ current relevance order.",
                            color = Color(0xFF9BA6B4),
                            fontSize = 14.sp,
                            modifier = Modifier.padding(top = 5.dp, bottom = 14.dp),
                        )
                        ExploreDriverGrid(
                            drivers = exploreDrivers(response),
                            columns = columns,
                        )
                    }
                    uiState.isLoadingHomeContext -> ExploreLoadingCard()
                    else -> ExploreEmptyCard()
                }

                Spacer(modifier = Modifier.height(18.dp))
                Text(
                    text = "Drivers are context, not proof of cause. Personal pattern notes describe associations in your history and are not a diagnosis.",
                    color = Color(0xFF8994A3),
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
                Spacer(modifier = Modifier.height(18.dp))
                BackendCard(uiState = uiState, onRetry = onRefresh)
            }
            SignedInNavigation(
                selectedPage = SignedInPage.EXPLORE,
                onSelectPage = onSelectPage,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun LocalConditionsSummaryCard(
    snapshot: LocalWeatherSnapshot?,
    isLoading: Boolean,
    onClick: () -> Unit,
) {
    val metrics = localWeatherMetrics(snapshot)
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaAmber.copy(alpha = 0.07f)),
        border = BorderStroke(1.dp, GaiaAmber.copy(alpha = 0.28f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Local Weather",
                        color = Color.White,
                        fontSize = 23.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = localWeatherLocationLabel(snapshot),
                        color = Color(0xFFB7C0CC),
                        fontSize = 14.sp,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                DriverPill(
                    label = when {
                        isLoading -> "Updating"
                        snapshot?.local != null -> localWeatherSourceLabel(snapshot)
                        else -> "Open"
                    },
                    color = when {
                        isLoading -> GaiaAmber
                        snapshot?.source == HomeContextSource.NETWORK -> GaiaGreen
                        else -> GaiaBlue
                    },
                )
            }

            if (metrics.isNotEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    metrics.take(3).forEach { metric ->
                        SupportingStatChip(
                            label = metric.label,
                            value = metric.value,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    repeat(3 - metrics.take(3).size) {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                }
                Text(
                    text = "Open current conditions and local health context ›",
                    color = GaiaAmber,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            } else {
                Text(
                    text = when {
                        isLoading -> "Checking your latest local conditions…"
                        snapshot?.location?.zip.isNullOrBlank() ->
                            "Add a ZIP code in Gaia Eyes to connect weather, air quality, and pressure."
                        else -> "Current local conditions are not available yet. Tap to review or refresh."
                    },
                    color = Color(0xFFB7C0CC),
                    fontSize = 15.sp,
                    lineHeight = 21.sp,
                )
            }
        }
    }
}

@Composable
private fun LocalWeatherScreen(
    uiState: HomeUiState,
    onClose: () -> Unit,
    onRefresh: () -> Unit,
    onLocalInsightsChanged: (Boolean) -> Unit,
    onZipChanged: (String) -> Unit,
    onUseDeviceLocation: () -> Unit,
    onSaveLocation: () -> Unit,
    onDismissMessage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snapshot = uiState.localWeather
    val metrics = localWeatherMetrics(snapshot)

    BackHandler(onBack = onClose)
    ScreenFrame(modifier = modifier) {
        ContentColumn(bottomPadding = 36.dp) {
            Header(
                subtitle = "Explore",
                trailing = {
                    TextButton(onClick = onClose) {
                        Text("Close", color = GaiaAmber)
                    }
                },
            )
            Spacer(modifier = Modifier.height(24.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Local Weather",
                        color = Color.White,
                        fontSize = 30.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Weather, air quality, and pressure near ${localWeatherLocationLabel(snapshot)}.",
                        color = Color(0xFF9BA6B4),
                        fontSize = 15.sp,
                        lineHeight = 22.sp,
                        modifier = Modifier.padding(top = 6.dp),
                    )
                }
                TextButton(
                    onClick = onRefresh,
                    enabled = !uiState.isLoadingLocalWeather,
                ) {
                    Text(if (uiState.isLoadingLocalWeather) "Refreshing…" else "Refresh")
                }
            }

            uiState.localWeatherMessage?.let { message ->
                Spacer(modifier = Modifier.height(14.dp))
                MessageCard(
                    message = message,
                    positive = snapshot?.local != null,
                    onDismiss = onDismissMessage,
                )
            }

            Spacer(modifier = Modifier.height(18.dp))
            LocalConditionsSettingsCard(
                uiState = uiState,
                onLocalInsightsChanged = onLocalInsightsChanged,
                onZipChanged = onZipChanged,
                onUseDeviceLocation = onUseDeviceLocation,
                onSaveLocation = onSaveLocation,
            )

            Spacer(modifier = Modifier.height(18.dp))
            Card(
                colors = CardDefaults.cardColors(containerColor = GaiaAmber.copy(alpha = 0.07f)),
                border = BorderStroke(1.dp, GaiaAmber.copy(alpha = 0.28f)),
                shape = RoundedCornerShape(26.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = localWeatherLocationLabel(snapshot),
                            color = Color.White,
                            fontSize = 22.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        DriverPill(
                            label = localWeatherSourceLabel(snapshot),
                            color = if (snapshot?.source == HomeContextSource.NETWORK) {
                                GaiaGreen
                            } else {
                                GaiaAmber
                            },
                        )
                    }
                    localWeatherObservedText(snapshot)?.let { observed ->
                        Text(
                            text = observed,
                            color = Color(0xFF9BA6B4),
                            fontSize = 13.sp,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            when {
                metrics.isNotEmpty() -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    metrics.chunked(2).forEach { rowMetrics ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            rowMetrics.forEach { metric ->
                                LocalWeatherMetricCard(
                                    metric = metric,
                                    modifier = Modifier.weight(1f),
                                )
                            }
                            repeat(2 - rowMetrics.size) {
                                Spacer(modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
                uiState.isLoadingLocalWeather -> ContextLoadingRow("Checking local conditions…")
                else -> Card(
                    colors = CardDefaults.cardColors(containerColor = GaiaPanel),
                    shape = RoundedCornerShape(24.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = if (snapshot?.location?.zip.isNullOrBlank()) {
                            "Local weather needs a ZIP code. Add or update your location in Gaia Eyes, then refresh this page."
                        } else {
                            "Current conditions have not arrived yet. Refresh to try again."
                        },
                        color = Color(0xFFB7C0CC),
                        fontSize = 16.sp,
                        lineHeight = 23.sp,
                        modifier = Modifier.padding(20.dp),
                    )
                }
            }

            snapshot?.local?.health?.messages
                .orEmpty()
                .map(String::trim)
                .filter(String::isNotEmpty)
                .distinct()
                .take(4)
                .takeIf { it.isNotEmpty() }
                ?.let { messages ->
                    Spacer(modifier = Modifier.height(18.dp))
                    Card(
                        colors = CardDefaults.cardColors(containerColor = GaiaBlue.copy(alpha = 0.07f)),
                        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.24f)),
                        shape = RoundedCornerShape(26.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Column(
                            modifier = Modifier.padding(20.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Text(
                                text = "What may be useful to notice",
                                color = Color.White,
                                fontSize = 21.sp,
                                fontWeight = FontWeight.Bold,
                            )
                            messages.forEach { message ->
                                Text(
                                    text = "• $message",
                                    color = Color(0xFFC4CCD7),
                                    fontSize = 15.sp,
                                    lineHeight = 21.sp,
                                )
                            }
                        }
                    }
                }

            Spacer(modifier = Modifier.height(18.dp))
            Text(
                text = "Local conditions provide context for your personal history. They do not prove a cause or predict a medical event.",
                color = Color(0xFF8994A3),
                fontSize = 13.sp,
                lineHeight = 19.sp,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

@Composable
private fun LocalWeatherMetricCard(
    metric: LocalWeatherMetric,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.Black.copy(alpha = 0.16f)),
        border = BorderStroke(1.dp, GaiaAmber.copy(alpha = 0.22f)),
        shape = RoundedCornerShape(20.dp),
        modifier = modifier.heightIn(min = 128.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(15.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = metric.label,
                color = Color(0xFF9BA6B4),
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = metric.value,
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
            metric.detail?.let { detail ->
                Text(
                    text = detail,
                    color = Color(0xFFADB7C5),
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                )
            }
        }
    }
}

@Composable
private fun ExploreSummaryCard(
    response: com.gaiaeyes.app.core.network.AllDriversResponse,
) {
    val counts = driverRoleCounts(response)
    val visible = exploreDrivers(response).size

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaBlue.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.28f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "All Drivers",
                        color = Color.White,
                        fontSize = 23.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = response.summary.note
                            ?.trim()
                            ?.takeIf(String::isNotEmpty)
                            ?: "See the signals Gaia Eyes is comparing for you right now.",
                        color = Color(0xFFB7C0CC),
                        fontSize = 14.sp,
                        lineHeight = 20.sp,
                        modifier = Modifier.padding(top = 5.dp),
                    )
                }
                DriverPill(
                    label = if (response.summary.activeDriverCount > 0) {
                        "${response.summary.activeDriverCount} active"
                    } else {
                        "Current order"
                    },
                    color = if (response.summary.activeDriverCount > 0) GaiaGreen else GaiaBlue,
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(9.dp),
            ) {
                DriverMetric("Visible", visible, Modifier.weight(1f))
                DriverMetric("Leading", counts.leading, Modifier.weight(1f))
                DriverMetric("Supporting", counts.supporting, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun DriverMetric(
    label: String,
    value: Int,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.04f)),
        shape = RoundedCornerShape(18.dp),
        modifier = modifier,
    ) {
        Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 11.dp)) {
            Text(
                text = label.uppercase(),
                color = Color(0xFF8F9AA9),
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = value.toString(),
                color = Color.White,
                fontSize = 21.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

@Composable
private fun ExploreDriverGrid(
    drivers: List<DriverItem>,
    columns: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        drivers.chunked(columns).forEach { rowDrivers ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                rowDrivers.forEach { driver ->
                    ExploreDriverCard(
                        driver = driver,
                        modifier = Modifier.weight(1f),
                    )
                }
                repeat(columns - rowDrivers.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun ExploreDriverCard(
    driver: DriverItem,
    modifier: Modifier = Modifier,
) {
    val tint = driverCategoryColor(driver)
    val reason = driverDisplayReason(driver)

    Card(
        colors = CardDefaults.cardColors(containerColor = tint.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.28f)),
        shape = RoundedCornerShape(24.dp),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = driver.label.ifBlank { "Current signal" },
                        color = Color.White,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = listOfNotNull(
                            driver.categoryLabel?.trim()?.takeIf(String::isNotEmpty),
                            driver.roleLabel?.trim()?.takeIf(String::isNotEmpty),
                        ).joinToString(" • ").ifBlank { "Current context" },
                        color = tint,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 3.dp),
                    )
                }
                DriverPill(
                    label = driver.stateLabel
                        ?.trim()
                        ?.takeIf(String::isNotEmpty)
                        ?: driver.state.ifBlank { "Current" },
                    color = tint,
                )
            }

            driver.reading
                ?.trim()
                ?.takeIf(String::isNotEmpty)
                ?.let { reading ->
                    Text(
                        text = reading,
                        color = Color.White,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }

            LinearProgressIndicator(
                progress = { driverSignalProgress(driver) },
                color = tint,
                trackColor = Color.White.copy(alpha = 0.09f),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(8.dp),
            )

            if (reason.isNotEmpty()) {
                Text(
                    text = reason,
                    color = Color(0xFFB7C0CC),
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                )
            }

            if (driver.currentSymptoms.isNotEmpty()) {
                Text(
                    text = "Active symptoms: ${driver.currentSymptoms.take(3).joinToString()}",
                    color = GaiaRose,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            val patternLabel = driver.patternStatusLabel
                ?.trim()
                ?.takeIf(String::isNotEmpty)
            val patternSummary = driver.patternSummary
                ?.trim()
                ?.takeIf(String::isNotEmpty)
                ?.takeUnless { it.equals(reason, ignoreCase = true) }
                ?.takeUnless { it == "We’re still learning how this tends to affect you." }
            if (patternLabel != null || patternSummary != null) {
                HorizontalDivider(color = Color.White.copy(alpha = 0.08f))
                patternLabel?.let {
                    Text(
                        text = it,
                        color = GaiaGreen,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
                patternSummary?.let {
                    Text(
                        text = it,
                        color = Color(0xFF9BA6B4),
                        fontSize = 12.sp,
                        lineHeight = 17.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun DriverPill(
    label: String,
    color: Color,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.16f)),
        shape = RoundedCornerShape(18.dp),
    ) {
        Text(
            text = label,
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
        )
    }
}

@Composable
private fun ExploreLoadingCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(modifier = Modifier.padding(20.dp)) {
            ContextLoadingRow(message = "Comparing current signals…")
        }
    }
}

@Composable
private fun ExploreEmptyCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Drivers will appear after Gaia Eyes finishes loading your current context.",
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            lineHeight = 21.sp,
            modifier = Modifier.padding(20.dp),
        )
    }
}

@Composable
private fun OutlookDayGrid(
    days: List<OutlookDay>,
    columns: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        days.chunked(columns).forEach { rowDays ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                rowDays.forEach { day ->
                    OutlookDayCard(
                        day = day,
                        modifier = Modifier.weight(1f),
                    )
                }
                repeat(columns - rowDays.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun OutlookDayCard(
    day: OutlookDay,
    modifier: Modifier = Modifier,
) {
    val drivers = visibleOutlookDrivers(day)
    val state = outlookDayState(day)
    val tint = outlookStatusColor(state)

    Card(
        colors = CardDefaults.cardColors(containerColor = tint.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.30f)),
        shape = RoundedCornerShape(26.dp),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = outlookDayTitle(day),
                        color = Color.White,
                        fontSize = 23.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = outlookDayDate(day),
                        color = Color(0xFF9BA6B4),
                        fontSize = 14.sp,
                        modifier = Modifier.padding(top = 3.dp),
                    )
                }
                OutlookPill(label = state, color = tint)
            }

            if (drivers.isNotEmpty()) {
                Text(
                    text = "Signals in view",
                    color = Color(0xFF9BA6B4),
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                drivers.forEach { driver ->
                    OutlookDriverRow(driver = driver)
                }
            }

            if (day.likelyElevatedDomains.isNotEmpty()) {
                Text(
                    text = "Possible symptoms",
                    color = Color(0xFF9BA6B4),
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                OutlookDomainGrid(
                    domains = day.likelyElevatedDomains,
                    drivers = drivers,
                )
            }

            if (drivers.isEmpty() && day.likelyElevatedDomains.isEmpty()) {
                Text(
                    text = day.voiceSemantic
                        ?.interpretation
                        ?.emptyState
                        ?.trim()
                        ?.takeIf(String::isNotEmpty)
                        ?: "No strong signal stands out for this day.",
                    color = Color(0xFFB7C0CC),
                    fontSize = 15.sp,
                    lineHeight = 21.sp,
                )
            }
        }
    }
}

@Composable
private fun OutlookDriverRow(driver: OutlookDriver) {
    val tint = outlookStatusColor(driver.severity)
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = outlookDriverLabel(driver),
                color = Color(0xFFC4CCD7),
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Text(
                text = outlookDriverValue(driver),
                color = tint,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.End,
            )
        }
        LinearProgressIndicator(
            progress = { outlookDriverProgress(driver) },
            color = tint,
            trackColor = Color.White.copy(alpha = 0.10f),
            modifier = Modifier
                .fillMaxWidth()
                .height(7.dp),
        )
    }
}

@Composable
private fun OutlookDomainGrid(
    domains: List<OutlookDomain>,
    drivers: List<OutlookDriver>,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        domains.chunked(2).forEach { rowDomains ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowDomains.forEach { domain ->
                    val tint = outlookStatusColor(domain.likelihood)
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = tint.copy(alpha = 0.10f),
                        ),
                        border = BorderStroke(1.dp, tint.copy(alpha = 0.24f)),
                        shape = RoundedCornerShape(18.dp),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(
                            text = outlookDomainLabel(domain, drivers),
                            color = Color(0xFFD2D8E1),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            lineHeight = 19.sp,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        )
                    }
                }
                repeat(2 - rowDomains.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun OutlookPill(
    label: String,
    color: Color,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.18f)),
        shape = RoundedCornerShape(18.dp),
    ) {
        Text(
            text = label,
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 7.dp),
        )
    }
}

@Composable
private fun OutlookLoadingCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(modifier = Modifier.padding(20.dp)) {
            ContextLoadingRow(message = "Building your latest Outlook…")
        }
    }
}

@Composable
private fun OutlookEmptyCard(message: String?) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = message
                ?.trim()
                ?.takeIf(String::isNotEmpty)
                ?: "Your Outlook will appear when forecast context is ready.",
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            lineHeight = 21.sp,
            modifier = Modifier.padding(20.dp),
        )
    }
}

@Composable
private fun SleepSummaryCard(
    features: FeaturesTodayResponse,
    wide: Boolean,
) {
    val efficiency = sleepEfficiencyPercent(features.sleepEfficiency)
    val stages = sleepStages(features)
    val columns = if (wide) 4 else 2

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.22f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = if (features.day.isNotBlank()) {
                        "Sleep (Today)"
                    } else {
                        "Sleep"
                    },
                    color = Color.White,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                )
                efficiency?.let {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = GaiaBlue.copy(alpha = 0.13f),
                        ),
                        shape = RoundedCornerShape(18.dp),
                    ) {
                        Text(
                            text = "$it%",
                            color = GaiaBlue,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                        )
                    }
                }
            }
            Text(
                text = sleepDurationText(features.sleepTotalMinutes),
                color = Color.White,
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
            )
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                stages.chunked(columns).forEach { rowStages ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        rowStages.forEach { stage ->
                            SleepStageCard(
                                stage = stage,
                                modifier = Modifier.weight(1f),
                            )
                        }
                        repeat(columns - rowStages.size) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SleepStageCard(
    stage: SleepStageModel,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.Black.copy(alpha = 0.18f)),
        shape = RoundedCornerShape(18.dp),
        modifier = modifier.heightIn(min = 108.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stage.label,
                color = Color(0xFF9BA6B4),
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = if (stage.minutes > 0) "${stage.minutes}m" else "—",
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
            )
            LinearProgressIndicator(
                progress = { stage.progress },
                color = GaiaBlue,
                trackColor = Color.White.copy(alpha = 0.10f),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(7.dp),
            )
        }
    }
}

@Composable
private fun HealthConnectCard(
    uiState: HomeUiState,
    onConnect: () -> Unit,
    onImport: () -> Unit,
) {
    val status = uiState.healthConnectStatus
    val description = when (status) {
        HealthConnectStatus.CHECKING -> "Checking Health Connect availability…"
        HealthConnectStatus.UNAVAILABLE -> "Health Connect isn't available on this device."
        HealthConnectStatus.UPDATE_REQUIRED ->
            "Install or update Health Connect to import Android health data."
        HealthConnectStatus.PERMISSIONS_REQUIRED ->
            "Connect sleep, steps, heart rate, resting heart rate, breathing rate, and oxygen saturation. HRV stays off until compatible measurement standards are confirmed."
        HealthConnectStatus.READY ->
            "Connected. Import the last 30 days now. Saved batches retry automatically if your connection drops."
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaBlue.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.28f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Health Connect",
                color = Color.White,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = description,
                color = Color(0xFFB4C0CE),
                fontSize = 15.sp,
                lineHeight = 21.sp,
            )
            if (uiState.pendingHealthSampleBatches > 0) {
                Text(
                    text = "${uiState.pendingHealthSampleBatches} saved ${if (uiState.pendingHealthSampleBatches == 1) "batch is" else "batches are"} waiting to retry.",
                    color = GaiaAmber,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            uiState.healthConnectMessage?.let { message ->
                Text(
                    text = message,
                    color = if (message.contains("couldn't")) GaiaRose else GaiaGreen,
                    fontSize = 14.sp,
                )
            }
            when (status) {
                HealthConnectStatus.PERMISSIONS_REQUIRED -> Button(
                    onClick = onConnect,
                    colors = ButtonDefaults.buttonColors(containerColor = GaiaBlue),
                ) {
                    Text("Connect Health Connect", fontWeight = FontWeight.Bold)
                }
                HealthConnectStatus.READY -> Button(
                    onClick = onImport,
                    enabled = !uiState.isImportingHealthConnect,
                    colors = ButtonDefaults.buttonColors(containerColor = GaiaBlue),
                ) {
                    if (uiState.isImportingHealthConnect) {
                        CircularProgressIndicator(
                            color = GaiaNavy,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(18.dp),
                        )
                    } else {
                        Text("Import recent health data", fontWeight = FontWeight.Bold)
                    }
                }
                else -> Unit
            }
        }
    }
}

@Composable
private fun HealthStatsCard(
    features: FeaturesTodayResponse,
    wide: Boolean,
) {
    val stats = bodyHealthStats(features)
    val columns = if (wide) 3 else 2

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaGreen.copy(alpha = 0.06f)),
        border = BorderStroke(1.dp, GaiaGreen.copy(alpha = 0.24f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Health Stats",
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                stats.chunked(columns).forEach { rowStats ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        rowStats.forEach { stat ->
                            BodyStatCard(
                                stat = stat,
                                modifier = Modifier.weight(1f),
                            )
                        }
                        repeat(columns - rowStats.size) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                SupportingStatChip(
                    label = "STEPS",
                    value = features.stepsTotal.takeIf { it > 0 }?.toString() ?: "—",
                    modifier = Modifier.weight(1f),
                )
                SupportingStatChip(
                    label = "HEART RANGE",
                    value = heartRangeText(features) ?: "—",
                    modifier = Modifier.weight(1.45f),
                )
            }
        }
    }
}

@Composable
private fun BodyStatCard(
    stat: BodyStatModel,
    modifier: Modifier = Modifier,
) {
    val tint = when (stat.tone) {
        BodyStatTone.LOW -> GaiaGreen
        BodyStatTone.MILD -> GaiaAmber
        BodyStatTone.ELEVATED -> Color(0xFFD69A5A)
    }
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.Black.copy(alpha = 0.16f)),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.24f)),
        shape = RoundedCornerShape(20.dp),
        modifier = modifier.heightIn(min = 142.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Text(
                text = stat.label,
                color = Color(0xFF9BA6B4),
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
            )
            Text(
                text = stat.value,
                color = Color.White,
                fontSize = 21.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
            Text(
                text = stat.detail,
                color = Color(0xFF9BA6B4),
                fontSize = 12.sp,
                lineHeight = 16.sp,
                maxLines = 2,
                modifier = Modifier.heightIn(min = 32.dp),
            )
            LinearProgressIndicator(
                progress = { stat.progress },
                color = tint,
                trackColor = Color.White.copy(alpha = 0.10f),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(7.dp),
            )
        }
    }
}

@Composable
private fun SupportingStatChip(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaGreen.copy(alpha = 0.10f)),
        border = BorderStroke(1.dp, GaiaGreen.copy(alpha = 0.25f)),
        shape = RoundedCornerShape(18.dp),
        modifier = modifier.heightIn(min = 78.dp),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = label,
                color = Color(0xFF9BA6B4),
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = value,
                color = Color.White,
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun BodyLoadingCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(modifier = Modifier.padding(20.dp)) {
            ContextLoadingRow(
                message = "Loading today’s sleep and health stats…",
            )
        }
    }
}

@Composable
private fun BodyEmptyCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Body data will appear after your Gaia Eyes health history finishes syncing.",
            color = Color(0xFFB7C0CC),
            fontSize = 15.sp,
            lineHeight = 21.sp,
            modifier = Modifier.padding(20.dp),
        )
    }
}

@Composable
private fun SignedInNavigation(
    selectedPage: SignedInPage,
    onSelectPage: (SignedInPage) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xF21A1E24)),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.12f)),
        shape = RoundedCornerShape(28.dp),
        modifier = modifier
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .fillMaxWidth()
            .widthIn(max = 460.dp),
    ) {
        Row(
            modifier = Modifier.padding(6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SignedInNavigationItem(
                label = "Home",
                selected = selectedPage == SignedInPage.HOME,
                onClick = { onSelectPage(SignedInPage.HOME) },
                modifier = Modifier.weight(1f),
            )
            SignedInNavigationItem(
                label = "Body",
                selected = selectedPage == SignedInPage.BODY,
                onClick = { onSelectPage(SignedInPage.BODY) },
                modifier = Modifier.weight(1f),
            )
            SignedInNavigationItem(
                label = "Patterns",
                selected = selectedPage == SignedInPage.PATTERNS,
                onClick = { onSelectPage(SignedInPage.PATTERNS) },
                modifier = Modifier.weight(1f),
            )
            SignedInNavigationItem(
                label = "Outlook",
                selected = selectedPage == SignedInPage.OUTLOOK,
                onClick = { onSelectPage(SignedInPage.OUTLOOK) },
                modifier = Modifier.weight(1f),
            )
            SignedInNavigationItem(
                label = "Explore",
                selected = selectedPage == SignedInPage.EXPLORE,
                onClick = { onSelectPage(SignedInPage.EXPLORE) },
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun SignedInNavigationItem(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val tint = if (selected) GaiaBlue else Color(0xFFADB7C5)
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (selected) GaiaBlue.copy(alpha = 0.16f) else Color.Transparent,
        ),
        shape = RoundedCornerShape(22.dp),
        modifier = modifier.clickable(onClick = onClick),
    ) {
        Text(
            text = label,
            color = tint,
            fontSize = 15.sp,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 13.dp),
        )
    }
}

@Composable
private fun TodayReadCard(
    uiState: HomeUiState,
    columns: Int,
    onLogSymptom: () -> Unit,
    onLogExposure: () -> Unit,
    onDailyCheckIn: () -> Unit,
    onOpenCurrentSymptoms: () -> Unit,
) {
    val activeLabels = uiState.currentSymptoms
        ?.symptoms
        ?.items
        .orEmpty()
        .map { it.label.trim() }
        .filter(String::isNotEmpty)
        .distinctBy { it.lowercase() }
    val possibleSymptoms = derivePossibleSymptoms(
        dashboard = uiState.dashboard?.dashboard,
        drivers = uiState.drivers?.drivers,
        activeLabels = activeLabels,
    )

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = "Today’s Read",
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
            ContextSectionHeading(
                title = "Possible Symptoms",
                detail = "Based on current signals.",
            )
            when {
                possibleSymptoms.isNotEmpty() -> {
                    SymptomGrid(
                        symptoms = possibleSymptoms.map {
                            SymptomChipModel(
                                label = it.label,
                                isMatched = it.isMatched,
                                isActive = false,
                            )
                        },
                        columns = columns,
                    )
                }
                uiState.isLoadingHomeContext -> ContextLoadingRow("Reading today’s signals…")
                else -> Text(
                    text = "No strong symptom signal stands out right now.",
                    color = Color(0xFF9BA6B4),
                    fontSize = 14.sp,
                )
            }

            HorizontalDivider(color = Color.White.copy(alpha = 0.10f))
            ContextSectionHeading(
                title = "Active Symptoms",
                detail = when {
                    activeLabels.isNotEmpty() -> "${activeLabels.size} active"
                    uiState.currentSymptoms == null && uiState.isLoadingHomeContext ->
                        "Checking recent logs…"
                    else -> "Nothing is active right now."
                },
            )
            if (activeLabels.isNotEmpty()) {
                Column(
                    modifier = Modifier.clickable(onClick = onOpenCurrentSymptoms),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    SymptomGrid(
                        symptoms = activeLabels.take(6).map {
                            SymptomChipModel(
                                label = it,
                                isMatched = false,
                                isActive = true,
                            )
                        },
                        columns = columns,
                    )
                    Text(
                        text = "Review or update active symptoms ›",
                        color = GaiaRose,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            HorizontalDivider(color = Color.White.copy(alpha = 0.10f))
            Text(
                text = if (uiState.pendingJournalWrites > 0) {
                    "${uiState.pendingJournalWrites} saved ${if (uiState.pendingJournalWrites == 1) "entry" else "entries"} waiting to sync"
                } else {
                    "Add today’s context"
                },
                color = Color(0xFF9BA6B4),
                fontSize = 14.sp,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                JournalActionButton(
                    label = "Symptom",
                    onClick = onLogSymptom,
                    modifier = Modifier.weight(1f),
                )
                JournalActionButton(
                    label = "Exposure",
                    onClick = onLogExposure,
                    modifier = Modifier.weight(1f),
                )
                JournalActionButton(
                    label = "Check-in",
                    onClick = onDailyCheckIn,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun JournalActionButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(
            containerColor = GaiaBlue.copy(alpha = 0.18f),
            contentColor = GaiaBlue,
        ),
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 10.dp),
        modifier = modifier,
    ) {
        Text(
            text = label,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
        )
    }
}

@Composable
private fun SignalsToWatchCard(
    uiState: HomeUiState,
    onClick: () -> Unit,
) {
    val driverResponse = uiState.drivers?.drivers
    val drivers = relevantDrivers(driverResponse).take(3)

    Card(
        colors = CardDefaults.cardColors(
            containerColor = GaiaBlue.copy(alpha = 0.08f),
        ),
        border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.25f)),
        shape = RoundedCornerShape(26.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Signals to Watch",
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Context clues, not a diagnosis.",
                color = Color(0xFF9BA6B4),
                fontSize = 14.sp,
            )
            Text(
                text = "View all drivers ›",
                color = GaiaBlue,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            driverResponse?.summary?.note
                ?.trim()
                ?.takeIf(String::isNotEmpty)
                ?.let { summary ->
                    Text(
                        text = summary,
                        color = Color(0xFFC4CCD7),
                        fontSize = 15.sp,
                        lineHeight = 21.sp,
                    )
                }

            when {
                drivers.isNotEmpty() -> drivers.forEach { DriverPreviewRow(it) }
                uiState.isLoadingHomeContext -> ContextLoadingRow("Checking current conditions…")
                else -> Text(
                    text = "No strong signal stands out right now.",
                    color = Color(0xFF9BA6B4),
                    fontSize = 14.sp,
                )
            }
        }
    }
}

@Composable
private fun ContextSectionHeading(
    title: String,
    detail: String,
) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            text = title,
            color = Color.White,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = detail,
            color = Color(0xFF8F9AA9),
            fontSize = 13.sp,
        )
    }
}

private data class SymptomChipModel(
    val label: String,
    val isMatched: Boolean,
    val isActive: Boolean,
)

@Composable
private fun SymptomGrid(
    symptoms: List<SymptomChipModel>,
    columns: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        symptoms.chunked(columns).forEach { rowSymptoms ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowSymptoms.forEach { symptom ->
                    SymptomChip(
                        symptom = symptom,
                        modifier = Modifier.weight(1f),
                    )
                }
                repeat(columns - rowSymptoms.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun SymptomChip(
    symptom: SymptomChipModel,
    modifier: Modifier = Modifier,
) {
    val tint = if (symptom.isActive) GaiaRose else GaiaBlue
    Card(
        colors = CardDefaults.cardColors(containerColor = tint.copy(alpha = 0.12f)),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.26f)),
        shape = RoundedCornerShape(18.dp),
        modifier = modifier.heightIn(min = 52.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 13.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = if (symptom.isMatched) "✓" else "•",
                color = tint,
                fontWeight = FontWeight.Bold,
            )
            Column {
                Text(
                    text = symptom.label,
                    color = Color.White,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                )
                if (symptom.isMatched) {
                    Text(
                        text = "Matched",
                        color = tint,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

@Composable
private fun DriverPreviewRow(driver: DriverItem) {
    val tint = when (driver.category.lowercase()) {
        "space" -> GaiaBlue
        "local" -> GaiaGreen
        else -> GaiaAmber
    }
    val reason = driver.personalReason
        ?.trim()
        ?.takeIf(String::isNotEmpty)
        ?: driver.shortReason.trim()

    Card(
        colors = CardDefaults.cardColors(containerColor = tint.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(20.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(15.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = driver.label.ifBlank { "Current signal" },
                        color = Color.White,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    driver.roleLabel
                        ?.trim()
                        ?.takeIf(String::isNotEmpty)
                        ?.let {
                            Text(
                                text = it,
                                color = tint,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = driver.stateLabel?.takeIf(String::isNotBlank) ?: driver.state,
                        color = tint,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    driver.reading
                        ?.takeIf(String::isNotBlank)
                        ?.let {
                            Text(
                                text = it,
                                color = Color(0xFFADB7C5),
                                fontSize = 12.sp,
                            )
                        }
                }
            }
            if (reason.isNotEmpty()) {
                Text(
                    text = reason,
                    color = Color(0xFFB7C0CC),
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                )
            }
        }
    }
}

@Composable
private fun ContextLoadingRow(message: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CircularProgressIndicator(
            color = GaiaBlue,
            strokeWidth = 2.dp,
            modifier = Modifier.size(18.dp),
        )
        Text(
            text = message,
            color = Color(0xFF9BA6B4),
            fontSize = 14.sp,
        )
    }
}

@Composable
private fun ScreenFrame(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GaiaNavy)
            .statusBarsPadding()
            .navigationBarsPadding(),
        content = content,
    )
}

@Composable
private fun ContentColumn(
    bottomPadding: Dp = 24.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .widthIn(max = 760.dp)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp)
            .padding(top = 18.dp, bottom = bottomPadding),
        content = content,
    )
}

@Composable
private fun Header(
    subtitle: String,
    trailing: @Composable (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.weight(1f),
        ) {
            GaiaMark()
            Column {
                Text(
                    text = "Gaia Eyes",
                    color = Color.White,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = subtitle,
                    color = Color(0xFF8F9AA9),
                    fontSize = 13.sp,
                    maxLines = 1,
                )
            }
        }
        trailing?.invoke()
    }
}

@Composable
private fun GaiaMark() {
    Box(
        modifier = Modifier
            .background(GaiaBlue.copy(alpha = 0.16f), CircleShape)
            .padding(12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "✦",
            color = GaiaBlue,
            fontSize = 24.sp,
        )
    }
}

private data class GaugeDefinition(
    val key: String,
    val fallbackLabel: String,
    val color: Color,
)

private val allGaugeDefinitions = listOf(
    GaugeDefinition("pain", "Pain", GaiaRose),
    GaugeDefinition("focus", "Focus", GaiaBlue),
    GaugeDefinition("heart", "Heart", GaiaGreen),
    GaugeDefinition("stamina", "Recovery Load", GaiaAmber),
    GaugeDefinition("energy", "Energy", GaiaAmber),
    GaugeDefinition("sleep", "Sleep", Color(0xFFA282E0)),
    GaugeDefinition("mood", "Mood", GaiaBlue),
    GaugeDefinition("health_status", "Health Status", GaiaGreen),
)

@Composable
private fun GaugeGrid(
    dashboard: DashboardGaugesResponse?,
    columns: Int,
    showAll: Boolean,
    onGaugeClick: (GaugeDefinition) -> Unit,
) {
    val definitions = if (showAll) allGaugeDefinitions else allGaugeDefinitions.take(4)
    val rows = (definitions.size + columns - 1) / columns
    val gridHeight = (rows * 164 + (rows - 1).coerceAtLeast(0) * 10).dp

    LazyVerticalGrid(
        columns = GridCells.Fixed(columns),
        userScrollEnabled = false,
        contentPadding = PaddingValues(0.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.height(gridHeight),
    ) {
        items(definitions, key = { it.key }) { definition ->
            GaugeCard(
                definition = definition,
                value = dashboard?.gauges?.get(definition.key),
                delta = dashboard?.gaugesDelta?.get(definition.key),
                displayLabel = dashboard?.gaugeLabels?.get(definition.key)
                    ?: definition.fallbackLabel,
                zoneLabel = dashboard?.gaugesMeta?.get(definition.key)?.label,
                onClick = { onGaugeClick(definition) },
            )
        }
    }
}

@Composable
private fun GaugeCard(
    definition: GaugeDefinition,
    value: Double?,
    delta: Int?,
    displayLabel: String,
    zoneLabel: String?,
    onClick: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = definition.color.copy(alpha = 0.09f),
        ),
        border = CardDefaults.outlinedCardBorder().copy(
            brush = androidx.compose.ui.graphics.SolidColor(
                definition.color.copy(alpha = 0.35f),
            ),
        ),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier
            .height(164.dp)
            .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = displayLabel,
                color = definition.color,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
                maxLines = 2,
            )
            Box(
                modifier = Modifier
                    .padding(top = 7.dp)
                    .size(68.dp),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    progress = { ((value ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f) },
                    color = definition.color,
                    trackColor = Color.White.copy(alpha = 0.10f),
                    strokeWidth = 7.dp,
                    modifier = Modifier.fillMaxSize(),
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = value?.roundToInt()?.toString() ?: "—",
                        color = Color.White,
                        fontSize = 23.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    delta?.let {
                        Text(
                            text = if (it > 0) "+$it" else it.toString(),
                            color = definition.color,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
            Text(
                text = "${zoneLabel ?: if (value == null) "Loading" else "Current"}  ›",
                color = Color(0xFF9BA6B4),
                fontSize = 12.sp,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun GaugeDetailScreen(
    model: GaugeDetailModel,
    color: Color,
    onClose: () -> Unit,
    onViewBody: () -> Unit,
    onViewDrivers: () -> Unit,
    onLogSymptom: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onClose)
    ScreenFrame(modifier = modifier) {
        ContentColumn(bottomPadding = 36.dp) {
            Header(
                subtitle = "Gauge details",
                trailing = {
                    TextButton(onClick = onClose) {
                        Text("Close", color = color)
                    }
                },
            )
            Spacer(modifier = Modifier.height(24.dp))
            Text(
                text = "Why This Matters Now",
                color = Color.White,
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "${model.title} — ${model.status}",
                color = color,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 10.dp),
            )

            Spacer(modifier = Modifier.height(18.dp))
            GaugeDetailSectionCard(title = "Today’s gauge", color = color) {
                Text(
                    text = model.score?.toString() ?: "—",
                    color = Color.White,
                    fontSize = 46.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = gaugeScoreExplanation,
                    color = Color(0xFFB7C0CC),
                    fontSize = 15.sp,
                    lineHeight = 22.sp,
                )
            }

            model.delta?.let { delta ->
                Spacer(modifier = Modifier.height(16.dp))
                GaugeDetailSectionCard(title = "Change from yesterday", color = color) {
                    Text(
                        text = "${if (delta > 0) "+" else ""}$delta points",
                        color = color,
                        fontSize = 30.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = gaugeDeltaExplanation,
                        color = Color(0xFFB7C0CC),
                        fontSize = 15.sp,
                        lineHeight = 22.sp,
                    )
                }
            }

            if (model.symptoms.isNotEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                GaugeDetailSectionCard(title = "Active symptoms", color = color) {
                    model.symptoms.forEach { symptom ->
                        GaugeDetailRow(text = symptom, color = GaiaRose)
                    }
                    TextButton(onClick = onViewBody, modifier = Modifier.align(Alignment.End)) {
                        Text("View Body ›", color = color)
                    }
                }
            }

            if (model.influencers.isNotEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                GaugeDetailSectionCard(title = "Current influencers", color = color) {
                    model.influencers.forEach { influencer ->
                        GaugeDetailRow(text = influencer, color = color)
                    }
                    TextButton(onClick = onViewDrivers, modifier = Modifier.align(Alignment.End)) {
                        Text("View all drivers ›", color = color)
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            GaugeDetailSectionCard(title = "Helpful right now", color = color) {
                model.helpfulTips.forEach { tip ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("•", color = GaiaGreen, fontSize = 19.sp)
                        Text(
                            text = tip,
                            color = Color(0xFFD3D9E2),
                            fontSize = 16.sp,
                            lineHeight = 23.sp,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(18.dp))
            Button(
                onClick = onLogSymptom,
                colors = ButtonDefaults.buttonColors(
                    containerColor = color,
                    contentColor = GaiaNavy,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Log a symptom", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun GaugeDetailSectionCard(
    title: String,
    color: Color,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.08f)),
        border = BorderStroke(1.dp, color.copy(alpha = 0.35f)),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(13.dp),
        ) {
            Text(
                text = title,
                color = Color(0xFFB7C0CC),
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
            )
            content()
        }
    }
}

@Composable
private fun GaugeDetailRow(text: String, color: Color) {
    Text(
        text = text,
        color = Color.White,
        fontSize = 16.sp,
        lineHeight = 22.sp,
        modifier = Modifier
            .fillMaxWidth()
            .background(color.copy(alpha = 0.10f), RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
    )
}

@Composable
private fun BackendCard(
    uiState: HomeUiState,
    onRetry: () -> Unit,
) {
    val statusColor = when (uiState.backendAvailable) {
        true -> GaiaGreen
        false -> GaiaRose
        null -> GaiaAmber
    }
    val statusText = when {
        uiState.isCheckingBackend -> "Checking live service"
        uiState.backendAvailable == true -> "Live data service connected"
        else -> "Live data service unavailable"
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = GaiaPanel),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier
                    .background(statusColor.copy(alpha = 0.18f), CircleShape)
                    .padding(10.dp),
            ) {
                Text(
                    text = if (uiState.backendAvailable == true) "✓" else "•",
                    color = statusColor,
                    fontWeight = FontWeight.Bold,
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = statusText,
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 17.sp,
                )
                Text(
                    text = uiState.backendDetail,
                    color = Color(0xFF9AA5B3),
                    fontSize = 14.sp,
                    modifier = Modifier.padding(top = 3.dp),
                )
            }
            if (uiState.backendAvailable == false && !uiState.isCheckingBackend) {
                Button(
                    onClick = onRetry,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = statusColor.copy(alpha = 0.2f),
                        contentColor = statusColor,
                    ),
                ) {
                    Text("Retry")
                }
            }
        }
    }
}

@Composable
private fun MessageCard(
    message: String,
    positive: Boolean,
    onDismiss: () -> Unit,
) {
    val color = if (positive) GaiaGreen else GaiaAmber
    Card(
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, top = 12.dp, end = 6.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = message,
                color = Color(0xFFC4CCD7),
                fontSize = 14.sp,
                lineHeight = 20.sp,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onDismiss) {
                Text("Dismiss", color = color)
            }
        }
    }
}

private fun dashboardFreshnessText(uiState: HomeUiState): String {
    val snapshot = uiState.dashboard
    return when {
        snapshot == null && uiState.isLoadingDashboard -> "Loading your latest dashboard…"
        snapshot == null -> "Your dashboard will appear here."
        snapshot.source == DashboardSource.CACHE -> "Saved dashboard • refreshing live data"
        snapshot.dashboard.stale -> "Live data is reconnecting"
        snapshot.dashboard.day.isNotBlank() -> "Updated for ${snapshot.dashboard.day}"
        else -> "Live dashboard"
    }
}

private fun dashboardFreshnessColor(uiState: HomeUiState): Color {
    val snapshot = uiState.dashboard
    return if (snapshot?.source == DashboardSource.NETWORK && !snapshot.dashboard.stale) {
        GaiaGreen
    } else {
        GaiaAmber
    }
}

private fun bodyFreshnessText(uiState: HomeUiState): String {
    val snapshot = uiState.body
    return when {
        snapshot == null && uiState.isLoadingBody -> "Loading today’s Body data…"
        snapshot == null -> "Your sleep and health stats will appear here."
        snapshot.source == BodySource.CACHE -> "Saved Body data • refreshing live details"
        snapshot.features.day.isNotBlank() -> "Updated for ${snapshot.features.day}"
        else -> "Live Body data"
    }
}

private fun bodyFreshnessColor(uiState: HomeUiState): Color {
    return if (uiState.body?.source == BodySource.NETWORK) GaiaGreen else GaiaAmber
}

private fun patternsFreshnessText(uiState: HomeUiState): String {
    val snapshot = uiState.patterns
    return when {
        snapshot == null && uiState.isLoadingPatterns -> "Loading your personal patterns…"
        snapshot == null -> "Your personal patterns will appear here."
        snapshot.source == PatternsSource.CACHE -> "Saved patterns • refreshing live details"
        snapshot.patterns.partial -> "Your clearest patterns are ready • loading more"
        snapshot.patterns.generatedAt?.isNotBlank() == true -> "Your latest pattern read"
        else -> "Personal patterns"
    }
}

private fun patternsFreshnessColor(uiState: HomeUiState): Color {
    return if (
        uiState.patterns?.source == PatternsSource.NETWORK &&
        uiState.patterns.patterns.partial.not()
    ) {
        GaiaGreen
    } else {
        GaiaAmber
    }
}

private fun outlookFreshnessText(uiState: HomeUiState): String {
    val snapshot = uiState.outlook
    return when {
        snapshot == null && uiState.isLoadingOutlook -> "Loading your latest Outlook…"
        snapshot == null -> "Your forecast context will appear here."
        snapshot.source == OutlookSource.CACHE -> "Saved Outlook • refreshing live details"
        snapshot.outlook.generatedAt?.isNotBlank() == true -> "Latest forecast context"
        else -> "Outlook"
    }
}

private fun outlookFreshnessColor(uiState: HomeUiState): Color {
    return if (uiState.outlook?.source == OutlookSource.NETWORK) GaiaGreen else GaiaAmber
}

private fun exploreFreshnessText(uiState: HomeUiState): String {
    val snapshot = uiState.drivers
    return when {
        snapshot == null && uiState.isLoadingHomeContext -> "Loading current drivers…"
        snapshot == null -> "Your current drivers will appear here."
        snapshot.source == HomeContextSource.CACHE -> "Saved drivers • refreshing live details"
        snapshot.drivers.asof?.isNotBlank() == true -> "Latest driver context"
        else -> "Current drivers"
    }
}

private fun exploreFreshnessColor(uiState: HomeUiState): Color {
    return if (uiState.drivers?.source == HomeContextSource.NETWORK) GaiaGreen else GaiaAmber
}

private fun driverCategoryColor(driver: DriverItem): Color {
    return when (driver.category.trim().lowercase()) {
        "space" -> GaiaBlue
        "earth" -> Color(0xFFA8B66E)
        "local" -> GaiaAmber
        "body_context" -> GaiaRose
        else -> GaiaGreen
    }
}

private fun outlookStatusColor(status: String?): Color {
    return when (status?.trim()?.lowercase()) {
        "high", "strong", "elevated", "active" -> GaiaRose
        "watch", "moderate", "medium" -> GaiaAmber
        "quiet", "low", "mild", "steady" -> GaiaGreen
        else -> GaiaBlue
    }
}

private fun patternConfidenceColor(confidence: String?): Color {
    return when (confidence?.trim()?.lowercase()) {
        "strong", "clear", "high" -> GaiaGreen
        "emerging", "moderate", "medium" -> GaiaAmber
        "weak", "low" -> GaiaRose
        else -> GaiaBlue
    }
}

private fun patternCardAccent(index: Int): Color {
    val palette = listOf(
        GaiaBlue,
        GaiaGreen,
        GaiaAmber,
        GaiaRose,
        Color(0xFF9D7BFF),
        Color(0xFF45C6B5),
    )
    return palette[index.mod(palette.size)]
}
