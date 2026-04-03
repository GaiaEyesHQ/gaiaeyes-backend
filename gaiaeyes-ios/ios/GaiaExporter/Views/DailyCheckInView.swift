import SwiftUI

private extension String {
    var nilIfBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

private struct DailyCheckInChoice: Identifiable, Hashable {
    let id: String
    let label: String
}

private let validSleepImpactChoiceIds: Set<String> = ["yes_strongly", "yes_somewhat", "not_much", "unsure"]

private struct DailyCheckInChoiceGrid: View {
    let title: String
    let subtitle: String?
    @Binding var selection: String
    let choices: [DailyCheckInChoice]

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
                .foregroundColor(.white)

            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.68))
            }

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(choices) { choice in
                    Button {
                        selection = choice.id
                    } label: {
                        Text(choice.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(selection == choice.id ? Color(red: 0.35, green: 0.58, blue: 0.92).opacity(0.28) : Color.white.opacity(0.05))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(selection == choice.id ? Color(red: 0.35, green: 0.58, blue: 0.92) : Color.white.opacity(0.08), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

private struct DailyCheckInMultiChoiceGrid: View {
    let title: String
    let subtitle: String?
    @Binding var selection: Set<String>
    let choices: [DailyCheckInChoice]

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
                .foregroundColor(.white)

            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.68))
            }

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(choices) { choice in
                    let isSelected = selection.contains(choice.id)
                    Button {
                        if isSelected {
                            selection.remove(choice.id)
                        } else {
                            selection.insert(choice.id)
                        }
                    } label: {
                        Text(choice.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(isSelected ? Color(red: 0.35, green: 0.58, blue: 0.92).opacity(0.28) : Color.white.opacity(0.05))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(isSelected ? Color(red: 0.35, green: 0.58, blue: 0.92) : Color.white.opacity(0.08), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

struct DailyCheckInView: View {
    let api: APIClient
    var mode: ExperienceMode = .scientific
    var tone: ToneStyle = .balanced
    var showsCloseButton: Bool = false
    let initialStatus: DailyCheckInStatus?
    let onStatusChanged: (DailyCheckInStatus) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var status: DailyCheckInStatus?
    @State private var isLoading: Bool = false
    @State private var isSaving: Bool = false
    @State private var statusMessage: String?
    @State private var alertMessage: String?
    @State private var didSeedForm: Bool = false
    @State private var comparedToYesterday: String = ""
    @State private var energyLevel: String = ""
    @State private var usableEnergy: String = ""
    @State private var systemLoad: String = ""
    @State private var painLevel: String = ""
    @State private var painType: String = ""
    @State private var energyDetail: String = ""
    @State private var moodLevel: String = ""
    @State private var moodType: String = ""
    @State private var sleepImpact: String = ""
    @State private var predictionMatch: String = ""
    @State private var noteText: String = ""
    @State private var exposures: Set<String> = []

    init(
        api: APIClient,
        mode: ExperienceMode = .scientific,
        tone: ToneStyle = .balanced,
        showsCloseButton: Bool = false,
        initialStatus: DailyCheckInStatus? = nil,
        onStatusChanged: @escaping (DailyCheckInStatus) -> Void
    ) {
        self.api = api
        self.mode = mode
        self.tone = tone
        self.showsCloseButton = showsCloseButton
        self.initialStatus = initialStatus
        self.onStatusChanged = onStatusChanged
        _status = State(initialValue: initialStatus)
    }

    private var prompt: DailyCheckInPrompt? {
        status?.prompt
    }

    private var latestEntry: DailyCheckInEntry? {
        status?.latestEntry
    }

    private var activeLabels: [String] {
        prompt?.activeSymptomLabels ?? []
    }

    private var targetDay: String {
        if let statusTargetDay = status?.targetDay ?? initialStatus?.targetDay, !statusTargetDay.isEmpty {
            return statusTargetDay
        }
        if let promptDay = prompt?.day, !promptDay.isEmpty {
            return promptDay
        }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private var isCompletedForTargetDay: Bool {
        latestEntry?.day == targetDay && latestEntry?.completedAt != nil
    }

    private var canSubmit: Bool {
        !comparedToYesterday.isEmpty &&
        !energyLevel.isEmpty &&
        !usableEnergy.isEmpty &&
        !systemLoad.isEmpty &&
        !painLevel.isEmpty &&
        !moodLevel.isEmpty
    }

    private var questionText: String {
        if mode == .mystical {
            if (prompt?.phase ?? "").lowercased() == "next_morning" {
                return "How did yesterday feel in your system?"
            }
            return "How did today feel in your system?"
        }
        return prompt?.questionText ?? "How did today feel?"
    }

    private var fallbackCalibrationSummary: FeedbackCalibrationSummary {
        (status ?? initialStatus)?.calibrationSummary ?? FeedbackCalibrationSummary(
            windowDays: 21,
            totalCheckins: 0,
            mostlyRight: 0,
            partlyRight: 0,
            notReally: 0,
            matchRate: nil,
            resolvedCount: 0,
            improvingCount: 0,
            worseCount: 0
        )
    }

    private var fallbackSettings: DailyCheckInSettings {
        (status ?? initialStatus)?.settings ?? DailyCheckInSettings(
            enabled: false,
            pushEnabled: false,
            cadence: "balanced",
            reminderTime: "20:00"
        )
    }

    private var energySubtitle: String {
        mode == .mystical ? "A quick read on how steady your system felt." : "Keep this broad and quick."
    }

    private var usableEnergySubtitle: String {
        mode == .mystical ? "A simple read on how open or limited the day felt." : "A simple read on how much you could actually do."
    }

    private var predictionSubtitle: String {
        mode == .mystical ? "This helps Gaia stay grounded over time." : "This helps Gaia stay calibrated over time."
    }

    private var comparisonChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "better", label: "Better than yesterday"),
            DailyCheckInChoice(id: "same", label: "About the same"),
            DailyCheckInChoice(id: "worse", label: "Worse than yesterday"),
        ]
    }

    private var energyChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "good", label: "Good"),
            DailyCheckInChoice(id: "manageable", label: "Manageable"),
            DailyCheckInChoice(id: "low", label: "Low"),
            DailyCheckInChoice(id: "depleted", label: "Depleted"),
        ]
    }

    private var usableEnergyChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "plenty", label: "Plenty"),
            DailyCheckInChoice(id: "enough", label: "Enough"),
            DailyCheckInChoice(id: "limited", label: "Limited"),
            DailyCheckInChoice(id: "very_limited", label: "Very limited"),
        ]
    }

    private var systemLoadChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "light", label: "Light"),
            DailyCheckInChoice(id: "moderate", label: "Moderate"),
            DailyCheckInChoice(id: "heavy", label: "Heavy"),
            DailyCheckInChoice(id: "overwhelming", label: "Overwhelming"),
        ]
    }

    private var painChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "none", label: "No"),
            DailyCheckInChoice(id: "a_little", label: "A little"),
            DailyCheckInChoice(id: "noticeable", label: "Yes, noticeably"),
            DailyCheckInChoice(id: "strong", label: "Yes, strongly"),
        ]
    }

    private var moodChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "calm", label: "Calm / steady"),
            DailyCheckInChoice(id: "slightly_off", label: "Slightly off"),
            DailyCheckInChoice(id: "noticeable", label: "Noticeably affected"),
            DailyCheckInChoice(id: "strong", label: "Strongly affected"),
        ]
    }

    private var predictionChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "mostly_right", label: "Mostly right"),
            DailyCheckInChoice(id: "partly_right", label: "Partly right"),
            DailyCheckInChoice(id: "not_really", label: "Not really"),
        ]
    }

    private var exposureChoices: [DailyCheckInChoice] {
        [
            DailyCheckInChoice(id: "overexertion", label: "Heavy activity / overdid it"),
            DailyCheckInChoice(id: "allergen_exposure", label: "Allergen exposure"),
        ]
    }

    private var painTypeChoices: [DailyCheckInChoice] {
        let suggested = prompt?.suggestedPainTypes ?? []
        let base = suggested.isEmpty ? ["sinus_pressure", "joint_pain", "nerve_pain", "muscle_pain", "head_pressure", "cycle_related_pain", "other"] : suggested
        return base.map { DailyCheckInChoice(id: $0, label: dailyChoiceLabel($0)) }
    }

    private var energyDetailChoices: [DailyCheckInChoice] {
        let suggested = prompt?.suggestedEnergyDetails ?? []
        let base = suggested.isEmpty ? ["tired", "drained", "heavy_body", "brain_fog", "crashed_later"] : suggested
        return base.map { DailyCheckInChoice(id: $0, label: dailyChoiceLabel($0)) }
    }

    private var moodTypeChoices: [DailyCheckInChoice] {
        let suggested = prompt?.suggestedMoodTypes ?? []
        let base = suggested.isEmpty ? ["anxious", "wired", "irritable", "low_mood", "emotionally_sensitive"] : suggested
        return base.map { DailyCheckInChoice(id: $0, label: dailyChoiceLabel($0)) }
    }

    private var sleepImpactChoices: [DailyCheckInChoice] {
        let suggested = (prompt?.suggestedSleepImpacts ?? []).filter { validSleepImpactChoiceIds.contains($0) }
        let base = suggested.isEmpty ? ["yes_strongly", "yes_somewhat", "not_much", "unsure"] : suggested
        return base.map { DailyCheckInChoice(id: $0, label: dailyChoiceLabel($0)) }
    }

    private var showsPainFollowUp: Bool {
        painLevel == "noticeable" || painLevel == "strong"
    }

    private var showsEnergyFollowUp: Bool {
        energyLevel == "low" || energyLevel == "depleted"
    }

    private var showsMoodFollowUp: Bool {
        moodLevel == "noticeable" || moodLevel == "strong"
    }

    private var showsSleepFollowUp: Bool {
        (prompt?.sleepLoggedRecently == true) || !(prompt?.suggestedSleepImpacts ?? []).isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerCard

                DailyCheckInChoiceGrid(
                    title: "Did today feel:",
                    subtitle: nil,
                    selection: $comparedToYesterday,
                    choices: comparisonChoices
                )

                DailyCheckInChoiceGrid(
                    title: "How was your energy?",
                    subtitle: energySubtitle,
                    selection: $energyLevel,
                    choices: energyChoices
                )

                DailyCheckInChoiceGrid(
                    title: "How much usable energy did you have today?",
                    subtitle: usableEnergySubtitle,
                    selection: $usableEnergy,
                    choices: usableEnergyChoices
                )

                DailyCheckInChoiceGrid(
                    title: "How demanding did today feel on your system?",
                    subtitle: nil,
                    selection: $systemLoad,
                    choices: systemLoadChoices
                )

                DailyCheckInMultiChoiceGrid(
                    title: "Anything likely affected today?",
                    subtitle: "Optional, but useful when gauges may be reading a confounder like overexertion or allergen load.",
                    selection: $exposures,
                    choices: exposureChoices
                )

                DailyCheckInChoiceGrid(
                    title: "Did pain stand out today?",
                    subtitle: nil,
                    selection: $painLevel,
                    choices: painChoices
                )

                DailyCheckInChoiceGrid(
                    title: "Did mood stand out today?",
                    subtitle: nil,
                    selection: $moodLevel,
                    choices: moodChoices
                )

                if showsPainFollowUp {
                    DailyCheckInChoiceGrid(
                        title: "What pain stood out most?",
                        subtitle: "Pick the closest fit.",
                        selection: $painType,
                        choices: painTypeChoices
                    )
                }

                if showsEnergyFollowUp {
                    DailyCheckInChoiceGrid(
                        title: "What best describes the energy dip?",
                        subtitle: nil,
                        selection: $energyDetail,
                        choices: energyDetailChoices
                    )
                }

                if showsMoodFollowUp {
                    DailyCheckInChoiceGrid(
                        title: "What best fits?",
                        subtitle: nil,
                        selection: $moodType,
                        choices: moodTypeChoices
                    )
                }

                if showsSleepFollowUp {
                    DailyCheckInChoiceGrid(
                        title: "Did sleep affect today?",
                        subtitle: nil,
                        selection: $sleepImpact,
                        choices: sleepImpactChoices
                    )
                }

                DailyCheckInChoiceGrid(
                    title: "Did Gaia’s read on today feel right?",
                    subtitle: predictionSubtitle,
                    selection: $predictionMatch,
                    choices: predictionChoices
                )

                noteCard
                actionCard
            }
            .padding(16)
        }
        .background(
            LinearGradient(
                colors: [Color.black, Color(red: 0.05, green: 0.07, blue: 0.12)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
        )
        .navigationTitle("Daily Check-In")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .task {
            AppAnalytics.track("daily_checkin_started")
            await loadStatus()
        }
        .refreshable {
            await loadStatus()
        }
        .alert(
            "Daily Check-In",
            isPresented: Binding(
                get: { alertMessage != nil },
                set: { newValue in
                    if !newValue {
                        alertMessage = nil
                    }
                }
            )
        ) {
            Button("OK", role: .cancel) { }
        } message: {
            Text(alertMessage ?? "")
        }
    }

    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(questionText)
                .font(.title3.weight(.bold))
                .foregroundColor(.white)

            if !activeLabels.isEmpty {
                Text("Logged today: \(activeLabels.prefix(3).joined(separator: ", "))")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.68))
            }

            if let latestEntry, isCompletedForTargetDay {
                Text("You already checked in for \(latestEntry.day). Update it if your read changed.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.68))
            } else if let reminder = status?.settings.reminderTime, !reminder.isEmpty {
                Text("Reminder: \(reminder)")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.58))
            }

            if let statusMessage, !statusMessage.isEmpty {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.78))
            }

            if let summary = status?.calibrationSummary, summary.totalCheckins > 0 {
                Text("Recent Gaia match rate: \(Int((summary.matchRate ?? 0) * 100))% across \(summary.totalCheckins) check-ins.")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.48))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    private var noteCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Optional note")
                .font(.headline)
                .foregroundColor(.white)

            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.white.opacity(0.05))

                if noteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Anything brief to note?")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.35))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                }

                TextEditor(text: $noteText)
                    .scrollContentBackground(.hidden)
                    .foregroundColor(.white)
                    .frame(minHeight: 90)
                    .padding(6)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private var actionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                Task { await submit() }
            } label: {
                HStack {
                    if isSaving {
                        ProgressView().scaleEffect(0.8)
                    }
                    Text(isCompletedForTargetDay ? "Update check-in" : "Save check-in")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!canSubmit || isSaving || isLoading)

            if let prompt, prompt.status != "answered" {
                HStack(spacing: 10) {
                    Button("Later tonight") {
                        Task { await dismissPrompt(action: "snooze", snoozeHours: 12) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(isSaving || isLoading)

                    Button("Skip for now") {
                        Task { await dismissPrompt(action: "dismiss", snoozeHours: nil) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(isSaving || isLoading)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func loadStatus() async {
        await MainActor.run {
            isLoading = true
            statusMessage = nil
        }
        do {
            let envelope = try await api.fetchDailyCheckInStatus()
            if envelope.ok == false, envelope.data == nil {
                throw NSError(domain: "DailyCheckIn", code: 1, userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Daily check-in unavailable"])
            }
            let nextStatus = envelope.payload ?? DailyCheckInStatus(
                prompt: nil,
                latestEntry: nil,
                targetDay: nil,
                calibrationSummary: FeedbackCalibrationSummary(
                    windowDays: 21,
                    totalCheckins: 0,
                    mostlyRight: 0,
                    partlyRight: 0,
                    notReally: 0,
                    matchRate: nil,
                    resolvedCount: 0,
                    improvingCount: 0,
                    worseCount: 0
                ),
                settings: DailyCheckInSettings(
                    enabled: false,
                    pushEnabled: false,
                    cadence: "balanced",
                    reminderTime: "20:00"
                )
            )

            await MainActor.run {
                status = nextStatus
                if !didSeedForm {
                    seedForm(from: nextStatus)
                    didSeedForm = true
                }
                isLoading = false
                onStatusChanged(nextStatus)
            }
        } catch {
            await MainActor.run {
                isLoading = false
                statusMessage = error.localizedDescription
            }
        }
    }

    private func seedForm(from status: DailyCheckInStatus) {
        guard
            let entry = status.latestEntry,
            entry.day == (status.targetDay ?? prompt?.day ?? entry.day)
        else { return }
        comparedToYesterday = entry.comparedToYesterday
        energyLevel = entry.energyLevel
        usableEnergy = entry.usableEnergy
        systemLoad = entry.systemLoad
        painLevel = entry.painLevel
        painType = entry.painType ?? ""
        energyDetail = entry.energyDetail ?? ""
        moodLevel = entry.moodLevel
        moodType = entry.moodType ?? ""
        sleepImpact = validSleepImpactChoiceIds.contains(entry.sleepImpact ?? "") ? (entry.sleepImpact ?? "") : ""
        predictionMatch = entry.predictionMatch ?? ""
        noteText = entry.noteText ?? ""
        exposures = Set(entry.exposures)
    }

    private func mergedStatus(with entry: DailyCheckInEntry) -> DailyCheckInStatus {
        DailyCheckInStatus(
            prompt: nil,
            latestEntry: entry,
            targetDay: entry.day,
            calibrationSummary: fallbackCalibrationSummary,
            settings: fallbackSettings
        )
    }

    private func submit() async {
        guard canSubmit else { return }
        await MainActor.run {
            isSaving = true
            statusMessage = nil
        }
        do {
            let envelope = try await api.submitDailyCheckIn(
                promptId: prompt?.id,
                day: targetDay,
                comparedToYesterday: comparedToYesterday,
                energyLevel: energyLevel,
                usableEnergy: usableEnergy,
                systemLoad: systemLoad,
                painLevel: painLevel,
                painType: painType.nilIfBlank,
                energyDetail: energyDetail.nilIfBlank,
                moodLevel: moodLevel,
                moodType: moodType.nilIfBlank,
                sleepImpact: sleepImpact.nilIfBlank,
                predictionMatch: predictionMatch.nilIfBlank,
                noteText: noteText.nilIfBlank,
                exposures: Array(exposures).sorted(),
                completedAt: Date()
            )
            if envelope.ok == false {
                throw NSError(domain: "DailyCheckIn", code: 2, userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Could not save daily check-in"])
            }
            let savedEntry = envelope.payload ?? DailyCheckInEntry(
                day: targetDay,
                promptId: prompt?.id,
                comparedToYesterday: comparedToYesterday,
                energyLevel: energyLevel,
                usableEnergy: usableEnergy,
                systemLoad: systemLoad,
                painLevel: painLevel,
                painType: painType.nilIfBlank,
                energyDetail: energyDetail.nilIfBlank,
                moodLevel: moodLevel,
                moodType: moodType.nilIfBlank,
                sleepImpact: sleepImpact.nilIfBlank,
                predictionMatch: predictionMatch.nilIfBlank,
                noteText: noteText.nilIfBlank,
                completedAt: ISO8601DateFormatter().string(from: Date()),
                exposures: Array(exposures).sorted()
            )
            let nextStatus = mergedStatus(with: savedEntry)
            AppAnalytics.track(
                "daily_checkin_completed",
                properties: [
                    "prediction_match": predictionMatch.nilIfBlank ?? "none",
                    "pain_type": painType.nilIfBlank ?? "none",
                    "energy_level": energyLevel,
                    "system_load": systemLoad,
                ]
            )
            await MainActor.run {
                status = nextStatus
                onStatusChanged(nextStatus)
                statusMessage = "Check-in saved."
                isSaving = false
            }
            if showsCloseButton {
                await MainActor.run {
                    dismiss()
                }
            }
        } catch {
            await MainActor.run {
                isSaving = false
                statusMessage = error.localizedDescription
                alertMessage = error.localizedDescription
            }
        }
    }

    private func dismissPrompt(action: String, snoozeHours: Int?) async {
        guard let promptId = prompt?.id else { return }
        await MainActor.run {
            isSaving = true
            statusMessage = nil
        }
        do {
            let envelope = try await api.dismissDailyCheckIn(promptId: promptId, action: action, snoozeHours: snoozeHours)
            if envelope.ok == false {
                throw NSError(domain: "DailyCheckIn", code: 3, userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Could not update the reminder"])
            }
            AppAnalytics.track("daily_checkin_skipped", properties: ["action": action])
            await MainActor.run {
                isSaving = false
                statusMessage = action == "dismiss" ? "Check-in skipped for now." : "Reminder moved later."
            }
            await loadStatus()
        } catch {
            await MainActor.run {
                isSaving = false
                statusMessage = error.localizedDescription
                alertMessage = error.localizedDescription
            }
        }
    }

    private func dailyChoiceLabel(_ value: String) -> String {
        value
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
            .replacingOccurrences(of: "Yes Strongly", with: "Yes, strongly")
            .replacingOccurrences(of: "Yes Somewhat", with: "Yes, somewhat")
            .replacingOccurrences(of: "Not Much", with: "Not much")
            .replacingOccurrences(of: "A Little", with: "A little")
    }
}
