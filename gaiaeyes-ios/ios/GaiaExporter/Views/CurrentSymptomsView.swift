import SwiftUI

private struct CurrentSymptomsCopy {
    let pageTitle: String
    let subtitle: String
    let activeNowTitle: String
    let logSymptomTitle: String
    let logSymptomsTitle: String
    let timelineTitle: String
    let contributingTitle: String
    let contributingEmptyBody: String
    let patternTitle: String
    let patternEmptyBody: String
    let notesTitle: String
    let notesEmptyBody: String
    let notesPlaceholder: String
    let emptyTitle: String
    let emptyBody: String
    let followUpTitle: String
    let followUpSyncingBody: String
    let viewAllDriversTitle: String
    let openAllDriversTitle: String
    let editDetailsTitle: String

    static func resolve(mode: ExperienceMode, tone: ToneStyle) -> CurrentSymptomsCopy {
        let vocabulary = mode.copyVocabulary
        switch mode {
        case .scientific:
            return CurrentSymptomsCopy(
                pageTitle: vocabulary.currentSymptomsLabel,
                subtitle: "Recent logs and current conditions, in one place",
                activeNowTitle: "Active Now",
                logSymptomTitle: "Log symptom",
                logSymptomsTitle: "Log symptoms",
                timelineTitle: "Timeline",
                contributingTitle: "Signals around this right now",
                contributingEmptyBody: "No nearby signals yet. When something is active, context will show up here.",
                patternTitle: "What has appeared with this before",
                patternEmptyBody: "No pattern yet. Keep logging to help this section fill in.",
                notesTitle: "Notes / Journal",
                notesEmptyBody: "No active symptoms to update right now.",
                notesPlaceholder: "More noticeable this afternoon, easier after resting, stronger after being outside…",
                emptyTitle: "No symptoms active right now",
                emptyBody: tone.resolveCopy(
                    balanced: "No symptoms are active right now. Log anything new here.",
                    humorous: "Nothing is waving a flag right now. Log anything new here."
                ),
                followUpTitle: "Follow-up check-ins",
                followUpSyncingBody: "Follow-up settings are still loading.",
                viewAllDriversTitle: "View \(vocabulary.allDriversLabel)",
                openAllDriversTitle: "Open \(vocabulary.allDriversLabel)",
                editDetailsTitle: "Edit symptom details"
            )
        case .mystical:
            return CurrentSymptomsCopy(
                pageTitle: vocabulary.currentSymptomsLabel,
                subtitle: "Recent logs and current conditions, in one place",
                activeNowTitle: "Active Right Now",
                logSymptomTitle: "Log symptom",
                logSymptomsTitle: "Log symptoms",
                timelineTitle: "Timeline",
                contributingTitle: "What may be shaping this",
                contributingEmptyBody: "No nearby signals yet. When something is active, context will show up here.",
                patternTitle: "What has echoed with this before",
                patternEmptyBody: "No pattern yet. Keep logging to help this section fill in.",
                notesTitle: "Notes / Reflections",
                notesEmptyBody: "No active symptoms to update right now.",
                notesPlaceholder: "More noticeable this afternoon, easier after resting, stronger after being outside…",
                emptyTitle: "No symptoms active right now",
                emptyBody: tone.resolveCopy(
                    balanced: "Your system looks calmer right now. If something shifts, log it here.",
                    humorous: "Your system looks calmer right now. If the plot thickens, log it here."
                ),
                followUpTitle: "Check-in reminders",
                followUpSyncingBody: "Check-in settings are still loading.",
                viewAllDriversTitle: "View \(vocabulary.allDriversLabel)",
                openAllDriversTitle: "Open \(vocabulary.allDriversLabel)",
                editDetailsTitle: "Edit symptom details"
            )
        }
    }
}

private extension String {
    var nilIfBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

private struct SymptomFollowUpComposerState: Identifiable {
    let item: CurrentSymptomItem
    let prompt: CurrentSymptomFollowUpPrompt
    let responseState: CurrentSymptomState

    var id: String {
        "\(prompt.id):\(responseState.rawValue)"
    }
}

private func isCurrentSymptomsCancellation(_ error: Error) -> Bool {
    if error is CancellationError {
        return true
    }
    let nsError = error as NSError
    return nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled
}

struct CurrentSymptomsView: View {
    let api: APIClient
    var mode: ExperienceMode = .scientific
    var tone: ToneStyle = .balanced
    var showsCloseButton: Bool = false
    let initialSnapshot: CurrentSymptomsSnapshot?
    let onLogMore: () -> Void
    let onOpenAllDrivers: ((String?) -> Void)?
    let onSnapshotChanged: (CurrentSymptomsSnapshot) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: CurrentSymptomsSnapshot?
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?
    @State private var selectedEpisodeId: String?
    @State private var noteDraft: String = ""
    @State private var severityDraft: Int = 5
    @State private var updatingEpisodeId: String?
    @State private var journalStatus: String?
    @State private var editingItem: CurrentSymptomItem?
    @State private var followUpComposer: SymptomFollowUpComposerState?
    @State private var showsAllPatternContext: Bool = false

    init(
        api: APIClient,
        mode: ExperienceMode = .scientific,
        tone: ToneStyle = .balanced,
        showsCloseButton: Bool = false,
        initialSnapshot: CurrentSymptomsSnapshot? = nil,
        onLogMore: @escaping () -> Void,
        onOpenAllDrivers: ((String?) -> Void)? = nil,
        onSnapshotChanged: @escaping (CurrentSymptomsSnapshot) -> Void
    ) {
        self.api = api
        self.mode = mode
        self.tone = tone
        self.showsCloseButton = showsCloseButton
        self.initialSnapshot = initialSnapshot
        self.onLogMore = onLogMore
        self.onOpenAllDrivers = onOpenAllDrivers
        self.onSnapshotChanged = onSnapshotChanged

        let firstItem = initialSnapshot?.items.first
        _snapshot = State(initialValue: initialSnapshot)
        _selectedEpisodeId = State(initialValue: firstItem?.id)
        _noteDraft = State(initialValue: firstItem?.notePreview ?? "")
        _severityDraft = State(initialValue: firstItem?.severity ?? firstItem?.originalSeverity ?? 5)
    }

    private var vocabulary: CopyVocabulary {
        mode.copyVocabulary
    }

    private var copy: CurrentSymptomsCopy {
        CurrentSymptomsCopy.resolve(mode: mode, tone: tone)
    }

    private var semantic: CurrentSymptomsVoiceSemantic? {
        snapshot?.voiceSemantic
    }

    private func semanticText(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return translatedText(trimmed) ?? trimmed
    }

    private var headerSummaryText: String? {
        semanticText(semantic?.interpretation?.headerSummary)
    }

    private var activeSummaryText: String? {
        semanticText(semantic?.interpretation?.activeSummary)
    }

    private var emptyStateBodyText: String? {
        semanticText(semantic?.interpretation?.emptyState)
    }

    private var contributingEmptyBodyText: String? {
        semanticText(semantic?.interpretation?.contributingEmpty)
    }

    private var patternEmptyBodyText: String? {
        semanticText(semantic?.interpretation?.patternEmpty)
    }

    private var followUpSummaryText: String? {
        semanticText(semantic?.interpretation?.followUpSummary)
    }

    private func translatedDriverLabel(for driver: CurrentSymptomDriver) -> String {
        vocabulary.driverLabel(for: driver.key, fallback: driver.label)
    }

    private func translatedText(_ raw: String?) -> String? {
        vocabulary.presenting(raw)
    }

    private var activeItems: [CurrentSymptomItem] {
        snapshot?.items ?? []
    }

    private var visiblePatternContext: [CurrentSymptomPatternHint] {
        let allPatterns = snapshot?.patternContext ?? []
        if showsAllPatternContext {
            return allPatterns
        }
        return Array(allPatterns.prefix(3))
    }

    private var selectedItem: CurrentSymptomItem? {
        if let selectedEpisodeId {
            return activeItems.first(where: { $0.id == selectedEpisodeId }) ?? activeItems.first
        }
        return activeItems.first
    }

    private var headerRefreshText: String? {
        guard let raw = snapshot?.generatedAt,
              let date = ISO8601DateFormatter().date(from: raw) else { return nil }
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter.string(from: date)
    }

    private var shouldRefreshOnAppear: Bool {
        guard let raw = snapshot?.generatedAt,
              let date = ISO8601DateFormatter().date(from: raw) else { return true }
        return Date().timeIntervalSince(date) > 90
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerCard
                activeNowCard
                contributingCard
                patternCard
                journalCard
                followUpCard
            }
            .padding(16)
        }
        .background(backgroundGradient.ignoresSafeArea())
        .navigationTitle(copy.pageTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .task {
            appLog("[CurrentSymptoms] page_open")
            if shouldRefreshOnAppear {
                await loadSnapshot()
            }
        }
        .refreshable {
            await loadSnapshot()
        }
        .sheet(item: $editingItem) { item in
            CurrentSymptomEditorSheet(
                item: item,
                isBusy: updatingEpisodeId == item.id,
                onSave: { severity, noteText in
                    await saveEditorChanges(for: item, severity: severity, noteText: noteText)
                },
                onDelete: {
                    await deleteSymptom(item)
                }
            )
        }
        .sheet(item: $followUpComposer) { composer in
            CurrentSymptomFollowUpSheet(
                item: composer.item,
                prompt: composer.prompt,
                responseState: composer.responseState,
                isBusy: updatingEpisodeId == composer.item.id,
                onSubmit: { detailChoice, noteText, timeBucket in
                    await submitFollowUpResponse(
                        prompt: composer.prompt,
                        item: composer.item,
                        state: composer.responseState,
                        detailChoice: detailChoice,
                        noteText: noteText,
                        timeBucket: timeBucket
                    )
                }
            )
        }
    }

    private var backgroundGradient: some View {
        LinearGradient(
            colors: [
                Color(red: 0.03, green: 0.04, blue: 0.08),
                Color(red: 0.06, green: 0.08, blue: 0.14),
                Color.black
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private func loadSnapshot() async {
        await MainActor.run {
            isLoading = true
            errorMessage = nil
        }
        do {
            let envelope = try await api.fetchCurrentSymptoms()
            if envelope.ok == false, envelope.data == nil {
                throw NSError(domain: "CurrentSymptoms", code: 1, userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Current symptoms unavailable"])
            }
            let payload = envelope.payload ?? CurrentSymptomsSnapshot(
                generatedAt: "",
                windowHours: 12,
                summary: CurrentSymptomsSummary(activeCount: 0, newCount: 0, ongoingCount: 0, improvingCount: 0, worseCount: 0, lastUpdatedAt: nil, followUpAvailable: false),
                items: [],
                contributingDrivers: [],
                patternContext: [],
                followUpSettings: CurrentSymptomsFollowUpSettings(notificationsEnabled: false, enabled: false, notificationFamilyEnabled: false, pushEnabled: false, cadence: "balanced", states: ["new", "ongoing", "improving", "worse"], symptomCodes: []),
                voiceSemantic: nil
            )
            await MainActor.run {
                snapshot = payload
                syncSelection(with: payload)
                onSnapshotChanged(payload)
                isLoading = false
            }
            appLog("[CurrentSymptoms] snapshot ok active=\(payload.summary.activeCount)")
        } catch {
            if isCurrentSymptomsCancellation(error) {
                await MainActor.run {
                    isLoading = false
                }
                return
            }
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoading = false
            }
            appLog("[CurrentSymptoms] snapshot error: \(error.localizedDescription)")
        }
    }

    private func syncSelection(with payload: CurrentSymptomsSnapshot) {
        if let selectedEpisodeId,
           let current = payload.items.first(where: { $0.id == selectedEpisodeId }) {
            noteDraft = current.notePreview ?? noteDraft
            severityDraft = current.severity ?? current.originalSeverity ?? severityDraft
            return
        }
        guard let first = payload.items.first else {
            selectedEpisodeId = nil
            noteDraft = ""
            severityDraft = 5
            return
        }
        selectedEpisodeId = first.id
        noteDraft = first.notePreview ?? ""
        severityDraft = first.severity ?? first.originalSeverity ?? 5
    }

    private func updateState(_ item: CurrentSymptomItem, to state: CurrentSymptomState) {
        guard updatingEpisodeId == nil else { return }
        updatingEpisodeId = item.id
        journalStatus = nil
        appLog("[CurrentSymptoms] state_change episode=\(item.id) state=\(state.rawValue)")
        Task {
            defer {
                Task { @MainActor in updatingEpisodeId = nil }
            }
            do {
                let response = try await api.updateCurrentSymptom(episodeId: item.id, state: state)
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 2, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not update symptom"])
                }
                await MainActor.run {
                    journalStatus = state == .resolved ? "\(item.label) marked resolved." : "\(item.label) updated."
                }
                await loadSnapshot()
            } catch {
                await MainActor.run {
                    journalStatus = error.localizedDescription
                }
                appLog("[CurrentSymptoms] state_change error: \(error.localizedDescription)")
            }
        }
    }

    private func handlePrimaryStateAction(_ item: CurrentSymptomItem, state: CurrentSymptomState) {
        if let prompt = item.pendingFollowUp {
            startFollowUpResponse(for: item, prompt: prompt, state: state)
            return
        }
        updateState(item, to: state)
    }

    private func startFollowUpResponse(for item: CurrentSymptomItem, prompt: CurrentSymptomFollowUpPrompt, state: CurrentSymptomState) {
        guard updatingEpisodeId == nil else { return }
        selectedEpisodeId = item.id
        if state == .improving {
            Task {
                _ = await submitFollowUpResponse(prompt: prompt, item: item, state: state, detailChoice: nil, noteText: nil, timeBucket: nil)
            }
            return
        }
        followUpComposer = SymptomFollowUpComposerState(item: item, prompt: prompt, responseState: state)
    }

    private func followUpSnoozeHours() -> Int {
        switch snapshot?.followUpSettings.cadence {
        case "minimal":
            return 18
        case "detailed":
            return 6
        default:
            return 12
        }
    }

    private func snoozeFollowUp(_ prompt: CurrentSymptomFollowUpPrompt, for item: CurrentSymptomItem) {
        guard updatingEpisodeId == nil else { return }
        updatingEpisodeId = item.id
        journalStatus = nil
        Task {
            defer {
                Task { @MainActor in updatingEpisodeId = nil }
            }
            do {
                let response = try await api.dismissSymptomFollowUp(
                    promptId: prompt.id,
                    action: "snooze",
                    snoozeHours: followUpSnoozeHours()
                )
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 6, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not move the follow-up"])
                }
                AppAnalytics.track("symptom_followup_dismissed", properties: ["action": "snooze", "symptom_code": item.symptomCode])
                await MainActor.run {
                    journalStatus = "Follow-up moved later."
                }
                await loadSnapshot()
            } catch {
                await MainActor.run {
                    journalStatus = error.localizedDescription
                }
            }
        }
    }

    private func dismissFollowUp(_ prompt: CurrentSymptomFollowUpPrompt, for item: CurrentSymptomItem) {
        guard updatingEpisodeId == nil else { return }
        updatingEpisodeId = item.id
        journalStatus = nil
        Task {
            defer {
                Task { @MainActor in updatingEpisodeId = nil }
            }
            do {
                let response = try await api.dismissSymptomFollowUp(promptId: prompt.id, action: "dismiss", snoozeHours: nil)
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 7, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not dismiss the follow-up"])
                }
                AppAnalytics.track("symptom_followup_dismissed", properties: ["action": "dismiss", "symptom_code": item.symptomCode])
                await MainActor.run {
                    journalStatus = "Follow-up dismissed."
                }
                await loadSnapshot()
            } catch {
                await MainActor.run {
                    journalStatus = error.localizedDescription
                }
            }
        }
    }

    private func submitFollowUpResponse(
        prompt: CurrentSymptomFollowUpPrompt,
        item: CurrentSymptomItem,
        state: CurrentSymptomState,
        detailChoice: String?,
        noteText: String?,
        timeBucket: String?
    ) async -> Bool {
        guard updatingEpisodeId == nil else { return false }
        await MainActor.run {
            updatingEpisodeId = item.id
            journalStatus = nil
        }
        defer {
            Task { @MainActor in updatingEpisodeId = nil }
        }
        do {
            let response = try await api.respondSymptomFollowUp(
                promptId: prompt.id,
                state: state,
                detailChoice: detailChoice,
                noteText: noteText,
                timeBucket: timeBucket,
                tsUtc: Date()
            )
            if response.ok == false {
                throw NSError(domain: "CurrentSymptoms", code: 8, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not save the follow-up"])
            }
            AppAnalytics.track(
                "symptom_followup_answered",
                properties: [
                    "state": state.rawValue,
                    "symptom_code": item.symptomCode,
                    "detail_choice": detailChoice ?? "none",
                ]
            )
            await MainActor.run {
                followUpComposer = nil
                journalStatus = state == .resolved ? "\(item.label) marked resolved." : "\(item.label) updated from follow-up."
            }
            await loadSnapshot()
            return true
        } catch {
            await MainActor.run {
                journalStatus = error.localizedDescription
            }
            return false
        }
    }

    private func openEditor(for item: CurrentSymptomItem) {
        selectedEpisodeId = item.id
        noteDraft = item.notePreview ?? ""
        severityDraft = item.severity ?? item.originalSeverity ?? 5
        editingItem = item
    }

    private func saveJournalEntry() {
        guard let selectedItem else { return }
        guard updatingEpisodeId == nil else { return }
        updatingEpisodeId = selectedItem.id
        journalStatus = nil
        appLog("[CurrentSymptoms] note_save episode=\(selectedItem.id)")
        Task {
            defer {
                Task { @MainActor in updatingEpisodeId = nil }
            }
            do {
                let response = try await api.updateCurrentSymptom(
                    episodeId: selectedItem.id,
                    severity: severityDraft,
                    noteText: noteDraft.nilIfBlank
                )
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 3, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not save note"])
                }
                await MainActor.run {
                    journalStatus = noteDraft.nilIfBlank == nil ? "Severity updated." : "Note saved."
                }
                await loadSnapshot()
            } catch {
                await MainActor.run {
                    journalStatus = error.localizedDescription
                }
                appLog("[CurrentSymptoms] note_save error: \(error.localizedDescription)")
            }
        }
    }

    private func saveEditorChanges(for item: CurrentSymptomItem, severity: Int, noteText: String?) async -> Bool {
        guard updatingEpisodeId == nil else { return false }
        await MainActor.run {
            updatingEpisodeId = item.id
            journalStatus = nil
        }
        appLog("[CurrentSymptoms] editor_save episode=\(item.id)")
        defer {
            Task { @MainActor in updatingEpisodeId = nil }
        }
        do {
            let response = try await api.updateCurrentSymptom(
                episodeId: item.id,
                severity: severity,
                noteText: noteText
            )
            if response.ok == false {
                throw NSError(domain: "CurrentSymptoms", code: 4, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not save symptom changes"])
            }
            await MainActor.run {
                journalStatus = noteText == nil ? "\(item.label) severity updated." : "\(item.label) updated."
                editingItem = nil
            }
            await loadSnapshot()
            return true
        } catch {
            await MainActor.run {
                journalStatus = error.localizedDescription
            }
            appLog("[CurrentSymptoms] editor_save error: \(error.localizedDescription)")
            return false
        }
    }

    private func deleteSymptom(_ item: CurrentSymptomItem) async -> Bool {
        guard updatingEpisodeId == nil else { return false }
        await MainActor.run {
            updatingEpisodeId = item.id
            journalStatus = nil
        }
        appLog("[CurrentSymptoms] delete episode=\(item.id)")
        defer {
            Task { @MainActor in updatingEpisodeId = nil }
        }
        do {
            let response = try await api.deleteCurrentSymptom(episodeId: item.id)
            if response.ok == false {
                throw NSError(domain: "CurrentSymptoms", code: 5, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not delete symptom"])
            }
            await MainActor.run {
                journalStatus = "\(item.label) removed."
                editingItem = nil
            }
            await loadSnapshot()
            return true
        } catch {
            await MainActor.run {
                journalStatus = error.localizedDescription
            }
            appLog("[CurrentSymptoms] delete error: \(error.localizedDescription)")
            return false
        }
    }

    private var headerCard: some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(copy.pageTitle)
                            .font(.title2.weight(.bold))
                            .foregroundColor(.white)
                        Text(copy.subtitle)
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.7))
                            .fixedSize(horizontal: false, vertical: true)
                        if let headerSummaryText {
                            Text(headerSummaryText)
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.72))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer()
                    if isLoading {
                        ProgressView()
                            .tint(.white.opacity(0.85))
                    }
                }

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.orange)
                } else if let headerRefreshText {
                    Text("Updated \(headerRefreshText)")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.55))
                }

                HStack(spacing: 10) {
                    Button(action: onLogMore) {
                        Label(copy.logSymptomTitle, systemImage: "plus.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    NavigationLink {
                        CurrentSymptomsTimelineView(api: api)
                    } label: {
                        Label(copy.timelineTitle, systemImage: "clock.arrow.circlepath")
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    private var activeNowCard: some View {
        card {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text(copy.activeNowTitle)
                        .font(.headline)
                        .foregroundColor(.white)
                    Spacer()
                    if let summary = snapshot?.summary {
                        Text("\(summary.activeCount)")
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }

                if activeItems.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(copy.emptyTitle)
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                        Text(emptyStateBodyText ?? copy.emptyBody)
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.7))
                        Button(copy.logSymptomsTitle) {
                            onLogMore()
                        }
                        .buttonStyle(.bordered)
                    }
                } else {
                    if let activeSummaryText {
                        Text(activeSummaryText)
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.7))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ForEach(activeItems) { item in
                        symptomCard(item)
                    }
                }
            }
        }
    }

    private func symptomCard(_ item: CurrentSymptomItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.label)
                        .font(.headline)
                        .foregroundColor(.white)
                    Text("\(severityLabel(for: item)) • \(timestampLine(for: item))")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.65))
                }
                Spacer()
                statePill(item.currentState)
            }

            if let notePreview = item.notePreview, !notePreview.isEmpty {
                Text(notePreview)
                    .font(.footnote)
                    .foregroundColor(.white.opacity(0.72))
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 8) {
                if item.noteCount > 0 {
                    indicatorChip("Notes \(item.noteCount)", tint: Color(red: 0.35, green: 0.58, blue: 0.92))
                }
                if !item.likelyDrivers.isEmpty {
                    indicatorChip("\(item.likelyDrivers.count) drivers", tint: Color(red: 0.87, green: 0.63, blue: 0.27))
                }
                if let badge = item.currentContextBadge, !badge.isEmpty {
                    indicatorChip(badge, tint: Color(red: 0.43, green: 0.76, blue: 0.63))
                }
            }

            if let prompt = item.pendingFollowUp {
                followUpPromptCard(prompt, for: item)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                actionButton(title: "Still active", state: .ongoing, item: item)
                actionButton(title: "Improving", state: .improving, item: item)
                actionButton(title: "Worse", state: .worse, item: item)
                actionButton(title: "Resolved", state: .resolved, item: item)
            }

            Button {
                openEditor(for: item)
            } label: {
                Text(copy.editDetailsTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.white.opacity(0.78))
            }
            .buttonStyle(.plain)
        }
        .padding(14)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }

    private func followUpPromptCard(_ prompt: CurrentSymptomFollowUpPrompt, for item: CurrentSymptomItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(prompt.questionText)
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.white)

            HStack(spacing: 10) {
                Button("Later") {
                    snoozeFollowUp(prompt, for: item)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button("Dismiss") {
                    dismissFollowUp(prompt, for: item)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(red: 0.11, green: 0.16, blue: 0.24))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private func actionButton(title: String, state: CurrentSymptomState, item: CurrentSymptomItem) -> some View {
        let isSelected = item.currentState == state
        return Button(title) {
            handlePrimaryStateAction(item, state: state)
        }
        .buttonStyle(.plain)
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(
            Capsule()
                .fill(isSelected ? stateColor(state).opacity(0.26) : Color.white.opacity(0.05))
        )
        .overlay(
            Capsule()
                .stroke(isSelected ? stateColor(state).opacity(0.95) : Color.white.opacity(0.08), lineWidth: 1)
        )
        .foregroundColor(.white)
        .opacity(updatingEpisodeId == item.id ? 0.6 : 1)
        .disabled(updatingEpisodeId == item.id)
    }

    private var contributingCard: some View {
        card {
            VStack(alignment: .leading, spacing: 12) {
                Text(copy.contributingTitle)
                    .font(.headline)
                    .foregroundColor(.white)

                if let drivers = snapshot?.contributingDrivers, !drivers.isEmpty {
                    ForEach(drivers.prefix(4)) { driver in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(translatedDriverLabel(for: driver))
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundColor(.white)
                                Spacer()
                                if let state = driver.state ?? driver.severity {
                                    Text(state.capitalized)
                                        .font(.caption2.weight(.semibold))
                                        .foregroundColor(.white.opacity(0.72))
                                }
                            }
                            if let relation = driver.relation, !relation.isEmpty {
                                Text(translatedText(relation) ?? relation)
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.7))
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            if !driver.relatedSymptoms.isEmpty {
                                Text(driver.relatedSymptoms.joined(separator: " • "))
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.54))
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    if let onOpenAllDrivers {
                        Button(copy.viewAllDriversTitle) {
                            onOpenAllDrivers(snapshot?.contributingDrivers.first?.key)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                } else {
                    Text(contributingEmptyBodyText ?? copy.contributingEmptyBody)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                    if let onOpenAllDrivers {
                        Button(copy.openAllDriversTitle) {
                            onOpenAllDrivers(nil)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
            }
        }
    }

    private var patternCard: some View {
        card {
            VStack(alignment: .leading, spacing: 12) {
                Text(copy.patternTitle)
                    .font(.headline)
                    .foregroundColor(.white)

                if let patternContext = snapshot?.patternContext, !patternContext.isEmpty {
                    ForEach(visiblePatternContext) { pattern in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(
                                translatedText(pattern.text)
                                ?? "In your history, \(vocabulary.driverLabel(for: pattern.signalKey, fallback: pattern.signal)) has appeared alongside \(pattern.outcome.lowercased())."
                            )
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(.white)
                                .fixedSize(horizontal: false, vertical: true)
                            if let confidence = pattern.confidence, !confidence.isEmpty {
                                Text(confidence)
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.56))
                            }
                        }
                    }

                    if patternContext.count > 3 {
                        Button(showsAllPatternContext ? "Show fewer pattern hints" : "Show all pattern hints") {
                            showsAllPatternContext.toggle()
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundColor(Color(red: 0.46, green: 0.7, blue: 1.0))
                        .buttonStyle(.plain)
                    }
                } else {
                    Text(patternEmptyBodyText ?? copy.patternEmptyBody)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                }
            }
        }
    }

    private var journalCard: some View {
        card {
            VStack(alignment: .leading, spacing: 12) {
                Text(copy.notesTitle)
                    .font(.headline)
                    .foregroundColor(.white)

                if activeItems.isEmpty {
                    Text(copy.notesEmptyBody)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                } else {
                    Picker("Symptom", selection: Binding(
                        get: { selectedEpisodeId ?? activeItems.first?.id ?? "" },
                        set: { newValue in
                            selectedEpisodeId = newValue
                            if let item = activeItems.first(where: { $0.id == newValue }) {
                                noteDraft = item.notePreview ?? ""
                                severityDraft = item.severity ?? item.originalSeverity ?? 5
                            }
                        }
                    )) {
                        ForEach(activeItems) { item in
                            Text(item.label).tag(item.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(.white)

                    HStack {
                        Text("Severity")
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                        Spacer()
                        Stepper(value: $severityDraft, in: 0...10) {
                            Text("\(severityDraft)/10")
                                .foregroundColor(.white.opacity(0.8))
                        }
                        .labelsHidden()
                    }

                    ZStack(alignment: .topLeading) {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(Color.white.opacity(0.05))
                        if noteDraft.isEmpty {
                            Text(copy.notesPlaceholder)
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.35))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 12)
                        }
                        TextEditor(text: $noteDraft)
                            .scrollContentBackground(.hidden)
                            .foregroundColor(.white)
                            .frame(minHeight: 108)
                            .padding(6)
                    }

                    HStack(spacing: 10) {
                        Button("Save note") {
                            saveJournalEntry()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(updatingEpisodeId == selectedEpisodeId)

                        if let selectedItem {
                            Text("For \(selectedItem.label)")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.56))
                        }
                    }
                }

                if let journalStatus, !journalStatus.isEmpty {
                    Text(journalStatus)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.72))
                }
            }
        }
    }

    private var followUpCard: some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text(copy.followUpTitle)
                    .font(.headline)
                    .foregroundColor(.white)

                if let settings = snapshot?.followUpSettings {
                    let enabled = settings.enabled || settings.notificationFamilyEnabled
                    Text(followUpSummaryText ?? followUpDescription(for: settings, enabled: enabled))
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))

                    HStack(spacing: 8) {
                        indicatorChip(enabled ? "Enabled" : "Off", tint: enabled ? Color(red: 0.43, green: 0.76, blue: 0.63) : Color.white.opacity(0.4))
                        indicatorChip(settings.cadence.capitalized, tint: Color(red: 0.35, green: 0.58, blue: 0.92))
                    }
                } else {
                    Text(copy.followUpSyncingBody)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                }
            }
        }
    }

    private func severityLabel(for item: CurrentSymptomItem) -> String {
        let severity = item.severity ?? item.originalSeverity
        if let severity {
            return "Severity \(severity)/10"
        }
        return "Severity pending"
    }

    private func timestampLine(for item: CurrentSymptomItem) -> String {
        let source = item.lastInteractionAt ?? item.loggedAt
        guard let date = ISO8601DateFormatter().date(from: source) else { return "Recently updated" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func followUpDescription(for settings: CurrentSymptomsFollowUpSettings, enabled: Bool) -> String {
        if enabled && settings.pushEnabled {
            return "Follow-up reminders are on. You can track whether a symptom is still active, improving, worse, or resolved."
        }
        if enabled && settings.notificationsEnabled {
            return "In-app follow-ups are on. Turn on push if you want reminders outside this view."
        }
        if enabled {
            return "Follow-up check-ins are on here, but push reminders are off."
        }
        return "These optional check-ins help you keep symptom updates current."
    }

    private func stateColor(_ state: CurrentSymptomState) -> Color {
        switch state {
        case .new:
            return Color(red: 0.35, green: 0.58, blue: 0.92)
        case .ongoing:
            return Color(red: 0.87, green: 0.63, blue: 0.27)
        case .improving:
            return Color(red: 0.43, green: 0.76, blue: 0.63)
        case .worse:
            return Color(red: 0.90, green: 0.35, blue: 0.33)
        case .resolved:
            return Color.white.opacity(0.5)
        }
    }

    private func statePill(_ state: CurrentSymptomState) -> some View {
        Text(state.rawValue.capitalized)
            .font(.caption.weight(.semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(stateColor(state).opacity(0.26))
            .overlay(
                Capsule()
                    .stroke(stateColor(state).opacity(0.95), lineWidth: 1)
            )
            .clipShape(Capsule())
    }

    private func indicatorChip(_ title: String, tint: Color) -> some View {
        Text(title)
            .font(.caption2.weight(.semibold))
            .foregroundColor(.white.opacity(0.88))
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(tint.opacity(0.18))
            .overlay(
                Capsule()
                    .stroke(tint.opacity(0.7), lineWidth: 1)
            )
            .clipShape(Capsule())
    }

    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

private struct CurrentSymptomEditorSheet: View {
    let item: CurrentSymptomItem
    let isBusy: Bool
    let onSave: (Int, String?) async -> Bool
    let onDelete: () async -> Bool

    @Environment(\.dismiss) private var dismiss
    @State private var noteDraft: String
    @State private var severityDraft: Int
    @State private var confirmDelete: Bool = false

    init(
        item: CurrentSymptomItem,
        isBusy: Bool,
        onSave: @escaping (Int, String?) async -> Bool,
        onDelete: @escaping () async -> Bool
    ) {
        self.item = item
        self.isBusy = isBusy
        self.onSave = onSave
        self.onDelete = onDelete
        _noteDraft = State(initialValue: item.notePreview ?? "")
        _severityDraft = State(initialValue: item.severity ?? item.originalSeverity ?? 5)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.label)
                            .font(.title3.weight(.bold))
                            .foregroundColor(.white)
                        Text("Update severity, add context, or remove an accidental log.")
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.68))
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Severity")
                            .font(.headline)
                            .foregroundColor(.white)
                        HStack {
                            Text("\(severityDraft)/10")
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(.white.opacity(0.88))
                            Spacer()
                            Stepper(value: $severityDraft, in: 0...10) {
                                EmptyView()
                            }
                            .labelsHidden()
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Note")
                            .font(.headline)
                            .foregroundColor(.white)
                        ZStack(alignment: .topLeading) {
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(Color.white.opacity(0.05))
                            if noteDraft.isEmpty {
                                Text("More noticeable this afternoon, easier after resting, stronger after being outside…")
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.35))
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 12)
                            }
                            TextEditor(text: $noteDraft)
                                .scrollContentBackground(.hidden)
                                .foregroundColor(.white)
                                .frame(minHeight: 120)
                                .padding(6)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))

                    VStack(alignment: .leading, spacing: 10) {
                        Button {
                            Task {
                                let saved = await onSave(severityDraft, noteDraft.nilIfBlank)
                                if saved {
                                    dismiss()
                                }
                            }
                        } label: {
                            HStack {
                                if isBusy {
                                    ProgressView().scaleEffect(0.8)
                                }
                                Text("Save changes")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isBusy)

                        Button(role: .destructive) {
                            confirmDelete = true
                        } label: {
                            Text("Delete symptom")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(isBusy)
                    }
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
            .navigationTitle("Edit Symptom")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .confirmationDialog(
                "Delete \(item.label)?",
                isPresented: $confirmDelete,
                titleVisibility: .visible
            ) {
                Button("Delete symptom", role: .destructive) {
                    Task {
                        let deleted = await onDelete()
                        if deleted {
                            dismiss()
                        }
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Use this for accidental logs. It removes the symptom from the current state and the original source event.")
            }
        }
    }
}

private struct CurrentSymptomFollowUpSheet: View {
    let item: CurrentSymptomItem
    let prompt: CurrentSymptomFollowUpPrompt
    let responseState: CurrentSymptomState
    let isBusy: Bool
    let onSubmit: (String?, String?, String?) async -> Bool

    @Environment(\.dismiss) private var dismiss
    @State private var detailChoice: String = ""
    @State private var timeBucket: String = ""
    @State private var noteDraft: String = ""

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    private var category: String {
        let focus = (prompt.detailFocus ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !focus.isEmpty {
            return focus
        }
        let code = item.symptomCode.lowercased()
        if ["headache", "migraine", "sinus_pressure", "pain", "joint_pain", "nerve_pain", "muscle_pain", "stiffness", "zaps"].contains(code) {
            return "pain"
        }
        if ["fatigue", "drained", "low_energy", "wired_tired", "wired", "brain_fog"].contains(code) {
            return "energy"
        }
        if ["anxious", "panic", "restless", "wired", "irritable", "low_mood"].contains(code) {
            return "mood"
        }
        if ["insomnia", "restless_sleep", "poor_sleep", "waking_unrefreshed"].contains(code) {
            return "sleep"
        }
        return "general"
    }

    private var titleText: String {
        switch responseState {
        case .ongoing:
            return "What’s most noticeable now?"
        case .worse:
            return "What stood out most?"
        case .resolved:
            return "About when did it ease up?"
        case .improving:
            return "What feels most improved?"
        case .new:
            return "Anything else to add?"
        }
    }

    private var introText: String {
        switch responseState {
        case .ongoing:
            return "You can keep this quick. Pick the closest fit or skip the extra detail."
        case .worse:
            return "This helps Gaia understand what changed without turning this into a full log."
        case .resolved:
            return "Rough timing is enough."
        case .improving:
            return "Optional detail only."
        case .new:
            return "Optional detail only."
        }
    }

    private var detailOptions: [String] {
        switch category {
        case "pain":
            return ["sinus_pressure", "joint_pain", "nerve_pain", "muscle_pain", "head_pressure", "other"]
        case "energy":
            return ["drained", "low_but_steady", "improved", "crashed_later"]
        case "mood":
            return ["anxious", "wired", "low_mood", "irritable", "emotionally_flat"]
        case "sleep":
            return ["falling_asleep", "staying_asleep", "waking_unrested", "restless_sleep"]
        default:
            return ["more_intense", "lingering", "on_and_off", "spread_out", "other"]
        }
    }

    private var timeBucketOptions: [String] {
        ["within_1_hour", "later_same_day", "overnight", "not_sure"]
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(prompt.questionText)
                            .font(.title3.weight(.bold))
                            .foregroundColor(.white)
                        Text(introText)
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.68))
                    }

                    if responseState == .resolved {
                        optionCard(
                            title: titleText,
                            selection: $timeBucket,
                            choices: timeBucketOptions
                        )
                    } else {
                        optionCard(
                            title: titleText,
                            selection: $detailChoice,
                            choices: detailOptions
                        )
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Optional note")
                            .font(.headline)
                            .foregroundColor(.white)
                        ZStack(alignment: .topLeading) {
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(Color.white.opacity(0.05))
                            if noteDraft.isEmpty {
                                Text("Anything short that would make this more useful later?")
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.35))
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 12)
                            }
                            TextEditor(text: $noteDraft)
                                .scrollContentBackground(.hidden)
                                .foregroundColor(.white)
                                .frame(minHeight: 100)
                                .padding(6)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))

                    Button {
                        Task {
                            let saved = await onSubmit(
                                detailChoice.nilIfBlank,
                                noteDraft.nilIfBlank,
                                timeBucket.nilIfBlank
                            )
                            if saved {
                                dismiss()
                            }
                        }
                    } label: {
                        HStack {
                            if isBusy {
                                ProgressView().scaleEffect(0.8)
                            }
                            Text("Save response")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isBusy)
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
            .navigationTitle(item.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }

    @ViewBuilder
    private func optionCard(title: String, selection: Binding<String>, choices: [String]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
                .foregroundColor(.white)

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(choices, id: \.self) { choice in
                    Button {
                        selection.wrappedValue = choice
                    } label: {
                        Text(label(for: choice))
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(selection.wrappedValue == choice ? Color(red: 0.35, green: 0.58, blue: 0.92).opacity(0.28) : Color.white.opacity(0.05))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(selection.wrappedValue == choice ? Color(red: 0.35, green: 0.58, blue: 0.92) : Color.white.opacity(0.08), lineWidth: 1)
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

    private func label(for value: String) -> String {
        value
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
            .replacingOccurrences(of: "Later Same Day", with: "Later the same day")
            .replacingOccurrences(of: "Within 1 Hour", with: "Within 1 hour")
            .replacingOccurrences(of: "Low But Steady", with: "Low but steady")
            .replacingOccurrences(of: "On And Off", with: "On and off")
            .replacingOccurrences(of: "Spread Out", with: "Spread out")
    }
}

struct CurrentSymptomsTimelineView: View {
    let api: APIClient

    @State private var entries: [CurrentSymptomTimelineEntry] = []
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.orange)
                }

                if isLoading && entries.isEmpty {
                    ProgressView("Loading timeline…")
                        .tint(.white)
                }

                ForEach(entries) { entry in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(entry.label)
                                    .font(.headline)
                                    .foregroundColor(.white)
                                Text(label(for: entry))
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.65))
                            }
                            Spacer()
                            Text(timestamp(for: entry))
                                .font(.caption2)
                                .foregroundColor(.white.opacity(0.54))
                        }

                        if let noteText = entry.noteText, !noteText.isEmpty {
                            Text(noteText)
                                .font(.footnote)
                                .foregroundColor(.white.opacity(0.72))
                        }
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .stroke(Color.white.opacity(0.07), lineWidth: 1)
                    )
                }

                if !isLoading && entries.isEmpty && errorMessage == nil {
                    Text("No recent symptom events yet.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                }
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
        .navigationTitle("Timeline")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            appLog("[CurrentSymptoms] timeline_open")
            await loadTimeline()
        }
        .refreshable {
            await loadTimeline()
        }
    }

    private func loadTimeline() async {
        await MainActor.run {
            isLoading = true
            errorMessage = nil
        }
        do {
            let envelope = try await api.fetchCurrentSymptomTimeline()
            if envelope.ok == false && (envelope.data ?? []).isEmpty {
                throw NSError(domain: "CurrentSymptomsTimeline", code: 1, userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Timeline unavailable"])
            }
            await MainActor.run {
                entries = envelope.payload ?? []
                isLoading = false
            }
        } catch {
            if isCurrentSymptomsCancellation(error) {
                await MainActor.run {
                    isLoading = false
                }
                return
            }
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoading = false
            }
            appLog("[CurrentSymptoms] timeline_error: \(error.localizedDescription)")
        }
    }

    private func label(for entry: CurrentSymptomTimelineEntry) -> String {
        switch entry.updateKind {
        case "logged":
            return "Logged"
        case "note":
            return "Note added"
        case "severity_update":
            return "Severity updated\(entry.severity.map { " to \($0)/10" } ?? "")"
        default:
            if let state = entry.state {
                return state.rawValue.capitalized
            }
            return entry.updateKind.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func timestamp(for entry: CurrentSymptomTimelineEntry) -> String {
        guard let date = ISO8601DateFormatter().date(from: entry.occurredAt) else { return "Recent" }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
