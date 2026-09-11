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
                subtitle: "See what’s active and update it as things change.",
                activeNowTitle: "Active Now",
                logSymptomTitle: "Log symptom",
                logSymptomsTitle: "Log symptoms",
                timelineTitle: "Symptom history",
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
                editDetailsTitle: "Add or edit details"
            )
        case .mystical:
            return CurrentSymptomsCopy(
                pageTitle: vocabulary.currentSymptomsLabel,
                subtitle: "See what’s active and update it as things change.",
                activeNowTitle: "Active Right Now",
                logSymptomTitle: "Log symptom",
                logSymptomsTitle: "Log symptoms",
                timelineTitle: "Symptom history",
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
                editDetailsTitle: "Add or edit details"
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
    let migraineDraft: MigraineFollowUpDraft?
    let accountScope: String

    var id: String {
        "\(prompt.id):\(responseState.rawValue)"
    }
}

private struct CurrentSymptomRowFeedback: Equatable {
    let message: String
    let isError: Bool
}

private func isCurrentSymptomsCancellation(_ error: Error) -> Bool {
    if error is CancellationError {
        return true
    }
    let nsError = error as NSError
    return nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled
}

private func isRecoverableCurrentSymptomsMutationError(_ error: Error) -> Bool {
    let nsError = error as NSError
    guard nsError.domain == NSURLErrorDomain else {
        return false
    }
    let code = URLError.Code(rawValue: nsError.code)
    switch code {
    case .timedOut, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed:
        return true
    default:
        return false
    }
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
    @State private var updatingEpisodeIds: Set<String> = []
    @State private var optimisticStates: [String: CurrentSymptomState] = [:]
    @State private var rowFeedback: [String: CurrentSymptomRowFeedback] = [:]
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

    private var currentAccountScope: String {
        let value = AuthManager.shared.currentSupabaseUserId()?.trimmingCharacters(in: .whitespacesAndNewlines)
        return value?.isEmpty == false ? value! : "anonymous"
    }

    private var structuredMigraineFollowUpEnabled: Bool {
        MigraineStructuredFollowUpFeature.isEnabled
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
                isBusy: isUpdating(item.id),
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
                api: api,
                item: composer.item,
                prompt: composer.prompt,
                responseState: composer.responseState,
                migraineDraft: composer.migraineDraft,
                isBusy: isUpdating(composer.item.id),
                onSubmit: { detailChoice, noteText, timeBucket, responseTimestamp, migraineEdit in
                    try await submitFollowUpResponse(
                        prompt: composer.prompt,
                        item: composer.item,
                        state: composer.responseState,
                        detailChoice: detailChoice,
                        noteText: noteText,
                        timeBucket: timeBucket,
                        responseTimestamp: responseTimestamp,
                        migraineEdit: migraineEdit,
                        draftAccountScope: composer.accountScope
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

    private func payload(from envelope: Envelope<CurrentSymptomsSnapshot>) throws -> CurrentSymptomsSnapshot {
        if envelope.ok == false, envelope.data == nil {
            throw NSError(
                domain: "CurrentSymptoms",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: envelope.error ?? "Current symptoms unavailable"]
            )
        }
        return envelope.payload ?? CurrentSymptomsSnapshot(
            generatedAt: "",
            windowHours: 12,
            summary: CurrentSymptomsSummary(activeCount: 0, newCount: 0, ongoingCount: 0, improvingCount: 0, worseCount: 0, lastUpdatedAt: nil, followUpAvailable: false),
            items: [],
            contributingDrivers: [],
            patternContext: [],
            followUpSettings: CurrentSymptomsFollowUpSettings(notificationsEnabled: false, enabled: false, notificationFamilyEnabled: false, pushEnabled: false, cadence: "balanced", states: ["new", "ongoing", "improving", "worse"], symptomCodes: []),
            voiceSemantic: nil
        )
    }

    private func loadSnapshot(showLoading: Bool = true, surfaceErrors: Bool = true) async {
        if showLoading {
            await MainActor.run {
                isLoading = true
                if surfaceErrors {
                    errorMessage = nil
                }
            }
        } else if surfaceErrors {
            await MainActor.run {
                errorMessage = nil
            }
        }
        do {
            let payload = try payload(from: try await api.fetchCurrentSymptoms())
            await MainActor.run {
                applySnapshot(payload)
                if showLoading {
                    isLoading = false
                }
            }
            appLog("[CurrentSymptoms] snapshot ok active=\(payload.summary.activeCount)")
        } catch {
            if isCurrentSymptomsCancellation(error) {
                if showLoading {
                    await MainActor.run {
                        isLoading = false
                    }
                }
                return
            }
            await MainActor.run {
                if surfaceErrors {
                    errorMessage = error.localizedDescription
                }
                if showLoading {
                    isLoading = false
                }
            }
            appLog("[CurrentSymptoms] snapshot error: \(error.localizedDescription)")
        }
    }

    private func refreshSnapshotSilently() async -> CurrentSymptomsSnapshot? {
        do {
            let refreshed = try payload(from: try await api.fetchCurrentSymptoms())
            await MainActor.run {
                applySnapshot(refreshed)
            }
            appLog("[CurrentSymptoms] snapshot ok active=\(refreshed.summary.activeCount)")
            return refreshed
        } catch {
            if !isCurrentSymptomsCancellation(error) {
                appLog("[CurrentSymptoms] snapshot error: \(error.localizedDescription)")
            }
            return nil
        }
    }

    private func confirmRecoveredState(episodeId: String, expectedState: CurrentSymptomState, removeOnSuccess: Bool = false) async -> Bool {
        for attempt in 0..<3 {
            if let refreshed = await refreshSnapshotSilently() {
                if removeOnSuccess {
                    if !refreshed.items.contains(where: { $0.id == episodeId }) {
                        return true
                    }
                } else if refreshed.items.first(where: { $0.id == episodeId })?.currentState == expectedState {
                    return true
                }
            }
            if attempt < 2 {
                try? await Task.sleep(nanoseconds: 450_000_000)
            }
        }
        return false
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

    private func isUpdating(_ episodeId: String) -> Bool {
        updatingEpisodeIds.contains(episodeId)
    }

    private func displayedState(for item: CurrentSymptomItem) -> CurrentSymptomState {
        optimisticStates[item.id] ?? item.currentState
    }

    @MainActor
    private func applySnapshot(_ payload: CurrentSymptomsSnapshot) {
        snapshot = payload
        syncSelection(with: payload)
        onSnapshotChanged(payload)
        let itemIds = Set(payload.items.map(\.id))
        optimisticStates = optimisticStates.filter { itemIds.contains($0.key) }
        rowFeedback = rowFeedback.filter { itemIds.contains($0.key) }
    }

    @MainActor
    private func replaceSnapshotItems(_ mutate: (inout [CurrentSymptomItem]) -> Void) {
        guard let current = snapshot else { return }
        var items = current.items
        mutate(&items)
        applySnapshot(
            CurrentSymptomsSnapshot(
                generatedAt: ISO8601DateFormatter().string(from: Date()),
                windowHours: current.windowHours,
                summary: CurrentSymptomsSummary(
                    activeCount: items.count,
                    newCount: items.filter { $0.currentState == .new }.count,
                    ongoingCount: items.filter { $0.currentState == .ongoing }.count,
                    improvingCount: items.filter { $0.currentState == .improving }.count,
                    worseCount: items.filter { $0.currentState == .worse }.count,
                    lastUpdatedAt: ISO8601DateFormatter().string(from: Date()),
                    followUpAvailable: items.contains { $0.pendingFollowUp != nil }
                ),
                items: items,
                contributingDrivers: current.contributingDrivers,
                patternContext: current.patternContext,
                followUpSettings: current.followUpSettings,
                voiceSemantic: current.voiceSemantic
            )
        )
    }

    @MainActor
    private func upsertItem(_ updatedItem: CurrentSymptomItem) {
        replaceSnapshotItems { items in
            if let index = items.firstIndex(where: { $0.id == updatedItem.id }) {
                items[index] = updatedItem
            } else {
                items.insert(updatedItem, at: 0)
            }
        }
    }

    @MainActor
    private func removeItem(_ episodeId: String) {
        replaceSnapshotItems { items in
            items.removeAll { $0.id == episodeId }
        }
    }

    @MainActor
    private func clearFollowUpPrompt(for episodeId: String) {
        replaceSnapshotItems { items in
            guard let index = items.firstIndex(where: { $0.id == episodeId }) else { return }
            let item = items[index]
            items[index] = CurrentSymptomItem(
                id: item.id,
                symptomCode: item.symptomCode,
                label: item.label,
                severity: item.severity,
                originalSeverity: item.originalSeverity,
                loggedAt: item.loggedAt,
                lastInteractionAt: item.lastInteractionAt,
                currentState: item.currentState,
                notePreview: item.notePreview,
                noteCount: item.noteCount,
                likelyDrivers: item.likelyDrivers,
                patternHint: item.patternHint,
                gaugeKeys: item.gaugeKeys,
                currentContextBadge: item.currentContextBadge,
                pendingFollowUp: nil
            )
        }
    }

    @MainActor
    private func updateJournalFields(for episodeId: String, severity: Int, noteText: String?) {
        replaceSnapshotItems { items in
            guard let index = items.firstIndex(where: { $0.id == episodeId }) else { return }
            let item = items[index]
            items[index] = CurrentSymptomItem(
                id: item.id,
                symptomCode: item.symptomCode,
                label: item.label,
                severity: severity,
                originalSeverity: item.originalSeverity,
                loggedAt: item.loggedAt,
                lastInteractionAt: item.lastInteractionAt,
                currentState: item.currentState,
                notePreview: noteText,
                noteCount: noteText == nil ? 0 : max(item.noteCount, 1),
                likelyDrivers: item.likelyDrivers,
                patternHint: item.patternHint,
                gaugeKeys: item.gaugeKeys,
                currentContextBadge: item.currentContextBadge,
                pendingFollowUp: item.pendingFollowUp
            )
        }
    }

    private func locallyUpdatedItem(
        from item: CurrentSymptomItem,
        state: CurrentSymptomState? = nil,
        severity: Int? = nil,
        noteText: String? = nil,
        useProvidedNote: Bool = false,
        pendingFollowUp: CurrentSymptomFollowUpPrompt? = nil,
        useProvidedPrompt: Bool = false
    ) -> CurrentSymptomItem {
        CurrentSymptomItem(
            id: item.id,
            symptomCode: item.symptomCode,
            label: item.label,
            severity: severity ?? item.severity,
            originalSeverity: item.originalSeverity,
            loggedAt: item.loggedAt,
            lastInteractionAt: ISO8601DateFormatter().string(from: Date()),
            currentState: state ?? item.currentState,
            notePreview: useProvidedNote ? noteText : item.notePreview,
            noteCount: useProvidedNote ? (noteText == nil ? 0 : max(item.noteCount, 1)) : item.noteCount,
            likelyDrivers: item.likelyDrivers,
            patternHint: item.patternHint,
            gaugeKeys: item.gaugeKeys,
            currentContextBadge: item.currentContextBadge,
            pendingFollowUp: useProvidedPrompt ? pendingFollowUp : item.pendingFollowUp
        )
    }

    private func updateState(_ item: CurrentSymptomItem, to state: CurrentSymptomState) {
        guard !isUpdating(item.id) else { return }
        updatingEpisodeIds.insert(item.id)
        optimisticStates[item.id] = state
        rowFeedback[item.id] = nil
        journalStatus = nil
        appLog("[CurrentSymptoms] state_change episode=\(item.id) state=\(state.rawValue)")
        Task {
            defer {
                Task { @MainActor in updatingEpisodeIds.remove(item.id) }
            }
            do {
                let response = try await api.updateCurrentSymptom(episodeId: item.id, state: state)
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 2, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not update symptom"])
                }
                await MainActor.run {
                    optimisticStates.removeValue(forKey: item.id)
                    if state == .resolved {
                        removeItem(item.id)
                        journalStatus = "\(item.label) marked resolved."
                    } else {
                        upsertItem(response.payload ?? locallyUpdatedItem(from: item, state: state))
                        rowFeedback[item.id] = CurrentSymptomRowFeedback(message: "\(item.label) updated.", isError: false)
                    }
                }
                await loadSnapshot(showLoading: false, surfaceErrors: false)
            } catch {
                let recovered = isRecoverableCurrentSymptomsMutationError(error)
                    ? await confirmRecoveredState(episodeId: item.id, expectedState: state, removeOnSuccess: state == .resolved)
                    : false
                await MainActor.run {
                    optimisticStates.removeValue(forKey: item.id)
                    if recovered {
                        if state == .resolved {
                            journalStatus = "\(item.label) marked resolved."
                        } else {
                            rowFeedback[item.id] = CurrentSymptomRowFeedback(message: "\(item.label) updated.", isError: false)
                        }
                    } else {
                        rowFeedback[item.id] = CurrentSymptomRowFeedback(message: error.localizedDescription, isError: true)
                    }
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
        guard !isUpdating(item.id) else { return }
        selectedEpisodeId = item.id
        let isStructuredMigraine = structuredMigraineFollowUpEnabled && item.symptomCode.uppercased() == "MIGRAINE"
        if state == .improving && !isStructuredMigraine {
            Task {
                _ = try? await submitFollowUpResponse(
                    prompt: prompt,
                    item: item,
                    state: state,
                    detailChoice: nil,
                    noteText: nil,
                    timeBucket: nil,
                    responseTimestamp: Date(),
                    migraineEdit: nil,
                    draftAccountScope: nil
                )
            }
            return
        }
        let draft = isStructuredMigraine
            ? MigraineFollowUpDraft(accountScope: currentAccountScope, promptId: prompt.id, episodeId: item.id)
            : nil
        followUpComposer = SymptomFollowUpComposerState(
            item: item,
            prompt: prompt,
            responseState: state,
            migraineDraft: draft,
            accountScope: currentAccountScope
        )
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
        guard !isUpdating(item.id) else { return }
        updatingEpisodeIds.insert(item.id)
        rowFeedback[item.id] = nil
        journalStatus = nil
        Task {
            defer {
                Task { @MainActor in updatingEpisodeIds.remove(item.id) }
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
                    clearFollowUpPrompt(for: item.id)
                    rowFeedback[item.id] = CurrentSymptomRowFeedback(message: "Follow-up moved later.", isError: false)
                }
                await loadSnapshot(showLoading: false, surfaceErrors: false)
            } catch {
                await MainActor.run {
                    rowFeedback[item.id] = CurrentSymptomRowFeedback(message: error.localizedDescription, isError: true)
                }
            }
        }
    }

    private func dismissFollowUp(_ prompt: CurrentSymptomFollowUpPrompt, for item: CurrentSymptomItem) {
        guard !isUpdating(item.id) else { return }
        updatingEpisodeIds.insert(item.id)
        rowFeedback[item.id] = nil
        journalStatus = nil
        Task {
            defer {
                Task { @MainActor in updatingEpisodeIds.remove(item.id) }
            }
            do {
                let response = try await api.dismissSymptomFollowUp(promptId: prompt.id, action: "dismiss", snoozeHours: nil)
                if response.ok == false {
                    throw NSError(domain: "CurrentSymptoms", code: 7, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not dismiss the follow-up"])
                }
                AppAnalytics.track("symptom_followup_dismissed", properties: ["action": "dismiss", "symptom_code": item.symptomCode])
                await MainActor.run {
                    clearFollowUpPrompt(for: item.id)
                    rowFeedback[item.id] = CurrentSymptomRowFeedback(message: "Follow-up dismissed.", isError: false)
                }
                await loadSnapshot(showLoading: false, surfaceErrors: false)
            } catch {
                await MainActor.run {
                    rowFeedback[item.id] = CurrentSymptomRowFeedback(message: error.localizedDescription, isError: true)
                }
            }
        }
    }

    private func submitFollowUpResponse(
        prompt: CurrentSymptomFollowUpPrompt,
        item: CurrentSymptomItem,
        state: CurrentSymptomState,
        detailChoice: String?, noteText: String?, timeBucket: String?,
        responseTimestamp: Date, migraineEdit: MigraineStructuredEdit?,
        draftAccountScope: String?
    ) async throws -> Bool {
        guard !isUpdating(item.id) else { return false }
        let accountScope = draftAccountScope ?? currentAccountScope
        try MigraineFollowUpWorkflow.checkAccount(accountScope, current: { currentAccountScope })
        updatingEpisodeIds.insert(item.id)
        rowFeedback[item.id] = nil
        journalStatus = nil
        defer { updatingEpisodeIds.remove(item.id) }
        do {
            let saved = try await MigraineFollowUpWorkflow.submit(
                api: api, promptId: prompt.id, episodeId: item.id, state: state,
                detailChoice: detailChoice, noteText: noteText, timeBucket: timeBucket,
                timestamp: responseTimestamp, edit: migraineEdit, accountScope: accountScope,
                currentAccountScope: { currentAccountScope }
            )
            // Only an acknowledged response for this account, prompt and episode
            // may dismiss the composer or change the visible canonical state.
            followUpComposer = nil
            if state == .resolved {
                removeItem(item.id)
                journalStatus = "\(item.label) marked resolved."
            } else {
                upsertItem(saved.episode)
                rowFeedback[item.id] = CurrentSymptomRowFeedback(message: "\(item.label) updated from follow-up.", isError: false)
            }
            AppAnalytics.track("symptom_followup_answered", properties: ["state": state.rawValue, "symptom_code": item.symptomCode])
            return true
        } catch {
            rowFeedback[item.id] = CurrentSymptomRowFeedback(message: error.localizedDescription, isError: true)
            throw error
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
        guard !isUpdating(selectedItem.id) else { return }
        updatingEpisodeIds.insert(selectedItem.id)
        journalStatus = nil
        appLog("[CurrentSymptoms] note_save episode=\(selectedItem.id)")
        Task {
            defer {
                Task { @MainActor in updatingEpisodeIds.remove(selectedItem.id) }
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
                    if let updatedItem = response.payload {
                        upsertItem(updatedItem)
                    } else {
                        updateJournalFields(for: selectedItem.id, severity: severityDraft, noteText: noteDraft.nilIfBlank)
                    }
                    journalStatus = noteDraft.nilIfBlank == nil ? "Severity updated." : "Note saved."
                }
                await loadSnapshot(showLoading: false, surfaceErrors: false)
            } catch {
                await MainActor.run {
                    journalStatus = error.localizedDescription
                }
                appLog("[CurrentSymptoms] note_save error: \(error.localizedDescription)")
            }
        }
    }

    private func saveEditorChanges(for item: CurrentSymptomItem, severity: Int, noteText: String?) async -> Bool {
        guard !isUpdating(item.id) else { return false }
        await MainActor.run {
            updatingEpisodeIds.insert(item.id)
            journalStatus = nil
        }
        appLog("[CurrentSymptoms] editor_save episode=\(item.id)")
        defer {
            Task { @MainActor in updatingEpisodeIds.remove(item.id) }
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
                if let updatedItem = response.payload {
                    upsertItem(updatedItem)
                } else {
                    updateJournalFields(for: item.id, severity: severity, noteText: noteText)
                }
                journalStatus = noteText == nil ? "\(item.label) severity updated." : "\(item.label) updated."
                editingItem = nil
            }
            await loadSnapshot(showLoading: false, surfaceErrors: false)
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
        guard !isUpdating(item.id) else { return false }
        await MainActor.run {
            updatingEpisodeIds.insert(item.id)
            journalStatus = nil
        }
        appLog("[CurrentSymptoms] delete episode=\(item.id)")
        defer {
            Task { @MainActor in updatingEpisodeIds.remove(item.id) }
        }
        do {
            let response = try await api.deleteCurrentSymptom(episodeId: item.id)
            if response.ok == false {
                throw NSError(domain: "CurrentSymptoms", code: 5, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not delete symptom"])
            }
            await MainActor.run {
                removeItem(item.id)
                journalStatus = "\(item.label) removed."
                editingItem = nil
            }
            await loadSnapshot(showLoading: false, surfaceErrors: false)
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
        let currentState = displayedState(for: item)
        let isSaving = isUpdating(item.id)
        return VStack(alignment: .leading, spacing: 10) {
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
                if isSaving {
                    ProgressView()
                        .controlSize(.small)
                        .tint(.white.opacity(0.7))
                }
                statePill(currentState)
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
                    indicatorChip(possibleInfluenceLabel(for: item.likelyDrivers.count), tint: Color(red: 0.87, green: 0.63, blue: 0.27))
                }
                if let badge = item.currentContextBadge, !badge.isEmpty, currentState != .new {
                    indicatorChip(badge, tint: Color(red: 0.43, green: 0.76, blue: 0.63))
                }
            }

            if let prompt = item.pendingFollowUp {
                followUpPromptCard(prompt, for: item)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                actionButton(title: "Still active", state: .ongoing, item: item)
                actionButton(title: "Improving", state: .improving, item: item)
                actionButton(title: "Getting worse", state: .worse, item: item)
                actionButton(title: "Resolved", state: .resolved, item: item)
            }

            if let feedback = rowFeedback[item.id] {
                Text(feedback.message)
                    .font(.caption2.weight(.medium))
                    .foregroundColor(feedback.isError ? .orange : Color(red: 0.66, green: 0.84, blue: 0.72))
                    .fixedSize(horizontal: false, vertical: true)
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
        let isSelected = displayedState(for: item) == state
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
                        .disabled(selectedEpisodeId.map(isUpdating) ?? false)

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

    private func possibleInfluenceLabel(for count: Int) -> String {
        count == 1 ? "1 possible influence" : "\(count) possible influences"
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
                                dismiss()
                                _ = await onSave(severityDraft, noteDraft.nilIfBlank)
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
    let api: APIClient
    let item: CurrentSymptomItem
    let prompt: CurrentSymptomFollowUpPrompt
    let responseState: CurrentSymptomState
    let isBusy: Bool
    let onSubmit: (String?, String?, String?, Date, MigraineStructuredEdit?) async throws -> Bool

    @Environment(\.dismiss) private var dismiss
    @State private var detailChoice: String = ""
    @State private var timeBucket: String = ""
    @State private var noteDraft: String = ""
    @State private var migraineDraft: MigraineFollowUpDraft?
    @State private var isLoadingMigraineDetail: Bool = false
    @State private var migraineDetailMessage: String?
    @State private var saveError: String?
    @FocusState private var noteIsFocused: Bool
    private let responseTimestamp: Date
    private let accountScope: String
    private let accountScopeProvider: @MainActor () -> String
    @State private var hasLoadFailure = false
    @State private var isSubmitting = false
    @State private var responseRecovery = MigraineFollowUpSaveRecovery()
    @State private var confirmUncertainClose = false
    @State private var conflictReview: MigraineEpisodeDetail?
    @State private var setAsideDraft: MigraineFollowUpDraft?
    private var inputsLocked: Bool { isBusy || isSubmitting || isLoadingMigraineDetail || responseRecovery.pending != nil || accountScope != currentAccountScope }
    private var noteBinding: Binding<String> {
        Binding(get: { noteDraft }, set: { if !inputsLocked { noteDraft = $0 } })
    }
    private func guardedChoice(_ binding: Binding<String>) -> Binding<String> {
        Binding(get: { binding.wrappedValue }, set: { if !inputsLocked { binding.wrappedValue = $0 } })
    }

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    init(
        api: APIClient,
        item: CurrentSymptomItem,
        prompt: CurrentSymptomFollowUpPrompt,
        responseState: CurrentSymptomState,
        migraineDraft: MigraineFollowUpDraft?,
        isBusy: Bool,
        accountScopeProvider: @escaping @MainActor () -> String = { MigraineFollowUpWorkflow.accountScope() },
        onSubmit: @escaping (String?, String?, String?, Date, MigraineStructuredEdit?) async throws -> Bool
    ) {
        self.api = api
        self.item = item
        self.prompt = prompt
        self.responseState = responseState
        self.isBusy = isBusy
        self.onSubmit = onSubmit
        self.accountScopeProvider = accountScopeProvider
        self.accountScope = migraineDraft?.accountScope ?? accountScopeProvider()
        _migraineDraft = State(initialValue: migraineDraft)
        _isLoadingMigraineDetail = State(initialValue: migraineDraft != nil)
        responseTimestamp = migraineDraft?.responseTimestamp ?? Date()
    }

    private var currentAccountScope: String { accountScopeProvider() }

    private var migraineDraftBinding: Binding<MigraineFollowUpDraft>? {
        guard migraineDraft != nil else { return nil }
        return Binding(
            get: { migraineDraft! },
            set: { if !inputsLocked { migraineDraft = $0 } }
        )
    }

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
                            selection: guardedChoice($timeBucket),
                            choices: timeBucketOptions
                        ).disabled(inputsLocked)
                    } else {
                        optionCard(
                            title: titleText,
                            selection: guardedChoice($detailChoice),
                            choices: detailOptions
                        ).disabled(inputsLocked)
                    }

                    if isLoadingMigraineDetail {
                        HStack(spacing: 10) {
                            ProgressView().tint(.white)
                            Text("Loading your saved migraine details…")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.7))
                        }
                    } else if !hasLoadFailure, let draft = migraineDraftBinding {
                        MigraineMedicineFields(draft: draft).disabled(inputsLocked)
                    }

                    if let migraineDetailMessage {
                        Text(migraineDetailMessage)
                            .font(.caption)
                            .foregroundColor(.orange.opacity(0.9))
                    }

                    if hasLoadFailure {
                        Button("Retry loading migraine details") {
                            Task { await loadMigraineDetailIfNeeded() }
                        }
                        .disabled(isLoadingMigraineDetail)
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
                            TextEditor(text: noteBinding)
                                .disabled(inputsLocked)
                                .accessibilityIdentifier("migraine-episode-note")
                                .focused($noteIsFocused)
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
                            guard !isSubmitting else { return }
                            noteIsFocused = false
                            isSubmitting = true
                            defer { isSubmitting = false }
                            saveError = nil
                            do {
                                try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
                                let request: MigraineFollowUpSaveRecovery.Pending
                                if let pending = responseRecovery.pending {
                                    request = pending
                                } else {
                                    var edit: MigraineStructuredEdit?
                                    if var draft = migraineDraft {
                                        draft.noteText = noteDraft; migraineDraft = draft
                                        edit = try draft.makeStructuredEdit(currentAccountScope: currentAccountScope)
                                            ?? MigraineStructuredEdit(expectedRevision: draft.expectedRevision,
                                                earlySigns: nil, contexts: nil, medicines: nil, notes: .retain)
                                    }
                                    request = try responseRecovery.request(.init(detailChoice: detailChoice.nilIfBlank,
                                        note: migraineDraft == nil ? noteDraft.nilIfBlank : edit?.followUpNoteText,
                                        timeBucket: timeBucket.nilIfBlank, timestamp: responseTimestamp, edit: edit, accountScope: accountScope))
                                }
                                let saved = try await onSubmit(request.detailChoice, request.note, request.timeBucket, request.timestamp, request.edit)
                                try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
                                if saved {
                                    responseRecovery.acknowledge(); dismiss()
                                } else { throw MigraineSaveError.unconfirmed }
                            } catch {
                                responseRecovery.failed(error)
                                saveError = responseRecovery.pending != nil
                                    ? "The response could not be confirmed. Your exact response is kept; retry it before making other edits."
                                    : error.localizedDescription
                            }
                        }
                    } label: {
                        HStack {
                            if isBusy || isSubmitting {
                                ProgressView().scaleEffect(0.8)
                            }
                            Text(isBusy || isSubmitting ? "Saving response…" : responseRecovery.pending != nil ? "Retry same response" : "Save response")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isBusy || isSubmitting || isLoadingMigraineDetail || hasLoadFailure || responseRecovery.needsConflictReload)
                    .accessibilityIdentifier("migraine-save-response")

                    if responseRecovery.needsConflictReload {
                        Button("Reload and keep my edits") { Task { await reloadKeepingEdits() } }
                            .disabled(inputsLocked || isLoadingMigraineDetail)
                            .accessibilityIdentifier("migraine-followup-reload")
                    }
                    if let detail = conflictReview, let draft = migraineDraft {
                        MigraineMedicineConflictReview(draft: draft, saved: detail) {
                            setAsideDraft = draft
                            var next = draft
                            do {
                                try next.apply(detail, forAccountScope: currentAccountScope)
                                migraineDraft = next; noteDraft = next.noteText; conflictReview = nil
                                responseRecovery.conflictReloaded()
                                saveError = "Using the reviewed saved details. Your earlier edits were set aside; no response was sent."
                            } catch { saveError = error.localizedDescription }
                        }.disabled(inputsLocked)
                    }
                    if let saveError {
                        Text(saveError)
                            .accessibilityIdentifier("migraine-save-error")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
                .padding(16)
                .disabled(isBusy || isSubmitting)
            }
            .scrollDismissesKeyboard(.interactively)
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
                    Button("Close") {
                        if responseRecovery.pending != nil { confirmUncertainClose = true } else { dismiss() }
                    }
                        .disabled(isBusy || isSubmitting)
                }
            }
            .interactiveDismissDisabled(inputsLocked)
            .confirmationDialog("Close with an unconfirmed response?", isPresented: $confirmUncertainClose, titleVisibility: .visible) {
                Button("Set aside response and close", role: .destructive) { dismiss() }
                Button("Keep editing", role: .cancel) {}
            } message: {
                Text("The response may already be saved. Closing sends nothing else and sets aside this local draft. Reopen the migraine to review its saved details.")
            }
            .onChange(of: currentAccountScope) { _, _ in
                migraineDraft = nil; responseRecovery = MigraineFollowUpSaveRecovery(); conflictReview = nil; setAsideDraft = nil
                noteDraft = ""; hasLoadFailure = true; saveError = MigraineDraftError.accountChanged.localizedDescription
            }
            .task {
                await loadMigraineDetailIfNeeded()
            }
        }
    }

    private func reloadKeepingEdits() async {
        guard !inputsLocked, var draft = migraineDraft else { return }
        isLoadingMigraineDetail = true
        defer { isLoadingMigraineDetail = false }
        do {
            try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
            let response = try await api.fetchMigraineEpisodeDetail(episodeId: item.id,
                validateRequest: { try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider) })
            try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
            guard response.ok != false, let detail = response.payload else { throw MigraineSaveError.invalidResponse }
            draft.noteText = noteDraft
            do { try draft.rebasePreservingChanges(detail, currentAccountScope: currentAccountScope) }
            catch MigraineDraftError.medicineListConflict {
                conflictReview = detail; saveError = MigraineDraftError.medicineListConflict.localizedDescription; return
            }
            migraineDraft = draft; noteDraft = draft.noteText; conflictReview = nil
            responseRecovery.conflictReloaded()
            saveError = "Saved details reloaded. Review your entries before saving the response."
        } catch { saveError = error.localizedDescription }
    }

    private func loadMigraineDetailIfNeeded() async {
        guard var draft = migraineDraft else { return }
        isLoadingMigraineDetail = true
        defer { isLoadingMigraineDetail = false }
        do {
            try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
            let response = try await api.fetchMigraineEpisodeDetail(episodeId: item.id)
            try MigraineFollowUpWorkflow.checkAccount(accountScope, current: accountScopeProvider)
            guard response.ok != false, let detail = response.payload, detail.episode.episodeId == item.id else {
                throw NSError(
                    domain: "CurrentSymptomFollowUpSheet",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: response.error ?? "Migraine details are unavailable"]
                )
            }
            try draft.apply(detail, forAccountScope: currentAccountScope)
            migraineDraft = draft
            noteDraft = draft.noteText
            hasLoadFailure = false
            migraineDetailMessage = nil
        } catch {
            if accountScope == currentAccountScope,
               !Task.isCancelled,
               MigraineFollowUpWorkflow.isUnsupportedCapability(error) {
                migraineDraft = nil
                hasLoadFailure = false
                migraineDetailMessage = "This server does not support extra migraine details yet. You can still save this check-in."
            } else {
                hasLoadFailure = true
                migraineDetailMessage = accountScope == currentAccountScope
                    ? "Couldn’t load your saved details. Retry loading before saving."
                    : MigraineDraftError.accountChanged.localizedDescription
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

private struct MigraineMedicineConflictReview: View {
    let draft: MigraineFollowUpDraft
    let saved: MigraineEpisodeDetail
    let useSaved: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Review medicine changes").font(.headline)
            Text("Your draft — not saved").font(.subheadline.weight(.semibold))
            ForEach(Array(draft.medicineRows.enumerated()), id: \.element.id) { index, row in
                Text("\(index + 1). \(row.name) · \(row.doseAmountText) \(row.doseUnit)\n\(row.takenAt.formatted(date: .abbreviated, time: .standard))\n\(row.relief.label)\n\(row.notes)")
            }
            Text("Draft note: " + draft.noteText)
            Text("Latest saved entries").font(.subheadline.weight(.semibold))
            ForEach(Array(saved.episode.medicines.enumerated()), id: \.offset) { index, medicine in
                Text("\(index + 1). \(medicine.name) · \(medicine.doseAmount.map { NSDecimalNumber(decimal: $0).stringValue } ?? "") \(medicine.doseUnit ?? "")\n\(medicine.takenAt.utc)\n\(medicine.reportedRelief ?? "Not recorded")\n\(medicine.notes ?? "")")
            }
            Text("Saved note: " + (saved.episode.notes ?? "None"))
            Text("Using the saved version sets aside your current edits. It sends no save. You can then choose the intended entry and make a new edit.")
            Button("Use saved version; set aside my edits", action: useSaved)
                .accessibilityIdentifier("migraine-medicine-use-saved")
        }.font(.caption).buttonStyle(.borderless)
    }
}

private struct MigraineMedicineFields: View {
    @Binding var draft: MigraineFollowUpDraft
    @State private var confirmClear = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Migraine details")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("Optional. Add only what feels useful; you can edit it later.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.62))
            }

            TextField("Early signs, separated by commas", text: $draft.earlySignsText)
                .textInputAutocapitalization(.sentences)
                .padding(12)
                .background(Color.white.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            Text("\(draft.originalMedicines.count) saved medicine entries. \(draft.medicineRows.count) entries in this draft.")
                .font(.caption)
                .accessibilityIdentifier("migraine-saved-medicine-summary")
            Text("Choose an entry to edit. Changes and removals stay in this draft until you save.")
                .font(.caption).foregroundColor(.white.opacity(0.7))
            Text("Entry dates are shown in " + (TimeZone.current.localizedName(for: .generic, locale: .current) ?? TimeZone.current.identifier) + ".")
                .font(.caption).foregroundColor(.white.opacity(0.7))
            ForEach(Array(draft.medicineRows.enumerated()), id: \.element.id) { index, row in
                Button { draft.selectMedicine(row.id) } label: {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(index + 1). " + (row.name.isEmpty ? "New medicine" : row.name))
                                .font(.subheadline.weight(.semibold))
                            Text(row.takenAt.formatted(date: .abbreviated, time: .standard))
                                .font(.caption)
                            if row.original == nil { Text("New entry · not saved").font(.caption) }
                            else if row.hasFieldChanges { Text("Edited · not saved").font(.caption) }
                        }
                        Spacer()
                        if row.id == draft.selectedMedicineID { Image(systemName: "checkmark.circle.fill") }
                    }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                        .background(row.id == draft.selectedMedicineID ? Color.blue.opacity(0.18) : Color.white.opacity(0.04))
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("migraine-medicine-entry-\(index + 1)")
            }
            Button("Add another medicine") { draft.addMedicine() }
                .accessibilityIdentifier("migraine-medicine-choice")
            if !draft.medicineRows.isEmpty {
                Button("Clear all entries", role: .destructive) { confirmClear = true }
                    .accessibilityIdentifier("migraine-medicine-clear")
            } else {
                Text(draft.medicineChoice == .none && draft.originalMedicines.isEmpty
                     ? "No medicine taken is selected. Save to confirm." : "No medicine entries in this draft. Save to confirm changes.")
                    .font(.caption)
                if draft.originalMedicines.isEmpty && draft.medicineChoice != .none {
                    Button("No medicine taken") { draft.chooseMedicine(.none) }
                }
            }
            if let selected = draft.selectedMedicine {
                VStack(alignment: .leading, spacing: 14) {
                Text("Edit selected entry").font(.subheadline.weight(.semibold))
                if let original = selected.original {
                    Text("Saved: " + original.takenAt.utc + " · " + (original.takenAt.timezoneName ?? "original time zone not recorded"))
                        .font(.caption).foregroundColor(.white.opacity(0.7))
                }
                TextField("Medicine name", text: $draft.medicineName)
                    .textInputAutocapitalization(.words)
                    .padding(12)
                    .background(Color.white.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                DatePicker(
                    "Taken",
                    selection: $draft.medicineTakenAt,
                    displayedComponents: [.date, .hourAndMinute]
                )
                .foregroundColor(.white)
                .tint(Color(red: 0.35, green: 0.58, blue: 0.92))

                HStack(spacing: 10) {
                    TextField("Dose", text: $draft.doseAmountText)
                        .keyboardType(.decimalPad)
                    TextField("Unit (mg, mL…)", text: $draft.doseUnit)
                        .textInputAutocapitalization(.never)
                }
                .padding(12)
                .background(Color.white.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                Picker("Relief", selection: $draft.reliefChoice) {
                    ForEach(MigraineReliefChoice.allCases) { choice in
                        Text(choice.label).tag(choice)
                    }
                }
                .pickerStyle(.menu)
                .tint(.white)
                .accessibilityIdentifier("migraine-medicine-relief")

                TextField("Medicine note (optional)", text: $draft.medicineNotesText, axis: .vertical)
                    .accessibilityLabel("Medicine note")
                    .accessibilityIdentifier("migraine-medicine-note")
                    .lineLimit(2...4)
                    .padding(12)
                    .background(Color.white.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                Button("Remove selected entry", role: .destructive) { draft.removeSelectedMedicine() }
                    .accessibilityIdentifier("migraine-medicine-remove")
                }.id(selected.id)
            }
        }
        .confirmationDialog("Clear every medicine entry from this draft?", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Clear all entries", role: .destructive) { draft.chooseMedicine(.none) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This changes only your draft. The entries are removed from the saved record when you save successfully.")
        }
        .foregroundColor(.white)
        .padding(16)
        .buttonStyle(.borderless)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

#if DEBUG
struct MigraineFollowUpFixtureScreen: View {
    @StateObject private var fixtureSession: MigraineFixtureSession
    private var api: APIClient { fixtureSession.api }
    private var fixtureServer: MigraineFixtureServer { fixtureSession.server }
    private let scenario: String
    private let item: CurrentSymptomItem
    private let prompt: CurrentSymptomFollowUpPrompt
    private let draft: MigraineFollowUpDraft
    @State private var accountScope = "fixture-account"
    @State private var isSaving = false
    @State private var saved = false
    @State private var releasedResponse = false

    init() {
        let args = ProcessInfo.processInfo.arguments
        let index = args.firstIndex(of: "-gaia-migraine-scenario")
        let scenario = index.flatMap { args.indices.contains($0 + 1) ? args[$0 + 1] : nil } ?? "success"
        self.scenario = scenario
        _fixtureSession = StateObject(wrappedValue: MigraineFixtureSession(scenario: scenario))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try! decoder.decode(MigraineEpisodeDetail.self, from: MigraineFixtureServer.detailDataForScenario(scenario))
        let id = detail.episode.episodeId
        prompt = CurrentSymptomFollowUpPrompt(id: "fixture-prompt", episodeId: id, symptomCode: "MIGRAINE",
            symptomLabel: "Migraine", questionText: "How is your migraine now?", detailFocus: "pain",
            trigger: nil, scheduledFor: nil, deliveredAt: nil, status: "pending", pushDeliveryEnabled: false)
        item = CurrentSymptomItem(id: id, symptomCode: "MIGRAINE", label: "Migraine", severity: 5,
            originalSeverity: 5, loggedAt: "2026-09-08T04:30:00Z", lastInteractionAt: nil, currentState: .ongoing,
            notePreview: detail.episode.notes, noteCount: 1, likelyDrivers: [], patternHint: nil,
            gaugeKeys: [], currentContextBadge: nil, pendingFollowUp: prompt)
        draft = MigraineFollowUpDraft(accountScope: "fixture-account", promptId: prompt.id,
            episodeId: id, responseTimestamp: Date(timeIntervalSince1970: 1_788_839_400))
    }

    var body: some View {
        VStack {
            if scenario.contains("detail-") {
                Text(isSaving ? "Save pending" : "Save idle")
                    .font(.caption).accessibilityIdentifier("migraine-fixture-save-state")
            }
            if scenario.hasPrefix("delayed-") || scenario.hasPrefix("calendar-pending") || scenario.contains("time-delayed") {
                Button("Release local response") {
                    fixtureServer.releaseReplies()
                    releasedResponse = true
                }
                .accessibilityIdentifier("migraine-release-response")
                if (scenario.hasPrefix("delayed-") || scenario.contains("time-delayed")) && scenario.contains("history") {
                    Text(isSaving ? "Save pending" : "Save idle")
                        .font(.caption)
                        .accessibilityIdentifier("migraine-fixture-save-state")
                }
                if releasedResponse {
                    Text(fixtureServer.submittedNote)
                        .font(.caption)
                        .accessibilityIdentifier("migraine-submitted-note")
                }
            }
            if scenario == "account-change" || scenario == "calendar-pending-account" || scenario.contains("time-delayed-account") || scenario.contains("detail-account") || scenario.contains("entries-account") {
                Button("Switch synthetic account") {
                    accountScope = "different-fixture-account"
                    api.devUserId = accountScope
                }
            }
            if scenario == "calendar-entry" {
                NavigationStack { CurrentSymptomsTimelineView(api: api) }
            } else if scenario.hasPrefix("calendar-") {
                NavigationStack {
                    MigraineHistoryView(api: api, accountScope: accountScope, accountScopeProvider: { accountScope },
                        initialDate: ISO8601DateFormatter().date(from: "2026-09-09T17:00:00Z")!,
                        timeZone: TimeZone(identifier: "America/Chicago")!)
                }
            } else if scenario.contains("history") {
                NavigationStack {
                    HistoricalSymptomEditor(api: api, episodeId: scenario.hasPrefix("time-") ? MigraineTimeFixture.episodeID : item.id, accountScopeProvider: { accountScope },
                        onBusyChange: { isSaving = $0 })
                }
            } else if saved {
                Text("Follow-up confirmed").accessibilityIdentifier("migraine-confirmed")
            } else {
                CurrentSymptomFollowUpSheet(api: api, item: item, prompt: prompt, responseState: .resolved,
                    migraineDraft: scenario.contains("legacy-follow-up") ? nil : draft, isBusy: isSaving, accountScopeProvider: { accountScope }) {
                    choice, note, bucket, timestamp, edit in
                    isSaving = true
                    defer { isSaving = false }
                    _ = try await MigraineFollowUpWorkflow.submit(api: api, promptId: prompt.id,
                        episodeId: item.id, state: .resolved, detailChoice: choice, noteText: note,
                        timeBucket: bucket, timestamp: timestamp, edit: edit, accountScope: draft.accountScope,
                        currentAccountScope: { accountScope })
                    saved = true
                    return true
                }
            }
        }
    }
}
#endif

struct CurrentSymptomsTimelineView: View {
    let api: APIClient
    @ObservedObject private var auth = AuthManager.shared

    @State private var entries: [CurrentSymptomTimelineEntry] = []
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if MigraineCalendarFeature.isEnabled {
                    NavigationLink {
                        MigraineHistoryView(api: api, accountScope: MigraineFollowUpWorkflow.accountScope())
                            .id(auth.supabaseUserId)
                    } label: {
                        Label("Migraine calendar", systemImage: "calendar")
                            .font(.headline).padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 16))
                    }
                    .accessibilityIdentifier("migraine-calendar-open")
                }
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
                    NavigationLink {
                        HistoricalSymptomEditor(api: api, episodeId: entry.episodeId)
                    } label: {
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
                    .buttonStyle(.plain)
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
        .navigationTitle("Symptom history")
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

struct HistoricalSymptomEditor: View {
    let api: APIClient
    let episodeId: String
    var accountScopeProvider: @MainActor () -> String = { MigraineFollowUpWorkflow.accountScope() }
    var onSaved: @MainActor () -> Void = {}
    var onBusyChange: @MainActor (Bool) -> Void = { _ in }
    @State private var loadedAccountScope: String?

    @State private var item: CurrentSymptomItem?
    @State private var severity = 5
    @State private var note = ""
    @FocusState private var noteIsFocused: Bool
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var statusMessage: String?
    @State private var migraineDraft: MigraineFollowUpDraft?
    @State private var isSavingMigraine = false
    @State private var isSavingTimeCorrection = false
    @State private var isReloadingMigraine = false
    @State private var migraineRecovery = MigraineDetailSaveRecovery()
    @State private var medicineConflictReview: MigraineEpisodeDetail?
    @State private var setAsideMedicineDraft: MigraineFollowUpDraft?
    @State private var migraineStatusMessage: String?

    @StateObject private var timeStore: MigraineTimeEditorStore

    init(api: APIClient, episodeId: String,
         accountScopeProvider: @escaping @MainActor () -> String = { MigraineFollowUpWorkflow.accountScope() },
         onSaved: @escaping @MainActor () -> Void = {}, onBusyChange: @escaping @MainActor (Bool) -> Void = { _ in }) {
        self.api = api; self.episodeId = episodeId; self.accountScopeProvider = accountScopeProvider
        self.onSaved = onSaved; self.onBusyChange = onBusyChange
        _timeStore = StateObject(wrappedValue: MigraineTimeEditorStore(api: api, episodeId: episodeId, accountScope: accountScopeProvider))
    }
    private var saving: Bool { isSaving || isSavingMigraine || isSavingTimeCorrection || isReloadingMigraine }
    private var otherEditsLocked: Bool { saving || timeStore.isLoading || timeStore.pendingRequest != nil || migraineRecovery.pending != nil }
    private var detailSaveLocked: Bool { saving || timeStore.isLoading || timeStore.pendingRequest != nil || migraineRecovery.needsConflictReload }
    private var noteBinding: Binding<String> {
        Binding(get: { note }, set: { if !otherEditsLocked { note = $0 } })
    }
    private var currentAccountScope: String { accountScopeProvider() }

    private var severityBinding: Binding<Int> {
        Binding(get: { severity }, set: { value in
            // Form can recreate an offscreen Stepper with stale enabled state.
            guard !isSaving, !isSavingMigraine, !isSavingTimeCorrection, !isReloadingMigraine, timeStore.pendingRequest == nil, migraineRecovery.pending == nil, !timeStore.isLoading else { return }
            severity = value
        })
    }

    private var migraineDraftBinding: Binding<MigraineFollowUpDraft>? {
        guard migraineDraft != nil else { return nil }
        return Binding(get: { migraineDraft! }, set: { if !otherEditsLocked { migraineDraft = $0 } })
    }

    var body: some View {
        Form {
            if isLoading {
                ProgressView("Loading symptom…")
            } else if let item {
                Section("Symptom") {
                    LabeledContent("Name", value: item.label)
                    LabeledContent("Status", value: (timeStore.context?.episode.state ?? item.currentState.rawValue).capitalized)
                    Stepper("Severity: \(severity)/10", value: severityBinding, in: 0...10)
                        .accessibilityIdentifier("migraine-history-severity")
                        .disabled(otherEditsLocked)
                }
                Section("Notes") {
                    TextField("Optional note", text: noteBinding, axis: .vertical)
                        .accessibilityIdentifier("migraine-history-note")
                        .focused($noteIsFocused)
                        .disabled(otherEditsLocked)
                        .lineLimit(3...6)
                }
                if item.symptomCode.uppercased() == "MIGRAINE", MigraineTimeEditingFeature.isEnabled {
                    MigraineTimeFields(store: timeStore) { await saveTimes() }
                }
                if item.symptomCode.uppercased() == "MIGRAINE",
                   MigraineStructuredFollowUpFeature.isEnabled,
                   let draft = migraineDraftBinding {
                    Section("Migraine details") {
                        MigraineMedicineFields(draft: draft)
                            .disabled(otherEditsLocked)
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                        Button(isSavingMigraine ? "Saving migraine details…" : migraineRecovery.pending != nil ? "Retry same migraine save" : "Save migraine details") {
                            Task { await saveMigraineDetails() }
                        }
                        .disabled(detailSaveLocked)
                        .accessibilityIdentifier("migraine-history-save")
                        if let migraineStatusMessage {
                            Text(migraineStatusMessage).font(.footnote)
                                .accessibilityIdentifier("migraine-history-status")
                        }
                        if migraineRecovery.needsConflictReload {
                            Text("Load the latest saved details and keep your edits. Review the note and medicine entries before saving again.")
                                .font(.footnote)
                            Button("Reload and keep my edits") {
                                Task { await reloadMigraineDetails() }
                            }
                            .disabled(otherEditsLocked)
                            .accessibilityIdentifier("migraine-history-reload")
                        }
                        if let detail = medicineConflictReview, let currentDraft = migraineDraft {
                            MigraineMedicineConflictReview(draft: currentDraft, saved: detail) {
                                guard !otherEditsLocked else { return }
                                do {
                                    var next = currentDraft
                                    try next.apply(detail, forAccountScope: currentAccountScope)
                                    setAsideMedicineDraft = currentDraft
                                    migraineDraft = next; note = next.noteText; medicineConflictReview = nil
                                    migraineRecovery.conflictReloaded()
                                    migraineStatusMessage = "Using the reviewed saved details. Your earlier edits were set aside; no save was sent."
                                    if MigraineTimeEditingFeature.isEnabled { Task { await timeStore.load(preservingDraft: true) } }
                                } catch { migraineStatusMessage = error.localizedDescription }
                            }.disabled(otherEditsLocked)
                        }
                        if migraineRecovery.needsUncertainReview {
                            Text("The earlier save may have completed, and newer changes now exist. Review the saved details before deciding what to keep. Retrying sends the same request; it never adds another entry.")
                                .font(.footnote)
                            Button("Review saved details") { Task { await reviewUncertainMigraineSave() } }
                                .disabled(saving).accessibilityIdentifier("migraine-history-review-uncertain")
                            if let reviewed = migraineRecovery.reviewed, let pending = migraineRecovery.pending {
                                Section("Unconfirmed request") {
                                    if let medicines = pending.edit.medicines { medicineReview(medicines) }
                                    if case .set(let text) = pending.edit.notes { Text("Note: " + text) }
                                    if case .clear = pending.edit.notes { Text("Clear the episode note") }
                                    if let signs = pending.edit.earlySigns { Text("Early signs: " + signs.map(\.label).joined(separator: ", ")) }
                                }
                                Section("Latest saved details") {
                                    medicineReview(reviewed.episode.medicines)
                                    Text("Note: " + (reviewed.episode.notes ?? "None"))
                                    Text("Early signs: " + reviewed.episode.earlySigns.map(\.label).joined(separator: ", "))
                                }
                                Text("Use saved version keeps these reviewed details and sets aside the unconfirmed edits. It sends no new save. You can then make a deliberate new edit if needed.")
                                    .font(.footnote)
                                Button("Use saved version; set aside my edits") { useReviewedMigraineVersion() }
                                    .disabled(saving).accessibilityIdentifier("migraine-history-use-reviewed")
                            }
                        }
                    }
                }
                Section {
                    Button(isSaving ? "Saving…" : "Save changes") {
                        Task { await save() }
                    }
                    .disabled(otherEditsLocked)
                    .accessibilityIdentifier("migraine-history-legacy-save")
                }
                if let statusMessage {
                    Section { Text(statusMessage).font(.footnote).accessibilityIdentifier("migraine-history-legacy-status") }
                }
            } else {
                Text(statusMessage ?? "Symptom unavailable.")
            }
        }
        .navigationTitle("Edit symptom")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .onChange(of: currentAccountScope) { _, _ in
            item = nil; migraineDraft = nil; timeStore.invalidate()
            migraineRecovery = MigraineDetailSaveRecovery(); onBusyChange(false)
            medicineConflictReview = nil; setAsideMedicineDraft = nil
            statusMessage = "Your signed-in account changed. Close this editor and open it again."
        }
        .task { await load() }
    }

    private func load() async {
        let scope = loadedAccountScope ?? currentAccountScope
        loadedAccountScope = scope
        do {
            try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider)
            let response = try await api.fetchCurrentSymptom(episodeId: episodeId)
            try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider)
            guard response.ok != false, let loaded = response.payload, loaded.id == episodeId else {
                throw NSError(domain: "HistoricalSymptomEditor", code: 1, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Symptom unavailable"])
            }
            item = loaded
            severity = loaded.severity ?? loaded.originalSeverity ?? 5
            note = loaded.notePreview ?? ""
            if loaded.symptomCode.uppercased() == "MIGRAINE",
               MigraineStructuredFollowUpFeature.isEnabled {
                var draft = MigraineFollowUpDraft(
                    accountScope: scope,
                    promptId: "history:\(episodeId)",
                    episodeId: episodeId
                )
                let detailResponse = try await api.fetchMigraineEpisodeDetail(episodeId: episodeId)
                try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider)
                guard detailResponse.ok != false, let detail = detailResponse.payload, detail.episode.episodeId == episodeId else {
                    throw NSError(
                        domain: "HistoricalSymptomEditor",
                        code: 3,
                        userInfo: [NSLocalizedDescriptionKey: detailResponse.error ?? "Migraine details unavailable"]
                    )
                }
                try draft.apply(detail, forAccountScope: currentAccountScope)
                migraineDraft = draft
                note = draft.noteText
            }
        } catch {
            if scope != currentAccountScope {
                item = nil
                migraineDraft = nil
            }
            statusMessage = MigraineFollowUpWorkflow.isUnsupportedCapability(error)
                ? "This server does not support extra migraine details yet."
                : error.localizedDescription
        }
        if item?.symptomCode.uppercased() == "MIGRAINE", MigraineTimeEditingFeature.isEnabled {
            await timeStore.load()
        }
        isLoading = false
    }

    private func save() async {
        guard item != nil, let scope = loadedAccountScope, !otherEditsLocked else { return }
        noteIsFocused = false
        isSaving = true; timeStore.externalBusy = true; onBusyChange(true)
        let submittedNote = note.trimmingCharacters(in: .whitespacesAndNewlines)
        var acknowledged = false
        defer {
            isSaving = false; timeStore.externalBusy = false; onBusyChange(false)
            if acknowledged, MigraineTimeEditingFeature.isEnabled { Task { await timeStore.otherDetailsSaved() } }
        }
        do {
            try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider)
            let response = try await api.updateCurrentSymptom(
                episodeId: episodeId,
                severity: severity,
                noteText: submittedNote,
                validateRequest: { try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider) }
            )
            try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScopeProvider)
            guard response.ok != false, let saved = response.payload, saved.id == episodeId else {
                throw NSError(domain: "HistoricalSymptomEditor", code: 2, userInfo: [NSLocalizedDescriptionKey: response.error ?? "Changes not saved"])
            }
            item = saved
            if var draft = migraineDraft {
                draft.noteText = note
                draft.acknowledgeLegacyNoteSave(episodeId: saved.id, submittedNote: submittedNote,
                    savedNote: saved.notePreview, currentAccountScope: currentAccountScope)
                migraineDraft = draft
            }
            acknowledged = true
            statusMessage = "Changes saved."
            onSaved()
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    private func saveMigraineDetails() async {
        guard var draft = migraineDraft, !detailSaveLocked else { return }
        noteIsFocused = false
        draft.noteText = note
        migraineDraft = draft
        isSavingMigraine = true; timeStore.externalBusy = true; onBusyChange(true)
        var acknowledged = false
        migraineStatusMessage = nil
        defer {
            isSavingMigraine = false
            timeStore.externalBusy = migraineRecovery.pending != nil
            onBusyChange(migraineRecovery.pending != nil)
            if acknowledged, MigraineTimeEditingFeature.isEnabled { Task { await timeStore.otherDetailsSaved() } }
        }
        do {
            guard let edit = try migraineRecovery.pending?.edit ?? draft.makeStructuredEdit(currentAccountScope: currentAccountScope) else {
                migraineStatusMessage = "No migraine detail changes to save."
                return
            }
            let pending = try migraineRecovery.request(edit, episodeId: episodeId, accountScope: currentAccountScope)
            let saved = try await MigraineFollowUpWorkflow.saveDetails(
                api: api, episodeId: pending.episodeId, edit: pending.edit, accountScope: pending.accountScope,
                currentAccountScope: accountScopeProvider
            )
            var refreshedDraft = draft
            try refreshedDraft.apply(saved, forAccountScope: currentAccountScope)
            migraineDraft = refreshedDraft
            note = refreshedDraft.noteText
            try migraineRecovery.acknowledge(saved, accountScope: currentAccountScope)
            acknowledged = true
            migraineStatusMessage = "Migraine details saved."
            onSaved()
        } catch {
            if draft.accountScope != currentAccountScope {
                migraineRecovery = MigraineDetailSaveRecovery()
                item = nil; migraineDraft = nil
            } else {
                migraineRecovery.failed(error)
            }
            migraineStatusMessage = migraineRecovery.pending != nil
                ? "This save could not be confirmed. Your exact request is kept. Retry the same save before making other edits."
                : migraineRecovery.needsConflictReload
                ? "The saved details changed. Your edits are still here; reload and review before saving."
                : "\(error.localizedDescription) Your changes are still here."
        }
    }

    @ViewBuilder private func medicineReview(_ medicines: [MigraineMedicineTaken]) -> some View {
        Text("\(medicines.count) medicine entries")
        ForEach(Array(medicines.enumerated()), id: \.offset) { index, medicine in
            VStack(alignment: .leading) {
                Text("\(index + 1). \(medicine.name)")
                if let amount = medicine.doseAmount { Text(NSDecimalNumber(decimal: amount).stringValue + " " + (medicine.doseUnit ?? "")) }
                if let date = MigraineFollowUpDraft.parseDate(medicine.takenAt.utc) { Text(date.formatted(date: .abbreviated, time: .standard)) }
                if let note = medicine.notes { Text(note) }
                if let relief = medicine.reportedRelief { Text("Relief: " + relief) }
            }.font(.footnote)
        }
    }

    private func reviewUncertainMigraineSave() async {
        guard !saving, let pending = migraineRecovery.pending, migraineRecovery.needsUncertainReview else { return }
        isReloadingMigraine = true; timeStore.externalBusy = true; onBusyChange(true)
        defer {
            isReloadingMigraine = false; timeStore.externalBusy = migraineRecovery.pending != nil
            onBusyChange(migraineRecovery.pending != nil)
        }
        do {
            try MigraineFollowUpWorkflow.checkAccount(pending.accountScope, current: accountScopeProvider)
            let response = try await api.fetchMigraineEpisodeDetail(episodeId: pending.episodeId,
                validateRequest: { try MigraineFollowUpWorkflow.checkAccount(pending.accountScope, current: accountScopeProvider) })
            try MigraineFollowUpWorkflow.checkAccount(pending.accountScope, current: accountScopeProvider)
            guard response.ok != false, let detail = response.payload else { throw MigraineSaveError.invalidResponse }
            try migraineRecovery.review(detail, accountScope: currentAccountScope)
            migraineStatusMessage = "Review the unconfirmed request and the latest saved details below. Your request is still kept."
        } catch {
            migraineStatusMessage = "Saved details could not be loaded. Your unconfirmed request is still kept."
        }
    }

    private func useReviewedMigraineVersion() {
        guard !saving, var draft = migraineDraft else { return }
        do {
            try MigraineFollowUpWorkflow.checkAccount(draft.accountScope, current: accountScopeProvider)
            let detail = try migraineRecovery.useReviewedVersion(accountScope: currentAccountScope)
            try draft.apply(detail, forAccountScope: currentAccountScope)
            migraineDraft = draft; note = draft.noteText
            timeStore.externalBusy = false; onBusyChange(false)
            migraineStatusMessage = "Using the reviewed saved version. The unconfirmed edits were set aside; no new save was sent."
            if MigraineTimeEditingFeature.isEnabled { Task { await timeStore.load(preservingDraft: true) } }
        } catch { migraineStatusMessage = error.localizedDescription }
    }

    private func reloadMigraineDetails() async {
        guard var draft = migraineDraft, !otherEditsLocked else { return }
        draft.noteText = note
        noteIsFocused = false
        isReloadingMigraine = true; timeStore.externalBusy = true; onBusyChange(true)
        defer { isReloadingMigraine = false; timeStore.externalBusy = false; onBusyChange(false) }
        do {
            try MigraineFollowUpWorkflow.checkAccount(draft.accountScope, current: accountScopeProvider)
            let response = try await api.fetchMigraineEpisodeDetail(episodeId: episodeId,
                validateRequest: { try MigraineFollowUpWorkflow.checkAccount(draft.accountScope, current: accountScopeProvider) })
            try MigraineFollowUpWorkflow.checkAccount(draft.accountScope, current: accountScopeProvider)
            guard response.ok != false, let detail = response.payload else { throw MigraineSaveError.invalidResponse }
            do { try draft.rebasePreservingChanges(detail, currentAccountScope: currentAccountScope) }
            catch MigraineDraftError.medicineListConflict {
                medicineConflictReview = detail
                migraineStatusMessage = MigraineDraftError.medicineListConflict.localizedDescription
                return
            }
            medicineConflictReview = nil
            migraineDraft = draft; note = draft.noteText; migraineRecovery.conflictReloaded()
            migraineStatusMessage = "Saved details reloaded. Your edits are still here; review them before saving."
            if MigraineTimeEditingFeature.isEnabled {
                timeStore.externalBusy = false
                await timeStore.load(preservingDraft: true)
            }
        } catch {
            migraineStatusMessage = "\(error.localizedDescription) Your changes are still here."
        }
    }
    private func saveTimes() async {
        guard !saving, migraineRecovery.pending == nil, !timeStore.inputsLocked else { return }
        noteIsFocused = false
        isSavingTimeCorrection = true
        onBusyChange(true)
        defer { isSavingTimeCorrection = false; onBusyChange(false) }
        if let saved = await timeStore.save() {
            if var draft = migraineDraft {
                if !draft.advanceAfterTimeCorrection(saved, currentAccountScope: currentAccountScope) {
                    // No uncertain structured request can coexist with this save.
                    migraineRecovery.requireConflictReload()
                    migraineStatusMessage = "Other saved details changed. Reload and review them before saving your remaining edits."
                }
                migraineDraft = draft
            }
            onSaved()
        }
    }

}
