import SwiftUI

struct OnboardingTagOption: Identifiable, Equatable {
    let id: String
    let title: String
    let subtitle: String?
}

struct OnboardingActivationDriver: Identifiable, Equatable {
    let id: String
    let title: String
    let detail: String
}

struct OnboardingActivationData: Equatable {
    let headline: String
    let explanation: String
    let drivers: [OnboardingActivationDriver]
    let nextActionTitle: String
    let secondaryActionTitle: String
    let footer: String?
}

private struct OnboardingFlowCopy {
    let headerSubtitle: String
    let welcomeTitle: String
    let welcomeSubtitle: String
    let modeTitle: String
    let modeSubtitle: String
    let guideTitle: String
    let guideSubtitle: String
    let toneTitle: String
    let toneSubtitle: String
    let temperatureTitle: String
    let temperatureSubtitle: String
    let sensitivitiesTitle: String
    let sensitivitiesSubtitle: String
    let healthContextTitle: String
    let healthContextSubtitle: String
    let locationTitle: String
    let locationSubtitle: String
    let useGPSOptionTitle: String
    let useGPSOptionSubtitle: String
    let enterZIPOptionTitle: String
    let enterZIPOptionSubtitle: String
    let localInsightsToggleTitle: String
    let healthDataTitle: String
    let healthDataSubtitle: String
    let healthDataHint: String
    let healthEmptySelectionBody: String
    let backfillTitle: String
    let backfillSubtitle: String
    let notificationsTitle: String
    let notificationsSubtitle: String
    let enableNotificationsTitle: String
    let signalAlertsTitle: String
    let localConditionAlertsTitle: String
    let personalizedAlertsTitle: String
    let geomagneticAlertTitle: String
    let solarWindAlertTitle: String
    let flareAlertTitle: String
    let schumannAlertTitle: String
    let pressureAlertTitle: String
    let aqiAlertTitle: String
    let temperatureAlertTitle: String
    let symptomFollowUpTitle: String
    let symptomFollowUpBody: String
    let quietHoursTitle: String
    let alertSensitivityTitle: String
    let activationTitle: String

    static func resolve(mode: ExperienceMode, tone: ToneStyle) -> OnboardingFlowCopy {
        let vocabulary = mode.copyVocabulary
        switch mode {
        case .scientific:
            return OnboardingFlowCopy(
                headerSubtitle: tone.resolveCopy(
                    straight: "Set up Gaia Eyes around what matters to you.",
                    balanced: "A few choices will help Gaia Eyes feel more relevant from the start.",
                    humorous: "A few quick choices, then Gaia Eyes can get out of your way and be useful."
                ),
                welcomeTitle: "Explore how your body, surroundings, and daily patterns may connect.",
                welcomeSubtitle: tone.resolveCopy(
                    straight: "Answer a few quick questions to personalize your dashboard and alerts.",
                    balanced: "Answer a few quick questions so Gaia Eyes can personalize your dashboard, alerts, and pattern tracking.",
                    humorous: "A few quick choices will personalize the app—no setup side quest required."
                ),
                modeTitle: "How do you want to experience Gaia Eyes?",
                modeSubtitle: "Choose the language style you prefer. Your data and calculations stay the same.",
                guideTitle: "Choose your guide",
                guideSubtitle: "Pick the guide style that makes daily check-ins feel easier.",
                toneTitle: "How should Gaia Eyes speak to you?",
                toneSubtitle: "Tone changes the wording, not the data.",
                temperatureTitle: "How do you prefer temperature?",
                temperatureSubtitle: "Choose the units you want to see. Gaia Eyes converts weather data for display.",
                sensitivitiesTitle: "What feels most relevant to you?",
                sensitivitiesSubtitle: "Choose the areas Gaia Eyes should emphasize first. You can change these later.",
                healthContextTitle: "Your health context",
                healthContextSubtitle: "Share only what feels relevant. Gaia Eyes uses this to personalize suggestions and patterns, not to diagnose.",
                locationTitle: "Where should Gaia Eyes track local conditions?",
                locationSubtitle: "Choose live GPS or a ZIP code. This powers local weather, pressure, air quality, and temperature context.",
                useGPSOptionTitle: "Use GPS",
                useGPSOptionSubtitle: "Best for live local conditions and travel days.",
                enterZIPOptionTitle: "Enter ZIP",
                enterZIPOptionSubtitle: "Best when you want a fixed local baseline.",
                localInsightsToggleTitle: "Use local insights",
                healthDataTitle: "Connect your health data",
                healthDataSubtitle: "Optional. Connect Apple Health to include sleep, heart rate, HRV, wrist temperature, and other selected wellness trends.",
                healthDataHint: tone.resolveCopy(
                    straight: "Choose what Gaia Eyes can import. Leave anything sensitive unchecked.",
                    balanced: "Choose what Gaia Eyes can import. You can leave something sensitive like cycle tracking unchecked and keep the rest.",
                    humorous: "Choose what Gaia Eyes can import. You can leave anything sensitive unchecked and keep the useful stuff."
                ),
                healthEmptySelectionBody: "Nothing is selected. Tap Not Now, or check at least one metric to request Health access.",
                backfillTitle: "Import up to 30 days of health history",
                backfillSubtitle: "Recent Apple Health history helps Gaia Eyes build useful baselines and personal patterns sooner.",
                notificationsTitle: "Choose your alerts",
                notificationsSubtitle: tone.resolveCopy(
                    straight: "Turn on only the updates you want. You can change these anytime.",
                    balanced: "Choose the updates that matter to you. Gaia Eyes will stay quiet until something meaningfully changes.",
                    humorous: "Choose what deserves a notification. Gaia Eyes can keep the drama low until something actually changes."
                ),
                enableNotificationsTitle: "Enable Notifications",
                signalAlertsTitle: "Earth + Space Alerts",
                localConditionAlertsTitle: "Local Condition Alerts",
                personalizedAlertsTitle: "Personal Pattern Alerts",
                geomagneticAlertTitle: "Geomagnetic activity (Kp)",
                solarWindAlertTitle: "Solar wind and Bz",
                flareAlertTitle: "Solar flares and solar storms",
                schumannAlertTitle: "Schumann activity",
                pressureAlertTitle: vocabulary.pressureSwingLabel,
                aqiAlertTitle: vocabulary.aqiLabel,
                temperatureAlertTitle: vocabulary.temperatureSwingLabel,
                symptomFollowUpTitle: "Follow-up Check-ins",
                symptomFollowUpBody: tone.resolveCopy(
                    balanced: "Gaia can send a check-in after you log a symptom so it can learn the arc, not just the spike.",
                    humorous: "Gaia can send a check-in after you log a symptom so it learns the arc, not just the plot twist."
                ),
                quietHoursTitle: "Quiet Hours",
                alertSensitivityTitle: "Alert Sensitivity",
                activationTitle: vocabulary.whatMattersNowLabel
            )
        case .mystical:
            return OnboardingFlowCopy(
                headerSubtitle: tone.resolveCopy(
                    straight: "Set up Gaia Eyes around what matters to you.",
                    balanced: "A few choices will help Gaia Eyes feel more relevant from the start.",
                    humorous: "A few quick choices, then Gaia Eyes can get out of your way and be useful."
                ),
                welcomeTitle: "Explore how your body, surroundings, and daily patterns may connect.",
                welcomeSubtitle: tone.resolveCopy(
                    straight: "Answer a few quick questions to personalize your dashboard and alerts.",
                    balanced: "Answer a few quick questions so Gaia Eyes can personalize your dashboard, alerts, and pattern tracking.",
                    humorous: "A few quick choices will personalize the app—no setup side quest required."
                ),
                modeTitle: "How do you want to experience Gaia Eyes?",
                modeSubtitle: "Choose the language style you prefer. Your data and calculations stay the same.",
                guideTitle: "Choose your guide",
                guideSubtitle: "Pick the guide style that makes daily check-ins feel easier.",
                toneTitle: "How should Gaia Eyes speak to you?",
                toneSubtitle: "Tone changes the wording, not the data.",
                temperatureTitle: "How do you prefer temperature?",
                temperatureSubtitle: "Choose the units you want to see. Gaia Eyes converts weather data for display.",
                sensitivitiesTitle: "What feels most relevant to you?",
                sensitivitiesSubtitle: "Choose the areas Gaia Eyes should emphasize first. You can change these later.",
                healthContextTitle: "Your health context",
                healthContextSubtitle: "Share only what feels relevant. Gaia Eyes uses this to personalize suggestions and patterns, not to diagnose.",
                locationTitle: "Where should Gaia Eyes track local conditions?",
                locationSubtitle: "Choose live GPS or a ZIP code. This powers local weather, \(vocabulary.pressureSwingLabel.lowercased()), \(vocabulary.aqiLabel.lowercased()), and temperature context.",
                useGPSOptionTitle: "Use GPS",
                useGPSOptionSubtitle: "Best for live local conditions and travel days.",
                enterZIPOptionTitle: "Enter ZIP",
                enterZIPOptionSubtitle: "Best when you want a fixed local baseline.",
                localInsightsToggleTitle: "Use local insights",
                healthDataTitle: "Connect your health data",
                healthDataSubtitle: "Optional. Connect Apple Health to include sleep, heart rate, HRV, wrist temperature, and other selected wellness trends.",
                healthDataHint: tone.resolveCopy(
                    straight: "Choose what Gaia Eyes can import. Leave anything sensitive unchecked.",
                    balanced: "Choose what Gaia Eyes can import. You can leave something sensitive like cycle tracking unchecked and keep the rest.",
                    humorous: "Choose what Gaia Eyes can import. You can leave anything sensitive unchecked and keep the useful stuff."
                ),
                healthEmptySelectionBody: "Nothing is selected. Tap Not Now, or check at least one metric to request Health access.",
                backfillTitle: "Import up to 30 days of health history",
                backfillSubtitle: "Recent Apple Health history helps Gaia Eyes build useful baselines and personal patterns sooner.",
                notificationsTitle: "Choose your alerts",
                notificationsSubtitle: tone.resolveCopy(
                    straight: "Turn on only the updates you want. You can change these anytime.",
                    balanced: "Choose the updates that matter to you. Gaia Eyes will stay quiet until something meaningfully changes.",
                    humorous: "Choose what deserves a notification. Gaia Eyes can keep the drama low until something actually changes."
                ),
                enableNotificationsTitle: "Enable Notifications",
                signalAlertsTitle: "Earth + Space Alerts",
                localConditionAlertsTitle: "Local Condition Alerts",
                personalizedAlertsTitle: "Personal Pattern Alerts",
                geomagneticAlertTitle: "\(vocabulary.geomagneticLabel) (\(vocabulary.kpLabel))",
                solarWindAlertTitle: "\(vocabulary.solarWindLabel) and \(vocabulary.bzLabel)",
                flareAlertTitle: "Solar flares and solar storms",
                schumannAlertTitle: "\(vocabulary.schumannLabel) activity",
                pressureAlertTitle: vocabulary.pressureSwingLabel,
                aqiAlertTitle: vocabulary.aqiLabel,
                temperatureAlertTitle: vocabulary.temperatureSwingLabel,
                symptomFollowUpTitle: "Follow-up Check-ins",
                symptomFollowUpBody: tone.resolveCopy(
                    balanced: "Gaia can send a check-in after you log a symptom so it can learn the arc, not just the spike.",
                    humorous: "Gaia can send a check-in after you log a symptom so it learns the arc, not just the plot twist."
                ),
                quietHoursTitle: "Quiet Hours",
                alertSensitivityTitle: "Alert Sensitivity",
                activationTitle: vocabulary.whatMattersNowLabel
            )
        }
    }
}

struct OnboardingFlowView: View {
    @Binding var isPresented: Bool
    @Binding var currentStep: OnboardingStep
    @Binding var profile: UserExperienceProfile
    @Binding var selectedTagKeys: Set<String>
    @Binding var zip: String
    @Binding var useGPS: Bool
    @Binding var localInsightsEnabled: Bool
    @Binding var selectedHealthPermissionKeys: Set<String>
    @Binding var notificationPreferences: AppNotificationPreferences

    let sensitivityOptions: [OnboardingTagOption]
    let healthContextOptions: [OnboardingTagOption]
    let activationData: OnboardingActivationData
    let locationMessage: String?
    let locationSaving: Bool
    let notificationSettingsSaving: Bool
    let notificationSettingsMessage: String?
    let pushPermissionGranted: Bool
    let pushDeviceTokenReady: Bool
    let healthPermissionsMessage: String?
    let healthReadAccessUnavailable: Bool
    let backfillMessage: String?
    let backfillInFlight: Bool
    let accountEmail: String?
    let accountMessage: String?
    let accountBusy: Bool
    let onContinueWithoutAccount: () async -> Bool
    let onSignInAccount: (String, String) async -> Bool
    let onCreateAccount: (String, String) async -> Bool
    let onPersistExperience: (UserExperienceProfileUpdate) async -> Void
    let onPersistTags: () async -> Void
    let onSaveLocation: () async -> Bool
    let onRequestHealthPermissions: () async -> Bool
    let onRunBackfill: () async -> Bool
    let onSaveNotifications: () async -> Void
    let onFinish: () async -> Void

    @State private var healthPermissionGrantedThisSession = false
    @State private var accountEmailInput: String = ""
    @State private var accountPasswordInput: String = ""
    @State private var accountCreateMode: Bool = false

    private var copy: OnboardingFlowCopy {
        OnboardingFlowCopy.resolve(mode: profile.mode, tone: profile.tone)
    }

    private var healthImportAvailable: Bool {
        healthPermissionGrantedThisSession || profile.healthkitRequestedAt != nil
    }

    private var progressLabel: String {
        let index = OnboardingStep.ordered.firstIndex(of: currentStep).map { $0 + 1 } ?? 1
        return "Step \(index) of \(OnboardingStep.ordered.count)"
    }

    private var locationSummary: String {
        if !localInsightsEnabled {
            return "You can keep local conditions off for now and add them later in Settings."
        }
        if useGPS {
            let cleaned = zip.trimmingCharacters(in: .whitespacesAndNewlines)
            return cleaned.isEmpty ? "GPS preferred for live local conditions." : "GPS preferred with ZIP \(cleaned) as a fallback."
        }
        let cleaned = zip.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Enter a ZIP code for local conditions." : "Using ZIP \(cleaned) for local conditions."
    }

    private var notificationStatus: String {
        if !notificationPreferences.enabled {
            return "Alerts are optional. You can turn them on later in Settings."
        }
        if !pushPermissionGranted {
            return "iOS permission is still off. Gaia will remember these alert categories for later."
        }
        return pushDeviceTokenReady ? "Push is ready on this device." : "Push token is still registering with Apple."
    }

    private func isSelected(_ option: OnboardingTagOption) -> Bool {
        selectedTagKeys.contains(option.id)
    }

    private func toggle(_ option: OnboardingTagOption) {
        if selectedTagKeys.contains(option.id) {
            selectedTagKeys.remove(option.id)
        } else {
            selectedTagKeys.insert(option.id)
        }
    }

    private func goNext() {
        guard let next = currentStep.next() else { return }
        currentStep = next
    }

    private func goBack() {
        guard let previous = currentStep.previous() else { return }
        currentStep = previous
    }

    private func isHealthPermissionSelected(_ option: HealthPermissionOption) -> Bool {
        selectedHealthPermissionKeys.contains(option.rawValue)
    }

    private func toggleHealthPermission(_ option: HealthPermissionOption) {
        if isHealthPermissionSelected(option) {
            selectedHealthPermissionKeys.remove(option.rawValue)
        } else {
            selectedHealthPermissionKeys.insert(option.rawValue)
        }
    }

    var body: some View {
        ZStack {
            GaiaAtmosphereBackground(variant: .onboarding)

            VStack(spacing: 0) {
                header
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        stepBody
                    }
                    .padding(20)
                    .frame(maxWidth: 720)
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .preferredColorScheme(.dark)
        .onChange(of: currentStep, initial: false) { _, newValue in
            if newValue == .activation {
                AppAnalytics.track("first_insight_viewed")
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Gaia Eyes")
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                    Text(copy.headerSubtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if currentStep != .welcome && currentStep != .healthkit {
                    Button("Close") {
                        AppAnalytics.track("onboarding_abandoned", properties: ["step": currentStep.rawValue])
                        isPresented = false
                    }
                    .buttonStyle(.bordered)
                    .tint(.white.opacity(0.3))
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(progressLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ProgressView(value: currentStep.progressValue)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 18)
        .padding(.bottom, 10)
        .background(Color.black.opacity(0.18))
    }

    @ViewBuilder
    private var stepBody: some View {
        switch currentStep {
        case .welcome:
            welcomeStep
        case .account:
            accountStep
        case .mode:
            modeStep
        case .guide:
            guideStep
        case .tone:
            toneStep
        case .temperatureUnit:
            temperatureStep
        case .sensitivities:
            tagStep(
                title: copy.sensitivitiesTitle,
                subtitle: copy.sensitivitiesSubtitle,
                options: sensitivityOptions
            )
        case .healthContext:
            tagStep(
                title: copy.healthContextTitle,
                subtitle: copy.healthContextSubtitle,
                options: healthContextOptions
            )
        case .location:
            locationStep
        case .healthkit:
            healthKitStep
        case .backfill:
            backfillStep
        case .notifications:
            notificationsStep
        case .activation:
            activationStep
        }
    }

    private var welcomeStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 20) {
                Text(copy.welcomeTitle)
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                Text(copy.welcomeSubtitle)
                    .font(.title3)
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 10) {
                    Text("What to expect after setup")
                        .font(.headline)
                    onboardingExpectationRow("Your first dashboard may take a minute to gather current conditions.")
                    onboardingExpectationRow("Apple Health details may fill in gradually after you allow access.")
                    onboardingExpectationRow("Personal patterns become more useful as you log how you feel.")
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                Button("Get Started") {
                    currentStep = .account
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
            }
        }
    }

    private func onboardingExpectationRow(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "sparkle")
                .font(.caption.weight(.bold))
                .foregroundStyle(Color(red: 0.51, green: 0.82, blue: 0.97))
                .padding(.top, 3)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var accountStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text("Account access")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Start without an email, or sign in now if you already have an account.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                if let accountEmail, !accountEmail.isEmpty {
                    Label("Signed in as \(accountEmail)", systemImage: "checkmark.seal.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Color(red: 0.59, green: 0.86, blue: 0.62))
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.white.opacity(0.06))
                        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 10) {
                    Text(accountCreateMode ? "Create account" : "Sign in")
                        .font(.headline)
                    TextField("Email", text: $accountEmailInput)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                        .textFieldStyle(.roundedBorder)
                    SecureField("Password", text: $accountPasswordInput)
                        .textContentType(accountCreateMode ? .newPassword : .password)
                        .textFieldStyle(.roundedBorder)

                    Button(accountCreateMode ? "Create Account" : "Sign In") {
                        Task {
                            let ok = accountCreateMode
                                ? await onCreateAccount(accountEmailInput, accountPasswordInput)
                                : await onSignInAccount(accountEmailInput, accountPasswordInput)
                            if ok {
                                currentStep = .mode
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(accountBusy || accountEmailInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || accountPasswordInput.isEmpty)

                    Button(accountCreateMode ? "Already have an account? Sign in" : "Create an account instead") {
                        accountCreateMode.toggle()
                    }
                    .font(.caption.weight(.semibold))
                    .buttonStyle(.plain)
                    .foregroundStyle(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

                VStack(alignment: .leading, spacing: 8) {
                    Text("Start without an email")
                        .font(.headline)
                    Text("Gaia Eyes can create an app-only account now. Add an email later for website access, restores, exports, and cross-device sync.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

                if let accountMessage, !accountMessage.isEmpty {
                    Text(accountMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button("Back") {
                        currentStep = .welcome
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button(accountBusy ? "Preparing..." : "Continue without email") {
                        Task {
                            if await onContinueWithoutAccount() {
                                currentStep = .mode
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(accountBusy)
                }
            }
        }
    }

    private var modeStep: some View {
        selectionStep(
            title: copy.modeTitle,
            subtitle: copy.modeSubtitle,
            options: ExperienceMode.allCases,
            selected: profile.mode,
            titleFor: \.title,
            subtitleFor: \.subtitle
        ) { mode in
            profile.mode = mode
            await onPersistExperience(UserExperienceProfileUpdate(mode: mode, onboardingStep: .guide))
            currentStep = .guide
        }
    }

    private var guideStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.guideTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(copy.guideSubtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                HStack {
                    Spacer()
                    VStack(spacing: 12) {
                        GuideAvatarView(
                            guide: profile.guide,
                            expression: .guide,
                            size: .large,
                            emphasis: .standard,
                            showBackingPlate: true,
                            animate: true
                        )
                        Text(profile.guide.title)
                            .font(.headline)
                        Text(profile.guide.subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    Spacer()
                }
                .padding(.vertical, 8)

                VStack(spacing: 12) {
                    ForEach(guideSelectionOptions, id: \.self) { guide in
                        Button {
                            Task {
                                profile.guide = guide
                                await onPersistExperience(UserExperienceProfileUpdate(guide: guide, onboardingStep: .tone))
                                currentStep = .tone
                            }
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: guide == profile.guide ? "checkmark.circle.fill" : "circle")
                                    .font(.title3)
                                    .foregroundStyle(
                                        guide == profile.guide
                                        ? Color(red: 0.51, green: 0.82, blue: 0.97)
                                        : .secondary
                                    )
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(guide.title)
                                        .font(.headline)
                                    Text(guide.subtitle)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(guide == profile.guide ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }

                Button("Back") {
                    goBack()
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private var guideSelectionOptions: [GuideType] {
        [.cat, .dog, .robot]
    }

    private var toneStep: some View {
        selectionStep(
            title: copy.toneTitle,
            subtitle: copy.toneSubtitle,
            options: ToneStyle.allCases,
            selected: profile.tone,
            titleFor: \.title,
            subtitleFor: \.subtitle
        ) { tone in
            profile.tone = tone
            await onPersistExperience(UserExperienceProfileUpdate(tone: tone, onboardingStep: .temperatureUnit))
            currentStep = .temperatureUnit
        }
    }

    private var temperatureStep: some View {
        selectionStep(
            title: copy.temperatureTitle,
            subtitle: copy.temperatureSubtitle,
            options: TemperatureUnit.allCases,
            selected: profile.tempUnit,
            titleFor: \.title,
            subtitleFor: \.subtitle
        ) { unit in
            profile.tempUnit = unit
            await onPersistExperience(UserExperienceProfileUpdate(tempUnit: unit, onboardingStep: .sensitivities))
            currentStep = .sensitivities
        }
    }

    private func tagStep(
        title: String,
        subtitle: String,
        options: [OnboardingTagOption]
    ) -> some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(title)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(subtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                VStack(spacing: 12) {
                    ForEach(options) { option in
                        Button {
                            toggle(option)
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: isSelected(option) ? "checkmark.circle.fill" : "circle")
                                    .font(.title3)
                                    .foregroundStyle(isSelected(option) ? Color(red: 0.51, green: 0.82, blue: 0.97) : .secondary)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(option.title)
                                        .font(.headline)
                                    if let subtitle = option.subtitle, !subtitle.isEmpty {
                                        Text(subtitle)
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(isSelected(option) ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }

                if currentStep == .healthContext {
                    lunarTrackingCard
                }

                HStack {
                    if currentStep == .healthContext {
                        Button("Skip for now") {
                            currentStep = .location
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Button("Back") {
                            goBack()
                        }
                        .buttonStyle(.bordered)
                    }

                    Spacer()

                    Button(currentStep == .sensitivities ? "Continue" : "Save and Continue") {
                        Task {
                            await onPersistTags()
                            if currentStep == .healthContext {
                                AppAnalytics.track(
                                    profile.lunarSensitivityDeclared ? "lunar_tracking_enabled" : "lunar_tracking_skipped",
                                    properties: ["surface": "onboarding"]
                                )
                                await onPersistExperience(
                                    UserExperienceProfileUpdate(
                                        lunarSensitivityDeclared: profile.lunarSensitivityDeclared,
                                        onboardingStep: .location
                                    )
                                )
                            }
                            currentStep = currentStep == .sensitivities ? .healthContext : .location
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var lunarTrackingCard: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "moon.stars.fill")
                .font(.title3)
                .foregroundStyle(Color(red: 0.51, green: 0.82, blue: 0.97))
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 8) {
                Toggle(isOn: $profile.lunarSensitivityDeclared) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Track moon phases")
                            .font(.headline)
                        Text("Compare full and new moon phases with sleep, cycle, pain, and energy patterns over time.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .toggleStyle(.switch)

                Text("Pattern tracking only. You can turn this off later in Settings.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(profile.lunarSensitivityDeclared ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var locationStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.locationTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(copy.locationSubtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    locationChoiceCard(
                        title: copy.useGPSOptionTitle,
                        subtitle: copy.useGPSOptionSubtitle,
                        isSelected: useGPS
                    ) {
                        useGPS = true
                    }

                    locationChoiceCard(
                        title: copy.enterZIPOptionTitle,
                        subtitle: copy.enterZIPOptionSubtitle,
                        isSelected: !useGPS
                    ) {
                        useGPS = false
                    }
                }

                TextField("ZIP code", text: $zip)
                    .textFieldStyle(.plain)
                    .padding(16)
                    .background(Color.white.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .keyboardType(.numberPad)
                    .disabled(useGPS)
                    .opacity(useGPS ? 0.55 : 1.0)

                Toggle(copy.localInsightsToggleTitle, isOn: $localInsightsEnabled)
                    .toggleStyle(.switch)

                Text(locationSummary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                if let locationMessage, !locationMessage.isEmpty {
                    Text(locationMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button("Back") {
                        goBack()
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button {
                        Task {
                            let saved = await onSaveLocation()
                            guard saved else { return }
                            await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .healthkit))
                            currentStep = .healthkit
                        }
                    } label: {
                        HStack {
                            if locationSaving {
                                ProgressView()
                                    .scaleEffect(0.9)
                            }
                            Text(locationSaving ? "Saving..." : "Continue")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(locationSaving)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var healthKitStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.healthDataTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(copy.healthDataSubtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                Text(copy.healthDataHint)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                VStack(spacing: 12) {
                    ForEach(HealthPermissionOption.allCases) { option in
                        Button {
                            toggleHealthPermission(option)
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: isHealthPermissionSelected(option) ? "checkmark.square.fill" : "square")
                                    .font(.title3)
                                    .foregroundStyle(
                                        isHealthPermissionSelected(option)
                                        ? Color(red: 0.51, green: 0.82, blue: 0.97)
                                        : .secondary
                                    )
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(option.title)
                                        .font(.headline)
                                    Text(option.subtitle)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                isHealthPermissionSelected(option)
                                ? Color.white.opacity(0.10)
                                : Color.white.opacity(0.04)
                            )
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }

                if selectedHealthPermissionKeys.isEmpty {
                    Text(copy.healthEmptySelectionBody)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if let healthPermissionsMessage, !healthPermissionsMessage.isEmpty {
                    Text(healthPermissionsMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button("Not Now") {
                        Task {
                            await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .backfill))
                            currentStep = .backfill
                        }
                    }
                    .buttonStyle(.bordered)

                    Spacer()
                    Button("Connect Health Data") {
                        Task {
                            let granted = await onRequestHealthPermissions()
                            healthPermissionGrantedThisSession = granted
                            await onPersistExperience(
                                UserExperienceProfileUpdate(
                                    healthkitRequested: true
                                )
                            )
                            await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .backfill))
                            currentStep = .backfill
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedHealthPermissionKeys.isEmpty)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var backfillStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.backfillTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(copy.backfillSubtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                Text(healthImportAvailable
                     ? "Gaia Eyes will import the Apple Health data you allowed."
                     : "You can keep going without importing history. Gaia Eyes will still show useful live conditions today.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                if healthImportAvailable {
                    Text("If Health data does not appear right away, open Apple Health and your wearable app once so they can finish syncing, then return to Gaia.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else if healthReadAccessUnavailable {
                    Text("Apple Health data is not available yet. You can try the import now, or continue and retry later from Settings.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if let backfillMessage, !backfillMessage.isEmpty {
                    Text(backfillMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button("Continue Without Import") {
                        Task {
                            await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .notifications))
                            currentStep = .notifications
                        }
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button {
                        Task {
                            let completed = await onRunBackfill()
                            if completed {
                                await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .notifications))
                                currentStep = .notifications
                            }
                        }
                    } label: {
                        HStack {
                            if backfillInFlight {
                                ProgressView()
                                    .scaleEffect(0.9)
                            }
                            Text(backfillInFlight ? "Importing..." : "Import Last 30 Days")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(backfillInFlight || !healthImportAvailable)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var notificationsStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.notificationsTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(copy.notificationsSubtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                Toggle(copy.enableNotificationsTitle, isOn: $notificationPreferences.enabled)
                    .toggleStyle(.switch)

                groupedNotificationSection(
                    title: copy.signalAlertsTitle,
                    enabled: $notificationPreferences.signalAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle(copy.geomagneticAlertTitle, isOn: $notificationPreferences.families.geomagnetic)
                    Toggle(copy.solarWindAlertTitle, isOn: $notificationPreferences.families.solarWind)
                    Toggle(copy.flareAlertTitle, isOn: $notificationPreferences.families.flareCmeSep)
                    Toggle(copy.schumannAlertTitle, isOn: $notificationPreferences.families.schumann)
                }

                groupedNotificationSection(
                    title: copy.localConditionAlertsTitle,
                    enabled: $notificationPreferences.localConditionAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle(copy.pressureAlertTitle, isOn: $notificationPreferences.families.pressure)
                    Toggle(copy.aqiAlertTitle, isOn: $notificationPreferences.families.aqi)
                    Toggle(copy.temperatureAlertTitle, isOn: $notificationPreferences.families.temp)
                }

                groupedNotificationSection(
                    title: copy.personalizedAlertsTitle,
                    enabled: $notificationPreferences.personalizedGaugeAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle("Meaningful gauge changes", isOn: $notificationPreferences.families.gaugeSpikes)
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text(copy.symptomFollowUpTitle)
                        .font(.subheadline.weight(.semibold))
                    Toggle("Symptom follow-up reminders", isOn: $notificationPreferences.symptomFollowupsEnabled)
                    Text(copy.symptomFollowUpBody)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if notificationPreferences.symptomFollowupsEnabled {
                        Toggle("Allow symptom follow-up notifications", isOn: $notificationPreferences.symptomFollowupPushEnabled)
                        Text("These reminders check back after a symptom log so you can mark whether it improved, continued, or resolved.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Picker("Follow-up cadence", selection: $notificationPreferences.symptomFollowupCadence) {
                            Text("Minimal").tag("minimal")
                            Text("Balanced").tag("balanced")
                            Text("Detailed").tag("detailed")
                        }
                        .pickerStyle(.segmented)
                    }
                }
                .disabled(!notificationPreferences.enabled)

                VStack(alignment: .leading, spacing: 12) {
                    Text("Daily Check-In")
                        .font(.subheadline.weight(.semibold))
                    Toggle("Daily check-ins", isOn: $notificationPreferences.dailyCheckinsEnabled)
                    Text("Get a brief reminder to record how the day felt and keep your personal patterns current.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if notificationPreferences.dailyCheckinsEnabled {
                        Toggle("Allow daily check-in notifications", isOn: $notificationPreferences.dailyCheckinPushEnabled)
                        Text("Daily check-ins are separate from symptom follow-up reminders.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Picker("Daily check-in cadence", selection: $notificationPreferences.dailyCheckinCadence) {
                            Text("Minimal").tag("minimal")
                            Text("Balanced").tag("balanced")
                            Text("Detailed").tag("detailed")
                        }
                        .pickerStyle(.segmented)
                        TextField("Reminder 20:00", text: $notificationPreferences.dailyCheckinReminderTime)
                            .textFieldStyle(.roundedBorder)
                    }
                }
                .disabled(!notificationPreferences.enabled)

                VStack(alignment: .leading, spacing: 12) {
                    Toggle(copy.quietHoursTitle, isOn: $notificationPreferences.quietHoursEnabled)
                    if notificationPreferences.quietHoursEnabled {
                        HStack {
                            TextField("Start 22:00", text: $notificationPreferences.quietStart)
                                .textFieldStyle(.roundedBorder)
                            TextField("End 08:00", text: $notificationPreferences.quietEnd)
                                .textFieldStyle(.roundedBorder)
                        }
                    }
                }
                .disabled(!notificationPreferences.enabled)

                VStack(alignment: .leading, spacing: 8) {
                    Text(copy.alertSensitivityTitle)
                        .font(.subheadline.weight(.semibold))
                    Picker("Alert Sensitivity", selection: $notificationPreferences.sensitivity) {
                        Text("Minimal").tag("minimal")
                        Text("Normal").tag("normal")
                        Text("Detailed").tag("detailed")
                    }
                    .pickerStyle(.segmented)
                    .disabled(!notificationPreferences.enabled)
                }

                Text(notificationStatus)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                if let notificationSettingsMessage, !notificationSettingsMessage.isEmpty {
                    Text(notificationSettingsMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Button {
                    Task {
                        await onSaveNotifications()
                        await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .activation))
                        currentStep = .activation
                    }
                } label: {
                    HStack {
                        if notificationSettingsSaving {
                            ProgressView()
                                .scaleEffect(0.9)
                        }
                        Text(notificationSettingsSaving ? "Saving..." : "Save and Continue")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(notificationSettingsSaving)
                .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
            }
        }
    }

    private var activationStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(copy.activationTitle)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(activationData.headline)
                    .font(.title2.weight(.semibold))
                Text(activationData.explanation)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                VStack(spacing: 12) {
                    ForEach(activationData.drivers) { driver in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(driver.title)
                                .font(.headline)
                            Text(driver.detail)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.white.opacity(0.06))
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                }

                if let footer = activationData.footer, !footer.isEmpty {
                    Text(footer)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button(activationData.secondaryActionTitle) {
                        Task {
                            profile.onboardingCompleted = true
                            await onFinish()
                            isPresented = false
                        }
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button(activationData.nextActionTitle) {
                        Task {
                            profile.onboardingCompleted = true
                            await onFinish()
                            isPresented = false
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private func onboardingCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            content()
        }
        .padding(24)
        .background(Color.black.opacity(0.40))
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.09), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private func selectionStep<Option: Identifiable & Equatable>(
        title: String,
        subtitle: String,
        options: [Option],
        selected: Option,
        titleFor: KeyPath<Option, String>,
        subtitleFor: KeyPath<Option, String>,
        onSelect: @escaping (Option) async -> Void
    ) -> some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text(title)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text(subtitle)
                    .font(.headline)
                    .foregroundStyle(.secondary)

                VStack(spacing: 12) {
                    ForEach(options) { option in
                        Button {
                            Task { await onSelect(option) }
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: option == selected ? "checkmark.circle.fill" : "circle")
                                    .font(.title3)
                                    .foregroundStyle(option == selected ? Color(red: 0.51, green: 0.82, blue: 0.97) : .secondary)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(option[keyPath: titleFor])
                                        .font(.headline)
                                    Text(option[keyPath: subtitleFor])
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(option == selected ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }

                Button("Back") {
                    goBack()
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private func locationChoiceCard(
        title: String,
        subtitle: String,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.headline)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
            .background(isSelected ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func groupedNotificationSection<Content: View>(
        title: String,
        enabled: Binding<Bool>,
        parentEnabled: Bool,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle(title, isOn: enabled)
            if enabled.wrappedValue {
                VStack(alignment: .leading, spacing: 10) {
                    content()
                }
                .padding(.leading, 6)
            }
        }
        .disabled(!parentEnabled)
    }
}
