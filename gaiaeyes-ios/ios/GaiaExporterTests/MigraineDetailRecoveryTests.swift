import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineDetailRecoveryTests {
    private func setup(_ scenario: String) async throws -> (MigraineFixtureServer, APIClient, MigraineFollowUpDraft, MigraineEpisodeDetail) {
        let server = MigraineFixtureServer(scenario: "time-history-" + scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let detail = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: MigraineTimeFixture.episodeID).payload)
        var draft = MigraineFollowUpDraft(accountScope: "a", promptId: "history", episodeId: detail.episode.episodeId)
        try draft.apply(detail, forAccountScope: "a")
        draft.chooseMedicine(.add); draft.medicineName = "New synthetic medicine"
        return (server, api, draft, detail)
    }
    private func send(_ pending: MigraineDetailSaveRecovery.Pending, _ api: APIClient,
                      scope: @escaping @MainActor () -> String = { "a" }) async throws -> MigraineEpisodeDetail {
        try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: pending.episodeId,
            edit: pending.edit, accountScope: pending.accountScope, currentAccountScope: scope)
    }

    @Test(arguments: ["detail-lost", "detail-before", "detail-cancelled"], [false, true])
    func uncertainSaveRetriesExactReplacementOnce(scenario: String, repeatedMedicine: Bool) async throws {
        let (server, api, initial, base) = try await setup(scenario)
        var draft = initial
        if repeatedMedicine {
            draft.medicineName = base.episode.medicines[0].name
            draft.medicineTakenAt = MigraineFollowUpDraft.parseDate(base.episode.medicines[0].takenAt.utc)!
            draft.doseAmountText = "2.5"; draft.doseUnit = "mg"
        }
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        var recovery = MigraineDetailSaveRecovery()
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        do { _ = try await send(pending, api); Issue.record("Expected synthetic uncertain delivery") }
        catch { recovery.failed(error) }
        #expect(recovery.pending?.edit == edit && recovery.uncertain && !recovery.needsConflictReload)
        let afterFailure = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: draft.episodeId).payload)
        #expect(afterFailure.revision == (scenario == "detail-before" ? 1 : 2))
        draft.medicineName = "A differing later draft must not replace the pending request"
        let differing = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let retry = try recovery.request(differing, episodeId: draft.episodeId, accountScope: "a")
        #expect(retry.edit == edit)
        let saved = try await send(retry, api)
        try recovery.acknowledge(saved, accountScope: "a")
        try draft.apply(saved, forAccountScope: "a")
        #expect(recovery.pending == nil && !recovery.uncertain)
        #expect(saved.revision == 2 && saved.episode.medicines.count == 2)
        #expect(saved.episode.medicines[0] == base.episode.medicines[0])
        #expect(saved.episode.medicines == edit.medicines && saved.episode.provenance == base.episode.provenance)
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
        let requests = server.requests.filter { $0.httpMethod == "PATCH" }
        #expect(requests.count == 2)
        #expect(try JSONSerialization.jsonObject(with: requests[0].httpBody!) as! NSDictionary
                == JSONSerialization.jsonObject(with: requests[1].httpBody!) as! NSDictionary)
        if scenario == "detail-lost" && !repeatedMedicine {
            try requests[0].httpBody!.write(to: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("gr23-pending-request.json"))
            let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
            try encoder.encode(saved).write(to: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("gr23-retry-ack.json"))
        }
    }

    @Test func genuineFirstConflictKeepsOneAddIntentForExplicitRebase() async throws {
        let (_, api, initial, _) = try await setup("external-details")
        var draft = initial; var recovery = MigraineDetailSaveRecovery()
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        do { _ = try await send(pending, api); Issue.record("Expected revision conflict") }
        catch { recovery.failed(error) }
        #expect(recovery.needsConflictReload && recovery.pending == nil && !recovery.uncertain)
        let latest = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: draft.episodeId).payload)
        try draft.rebasePreservingChanges(latest, currentAccountScope: "a"); recovery.conflictReloaded()
        let rebased = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let next = try recovery.request(rebased, episodeId: draft.episodeId, accountScope: "a")
        let saved = try await send(next, api); try recovery.acknowledge(saved, accountScope: "a")
        #expect(saved.episode.medicines.count == latest.episode.medicines.count + 1)
        #expect(saved.episode.medicines.filter { $0.name == "New synthetic medicine" }.count == 1)
        #expect(Array(saved.episode.medicines.dropLast()) == latest.episode.medicines)
    }

    @Test func laterExternalEditRetainsUncertainRequestUntilExplicitReviewedChoice() async throws {
        let (server, api, initial, _) = try await setup("detail-lost-later")
        var draft = initial; var recovery = MigraineDetailSaveRecovery()
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        for _ in 0..<2 {
            do { _ = try await send(pending, api); Issue.record("Expected lost response then later conflict") }
            catch { recovery.failed(error) }
        }
        #expect(recovery.pending?.edit == edit && recovery.needsUncertainReview && !recovery.needsConflictReload)
        let latest = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: draft.episodeId).payload)
        try recovery.review(latest, accountScope: "a")
        #expect(recovery.pending?.edit == edit && draft.medicineChoice == .add && draft.expectedRevision == 1)
        #expect(latest.revision == 3 && latest.episode.medicines.count == 2)
        let reviewed = try recovery.useReviewedVersion(accountScope: "a")
        try draft.apply(reviewed, forAccountScope: "a")
        #expect(recovery.pending == nil && recovery.setAsideRequest?.edit == edit)
        #expect(draft.noteText == "A later saved note" && draft.originalMedicines.count == 2)
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
        #expect(server.requests.filter { $0.httpMethod == "PATCH" }.count == 2)
    }

    @Test func validationDoesNotForceReloadAndDoesNotReplaceUncertainRequest() async throws {
        let (_, api, initial, _) = try await setup("detail-rejected")
        var draft = initial; var recovery = MigraineDetailSaveRecovery()
        draft.medicineName = ""
        #expect(throws: MigraineDraftError.self) { try draft.makeStructuredEdit(currentAccountScope: "a") }
        #expect(recovery.pending == nil && !recovery.needsConflictReload)
        draft.medicineName = "Corrected name"
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        do { _ = try await send(pending, api); Issue.record("Expected validation rejection") }
        catch { recovery.failed(error) }
        #expect(recovery.pending == nil && !recovery.needsConflictReload)
        let retry = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        recovery.failed(URLError(.cancelled))
        recovery.failed(APIError.server(code: 422, body: "new server validation"))
        #expect(recovery.pending?.edit == retry.edit && recovery.uncertain && !recovery.needsConflictReload)
    }

    @Test func accountAndEpisodeCannotUseAnotherPendingRequestOrReceipt() async throws {
        let (server, api, draft, base) = try await setup("detail-before")
        var recovery = MigraineDetailSaveRecovery()
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        #expect(throws: MigraineDraftError.self) { try recovery.request(edit, episodeId: "other", accountScope: "a") }
        #expect(throws: MigraineDraftError.self) { try recovery.request(edit, episodeId: draft.episodeId, accountScope: "b") }
        var scope = "a"; api.bearerProvider = { scope = "b"; return "synthetic-token" }
        await #expect(throws: MigraineDraftError.self) { try await send(pending, api, scope: { scope }) }
        #expect(server.requests.filter { $0.httpMethod == "PATCH" }.isEmpty)
        #expect(throws: MigraineDraftError.self) { try recovery.acknowledge(base, accountScope: "b") }
        #expect(recovery.pending?.edit == edit)
    }
}
