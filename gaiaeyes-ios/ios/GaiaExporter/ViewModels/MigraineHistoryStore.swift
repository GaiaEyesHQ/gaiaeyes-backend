import Foundation
import Combine

@MainActor
final class MigraineHistoryStore: ObservableObject {
    typealias Fetch = (DateInterval, String?, @escaping @MainActor () throws -> Void) async throws -> MigraineHistoryPage
    @Published private(set) var items: [MigraineHistoryEpisode] = []
    @Published private(set) var isLoading = false
    @Published private(set) var complete = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var asOf: Date?
    private(set) var range: DateInterval?
    private(set) var scope: String?
    private var generation = UUID()
    private var nextCursor: String?
    private var snapshot: String?
    private var seenCursors: Set<String> = []
    private let fetch: Fetch
    private let accountScope: @MainActor () -> String

    init(api: APIClient, accountScope: @escaping @MainActor () -> String) {
        self.accountScope = accountScope
        fetch = { range, cursor, validate in
            let response = try await api.fetchMigraineHistory(range: range, cursor: cursor, validateRequest: validate)
            guard response.ok != false, let page = response.payload else { throw MigraineSaveError.invalidResponse }
            return page
        }
    }

    init(accountScope: @escaping @MainActor () -> String, fetch: @escaping Fetch) {
        self.accountScope = accountScope
        self.fetch = fetch
    }

    func invalidate() {
        generation = UUID()
        items = []; complete = false; isLoading = false; errorMessage = nil
        nextCursor = nil; snapshot = nil; asOf = nil; range = nil; scope = nil; seenCursors = []
    }

    func load(range requestedRange: DateInterval, scope requestedScope: String, restart: Bool = true) async {
        if restart {
            invalidate()
            range = requestedRange; scope = requestedScope
        } else {
            guard range == requestedRange, scope == requestedScope, !isLoading, !complete else { return }
        }
        let token = generation
        let validate: @MainActor () throws -> Void = { [weak self] in
            try Task.checkCancellation()
            guard let self, self.generation == token, self.accountScope() == requestedScope else {
                throw MigraineDraftError.accountChanged
            }
        }
        isLoading = true; errorMessage = nil
        defer { if token == generation { isLoading = false } }
        do {
            repeat {
                try validate()
                let page = try await fetch(requestedRange, nextCursor, validate)
                try validate()
                guard page.start == requestedRange.start, page.end == requestedRange.end,
                      !page.snapshot.isEmpty, page.complete == (page.nextCursor == nil),
                      snapshot == nil || (snapshot == page.snapshot && asOf == page.asOf),
                      page.nextCursor == nil || (!page.items.isEmpty && !seenCursors.contains(page.nextCursor!)),
                      Set(page.items.map(\.id)).count == page.items.count,
                      Set(items.map(\.id)).isDisjoint(with: page.items.map(\.id)),
                      page.items.allSatisfy({ UUID(uuidString: $0.id) != nil && ["recorded", "open", "unknown"].contains($0.endStatus)
                          && $0.matches(requestedRange, asOf: page.asOf) }) else {
                    throw MigraineSaveError.invalidResponse
                }
                snapshot = page.snapshot; asOf = page.asOf
                items.append(contentsOf: page.items)
                complete = page.complete; nextCursor = page.nextCursor
                if let nextCursor { seenCursors.insert(nextCursor) }
            } while !complete
        } catch {
            guard token == generation else { return }
            if accountScope() != requestedScope { invalidate(); return }
            if case APIError.server(409, _) = error {
                items = []; nextCursor = nil; snapshot = nil; asOf = nil; seenCursors = []
                errorMessage = "History changed while loading. Refresh this month to load the current episodes."
            } else if case APIError.server(let code, _) = error, code == 404 || code == 503 {
                errorMessage = "Migraine calendar history is not available on this server yet. Recent symptom history is still available."
            } else {
                errorMessage = items.isEmpty ? "History could not be loaded. Try again."
                    : "Some history is still missing. Retry to finish loading this month."
            }
            complete = false
        }
    }
}
