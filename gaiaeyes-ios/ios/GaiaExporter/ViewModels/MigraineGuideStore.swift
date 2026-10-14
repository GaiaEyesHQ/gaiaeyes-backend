import Foundation
import Combine

@MainActor
final class MigraineGuideStore: ObservableObject {
    @Published var draft: MigraineGuideDraft
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    @Published private(set) var ready = false
    let api: APIClient
    let scope: String
    let accountScope: @MainActor () -> String
    private var storageEpisodeID: String?
    private var completed = false
    private let defaults: UserDefaults

    init(api: APIClient, episodeID: String?, accountScope: @escaping @MainActor () -> String, defaults: UserDefaults = .standard) {
        self.api = api; self.accountScope = accountScope; self.scope = accountScope(); self.defaults = defaults
        storageEpisodeID = episodeID
        draft = MigraineGuideStorage.draft(scope: scope, episodeID: episodeID, defaults: defaults) ?? MigraineGuideDraft()
        if draft.episodeID == nil { draft.episodeID = episodeID }
        if episodeID != nil && draft.base == nil { draft.step = .symptoms }
    }
    var sameAccount: Bool { scope == accountScope() }
    var locked: Bool { busy || draft.inputsLocked || !sameAccount || !ready }
    func persist() {
        guard sameAccount, !completed else { return }
        do {
            try MigraineGuideStorage.save(draft, scope: scope, defaults: defaults)
            if storageEpisodeID != draft.episodeID {
                MigraineGuideStorage.remove(scope: scope, episodeID: storageEpisodeID, defaults: defaults)
                storageEpisodeID = draft.episodeID
            }
        } catch { message = "This draft could not be kept on this device. Keep this screen open and retry saving." }
    }
    func load() async {
        guard !ready, !busy else { return }
        guard sameAccount else { message = MigraineDraftError.accountChanged.localizedDescription; return }
        if draft.episodeID == nil || draft.base != nil { ready = true; return }
        busy = true; defer { busy = false }
        do {
            let detail = try await fetchDetail()
            if draft.reportedAt != nil || !draft.changed.isEmpty { try setBase(detail) }
            else { try draft.load(detail) }
            ready = true; persist()
        } catch { message = "Saved details could not be loaded. Retry before editing this episode." }
    }
    private func validate() throws { try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScope) }
    private func fetchDetail() async throws -> MigraineEpisodeDetail {
        guard let id = draft.episodeID else { throw MigraineSaveError.invalidResponse }
        let response = try await api.fetchMigraineEpisodeDetail(episodeId: id, validateRequest: { try self.validate() })
        try validate()
        guard response.ok == true, let value = response.payload, value.episode.episodeId == id else { throw MigraineSaveError.invalidResponse }
        return value
    }
    private func setBase(_ detail: MigraineEpisodeDetail) throws {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        draft.baseData = try encoder.encode(detail)
    }
    /// Frozen input is retained after an uncertain response; retry sends the same
    /// onset and structured revision. Never infer success from a subsequent GET.
    func save() async -> String? {
        guard !busy, sameAccount, ready else { return nil }
        busy = true; message = nil
        defer { busy = false }
        do {
            try validate()
            guard scope != "anonymous" && scope != "signed_out" else { throw MigraineGuideError.signedOut }
            guard let onset = draft.onset else { throw MigraineGuideError.onsetRequired }
            let reportedAt = draft.reportedAt ?? Date(); draft.reportedAt = reportedAt
            // Validate optional entries before creating the canonical episode.
            if draft.changed.contains("medicines") { _ = try draft.medicines.map { try $0.value(reportedAt: reportedAt) } }
            if draft.episodeID == nil {
                draft.pendingCreation = true; persist()
                let event = SymptomQueuedEvent(id: draft.id, symptomCode: "MIGRAINE", tsUtc: onset,
                                               severity: nil, freeText: nil)
                let receipt = try await api.postSymptomEvent(from: event, validateRequest: { try self.validate() })
                try validate()
                guard let id = receipt.episodeId else { throw MigraineSaveError.invalidResponse }
                draft.episodeID = id; draft.pendingCreation = false
                persist()
            }
            if draft.base == nil { try setBase(await fetchDetail()); persist() }
            let edit = try draft.edit()
            if edit.hasChanges {
                if draft.pendingEditData == nil { draft.pendingEditData = try JSONEncoder().encode(edit) }
                draft.pendingDetails = true; persist()
                let saved = try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: draft.episodeID!, edit: edit,
                    accountScope: scope, currentAccountScope: accountScope)
                try validate(); try setBase(saved)
                draft.changed = []; draft.pendingDetails = false; draft.pendingEditData = nil; persist()
            }
            if draft.severityChanged, let severity = draft.severity {
                draft.pendingSeverity = true; persist()
                let response = try await api.updateCurrentSymptom(episodeId: draft.episodeID!, severity: severity,
                    tsUtc: reportedAt, validateRequest: { try self.validate() })
                try validate()
                guard response.ok == true, let saved = response.payload,
                      saved.id == draft.episodeID, saved.severity == severity else { throw MigraineSaveError.invalidResponse }
                draft.severityChanged = false; draft.pendingSeverity = false; persist()
            }
            let id = draft.episodeID!
            MigraineGuideStorage.remove(scope: scope, episodeID: storageEpisodeID, defaults: defaults)
            NotificationCenter.default.post(name: .symptomEpisodesDidChange, object: nil)
            completed = true
            message = "Saved"
            return id
        } catch {
            if !sameAccount { message = MigraineDraftError.accountChanged.localizedDescription; return nil }
            if case APIError.server(let status, _) = error, status == 422 {
                draft.pendingCreation = false; draft.pendingDetails = false; draft.pendingEditData = nil; draft.pendingSeverity = false
            }
            persist()
            if draft.inputsLocked {
                message = "The save is not confirmed. Your answers are kept on this device. Retry the same save; it will not create another migraine."
                if case APIError.server(409, _) = error {
                    message = "This episode changed elsewhere. Your draft is kept. Review the saved summary before choosing which version to keep."
                }
            } else { message = error.localizedDescription }
            return nil
        }
    }
    func discardAndReload() async {
        guard sameAccount, !busy else { return }
        // Called only after the user explicitly chooses to discard this draft.
        MigraineGuideStorage.remove(scope: scope, episodeID: storageEpisodeID, defaults: defaults)
        draft = MigraineGuideDraft(); draft.episodeID = storageEpisodeID
        ready = false; message = nil; await load()
    }
}
