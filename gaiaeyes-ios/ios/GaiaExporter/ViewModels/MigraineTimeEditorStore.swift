import Foundation
import Combine

@MainActor
final class MigraineTimeEditorStore: ObservableObject {
    @Published private(set) var context: MigraineTimeContext?
    @Published private(set) var draft: MigraineTimeDraft?
    @Published private(set) var isSaving = false
    @Published private(set) var isLoading = false
    @Published private(set) var message: String?
    @Published private(set) var needsReload = false
    @Published var externalBusy = false
    @Published private(set) var pendingRequest: MigraineTimeRequest?
    private let api: APIClient
    private let episodeId: String
    private let accountScope: @MainActor () -> String
    private var loadedScope: String?
    private var generation = UUID()
    var inputsLocked: Bool { isSaving || isLoading || externalBusy }

    init(api: APIClient, episodeId: String, accountScope: @escaping @MainActor () -> String) {
        self.api = api; self.episodeId = episodeId; self.accountScope = accountScope
    }
    func edit(_ change: (inout MigraineTimeDraft) -> Void) {
        guard !inputsLocked, pendingRequest == nil, var value = draft else { return }
        change(&value); draft = value
    }
    func invalidate() {
        generation = UUID(); context = nil; draft = nil; loadedScope = nil; pendingRequest = nil
        isSaving = false; isLoading = false; needsReload = true
        message = "Your signed-in account changed. Close this editor and open it again."
    }
    private func check(_ token: UUID, _ scope: String) throws {
        try MigraineFollowUpWorkflow.checkAccount(scope, current: accountScope)
        guard generation == token else { throw MigraineDraftError.accountChanged }
    }
    func load(preservingDraft: Bool = false) async {
        guard !isSaving, !externalBusy else { return }
        let token = UUID(); generation = token
        let scope = loadedScope ?? accountScope(); loadedScope = scope
        isLoading = true
        defer { if token == generation { isLoading = false } }
        do {
            try check(token, scope)
            let response = try await api.fetchMigraineTimeContext(episodeId: episodeId,
                validateRequest: { try self.check(token, scope) })
            try check(token, scope)
            guard response.ok != false, let value = response.payload,
                  value.episode.episodeId == episodeId,
                  MigraineFollowUpDraft.parseDate(value.canonicalUpdatedAt) != nil else { throw MigraineSaveError.invalidResponse }
            context = value
            if !preservingDraft || draft == nil { draft = MigraineTimeDraft(context: value) }
            pendingRequest = nil; needsReload = false
            message = preservingDraft ? "Saved version reloaded. Your intended changes are still here; review them before saving." : nil
        } catch {
            guard token == generation else { return }
            if scope != accountScope() { invalidate(); return }
            message = "Saved times could not be loaded. Your changes are still here."
            needsReload = true
        }
    }
    func otherDetailsSaved() async {
        if draft?.hasIntent == true || pendingRequest != nil {
            needsReload = true
            message = "Other details were saved. Reload the saved version before applying your time correction. Your changes are still here."
        } else { await load() }
    }
    func save() async -> MigraineTimeContext? {
        guard !inputsLocked, !needsReload, let context, let draft, let scope = loadedScope else { return nil }
        let token = generation
        do {
            let request = try pendingRequest ?? draft.request(base: context)
            try check(token, scope)
            pendingRequest = request; isSaving = true; message = nil
            defer { if generation == token { isSaving = false } }
            let response = try await api.correctMigraineTimes(episodeId: episodeId, correction: request,
                validateRequest: { try self.check(token, scope) })
            try check(token, scope)
            guard response.ok != false, let saved = response.payload,
                  request.confirms(saved, base: context) else { throw MigraineSaveError.invalidResponse }
            self.context = saved; self.draft = MigraineTimeDraft(context: saved); pendingRequest = nil
            let newer = saved.currentRevision != saved.appliedRevision || saved.currentCanonicalUpdatedAt != saved.canonicalUpdatedAt
            needsReload = newer
            message = newer ? "This correction was saved earlier; newer changes exist. Reload the current saved version."
                : saved.refresh?.status == "complete" ? "Migraine times saved." : "Migraine times saved. Some derived summaries still need refresh."
            return saved
        } catch {
            guard token == generation else { return nil }
            if scope != accountScope() { invalidate(); return nil }
            isSaving = false
            if case APIError.server(let code, _) = error, code == 409 || code == 422 {
                pendingRequest = nil; needsReload = code == 409
                message = code == 409 ? "The saved episode changed. Reload the saved version; your intended changes are still here."
                    : "Check the times and status. Your changes are still here."
            } else if let validation = error as? MigraineTimeError {
                pendingRequest = nil; message = validation.localizedDescription
            } else {
                message = "The save could not be confirmed. Retry the same correction, or reload the saved version before changing it."
            }
            return nil
        }
    }
}
