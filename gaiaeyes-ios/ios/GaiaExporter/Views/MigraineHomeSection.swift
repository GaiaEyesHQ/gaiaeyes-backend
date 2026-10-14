import SwiftUI

struct MigraineHomeSection: View {
    let api: APIClient
    let items: [CurrentSymptomItem]
    let isRefreshing: Bool
    let refreshError: String?
    let accountScope: @MainActor () -> String
    var onRefresh: () async -> Void
    @State private var route: Route?
    @State private var draftRevision = 0
    private var scope: String { accountScope() }
    private var active: [CurrentSymptomItem] { items.filter { normalize($0.symptomCode) == "MIGRAINE" && $0.currentState != .resolved } }
    private enum Route: Identifiable {
        case guide(String?), severity(CurrentSymptomItem), end(CurrentSymptomItem), summary(String), calendar
        var id: String {
            switch self {
            case .guide(let id): return "guide-" + (id ?? "new")
            case .severity(let item): return "severity-" + item.id
            case .end(let item): return "end-" + item.id
            case .summary(let id): return "summary-" + id
            case .calendar: return "calendar"
            }
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let first = active.first {
                card(first)
                if active.count > 1 {
                    DisclosureGroup("Review \(active.count - 1) other unresolved migraine\(active.count == 2 ? "" : "s")") {
                        Text("These records remain active until you explicitly end them. Review their dates before making changes.")
                            .font(.footnote).foregroundStyle(.secondary)
                        ForEach(Array(active.dropFirst())) { card($0) }
                    }
                }
            }
            if MigraineGuideStorage.draft(scope: scope, episodeID: nil) != nil {
                Button { route = .guide(nil) } label: { Label("Resume migraine draft", systemImage: "square.and.pencil") }
                    .accessibilityIdentifier("home-migraine-resume")
                Text("Kept on this device; this draft is not a confirmed saved episode.").font(.caption).foregroundStyle(.secondary)
            }
            if active.isEmpty {
                Button { route = .guide(nil) } label: { Label("Log migraine", systemImage: "plus.circle.fill") }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("home-migraine-log")
            }
            HStack {
                Button { route = .calendar } label: { Label("Migraine calendar", systemImage: "calendar") }
                    .accessibilityIdentifier("home-migraine-calendar")
                Spacer()
                if isRefreshing { ProgressView().accessibilityLabel("Refreshing migraine status") }
                else { Button { Task { await onRefresh() } } label: { Image(systemName: "arrow.clockwise") }.accessibilityLabel("Refresh migraine status") }
            }
            if refreshError != nil {
                Text("Migraine status could not be refreshed. Any displayed episode is the last saved view.")
                    .font(.footnote).foregroundStyle(.orange)
            }
        }.padding(16).background(Color.cyan.opacity(0.07), in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.cyan.opacity(0.25)))
            .id("\(scope)-\(draftRevision)")
            .onChange(of: scope) { _, _ in route = nil }
            .sheet(item: $route, onDismiss: { draftRevision += 1; Task { await onRefresh() } }) { value in
                switch value {
                case .guide(let id):
                    MigraineGuideView(api: api, episodeID: id, accountScope: accountScope) { _ in Task { await onRefresh() } }
                case .severity(let item):
                    MigraineActiveActionView(api: api, item: item, ending: false, accountScope: accountScope)
                case .end(let item):
                    MigraineActiveActionView(api: api, item: item, ending: true, accountScope: accountScope)
                case .summary(let id):
                    MigraineEpisodeSummaryView(api: api, episodeID: id, accountScope: scope, timeZone: .current, accountScopeProvider: accountScope)
                case .calendar:
                    NavigationStack { MigraineHistoryView(api: api, accountScope: scope, accountScopeProvider: accountScope) }
                }
            }
    }
    private func card(_ item: CurrentSymptomItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Migraine active", systemImage: "waveform.path").font(.title3.bold())
                .accessibilityIdentifier("home-migraine-active-\(item.id)")
            if let start = MigraineFollowUpDraft.parseDate(item.loggedAt) {
                Text("Started \(start.formatted(date: .abbreviated, time: .shortened))").font(.subheadline)
                TimelineView(.periodic(from: .now, by: 60)) { context in
                    Text("Time since start: \(MigraineEpisodeSummary.elapsed(from: start, to: context.date))").font(.caption).foregroundStyle(.secondary)
                }
                if Date().timeIntervalSince(start) > 7 * 24 * 3600 {
                    Text("This earlier episode is still marked active. Review it when you are ready.").font(.footnote).foregroundStyle(.secondary)
                }
            }
            Text(item.severity.map { "Last reported severity: \($0)/10" } ?? "Severity not reported")
            VStack(alignment: .leading, spacing: 8) {
                Button { route = .guide(item.id) } label: { Label("Add details", systemImage: "square.and.pencil") }
                    .accessibilityIdentifier("home-migraine-details-\(item.id)")
                Button { route = .severity(item) } label: { Label("Update severity", systemImage: "slider.horizontal.3") }
                    .accessibilityIdentifier("home-migraine-severity-\(item.id)")
                Button { route = .end(item) } label: { Label("End migraine", systemImage: "checkmark.circle") }
                    .accessibilityIdentifier("home-migraine-end-\(item.id)")
            }.buttonStyle(.bordered).controlSize(.large)
            Button("View episode and timeline") { route = .summary(item.id) }
                .accessibilityIdentifier("home-migraine-summary-\(item.id)")
            if MigraineGuideStorage.draft(scope: scope, episodeID: item.id) != nil {
                Text("Unfinished details are kept on this device. Choose Add details to resume.").font(.caption).foregroundStyle(.secondary)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct MigraineActiveActionView: View {
    let api: APIClient
    let item: CurrentSymptomItem
    let ending: Bool
    let accountScope: @MainActor () -> String
    @State private var openedScope: String
    @State private var severity: Int?
    @State private var selectedEnd: Date?
    @State private var proposedEnd = Date()
    @State private var submittedAt: Date?
    @State private var busy = false
    @State private var message: String?
    @Environment(\.dismiss) private var dismiss
    init(api: APIClient, item: CurrentSymptomItem, ending: Bool, accountScope: @escaping @MainActor () -> String) {
        self.api = api; self.item = item; self.ending = ending; self.accountScope = accountScope
        _openedScope = State(initialValue: accountScope())
    }
    var body: some View {
        NavigationStack {
            Form {
                Section(ending ? "When did this migraine end?" : "How severe is it now?") {
                    if ending {
                        Text("Ending this episode removes it from active migraines and keeps it in your calendar.")
                        Button("Ended now") { selectedEnd = Date() }.accessibilityIdentifier("migraine-end-now")
                        DatePicker("Choose end time", selection: $proposedEnd,
                            in: min(MigraineFollowUpDraft.parseDate(item.loggedAt) ?? .distantPast, Date())...Date(), displayedComponents: [.date, .hourAndMinute])
                        Button("Use selected end time") { selectedEnd = proposedEnd }
                        if let selectedEnd { Text("End: \(selectedEnd.formatted(date: .abbreviated, time: .shortened))") }
                        else { Text("No end time selected").foregroundStyle(.secondary) }
                    } else {
                        Text(item.severity.map { "Last reported severity: \($0)/10" } ?? "No severity reported yet")
                        MigraineSeverityScale(value: $severity)
                        Text("Saving zero does not end the migraine. Earlier severity reports stay in the timeline.").font(.footnote)
                    }
                }.disabled(busy || submittedAt != nil || openedScope != accountScope())
                if let message { Text(message).foregroundStyle(.orange).accessibilityIdentifier("migraine-action-error") }
                Button(submittedAt != nil ? "Retry same update" : ending ? "Confirm end migraine" : "Save current severity") {
                    Task { await save() }
                }.disabled(busy || openedScope != accountScope() || (ending ? selectedEnd == nil : severity == nil))
                    .accessibilityIdentifier("migraine-action-save")
            }
            .navigationTitle(ending ? "End migraine" : "Update severity").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Cancel") { dismiss() }.disabled(busy) }
            .interactiveDismissDisabled(busy)
        }
    }
    private func save() async {
        guard !busy else { return }
        let timestamp = submittedAt ?? (ending ? selectedEnd! : Date()); submittedAt = timestamp
        busy = true; defer { busy = false }
        do {
            let response = try await api.updateCurrentSymptom(episodeId: item.id, state: ending ? .resolved : nil,
                severity: ending ? nil : severity, tsUtc: timestamp,
                validateRequest: { try MigraineFollowUpWorkflow.checkAccount(openedScope, current: accountScope) })
            try MigraineFollowUpWorkflow.checkAccount(openedScope, current: accountScope)
            guard response.ok == true, let saved = response.payload, saved.id == item.id,
                  ending ? saved.currentState == .resolved : saved.severity == severity else { throw MigraineSaveError.invalidResponse }
            NotificationCenter.default.post(name: .symptomEpisodesDidChange, object: nil); dismiss()
        } catch {
            message = "This update could not be confirmed. Retry the same update or close and refresh the saved episode."
            if openedScope != accountScope() { message = MigraineDraftError.accountChanged.localizedDescription }
        }
    }
}
