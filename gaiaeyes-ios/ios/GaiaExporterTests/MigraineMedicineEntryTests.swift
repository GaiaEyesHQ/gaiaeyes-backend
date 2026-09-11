import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineMedicineEntryTests {
    private func detail(_ transform: (inout [String: Any]) -> Void = { _ in }) throws -> MigraineEpisodeDetail {
        var value = try JSONSerialization.jsonObject(with: MigraineFixtureServer.detailDataForScenario("entries")) as! [String: Any]
        transform(&value)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(MigraineEpisodeDetail.self, from: JSONSerialization.data(withJSONObject: value))
    }
    private func draft(_ detail: MigraineEpisodeDetail) throws -> MigraineFollowUpDraft {
        var draft = MigraineFollowUpDraft(accountScope: "a", promptId: "fixture-prompt", episodeId: detail.episode.episodeId,
            responseTimestamp: Date(timeIntervalSince1970: 1_788_839_400))
        try draft.apply(detail, forAccountScope: "a"); return draft
    }

    @Test func selectionRetainsInvalidFieldsAndStableRowsThroughTwoAddsAndRemoval() throws {
        let base = try detail(); var draft = try draft(base)
        let ids = draft.medicineRows.map(\.id)
        draft.selectMedicine(ids[1]); draft.doseAmountText = "invalid"
        draft.selectMedicine(ids[2]); draft.medicineNotesText = "Edited last note"
        draft.addMedicine(); draft.medicineName = "Repeated medicine"
        let firstAdded = draft.selectedMedicineID
        draft.addMedicine(); draft.medicineName = "Repeated medicine"
        let secondAdded = draft.selectedMedicineID
        #expect(firstAdded != secondAdded && draft.medicineRows.count == 5)
        draft.selectMedicine(ids[0]); draft.removeSelectedMedicine()
        #expect(draft.medicineRows.map(\.id) == [ids[1], ids[2], firstAdded!, secondAdded!])
        #expect(throws: MigraineDraftError.self) { try draft.makeStructuredEdit(currentAccountScope: "a") }
        draft.selectMedicine(ids[1]); #expect(draft.doseAmountText == "invalid")
        draft.doseAmountText = "2.500000000000000001"
        let values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values.count == 4 && values[0] == base.episode.medicines[1])
        #expect(values[1].notes == "Edited last note" && values[1].takenAt == base.episode.medicines[2].takenAt)
        #expect(values[2] == values[3]) // Exact legitimate repetitions remain two entries.
        #expect(draft.medicineRows.map(\.id) == [ids[1], ids[2], firstAdded!, secondAdded!])
    }

    @Test(arguments: ["", "2oops", "2.123456789012345678901234567890123456789012345", "1e999", "-2"])
    func invalidDoseCannotSilentlyRoundOrReplaceValidSiblings(text: String) throws {
        let base = try detail(); var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id); draft.doseAmountText = text
        #expect(throws: MigraineDraftError.self) { try draft.makeStructuredEdit(currentAccountScope: "a") }
        #expect(draft.originalMedicines == base.episode.medicines)
        draft.doseAmountText = "2.500000000000000001"
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
    }

    @Test func missingUnknownAndNoReliefStayDistinct() throws {
        let base = try detail(); var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id)
        #expect(draft.reliefChoice == .unknown)
        draft.selectMedicine(draft.medicineRows[2].id)
        #expect(draft.reliefChoice == .notReported)
        draft.reliefChoice = .unknown
        var values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values[2].reportedRelief == "unknown" && values[2].reliefReportedAt != nil)
        #expect(values[0] == base.episode.medicines[0] && values[1] == base.episode.medicines[1])
        draft.reliefChoice = .none
        values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values[2].reportedRelief == "none")
        #expect(values[2].takenAt == base.episode.medicines[2].takenAt && values[2].takenAt.timezoneName == nil)
        draft.reliefChoice = .notReported
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
    }

    @Test func removingOneOrAllIsDistinctFromUnanswered() throws {
        let base = try detail(); var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id); draft.removeSelectedMedicine()
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines == [base.episode.medicines[0], base.episode.medicines[2]])
        draft.chooseMedicine(.none)
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines == [])
        var empty = MigraineFollowUpDraft(accountScope: "a", promptId: "p", episodeId: "e")
        empty.addMedicine(); empty.medicineName = "Uncommitted entry"; empty.removeSelectedMedicine()
        #expect(try empty.makeStructuredEdit(currentAccountScope: "a") == nil)
        empty.chooseMedicine(.none)
        #expect(try empty.makeStructuredEdit(currentAccountScope: "a")?.medicines == [])
    }

    @Test func deliberateRebaseKeepsRowEditsRemovalsAddsAndLatestUntouchedMetadata() throws {
        let base = try detail(); var draft = try draft(base)
        let ids = draft.medicineRows.map(\.id)
        draft.selectMedicine(ids[1]); draft.reliefChoice = .none
        draft.selectMedicine(ids[2]); draft.removeSelectedMedicine()
        draft.addMedicine(); draft.medicineName = "Added one"
        draft.addMedicine(); draft.medicineName = "Added two"
        let added = draft.medicineRows.suffix(2).map(\.id)
        let latest = try detail {
            $0["revision"] = 3
            var episode = $0["episode"] as! [String: Any]
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines[0]["notes"] = "Latest first metadata"
            medicines[1]["notes"] = "Latest middle metadata"
            var new = medicines[0]; new["name"] = "External addition"
            medicines.insert(new, at: 0); episode["medicines"] = medicines; $0["episode"] = episode
        }
        try draft.rebasePreservingChanges(latest, currentAccountScope: "a")
        let values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values.map(\.name) == ["External addition", "Test medicine", "Test medicine", "Added one", "Added two"])
        #expect(values[1] == latest.episode.medicines[1])
        #expect(values[2].notes == "Latest middle metadata" && values[2].reportedRelief == "none")
        #expect(values[2].doseAmount == base.episode.medicines[1].doseAmount && values[2].takenAt == base.episode.medicines[1].takenAt)
        #expect(draft.medicineRows[1].id == ids[0] && draft.medicineRows[2].id == ids[1])
        #expect(draft.medicineRows.suffix(2).map(\.id) == added)
    }

    @Test(arguments: [false, true])
    func ambiguousExternalIdentityKeepsEntireDraft(remove: Bool) throws {
        let base = try detail(); var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id)
        if remove { draft.removeSelectedMedicine() } else { draft.medicineName = "Intended renamed middle" }
        let retained = draft
        let latest = try detail {
            $0["revision"] = 3
            var episode = $0["episode"] as! [String: Any]
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines[1]["name"] = "Externally renamed middle"; episode["medicines"] = medicines; $0["episode"] = episode
        }
        #expect(throws: MigraineDraftError.self) { try draft.rebasePreservingChanges(latest, currentAccountScope: "a") }
        #expect(draft == retained)
    }

    @Test(arguments: ["detail-lost", "detail-before", "detail-cancelled"])
    func actualHistoryWorkflowRetainsCompleteMultiEntryRequest(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: "time-history-entries-" + scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let base = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: MigraineTimeFixture.episodeID).payload)
        var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id); draft.reliefChoice = .none
        draft.addMedicine(); draft.medicineName = "Additional one"
        draft.addMedicine(); draft.medicineName = "Additional two"
        draft.selectMedicine(draft.medicineRows[2].id); draft.removeSelectedMedicine()
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        var recovery = MigraineDetailSaveRecovery()
        let pending = try recovery.request(edit, episodeId: draft.episodeId, accountScope: "a")
        do { _ = try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: draft.episodeId, edit: pending.edit, accountScope: "a", currentAccountScope: { "a" }); Issue.record("Expected uncertain first response") }
        catch { recovery.failed(error) }
        #expect(recovery.pending?.edit == edit)
        let saved = try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: draft.episodeId, edit: pending.edit, accountScope: "a", currentAccountScope: { "a" })
        try recovery.acknowledge(saved, accountScope: "a")
        #expect(saved.episode.medicines == edit.medicines && saved.episode.medicines.count == 4)
        #expect(saved.episode.medicines[0] == base.episode.medicines[0])
        #expect(saved.episode.medicines[1].takenAt == base.episode.medicines[1].takenAt)
        let writes = server.requests.filter { $0.httpMethod == "PATCH" }
        #expect(writes.count == 2)
        #expect(try JSONSerialization.jsonObject(with: writes[0].httpBody!) as! NSDictionary == JSONSerialization.jsonObject(with: writes[1].httpBody!) as! NSDictionary)
        try draft.apply(saved, forAccountScope: "a")
        #expect(try draft.makeStructuredEdit(currentAccountScope: "a") == nil)
    }

    @Test(arguments: ["entries-timeout", "entries-committed-timeout"])
    func actualFollowUpWholeResponseRetryRetainsAllEntries(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario), api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var draft = try draft(detail())
        draft.selectMedicine(draft.medicineRows[2].id); draft.medicineNotesText = "Third entry edited"
        draft.addMedicine(); draft.medicineName = "Separate fourth entry"
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        var recovery = MigraineFollowUpSaveRecovery()
        let value = MigraineFollowUpSaveRecovery.Pending(detailChoice: "head_pressure", note: nil, timeBucket: "overnight", timestamp: draft.responseTimestamp, edit: edit, accountScope: "a")
        let first = try recovery.request(value)
        func send(_ value: MigraineFollowUpSaveRecovery.Pending) async throws -> SymptomFollowUpResult {
            try await MigraineFollowUpWorkflow.submit(api: api, promptId: draft.promptId, episodeId: draft.episodeId, state: .resolved,
                detailChoice: value.detailChoice, noteText: value.note, timeBucket: value.timeBucket, timestamp: value.timestamp,
                edit: value.edit, accountScope: value.accountScope, currentAccountScope: { "a" })
        }
        do { _ = try await send(first); Issue.record("Expected uncertain response") } catch { recovery.failed(error) }
        let retry = try recovery.request(.init(detailChoice: "different", note: "different", timeBucket: nil, timestamp: Date(), edit: nil, accountScope: "a"))
        #expect(retry == first)
        let saved = try await send(retry); recovery.acknowledge()
        #expect(saved.migraineDetail?.episode.medicines == edit.medicines && saved.migraineDetail?.episode.medicines.count == 4)
        let writes = server.requests.filter { $0.httpMethod == "POST" }
        #expect(try JSONSerialization.jsonObject(with: writes[0].httpBody!) as! NSDictionary == JSONSerialization.jsonObject(with: writes[1].httpBody!) as! NSDictionary)
    }

    @Test func timeAcknowledgementPreservesUnsavedRowsAndSharedRevision() async throws {
        let server = MigraineFixtureServer(scenario: "time-history-entries-success"), api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let base = try #require(try await api.fetchMigraineEpisodeDetail(episodeId: MigraineTimeFixture.episodeID).payload)
        var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[1].id); draft.medicineNotesText = "Middle edit before time save"
        draft.addMedicine(); draft.medicineName = "Fourth entry before time save"
        let rows = draft.medicineRows, selected = draft.selectedMedicineID
        let store = MigraineTimeEditorStore(api: api, episodeId: draft.episodeId, accountScope: { "a" })
        await store.load(); store.edit { $0.correctStart = true; $0.start.dateText = "2026-08-31" }
        let ack = try #require(await store.save())
        let advanced = draft.advanceAfterTimeCorrection(ack, currentAccountScope: "a")
        #expect(advanced)
        #expect(draft.medicineRows == rows && draft.selectedMedicineID == selected && draft.expectedRevision == 2)
        let edit = try #require(try draft.makeStructuredEdit(currentAccountScope: "a"))
        let saved = try await MigraineFollowUpWorkflow.saveDetails(api: api, episodeId: draft.episodeId, edit: edit, accountScope: "a", currentAccountScope: { "a" })
        #expect(saved.revision == 3 && saved.episode.medicines == edit.medicines)
    }

    @Test func followUpDefinitiveConflictAndAccountIsolationKeepDraftIntent() throws {
        let base = try detail(); var draft = try draft(base)
        draft.selectMedicine(draft.medicineRows[2].id); draft.medicineName = "Edited last"
        var recovery = MigraineFollowUpSaveRecovery()
        let value = MigraineFollowUpSaveRecovery.Pending(detailChoice: nil, note: nil, timeBucket: nil,
            timestamp: draft.responseTimestamp, edit: try draft.makeStructuredEdit(currentAccountScope: "a"), accountScope: "a")
        _ = try recovery.request(value); recovery.failed(MigraineSaveError.conflict)
        #expect(recovery.pending == nil && recovery.needsConflictReload)
        #expect(draft.medicineName == "Edited last")
        _ = try recovery.request(value); recovery.failed(URLError(.cancelled)); recovery.failed(MigraineSaveError.conflict)
        #expect(recovery.pending == value && recovery.uncertain && !recovery.needsConflictReload)
        #expect(throws: MigraineDraftError.self) { try recovery.request(.init(detailChoice: nil, note: nil, timeBucket: nil, timestamp: Date(), edit: nil, accountScope: "b")) }
        #expect(throws: MigraineDraftError.self) { try draft.makeStructuredEdit(currentAccountScope: "b") }
    }

    @Test func blankNameCorrectionPreservesOtherRows() throws {
        let base = try detail(); var draft = try draft(base)
        draft.addMedicine()
        let id = draft.selectedMedicineID
        #expect(throws: MigraineDraftError.self) { try draft.makeStructuredEdit(currentAccountScope: "a") }
        draft.selectMedicine(draft.medicineRows[1].id); draft.reliefChoice = .none
        draft.selectMedicine(id!); draft.medicineName = "Corrected new name"
        let values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values.count == 4 && values[0] == base.episode.medicines[0] && values[2] == base.episode.medicines[2])
        #expect(values[1].reportedRelief == "none" && draft.selectedMedicineID == id)
        try MigraineFixtureServer.detailDataForScenario("entries").write(to:
            URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("g014-original-detail.json"))
    }

    @Test func identicalSavedRowsAreDistinctAndAnAmbiguousRemovalCannotRebase() throws {
        let base = try detail {
            var episode = $0["episode"] as! [String: Any]
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines[1] = medicines[0]; episode["medicines"] = medicines; $0["episode"] = episode
        }
        var draft = try draft(base)
        #expect(draft.medicineRows[0].id != draft.medicineRows[1].id)
        draft.selectMedicine(draft.medicineRows[1].id); draft.medicineNotesText = "Only second occurrence edited"
        let values = try #require(try draft.makeStructuredEdit(currentAccountScope: "a")?.medicines)
        #expect(values[0] == base.episode.medicines[0] && values[1].notes == "Only second occurrence edited")
        let latest = try detail {
            $0["revision"] = 3
            var episode = $0["episode"] as! [String: Any]
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines.remove(at: 1); episode["medicines"] = medicines; $0["episode"] = episode
        }
        let retained = draft
        #expect(throws: MigraineDraftError.self) { try draft.rebasePreservingChanges(latest, currentAccountScope: "a") }
        #expect(draft == retained)
    }
}
