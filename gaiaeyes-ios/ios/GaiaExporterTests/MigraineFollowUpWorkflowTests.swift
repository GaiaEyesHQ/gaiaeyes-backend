import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineFollowUpWorkflowTests {
    private func draft() throws -> MigraineFollowUpDraft {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode(MigraineEpisodeDetail.self, from: MigraineFixtureServer.detailData)
        var draft = MigraineFollowUpDraft(accountScope: "a", promptId: "fixture-prompt",
            episodeId: detail.episode.episodeId, responseTimestamp: Date(timeIntervalSince1970: 1_788_839_400))
        try draft.apply(detail, forAccountScope: "a")
        return draft
    }

    private func submit(_ api: APIClient, draft: MigraineFollowUpDraft,
                        scope: @escaping () -> String = { "a" }) async throws -> SymptomFollowUpResult {
        let edit = try draft.makeStructuredEdit(currentAccountScope: "a")
            ?? MigraineStructuredEdit(expectedRevision: draft.expectedRevision, earlySigns: nil,
                                      contexts: nil, medicines: nil, notes: .retain)
        return try await MigraineFollowUpWorkflow.submit(api: api, promptId: draft.promptId,
            episodeId: draft.episodeId, state: .resolved, detailChoice: "head_pressure", noteText: edit.followUpNoteText,
            timeBucket: "later_same_day", timestamp: draft.responseTimestamp, edit: edit,
            accountScope: draft.accountScope, currentAccountScope: scope)
    }

    @Test(arguments: ["timeout", "committed-timeout"])
    func uncertainSaveKeepsDraftAndRetriesTheExactRequest(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var draft = try draft()
        draft.medicineChoice = .none
        draft.noteText = ""
        let retained = draft
        do { _ = try await submit(api, draft: draft); Issue.record("An uncertain POST must not report success") }
        catch { #expect(error is MigraineSaveError) }
        #expect(draft == retained)
        // No GET can prove a specific prompt answer, even after a server commit.
        #expect(server.requests.filter { $0.url!.path.hasSuffix("/migraine-detail") }.isEmpty)
        let saved = try await submit(api, draft: draft)
        #expect(saved.prompt.status == "answered")
        #expect(saved.episode.currentState == .resolved)
        #expect(saved.migraineDetail?.episode.medicines.isEmpty == true)
        #expect(saved.migraineDetail?.episode.notes == nil)
        let requests = server.requests.filter { $0.httpMethod == "POST" }
        #expect(requests.count == 2)
        let first = try JSONSerialization.jsonObject(with: requests[0].httpBody!) as! NSDictionary
        let second = try JSONSerialization.jsonObject(with: requests[1].httpBody!) as! NSDictionary
        #expect(first == second)
        #expect(first["time_bucket"] as? String == "later_same_day")
        #expect(first["detail_choice"] as? String == "head_pressure")
        #expect(first["ts_utc"] != nil)
        let edit = first["migraine"] as! [String: Any]
        #expect(edit["expected_revision"] as? Int == 2)
        #expect((edit["medicines"] as? [Any])?.isEmpty == true)
        #expect(edit["notes"] is NSNull)
    }

    @Test(arguments: ["conflict", "rejected", "cancelled", "pending", "unchanged",
        "wrong-prompt", "wrong-state", "wrong-episode", "wrong-detail-state", "wrong-detail-episode"])
    func rejectionOrMismatchedReceiptNeverBecomesSuccess(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var draft = try draft()
        draft.medicineChoice = .none
        let retained = draft
        do { _ = try await submit(api, draft: draft); Issue.record("Invalid acknowledgement accepted: \(scenario)") }
        catch { #expect(draft == retained) }
        #expect(server.requests.filter { $0.httpMethod == "POST" }.count == 1)
        #expect(server.requests.filter { $0.httpMethod == "GET" && $0.url!.path != "/health" }.isEmpty)
    }

    @Test(arguments: [1, 2, 3])
    func accountChangeIsCheckedBeforeSendAndAfterAwait(changeAtCheck: Int) async throws {
        let server = MigraineFixtureServer()
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let draft = try draft()
        var checks = 0
        do {
            _ = try await submit(api, draft: draft) {
                checks += 1
                return checks >= changeAtCheck ? "b" : "a"
            }
            Issue.record("A different account must not confirm or reuse this draft")
        } catch { #expect(error is MigraineDraftError) }
        #expect(server.requests.filter { $0.httpMethod == "POST" }.count == (changeAtCheck == 3 ? 1 : 0))
    }

    @Test
    func cancellationBeforeSubmissionMakesNoRequests() async throws {
        let server = MigraineFixtureServer()
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let draft = try draft()
        let task = Task { @MainActor in
            withUnsafeCurrentTask { $0?.cancel() }
            return try await submit(api, draft: draft)
        }
        do { _ = try await task.value; Issue.record("Cancelled task saved") }
        catch { #expect(error is CancellationError) }
        #expect(server.requests.isEmpty)
    }

    @Test(arguments: ["unsupported", "old-route", "missing-episode", "load-failure"])
    func onlyKnownMissingCapabilityAllowsLegacyFallback(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let draft = try draft()
        do { _ = try await api.fetchMigraineEpisodeDetail(episodeId: draft.episodeId); Issue.record("Expected load error") }
        catch { #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error) == ["unsupported", "old-route"].contains(scenario)) }
        #expect(server.requests.allSatisfy { $0.httpMethod == "GET" })
    }

    @Test
    func actualHistorySavePreservesUntouchedMedicineAndMetadata() async throws {
        let server = MigraineFixtureServer()
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var draft = try draft()
        let untouched = draft.originalMedicines[1]
        let first = draft.originalMedicines[0]
        draft.noteText = "Updated history note"
        draft.reliefChoice = .complete
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let saved = try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: draft.episodeId,
            edit: edit, accountScope: "a", currentAccountScope: { "a" })
        #expect(saved.episode.medicines.count == 2)
        #expect(saved.episode.medicines[1] == untouched)
        #expect(saved.episode.medicines[0].notes == first.notes)
        #expect(saved.episode.medicines[0].takenAt == first.takenAt)
        #expect(saved.episode.notes == "Updated history note")
        try draft.apply(saved, forAccountScope: "a")
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
        #expect(server.requests.filter { $0.httpMethod == "PATCH" }.count == 1)
    }
}
