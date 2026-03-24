import SwiftUI

enum CurrentSymptomsPresentationMode {
    case scientific
    case mystical
}

enum CurrentSymptomsTone {
    case straight
    case balanced
    case humorous
}

private struct CurrentSymptomsCopy {
    let pageTitle: String
    let subtitle: String
    let contributingTitle: String
    let patternTitle: String
    let notesTitle: String
    let emptyTitle: String
    let emptyBody: String
    let followUpTitle: String

    static func resolve(mode: CurrentSymptomsPresentationMode, tone: CurrentSymptomsTone) -> CurrentSymptomsCopy {
        switch mode {
        case .scientific:
            return CurrentSymptomsCopy(
                pageTitle: "Current Symptoms",
                subtitle: "Based on your recent logs and current conditions",
                contributingTitle: "Likely contributing drivers",
                patternTitle: "Observed pattern context",
                notesTitle: "Notes / Journal",
                emptyTitle: "No symptoms currently being tracked",
                emptyBody: tone == .humorous ? "Nothing is waving a red flag right now. Log if something changes." : "Nothing active right now. Log if something changes.",
                followUpTitle: "Follow-up prompts"
            )
        case .mystical:
            return CurrentSymptomsCopy(
                pageTitle: "How You're Feeling Right Now",
                subtitle: "Based on your recent logs and the conditions moving through today",
                contributingTitle: "What may be shaping this",
                patternTitle: "Patterns we've seen before",
                notesTitle: "Notes / Reflections",
                emptyTitle: "Nothing active right now",
                emptyBody: tone == .humorous ? "Your system looks quieter right now. If the plot thickens, log it." : "Your system looks quieter right now. If something shifts, log it here.",
                followUpTitle: "Check-in prompts"
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

struct CurrentSymptomsView: View {
    let api: APIClient
    var mode: CurrentSymptomsPresentationMode = .scientific
    var tone: CurrentSymptomsTone = .balanced
    var showsCloseButton: Bool = false
    let onLogMore: () -> Void
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

    private var copy: CurrentSymptomsCopy {
        CurrentSymptomsCopy.resolve(mode: mode, tone: tone)
    }

    private var activeItems: [CurrentSymptomItem] {
        snapshot?.items ?? []
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerCard
                activeNowCard
                contributingCard
                patternCard
                journalCard
                followUpCard
                logMoreCard
                timelineCard
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
            if snapshot == nil {
                appLog("[CurrentSymptoms] page_open")
                await loadSnapshot()
            }
        }
        .refreshable {
            await loadSnapshot()
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
                summary: CurrentSymptomsSummary(activeCount: 0, newCount: 0, ongoingCount: 0, improvingCount: 0, lastUpdatedAt: nil, followUpAvailable: false),
                items: [],
                contributingDrivers: [],
                patternContext: [],
                followUpSettings: CurrentSymptomsFollowUpSettings(notificationsEnabled: false, enabled: false, notificationFamilyEnabled: false, cadence: "balanced", states: ["new", "ongoing", "improving"], symptomCodes: [])
            )
            await MainActor.run {
                snapshot = payload
                syncSelection(with: payload)
                onSnapshotChanged(payload)
                isLoading = false
            }
            appLog("[CurrentSymptoms] snapshot ok active=\(payload.summary.activeCount)")
        } catch {
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
                        Label("+ Log", systemImage: "plus.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    NavigationLink {
                        CurrentSymptomsTimelineView(api: api)
                    } label: {
                        Label("Timeline", systemImage: "clock.arrow.circlepath")
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
                    Text("Active Now")
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
                        Text(copy.emptyBody)
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.7))
                        Button("Log symptoms") {
                            onLogMore()
                        }
                        .buttonStyle(.bordered)
                    }
                } else {
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

            HStack(spacing: 8) {
                actionButton(title: "Still active", state: .ongoing, item: item)
                actionButton(title: "Improving", state: .improving, item: item)
                actionButton(title: "Resolved", state: .resolved, item: item)
            }

            Button {
                selectedEpisodeId = item.id
                noteDraft = item.notePreview ?? ""
                severityDraft = item.severity ?? item.originalSeverity ?? 5
            } label: {
                Text("Add note or adjust severity")
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

    private func actionButton(title: String, state: CurrentSymptomState, item: CurrentSymptomItem) -> some View {
        let isSelected = item.currentState == state
        return Button(title) {
            updateState(item, to: state)
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
                                Text(driver.label)
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
                                Text(relation)
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
                } else {
                    Text("Current drivers will show up here once there are active symptoms to compare against live conditions.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
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
                    ForEach(patternContext.prefix(3)) { pattern in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(pattern.text ?? "\(pattern.signal) matches your \(pattern.outcome.lowercased()) pattern.")
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
                } else {
                    Text("We're still learning what tends to line up with this.")
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
                    Text("Nothing active to attach a note to right now.")
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
                            Text("Worse this afternoon, improved after resting, felt better after allergy meds…")
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
                    Text(enabled ? "Current symptoms can support future follow-up check-ins on a \(settings.cadence) cadence." : "Follow-up prompts are off right now, but this state history is ready for future check-ins.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))

                    HStack(spacing: 8) {
                        indicatorChip(enabled ? "Enabled" : "Off", tint: enabled ? Color(red: 0.43, green: 0.76, blue: 0.63) : Color.white.opacity(0.4))
                        indicatorChip(settings.cadence.capitalized, tint: Color(red: 0.35, green: 0.58, blue: 0.92))
                    }
                } else {
                    Text("Follow-up settings are still syncing.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                }
            }
        }
    }

    private var logMoreCard: some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text("Log More Symptoms")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("Each symptom stays trackable on its own, even when you log several at once.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
                Button(action: onLogMore) {
                    Label("Log symptoms", systemImage: "plus.circle.fill")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private var timelineCard: some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text("Timeline / Recent Events")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("Review onset, updates, notes, and resolution in one place.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
                NavigationLink {
                    CurrentSymptomsTimelineView(api: api)
                } label: {
                    Label("Open timeline", systemImage: "clock.arrow.circlepath")
                }
                .buttonStyle(.bordered)
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

    private func stateColor(_ state: CurrentSymptomState) -> Color {
        switch state {
        case .new:
            return Color(red: 0.35, green: 0.58, blue: 0.92)
        case .ongoing:
            return Color(red: 0.87, green: 0.63, blue: 0.27)
        case .improving:
            return Color(red: 0.43, green: 0.76, blue: 0.63)
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
