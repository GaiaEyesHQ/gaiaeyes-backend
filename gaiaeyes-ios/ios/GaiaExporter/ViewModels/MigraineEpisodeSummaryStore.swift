import Foundation
import Combine

@MainActor
final class MigraineEpisodeSummaryStore: ObservableObject {
    typealias Fetch = (String, @escaping @MainActor () throws -> Void) async throws -> MigraineEpisodeDetail
    @Published private(set) var summary: MigraineEpisodeSummary?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    private(set) var episodeID: String?
    private(set) var scope: String?
    private var generation = UUID()
    private let fetch: Fetch
    private let accountScope: @MainActor () -> String

    init(api: APIClient, accountScope: @escaping @MainActor () -> String) {
        self.accountScope = accountScope
        fetch = { id, validate in
            let response = try await api.fetchMigraineEpisodeDetail(episodeId: id, validateRequest: validate)
            guard response.ok == true, let detail = response.payload else { throw MigraineSaveError.invalidResponse }
            return detail
        }
    }

    init(accountScope: @escaping @MainActor () -> String, fetch: @escaping Fetch) {
        self.accountScope = accountScope; self.fetch = fetch
    }

    func invalidate() {
        generation = UUID(); summary = nil; isLoading = false; errorMessage = nil; episodeID = nil; scope = nil
    }

    func load(episodeID requestedID: String, scope requestedScope: String, timeZone: TimeZone) async {
        invalidate(); episodeID = requestedID; scope = requestedScope
        let token = generation
        let validate: @MainActor () throws -> Void = { [weak self] in
            try Task.checkCancellation()
            guard let self, self.generation == token, self.accountScope() == requestedScope else {
                throw MigraineDraftError.accountChanged
            }
        }
        isLoading = true
        defer { if generation == token { isLoading = false } }
        do {
            try validate()
            guard UUID(uuidString: requestedID) != nil else { throw MigraineSaveError.invalidResponse }
            let detail = try await fetch(requestedID, validate)
            try validate()
            summary = try MigraineEpisodeSummary(detail: detail, episodeID: requestedID, timeZone: timeZone)
        } catch {
            guard generation == token else { return }
            summary = nil
            if accountScope() != requestedScope {
                invalidate(); errorMessage = "Your signed-in account changed. Close this summary and open it again."
            } else if case MigraineEpisodeSummaryError.unavailable = error {
                errorMessage = "This saved episode is no longer available."
            } else if case APIError.server(let code, _) = error, code == 404 || code == 410 {
                errorMessage = "This saved episode is unavailable. It may have been removed, or this server may not support summaries yet."
            } else if case APIError.server(let code, _) = error, code == 501 || code == 503 {
                errorMessage = "Saved migraine details are not available on this server right now. Try again later."
            } else if error is DecodingError {
                errorMessage = "The saved episode response could not be read. Try again."
            } else if case MigraineSaveError.invalidResponse = error {
                errorMessage = "The saved episode response could not be read. Try again."
            } else if error is CancellationError || (error as? URLError)?.code == .cancelled {
                errorMessage = "Summary loading was cancelled. Retry to load the saved episode."
            } else {
                errorMessage = "The saved episode could not be loaded. Check your connection and try again."
            }
        }
    }
}
