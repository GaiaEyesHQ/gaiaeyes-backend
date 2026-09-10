import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineHistoryTests {
    private let start = Date(timeIntervalSince1970: 1_788_220_800) // September 1 UTC
    private func date(_ text: String) -> Date { ISO8601DateFormatter().date(from: text)! }
    private func episode(_ id: Int, start: Date, end: Date? = nil, status: String = "open") -> MigraineHistoryEpisode {
        MigraineHistoryEpisode(id: String(format: "00000000-0000-4000-8000-%012d", id), startedAt: start,
            endedAt: end, state: status == "open" ? "ongoing" : "resolved", endStatus: status, severity: 5, notePreview: nil)
    }

    @Test(arguments: ["America/Chicago", "America/New_York", "Europe/London", "UTC"])
    func calendarBoundariesAndEpisodeDayMatching(timezone: String) {
        let calendar = MigraineHistoryDates.calendar(timeZone: TimeZone(identifier: timezone)!)
        for text in ["2026-03-08T12:00:00Z", "2026-11-01T12:00:00Z", "2026-03-29T12:00:00Z", "2026-10-25T12:00:00Z"] {
            let day = calendar.dateInterval(of: .day, for: date(text))!
            let month = MigraineHistoryDates.month(containing: day.start, calendar: calendar)
            let days = MigraineHistoryDates.days(in: month, calendar: calendar)
            #expect(days.count == calendar.range(of: .day, in: .month, for: day.start)!.count)
            #expect(Set(days).count == days.count)
            let crossing = episode(1, start: day.start.addingTimeInterval(-3600), end: day.start.addingTimeInterval(3600), status: "recorded")
            #expect(crossing.matches(day, asOf: day.end))
            #expect(!episode(2, start: crossing.startedAt, end: day.start, status: "recorded").matches(day, asOf: day.end))
            #expect(!episode(3, start: day.end).matches(day, asOf: day.end))
            #expect(!episode(4, start: crossing.startedAt, status: "unknown").matches(day, asOf: day.end))
            #expect(episode(5, start: day.start, end: day.start, status: "recorded").matches(day, asOf: day.end))
        }
        if timezone == "America/Chicago" {
            #expect(calendar.dateInterval(of: .day, for: date("2026-03-08T12:00:00Z"))!.duration == 23 * 3600)
            #expect(calendar.dateInterval(of: .day, for: date("2026-11-01T12:00:00Z"))!.duration == 25 * 3600)
            let day = calendar.dateInterval(of: .day, for: date("2026-09-01T04:30:00Z"))!
            #expect(calendar.component(.day, from: day.start) == 31)
        }
    }

    @Test
    func defaultAndReleaseGate() {
        #expect(!MigraineCalendarFeature.resolve(isDebugBuild: true, arguments: []))
        #expect(!MigraineCalendarFeature.resolve(isDebugBuild: false, arguments: ["-gaia-enable-migraine-calendar"]))
        #expect(MigraineCalendarFeature.resolve(isDebugBuild: true, arguments: ["-gaia-enable-migraine-calendar"]))
    }

    @Test
    func decodeActualDisposableBackendPageThroughAPIClient() async throws {
        let server = MigraineFixtureServer(scenario: "calendar-backend-json")
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/migraine_history_backend_page.json")
        server.historyPageData = try Data(contentsOf: source)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let range = DateInterval(start: date("2026-09-01T00:00:00Z"), end: date("2026-10-01T00:00:00Z"))
        let response = try await api.fetchMigraineHistory(range: range, cursor: nil, validateRequest: {})
        let page = try #require(response.payload)
        #expect(page.complete && page.nextCursor == nil && page.start == range.start && page.end == range.end)
        #expect(page.items.first?.id == "11111111-1111-4111-8111-111111111111")
        #expect(page.items.first?.endedAt == nil && page.items.first?.notePreview == nil)
        #expect(page.asOf > range.start && page.items.first?.startedAt == date("2026-09-01T01:00:00Z"))
    }

    @Test
    func accountChangeDuringGetAuthorizationPreventsTheHistoryRequest() async {
        let server = MigraineFixtureServer(scenario: "calendar-success")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var scope = "a"
        api.bearerProvider = { scope = "b"; return "synthetic-token" }
        let store = MigraineHistoryStore(api: api, accountScope: { scope })
        await store.load(range: DateInterval(start: start, duration: 86400 * 30), scope: "a")
        #expect(store.items.isEmpty && !store.complete)
        #expect(!server.requests.contains { $0.url?.path == "/v1/symptoms/migraine/history" })
    }

    @Test(arguments: ["calendar-error", "calendar-conflict", "calendar-pagination", "calendar-pending-account"])
    func actualTransportRecovery(scenario: String) async {
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var scope = "fixture-account"
        let store = MigraineHistoryStore(api: api, accountScope: { scope })
        let range = DateInterval(start: date("2026-09-01T05:00:00Z"), end: date("2026-10-01T05:00:00Z"))
        if scenario == "calendar-pending-account" {
            scope = "different-fixture-account"; api.devUserId = scope
            await store.load(range: range, scope: scope)
            #expect(store.complete, Comment(rawValue: store.errorMessage ?? "still loading"))
            #expect(store.items.isEmpty)
        } else {
            await store.load(range: range, scope: scope)
            #expect(!store.complete && store.errorMessage != nil)
            await store.load(range: range, scope: scope, restart: scenario != "calendar-pagination")
            #expect(store.complete, Comment(rawValue: store.errorMessage ?? "still loading"))
            #expect(store.items.count == 2)
        }
    }

    @Test
    func partialPageFailureRetriesWithoutDroppingOtherEpisodes() async {
        let range = DateInterval(start: start, duration: 86400 * 30)
        var failed = false
        var cursors: [String?] = []
        let store = MigraineHistoryStore(accountScope: { "a" }) { range, cursor, validate in
            try validate(); cursors.append(cursor)
            if cursor != nil && !failed { failed = true; throw URLError(.notConnectedToInternet) }
            return MigraineHistoryPage(items: [episode(cursor == nil ? 1 : 2, start: start)], start: range.start,
                end: range.end, asOf: range.end, snapshot: "same", nextCursor: cursor == nil ? "page2" : nil, complete: cursor != nil)
        }
        await store.load(range: range, scope: "a")
        #expect(store.items.count == 1 && !store.complete && store.errorMessage != nil)
        await store.load(range: range, scope: "a", restart: false)
        #expect(store.items.count == 2 && store.complete && store.errorMessage == nil)
        #expect(cursors == [nil, "page2", "page2"])
    }

    @Test(arguments: ["account", "month"])
    func lateResponsesNeverReplaceChangedSelection(change: String) async {
        let range = DateInterval(start: start, duration: 86400 * 30)
        var scope = "a"
        var pending: CheckedContinuation<MigraineHistoryPage, Never>?
        let store = MigraineHistoryStore(accountScope: { scope }) { request, _, validate in
            try validate()
            if request == range && scope == "a" {
                return await withCheckedContinuation { pending = $0 }
            }
            return MigraineHistoryPage(items: [], start: request.start, end: request.end, asOf: request.end,
                snapshot: "new", nextCursor: nil, complete: true)
        }
        let old = Task { await store.load(range: range, scope: "a") }
        while pending == nil { await Task.yield() }
        if change == "account" { scope = "b" }
        let newRange = change == "month" ? DateInterval(start: range.end, duration: 86400 * 31) : range
        await store.load(range: newRange, scope: scope)
        pending!.resume(returning: MigraineHistoryPage(items: [episode(1, start: start)], start: range.start,
            end: range.end, asOf: range.end, snapshot: "old", nextCursor: nil, complete: true))
        await old.value
        #expect(store.items.isEmpty && store.complete && store.scope == scope && store.range == newRange)
    }

    @Test(arguments: ["conflict", "duplicate", "range", "snapshot", "cursor-loop"])
    func invalidOrChangedPagesCannotCompleteTheCalendar(failure: String) async {
        let range = DateInterval(start: start, duration: 86400 * 30)
        let store = MigraineHistoryStore(accountScope: { "a" }) { range, cursor, validate in
            try validate()
            if cursor != nil && failure == "conflict" { throw APIError.server(code: 409, body: "changed") }
            return MigraineHistoryPage(items: [episode(cursor == nil || failure == "duplicate" ? 1 : 2, start: start)],
                start: failure == "range" ? range.start.addingTimeInterval(1) : range.start, end: range.end, asOf: range.end,
                snapshot: cursor != nil && failure == "snapshot" ? "changed" : "same",
                nextCursor: cursor == nil || failure == "cursor-loop" ? "page2" : nil,
                complete: cursor != nil && failure != "cursor-loop")
        }
        await store.load(range: range, scope: "a")
        #expect(!store.complete && store.errorMessage != nil)
        if failure == "conflict" { #expect(store.items.isEmpty) }
    }
}
