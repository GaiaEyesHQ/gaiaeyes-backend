import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineGuideTests {
    @Test func newDraftMakesNoHealthObservations() {
        let draft = MigraineGuideDraft()
        #expect(draft.onset == nil && draft.severity == nil && draft.medicines.isEmpty)
        #expect(draft.symptoms.isEmpty && draft.locations.isEmpty && draft.reliefs.isEmpty)
        #expect(!draft.inputsLocked && !draft.severityChanged)
    }
    @Test func medicineRequiresConfirmedTimeAndKeepsExactDose() throws {
        var row = MigraineGuideMedicine(); row.name = "Synthetic medicine"; row.dose = "0.125"; row.unit = "mg"
        #expect(throws: MigraineGuideError.self) { try row.value(reportedAt: Date()) }
        row.takenAt = Date(timeIntervalSince1970: 1_790_000_000)
        let value = try row.value(reportedAt: row.takenAt!)
        #expect(value.doseAmount == Decimal(string: "0.125"))
        let roundtrip = MigraineGuideMedicine(value)
        #expect(roundtrip.original == value)
    }
    @Test func draftsAndFavoritesAreAccountScopedAndNeverPrefillObservation() throws {
        let name = "synthetic-guide-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        var draft = MigraineGuideDraft(); draft.onset = Date(timeIntervalSince1970: 1_790_000_000)
        draft.symptoms = ["Synthetic symptom"]; draft.step = .location; draft.pendingCreation = true
        try MigraineGuideStorage.save(draft, scope: "a", defaults: defaults)
        #expect(MigraineGuideStorage.draft(scope: "a", episodeID: nil, defaults: defaults) == draft)
        #expect(MigraineGuideStorage.draft(scope: "b", episodeID: nil, defaults: defaults) == nil)
        MigraineGuideStorage.toggleFavorite("Synthetic medicine", scope: "a", category: "medicines", defaults: defaults)
        #expect(MigraineGuideStorage.favorites(scope: "a", category: "medicines", defaults: defaults) == ["Synthetic medicine"])
        #expect(MigraineGuideStorage.favorites(scope: "b", category: "medicines", defaults: defaults).isEmpty)
        #expect(MigraineGuideDraft().medicines.isEmpty)
    }
    @Test func savedFieldsRemainDistinctAndZeroIsRetained() throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let original = try decoder.decode(MigraineTimeContext.self, from: MigraineTimeFixture.contextData)
        var episode = original.episode
        episode.symptoms = [MigraineEarlySign(label: "Nausea", code: nil, reportedAt: nil, notes: nil)]
        episode.painLocations = [MigraineEarlySign(label: "Your left temple", code: nil, reportedAt: nil, notes: nil)]
        episode.reliefs = [MigraineEarlySign(label: "Rest", code: nil, reportedAt: nil, notes: nil)]
        let detail = MigraineEpisodeDetail(revision: original.revision, changed: false, episode: episode)
        var draft = MigraineGuideDraft(); try draft.load(detail)
        #expect(draft.base == detail && draft.severity == nil && draft.onset != nil)
        #expect(draft.symptoms == ["Nausea"] && draft.locations == ["Your left temple"] && draft.reliefs == ["Rest"])
        draft.reportedAt = Date(); draft.changed = ["symptoms", "notes"]; draft.symptoms = []; draft.notes = "  Synthetic note \n"
        let edit = try draft.edit()
        #expect(edit.notes == .set("Synthetic note"))
        #expect(edit.symptoms == [] && edit.painLocations == nil && edit.reliefs == nil && edit.medicines == nil)
    }
    @Test func acknowledgementRequiresCanonicalEpisodeAndExactOnset() throws {
        let date = Date(timeIntervalSince1970: 1_790_000_000.123)
        let event = SymptomQueuedEvent(symptomCode: "MIGRAINE", tsUtc: date, severity: nil)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let timestamp = MigraineFollowUpDraft.timestamp(date).utc
        func response(_ episode: String?, _ time: String) throws -> SymptomPostResponse {
            var payload: [String:Any] = ["id":"synthetic-event", "ts_utc":time]
            payload["episode_id"] = episode
            return try decoder.decode(SymptomPostResponse.self, from: JSONSerialization.data(withJSONObject:["ok":true,"data":payload]))
        }
        #expect(throws: MigraineSaveError.self) { try response(nil, timestamp).validated(for:event) }
        #expect(throws: MigraineSaveError.self) { try response(MigraineTimeFixture.episodeID, "2020-01-01T00:00:00Z").validated(for:event) }
        #expect(try response(MigraineTimeFixture.episodeID, timestamp).validated(for:event).episodeId == MigraineTimeFixture.episodeID)
    }
    @Test func pendingStructuredRetryKeepsTimezoneProvenanceAfterResume() throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let context = try decoder.decode(MigraineTimeContext.self, from: MigraineTimeFixture.contextData)
        let detail = MigraineEpisodeDetail(revision:context.revision,changed:false,episode:context.episode)
        var draft = MigraineGuideDraft(); try draft.load(detail)
        draft.reportedAt = Date(timeIntervalSince1970:1_790_000_000)
        draft.changed = ["symptoms", "notes"]; draft.symptoms = ["Synthetic symptom"]; draft.notes = ""
        // Deliberately differ from the current environment; changing NSTimeZone.default
        // alone does not necessarily invalidate Foundation's cached current zone.
        let savedZone = TimeZone.current.identifier == "Asia/Tokyo" ? "Pacific/Honolulu" : "Asia/Tokyo"
        let offset = savedZone == "Asia/Tokyo" ? 540 : -600
        let timestamp = MigraineEpisodeTimestamp(utc:"2026-09-22T18:13:20Z", originalTime:nil,
            timezoneName:savedZone, utcOffsetMinutes:offset, timezoneSource:"user")
        let submitted = MigraineStructuredEdit(expectedRevision:detail.revision, earlySigns:nil, contexts:nil,
            medicines:nil, notes:.clear,
            symptoms:[MigraineEarlySign(label:"Synthetic symptom",code:nil,reportedAt:timestamp,notes:nil)])
        #expect(savedZone != TimeZone.current.identifier)
        draft.pendingEditData = try JSONEncoder().encode(submitted)
        let stored = try JSONEncoder().encode(draft)
        let resumed = try JSONDecoder().decode(MigraineGuideDraft.self, from:stored)
        #expect(try resumed.edit() == submitted)
        #expect(try resumed.edit().symptoms?.first?.reportedAt?.timezoneName == savedZone)
        #expect(try resumed.edit().notes == .clear)
    }
    @Test func ongoingDurationNeverInventsAnEnd() throws {
        let start = Date(timeIntervalSince1970: 1_790_000_000)
        #expect(MigraineEpisodeSummary.elapsed(from:start, to:start.addingTimeInterval(3600)) == "1 hour")
        #expect(MigraineEpisodeSummary.elapsed(from:start, to:start.addingTimeInterval(-60)).contains("future"))
    }
}
