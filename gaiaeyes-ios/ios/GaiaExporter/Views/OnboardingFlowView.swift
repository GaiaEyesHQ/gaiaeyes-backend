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

struct OnboardingFlowView: View {
    @Binding var isPresented: Bool
    @Binding var currentStep: OnboardingStep
    @Binding var profile: UserExperienceProfile
    @Binding var selectedTagKeys: Set<String>
    @Binding var zip: String
    @Binding var useGPS: Bool
    @Binding var localInsightsEnabled: Bool
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
    let backfillMessage: String?
    let backfillInFlight: Bool
    let onPersistExperience: (UserExperienceProfileUpdate) async -> Void
    let onPersistTags: () async -> Void
    let onSaveLocation: () async -> Bool
    let onRequestHealthPermissions: () async -> Bool
    let onRunBackfill: () async -> Bool
    let onSaveNotifications: () async -> Void
    let onFinish: () async -> Void

    @State private var healthPermissionGrantedThisSession = false

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
        Task { await onPersistTags() }
    }

    private func goNext() {
        guard let next = currentStep.next() else { return }
        currentStep = next
    }

    private func goBack() {
        guard let previous = currentStep.previous() else { return }
        currentStep = previous
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.05, green: 0.06, blue: 0.1), Color(red: 0.09, green: 0.12, blue: 0.18)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

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
                    Text("Gaia Eyes is learning how to speak to you.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if currentStep != .welcome {
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
        case .mode:
            modeStep
        case .guide:
            guideStep
        case .tone:
            toneStep
        case .sensitivities:
            tagStep(
                title: "What tends to affect you most?",
                subtitle: "Pick the signals Gaia should emphasize first. You can adjust these later.",
                options: sensitivityOptions
            )
        case .healthContext:
            tagStep(
                title: "Optional health context",
                subtitle: "Self-reported context only. This helps Gaia weigh patterns more personally without making diagnoses.",
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
                Text("Understand how the world around you may connect to how you feel.")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                Text("We’ll set up just enough to make your first session useful, personal, and calm.")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                Button("Get Started") {
                    currentStep = .mode
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
            }
        }
    }

    private var modeStep: some View {
        selectionStep(
            title: "How do you want to experience Gaia Eyes?",
            subtitle: "The underlying signal model stays the same. Only the presentation changes.",
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
        selectionStep(
            title: "Choose your guide",
            subtitle: "A little personality, without changing the truth layer.",
            options: GuideType.allCases,
            selected: profile.guide,
            titleFor: \.title,
            subtitleFor: \.subtitle
        ) { guide in
            profile.guide = guide
            await onPersistExperience(UserExperienceProfileUpdate(guide: guide, onboardingStep: .tone))
            currentStep = .tone
        }
    }

    private var toneStep: some View {
        selectionStep(
            title: "How should Gaia Eyes speak to you?",
            subtitle: "Tone changes the presentation, not the underlying truth.",
            options: ToneStyle.allCases,
            selected: profile.tone,
            titleFor: \.title,
            subtitleFor: \.subtitle
        ) { tone in
            profile.tone = tone
            await onPersistExperience(UserExperienceProfileUpdate(tone: tone, onboardingStep: .sensitivities))
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
                            currentStep = currentStep == .sensitivities ? .healthContext : .location
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var locationStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text("Where should Gaia Eyes track local conditions?")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Choose live GPS or a ZIP code. This powers local weather, pressure, air quality, and temperature context.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    locationChoiceCard(
                        title: "Use GPS",
                        subtitle: "Best for live local conditions and travel days.",
                        isSelected: useGPS
                    ) {
                        useGPS = true
                    }

                    locationChoiceCard(
                        title: "Enter ZIP",
                        subtitle: "Best when you want a fixed local baseline.",
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

                Toggle("Use local insights", isOn: $localInsightsEnabled)
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
                Text("Connect your health data")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Optional, but useful for sleep, heart rate, recovery trends, and faster pattern detection.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 10) {
                    featureRow("Heart rate, HRV, resting heart rate")
                    featureRow("Sleep, SpO2, respiratory rate")
                    featureRow("Blood pressure and wrist temperature when supported")
                    featureRow("Menstrual-flow timing only if you allow it")
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
                                    onboardingStep: .backfill,
                                    healthkitRequested: true
                                )
                            )
                            currentStep = .backfill
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var backfillStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text("Sync your last 30 days")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Import recent data so Gaia Eyes can recognize patterns sooner.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                Text(healthPermissionGrantedThisSession || profile.healthkitRequestedAt != nil
                     ? "Gaia will try to import every HealthKit signal you allowed."
                     : "You can keep going without a backfill. Gaia will still show useful live conditions today.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

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
                            }
                            currentStep = .notifications
                        }
                    } label: {
                        HStack {
                            if backfillInFlight {
                                ProgressView()
                                    .scaleEffect(0.9)
                            }
                            Text(backfillInFlight ? "Importing..." : "Sync Last 30 Days")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(backfillInFlight)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var notificationsStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text("Would you like helpful alerts?")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Choose the alert families you care about. Gaia can stay quiet until something meaningfully changes.")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                Toggle("Enable Notifications", isOn: $notificationPreferences.enabled)
                    .toggleStyle(.switch)

                groupedNotificationSection(
                    title: "Signal Alerts",
                    enabled: $notificationPreferences.signalAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle("Geomagnetic / Kp", isOn: $notificationPreferences.families.geomagnetic)
                    Toggle("Solar wind / Bz coupling", isOn: $notificationPreferences.families.solarWind)
                    Toggle("Flares / CME / SEP / DRAP", isOn: $notificationPreferences.families.flareCmeSep)
                    Toggle("Schumann spike / elevated", isOn: $notificationPreferences.families.schumann)
                }

                groupedNotificationSection(
                    title: "Local Condition Alerts",
                    enabled: $notificationPreferences.localConditionAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle("Pressure swing", isOn: $notificationPreferences.families.pressure)
                    Toggle("AQI", isOn: $notificationPreferences.families.aqi)
                    Toggle("Temperature swing", isOn: $notificationPreferences.families.temp)
                }

                groupedNotificationSection(
                    title: "Personalized Alerts",
                    enabled: $notificationPreferences.personalizedGaugeAlertsEnabled,
                    parentEnabled: notificationPreferences.enabled
                ) {
                    Toggle("Gauge spikes", isOn: $notificationPreferences.families.gaugeSpikes)
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("Symptom Follow-up Prompts")
                        .font(.subheadline.weight(.semibold))
                    Toggle("Symptom follow-up prompts", isOn: $notificationPreferences.symptomFollowupsEnabled)
                    Text("Gaia can send a check-in after you log a symptom so it can learn the arc, not just the spike.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .disabled(!notificationPreferences.enabled)

                VStack(alignment: .leading, spacing: 12) {
                    Toggle("Quiet Hours", isOn: $notificationPreferences.quietHoursEnabled)
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
                    Text("Alert Sensitivity")
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

                HStack {
                    Button("Continue") {
                        Task {
                            await onSaveNotifications()
                            await onPersistExperience(UserExperienceProfileUpdate(onboardingStep: .activation))
                            currentStep = .activation
                        }
                    }
                    .buttonStyle(.bordered)

                    Spacer()

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
                            Text(notificationSettingsSaving ? "Saving..." : "Save Alerts")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(notificationSettingsSaving)
                    .tint(Color(red: 0.51, green: 0.82, blue: 0.97))
                }
            }
        }
    }

    private var activationStep: some View {
        onboardingCard {
            VStack(alignment: .leading, spacing: 18) {
                Text("What matters now")
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
        .background(Color.black.opacity(0.34))
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
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

                if currentStep != .mode {
                    Button("Back") {
                        goBack()
                    }
                    .buttonStyle(.bordered)
                }
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

    private func featureRow(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(Color(red: 0.51, green: 0.82, blue: 0.97))
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
        }
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
