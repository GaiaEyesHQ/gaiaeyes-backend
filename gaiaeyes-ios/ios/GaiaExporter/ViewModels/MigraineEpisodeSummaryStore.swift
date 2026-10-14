import Foundation
import Combine

@MainActor
final class MigraineEpisodeSummaryStore: ObservableObject {
    typealias Fetch = (String, @escaping @MainActor () throws -> Void) async throws -> MigraineEpisodeDetail
    @Published private(set) var summary: MigraineEpisodeSummary?
    @Published private(set) var timeline: [CurrentSymptomTimelineEntry] = []
    @Published private(set) var timelineLoaded = false
    @Published private(set) var timelineError: String?
    @Published private(set) var highestRecordedSeverity: Int?
    private var fetchTimeline: ((String, @escaping @MainActor () throws -> Void) async throws -> [CurrentSymptomTimelineEntry])?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    private(set) var episodeID: String?
    private(set) var scope: String?
    private var generation = UUID()
    private let fetch: Fetch
    private let accountScope: @MainActor () -> String

    init(api: APIClient, accountScope: @escaping @MainActor () -> String) {
        self.accountScope = accountScope
        fetchTimeline = { id, validate in
            let response = try await api.fetchMigraineEpisodeTimeline(episodeId: id, validateRequest: validate)
            guard response.ok == true, let entries = response.payload,
                  entries.allSatisfy({ $0.episodeId == id && $0.symptomCode == "MIGRAINE"
                      && ($0.severity.map { (0...10).contains($0) } ?? true)
                      && MigraineFollowUpDraft.parseDate($0.occurredAt) != nil }) else { throw MigraineSaveError.invalidResponse }
            return entries
        }
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
        timeline = []; timelineLoaded = false; timelineError = nil; highestRecordedSeverity = nil
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
            if let fetchTimeline {
                do {
                    let entries = try await fetchTimeline(requestedID, validate)
                    try validate()
                    timeline = entries.sorted { MigraineFollowUpDraft.parseDate($0.occurredAt)! > MigraineFollowUpDraft.parseDate($1.occurredAt)! }
                    highestRecordedSeverity = (entries.compactMap(\.severity) + [detail.episode.severity].compactMap { $0 }).max()
                    timelineLoaded = true
                } catch {
                    try validate()
                    timelineError = "The full episode timeline could not be loaded. Highest recorded severity is unavailable. Refresh to retry."
                }
            }
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
