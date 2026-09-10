import Foundation

// A retained request is a complete replacement patch, never a fresh add intent.
// Only a matching response or an explicit reviewed-version decision resolves it.
struct MigraineDetailSaveRecovery {
    struct Pending {
        let edit: MigraineStructuredEdit
        let episodeId: String
        let accountScope: String
    }
    private(set) var pending: Pending?
    private(set) var uncertain = false
    private(set) var needsConflictReload = false
    private(set) var needsUncertainReview = false
    private(set) var reviewed: MigraineEpisodeDetail?
    private(set) var setAsideRequest: Pending?

    mutating func request(_ edit: MigraineStructuredEdit, episodeId: String, accountScope: String) throws -> Pending {
        if let pending {
            guard pending.episodeId == episodeId, pending.accountScope == accountScope else { throw MigraineDraftError.accountChanged }
            return pending
        }
        let request = Pending(edit: edit, episodeId: episodeId, accountScope: accountScope)
        pending = request; uncertain = false; needsConflictReload = false; needsUncertainReview = false; reviewed = nil
        return request
    }

    mutating func failed(_ error: Error) {
        guard pending != nil else { return } // Local validation never creates a pending request.
        if !uncertain, case APIError.server(let code, _) = error, code == 409 || code == 422 {
            pending = nil; needsConflictReload = code == 409
            return
        }
        uncertain = true
        if case APIError.server(let code, _) = error, code == 409 { needsUncertainReview = true }
    }

    mutating func acknowledge(_ detail: MigraineEpisodeDetail, accountScope: String) throws {
        guard let pending, pending.accountScope == accountScope, pending.episodeId == detail.episode.episodeId else {
            throw MigraineDraftError.accountChanged
        }
        guard pending.edit.matches(detail) else { throw MigraineSaveError.invalidResponse }
        self.pending = nil; uncertain = false; needsUncertainReview = false; needsConflictReload = false; reviewed = nil
    }

    mutating func review(_ detail: MigraineEpisodeDetail, accountScope: String) throws {
        guard let pending, pending.accountScope == accountScope, pending.episodeId == detail.episode.episodeId else {
            throw MigraineDraftError.accountChanged
        }
        guard needsUncertainReview, detail.revision >= pending.edit.expectedRevision else { throw MigraineSaveError.invalidResponse }
        reviewed = detail // A GET is not an acknowledgement and must not rebase the add draft.
    }

    mutating func useReviewedVersion(accountScope: String) throws -> MigraineEpisodeDetail {
        guard let pending, pending.accountScope == accountScope else { throw MigraineDraftError.accountChanged }
        guard let reviewed, reviewed.episode.episodeId == pending.episodeId else { throw MigraineSaveError.invalidResponse }
        setAsideRequest = pending // Retain the exact request even after this explicit local choice.
        self.pending = nil; uncertain = false; needsUncertainReview = false; needsConflictReload = false; self.reviewed = nil
        return reviewed
    }

    mutating func conflictReloaded() { needsConflictReload = false }
    mutating func requireConflictReload() { if pending == nil { needsConflictReload = true } }
}

enum MigraineSaveError: Error, LocalizedError {
    case unconfirmed
    case invalidResponse
    case conflict
    case rejected

    var errorDescription: String? {
        switch self {
        case .unconfirmed:
            return "The save could not be confirmed. Your answers are still here. Retry without changing them to confirm the same response."
        case .invalidResponse:
            return "The server did not confirm this response. Your answers are still here."
        case .conflict:
            return "This migraine changed since you opened it. These answers have not been saved and are still here."
        case .rejected:
            return "Some answers could not be saved. Your changes are still here; review them and try again."
        }
    }
}

/// Shared by the actual sheet/history editor and local injected-response tests.
/// A detail GET has no receipt for the specific prompt/choice/time bucket. It
/// cannot turn a failed POST into success, even when its contents happen to match.
@MainActor
enum MigraineFollowUpWorkflow {
    static func accountScope() -> String {
        let value = AuthManager.shared.currentSupabaseUserId()?.trimmingCharacters(in: .whitespacesAndNewlines)
        return value?.isEmpty == false ? value! : "anonymous"
    }

    static func checkAccount(_ expected: String, current: @MainActor () -> String) throws {
        try Task.checkCancellation()
        guard expected == current() else { throw MigraineDraftError.accountChanged }
    }

    static func submit(
        api: APIClient, promptId: String, episodeId: String, state: CurrentSymptomState,
        detailChoice: String?, noteText: String?, timeBucket: String?, timestamp: Date,
        edit: MigraineStructuredEdit?, accountScope: String, currentAccountScope: @escaping @MainActor () -> String
    ) async throws -> SymptomFollowUpResult {
        try checkAccount(accountScope, current: currentAccountScope)
        do {
            let response = try await api.respondSymptomFollowUp(
                promptId: promptId, state: state, detailChoice: detailChoice,
                noteText: noteText, timeBucket: timeBucket, tsUtc: timestamp, migraine: edit,
                validateRequest: { try checkAccount(accountScope, current: currentAccountScope) }
            )
            try checkAccount(accountScope, current: currentAccountScope)
            guard response.ok != false, let saved = response.payload,
                  saved.prompt.id == promptId, saved.prompt.episodeId == episodeId,
                  saved.prompt.status == "answered", saved.episode.id == episodeId,
                  saved.episode.currentState == state,
                  saved.episode.pendingFollowUp?.id != promptId else {
                throw MigraineSaveError.invalidResponse
            }
            if let edit {
                guard let detail = saved.migraineDetail,
                      detail.episode.episodeId == episodeId,
                      detail.episode.state == state.rawValue,
                      edit.matches(detail) else { throw MigraineSaveError.invalidResponse }
            }
            return saved
        } catch {
            try checkAccount(accountScope, current: currentAccountScope)
            if let urlError = error as? URLError,
               [.timedOut, .networkConnectionLost].contains(urlError.code) {
                throw MigraineSaveError.unconfirmed
            }
            throw displayError(error)
        }
    }

    static func saveDetails(api: APIClient, episodeId: String, edit: MigraineStructuredEdit,
                            accountScope: String, currentAccountScope: @escaping @MainActor () -> String) async throws -> MigraineEpisodeDetail {
        try checkAccount(accountScope, current: currentAccountScope)
        let response = try await api.updateMigraineEpisodeDetail(episodeId: episodeId, edit: edit,
            validateRequest: { try checkAccount(accountScope, current: currentAccountScope) })
        try checkAccount(accountScope, current: currentAccountScope)
        guard response.ok != false, let saved = response.payload,
              saved.episode.episodeId == episodeId, edit.matches(saved) else {
            throw MigraineSaveError.invalidResponse
        }
        return saved
    }

    private static func displayError(_ error: Error) -> Error {
        guard case let APIError.server(code, _) = error else { return error }
        switch code {
        case 409: return MigraineSaveError.conflict
        case 422: return MigraineSaveError.rejected
        default: return MigraineSaveError.invalidResponse
        }
    }

    static func isUnsupportedCapability(_ error: Error) -> Bool {
        guard case let APIError.server(code, body) = error,
              let data = body.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = object["detail"] as? String else { return false }
        return (code == 404 && detail == "Not Found")
            || (code == 503 && detail == "structured migraine detail storage is not installed")
    }
}
