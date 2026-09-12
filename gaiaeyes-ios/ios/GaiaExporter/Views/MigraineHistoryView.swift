import SwiftUI

struct MigraineHistoryView: View {
    let api: APIClient
    let accountScope: String
    let accountScopeProvider: @MainActor () -> String
    private let calendar: Calendar
    @StateObject private var store: MigraineHistoryStore
    @State private var selectedDay: Date
    @State private var selectedEpisode: MigraineHistoryEpisode?
    @State private var summaryEpisode: MigraineHistoryEpisode?
    @State private var editorIsSaving = false

    init(api: APIClient, accountScope: String,
         accountScopeProvider: @escaping @MainActor () -> String = { MigraineFollowUpWorkflow.accountScope() },
         initialDate: Date = Date(), timeZone: TimeZone = .current) {
        self.api = api; self.accountScope = accountScope; self.accountScopeProvider = accountScopeProvider
        calendar = MigraineHistoryDates.calendar(timeZone: timeZone)
        _selectedDay = State(initialValue: initialDate)
        _store = StateObject(wrappedValue: MigraineHistoryStore(api: api, accountScope: accountScopeProvider))
    }

    private var month: DateInterval { MigraineHistoryDates.month(containing: selectedDay, calendar: calendar) }
    private var currentData: Bool { store.scope == accountScope && store.range == month }
    private var day: DateInterval { calendar.dateInterval(of: .day, for: selectedDay)! }
    private var entries: [MigraineHistoryEpisode] {
        guard currentData, let asOf = store.asOf else { return [] }
        return store.items.filter { $0.matches(day, asOf: asOf) }
    }
    private var loadKey: String { "\(accountScope):\(month.start.timeIntervalSince1970)" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Button { moveMonth(-1) } label: { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                        .accessibilityLabel("Previous month").accessibilityIdentifier("migraine-calendar-previous")
                    Spacer()
                    Text(formatted(month.start, "MMMM yyyy")).font(.headline)
                        .accessibilityIdentifier("migraine-calendar-month")
                    Spacer()
                    Button { moveMonth(1) } label: { Image(systemName: "chevron.right").frame(width: 44, height: 44) }
                        .accessibilityLabel("Next month").accessibilityIdentifier("migraine-calendar-next")
                }
                calendarGrid
                Text("Times shown in \(calendar.timeZone.identifier)").font(.caption).foregroundStyle(.secondary)
                if currentData, store.complete, let asOf = store.asOf {
                    Text("History as of \(formatted(asOf, "MMM d, yyyy 'at' h:mm a"))")
                        .font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("migraine-calendar-asof")
                }
                if !currentData || store.isLoading {
                    ProgressView(store.items.isEmpty ? "Loading history…" : "Loading more history…")
                        .accessibilityIdentifier("migraine-calendar-loading")
                }
                if currentData, let message = store.errorMessage {
                    Text(message).foregroundStyle(.orange).accessibilityIdentifier("migraine-calendar-error")
                    Button("Retry history") { Task { await load(restart: false) } }
                        .accessibilityIdentifier("migraine-calendar-retry")
                }
                Text(formatted(selectedDay, "EEEE, MMMM d, yyyy")).font(.headline)
                    .accessibilityIdentifier("migraine-calendar-selected-day")
                if currentData && store.complete {
                    Text(entries.isEmpty ? "No migraine episodes recorded for this day." : "\(entries.count) migraine episode\(entries.count == 1 ? "" : "s")")
                        .font(.subheadline).accessibilityIdentifier("migraine-calendar-count")
                } else {
                    Text("This day's history is not complete yet.").font(.subheadline)
                        .accessibilityIdentifier("migraine-calendar-incomplete")
                }
                ForEach(entries) { episode in
                    Button { selectedEpisode = episode } label: {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Text("Migraine").font(.headline)
                                Spacer()
                                if let severity = episode.severity { Text("\(severity)/10") }
                                Image(systemName: "chevron.right")
                            }
                            Text("Started \(formatted(episode.startedAt, "MMM d, yyyy 'at' h:mm a"))")
                            if let endedAt = episode.endedAt, episode.endStatus == "recorded" {
                                Text("Ended \(formatted(endedAt, "MMM d, yyyy 'at' h:mm a"))")
                            } else {
                                Text(episode.endStatus == "open" ? "No end recorded · \(episode.state.capitalized)" : "End time unknown · \(episode.state.capitalized)")
                            }
                            if let note = episode.notePreview, !note.isEmpty { Text(note).lineLimit(3) }
                        }
                        .font(.subheadline).frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14).background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 16))
                    }
                    .buttonStyle(.plain).accessibilityIdentifier("migraine-calendar-episode-\(episode.id)")
                    .accessibilityHint("Edit this saved episode")
                    if MigraineCalendarFeature.isEnabled {
                        Button { summaryEpisode = episode } label: { Label("View summary", systemImage: "doc.text") }
                            .accessibilityLabel("View summary for migraine started \(formatted(episode.startedAt, "MMM d 'at' h:mm a"))")
                            .accessibilityIdentifier("migraine-calendar-summary-\(episode.id)")
                            .disabled(editorIsSaving || selectedEpisode != nil)
                    }
                }
            }.padding(16)
        }
        .background(Color(red: 0.03, green: 0.05, blue: 0.09).ignoresSafeArea())
        .foregroundStyle(.white).tint(.cyan)
        .navigationTitle("Migraine calendar").navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Refresh") { Task { await load() } }.accessibilityIdentifier("migraine-calendar-refresh") }
        .task(id: loadKey) { await load() }
        .onChange(of: accountScope) { _, _ in selectedEpisode = nil; summaryEpisode = nil }
        .refreshable { await load() }
        .sheet(item: $selectedEpisode, onDismiss: { editorIsSaving = false; Task { await load() } }) { episode in
            NavigationStack {
                HistoricalSymptomEditor(api: api, episodeId: episode.id, accountScopeProvider: accountScopeProvider,
                    onSaved: { Task { await load() } }, onBusyChange: { editorIsSaving = $0 })
                    .toolbar {
                        Button("Done") { selectedEpisode = nil }.disabled(editorIsSaving)
                            .accessibilityIdentifier("migraine-calendar-editor-done")
#if DEBUG
                        if (ProcessInfo.processInfo.arguments.contains("calendar-save-pending") || ProcessInfo.processInfo.arguments.contains("calendar-time-delayed")) {
                            Button("Release local response") { MigraineFixtureURLProtocol.server?.releaseReplies() }
                                .accessibilityIdentifier("migraine-calendar-release-save")
                        }
#endif
                    }
            }
            .interactiveDismissDisabled(editorIsSaving)
        }
        .sheet(item: $summaryEpisode) { episode in
            MigraineEpisodeSummaryView(api: api, episodeID: episode.id, accountScope: accountScope,
                                       timeZone: calendar.timeZone, accountScopeProvider: accountScopeProvider)
                .id(episode.id)
        }
    }

    private var calendarGrid: some View {
        let days = MigraineHistoryDates.days(in: month, calendar: calendar)
        let offset = (calendar.component(.weekday, from: month.start) - calendar.firstWeekday + 7) % 7
        return LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 7), spacing: 4) {
            ForEach(0..<7, id: \.self) { index in
                Text(calendar.veryShortStandaloneWeekdaySymbols[(index + calendar.firstWeekday - 1) % 7])
                    .font(.caption).foregroundStyle(.secondary).accessibilityHidden(true)
            }
            ForEach(0..<offset, id: \.self) { _ in Color.clear.frame(height: 48) }
            ForEach(days, id: \.self) { date in
                let selected = calendar.isDate(date, inSameDayAs: selectedDay)
                let interval = calendar.dateInterval(of: .day, for: date)!
                let count = currentData && store.complete ? store.items.filter { $0.matches(interval, asOf: store.asOf!) }.count : nil
                Button { selectedDay = date } label: {
                    VStack(spacing: 2) {
                        Text("\(calendar.component(.day, from: date))").fontWeight(selected ? .bold : .regular)
                        Text(count.map { $0 > 0 ? "\($0)" : " " } ?? "·").font(.caption2)
                    }
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .background(selected ? Color.cyan.opacity(0.25) : .white.opacity(0.04), in: RoundedRectangle(cornerRadius: 9))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(formatted(date, "EEEE, MMMM d, yyyy"))
                .accessibilityValue(count.map { "\($0) episodes" } ?? "History incomplete")
                .accessibilityIdentifier("migraine-calendar-day-\(formatted(date, "yyyy-MM-dd"))")
            }
        }
    }

    private func formatted(_ date: Date, _ format: String) -> String {
        let formatter = DateFormatter(); formatter.calendar = calendar; formatter.timeZone = calendar.timeZone
        formatter.dateFormat = format
        return formatter.string(from: date)
    }
    private func moveMonth(_ delta: Int) {
        selectedDay = calendar.date(byAdding: .month, value: delta, to: month.start)!
    }
    private func load(restart: Bool = true) async { await store.load(range: month, scope: accountScope, restart: restart) }
}
