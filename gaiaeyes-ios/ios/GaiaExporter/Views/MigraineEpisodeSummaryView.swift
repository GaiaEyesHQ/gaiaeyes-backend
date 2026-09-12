import SwiftUI

struct MigraineEpisodeSummaryView: View {
    let episodeID: String
    let timeZone: TimeZone
    let accountScopeProvider: @MainActor () -> String
    @State private var openedAccount: String
    @StateObject private var store: MigraineEpisodeSummaryStore
    @Environment(\.dismiss) private var dismiss

    init(api: APIClient, episodeID: String, accountScope: String, timeZone: TimeZone,
         accountScopeProvider: @escaping @MainActor () -> String) {
        self.episodeID = episodeID; self.timeZone = timeZone; self.accountScopeProvider = accountScopeProvider
        _openedAccount = State(initialValue: accountScope)
        _store = StateObject(wrappedValue: MigraineEpisodeSummaryStore(api: api, accountScope: accountScopeProvider))
    }

    private var sameAccount: Bool { accountScopeProvider() == openedAccount }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if !MigraineCalendarFeature.isEnabled {
                        Text("Migraine summaries are not enabled.")
                    } else if !sameAccount {
                        Text("Your signed-in account changed. Close this summary and open it again.")
                            .accessibilityIdentifier("migraine-summary-account-error")
                    } else if store.isLoading {
                        ProgressView("Loading saved episode…").accessibilityIdentifier("migraine-summary-loading")
                    } else if store.scope == openedAccount, store.episodeID == episodeID, let summary = store.summary {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Saved episode").font(.title2.bold()).accessibilityIdentifier("migraine-summary-saved")
                            Text("Times shown in \(summary.displayTimezone)")
                        }.font(.caption).foregroundStyle(.secondary)
                        section("Episode", entries: summary.timing, empty: "Not recorded", id: "timing")
                        section("Medicines", entries: summary.medicines, empty: "No medicine entries recorded", id: "medicines")
                        section("Recorded early signs", entries: summary.earlySigns, empty: "Not recorded", id: "signs")
                        section("Recorded context", entries: summary.contexts, empty: "Not recorded", id: "contexts",
                                introduction: "Recorded context does not establish a cause.")
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Episode notes").font(.headline)
                            Text(summary.notes).fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled).accessibilityIdentifier("migraine-summary-notes")
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    } else if let message = store.errorMessage {
                        Text(message).foregroundStyle(.orange).accessibilityIdentifier("migraine-summary-error")
                        Button("Retry summary") { Task { await load() } }.accessibilityIdentifier("migraine-summary-retry")
                    }
                }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Color(red: 0.03, green: 0.05, blue: 0.09).ignoresSafeArea())
            .foregroundStyle(.white).tint(.cyan)
            .navigationTitle("Migraine summary").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { store.invalidate(); dismiss() }.accessibilityIdentifier("migraine-summary-done")
                }
                ToolbarItem(placement: .primaryAction) {
                    Button("Refresh") { Task { await load() } }
                        .disabled(!sameAccount || !MigraineCalendarFeature.isEnabled)
                        .accessibilityIdentifier("migraine-summary-refresh")
                }
#if DEBUG
                if ProcessInfo.processInfo.arguments.contains("calendar-summary-account") {
                    ToolbarItem(placement: .bottomBar) {
                        Button("Switch synthetic account") {
                            NotificationCenter.default.post(name: Notification.Name("MigraineSummarySyntheticAccountChange"), object: nil)
                            MigraineFixtureURLProtocol.server?.releaseReplies()
                        }.accessibilityIdentifier("migraine-summary-fixture-account")
                    }
                }
#endif
            }
            .task(id: episodeID) { await load() }
            .onChange(of: accountScopeProvider()) { _, _ in store.invalidate() }
            .onDisappear { store.invalidate() }
        }
    }

    private func load() async {
        guard sameAccount, MigraineCalendarFeature.isEnabled else { store.invalidate(); return }
        await store.load(episodeID: episodeID, scope: openedAccount, timeZone: timeZone)
    }

    private func section(_ title: String, entries: [MigraineEpisodeSummary.Entry], empty: String, id: String,
                         introduction: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.title3.bold()).accessibilityIdentifier("migraine-summary-\(id)-heading")
            if let introduction { Text(introduction).font(.caption).foregroundStyle(.secondary) }
            if entries.isEmpty { Text(empty).accessibilityIdentifier("migraine-summary-\(id)-empty") }
            ForEach(entries) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    Text(entry.title).font(.headline).accessibilityIdentifier("migraine-summary-\(entry.id)-title")
                    ForEach(Array(entry.lines.enumerated()), id: \.offset) { index, line in
                        Text(line).fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("migraine-summary-\(entry.id)-line-\(index)")
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
