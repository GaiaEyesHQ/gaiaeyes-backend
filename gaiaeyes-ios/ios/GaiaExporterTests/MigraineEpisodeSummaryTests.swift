import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineEpisodeSummaryTests {
    private let first = "11111111-1111-4111-8111-111111111111"
    private let second = "33333333-3333-4333-8333-333333333333"
    private let zone = TimeZone(identifier: "America/Chicago")!

    private func detail(id: String? = nil, revision: Int = 2,
                        change: (inout [String: Any]) -> Void = { _ in }) throws -> MigraineEpisodeDetail {
        var body = try JSONSerialization.jsonObject(with: MigraineFixtureServer.detailDataForScenario("entries")) as! [String: Any]
        var episode = body["episode"] as! [String: Any]
        episode["episode_id"] = id ?? first
        var lifecycle = episode["lifecycle"] as! [String: Any]
        lifecycle["revision"] = revision; episode["lifecycle"] = lifecycle
        body["revision"] = revision
        change(&episode); body["episode"] = episode
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(MigraineEpisodeDetail.self, from: JSONSerialization.data(withJSONObject: body))
    }

    @Test
    func canonicalSavedEpisodeNeedsNoStructuredRowForSummary() throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let saved = try decoder.decode(MigraineEpisodeDetail.self, from: MigraineCalendarFixture.summaryWithoutStructuredRow)
        #expect(saved.revision == 0 && saved.episode.lifecycle.revision == 1)
        let summary = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone)
        #expect(summary.revision == 0 && summary.notes == "Saved manual migraine note.")
        #expect(summary.timing.first { $0.id == "severity" }?.lines == ["5/10"])
        #expect(summary.medicines.isEmpty && summary.earlySigns.isEmpty && summary.contexts.isEmpty)
    }

    @Test(arguments: [(0, 0), (0, 2), (-1, 1), (1, 0), (2, 1), (2, 3)])
    func candidateExceptionDoesNotAcceptOtherRevisionMismatches(stored: Int, lifecycle: Int) throws {
        let saved = try detail(revision: stored) { episode in
            var life = episode["lifecycle"] as! [String: Any]
            life["revision"] = lifecycle; episode["lifecycle"] = life
        }
        do {
            _ = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone)
            Issue.record("Unexpected revision pair accepted: \(stored)/\(lifecycle)")
        } catch {}
    }

    @Test
    func ordinaryEpisodeStoreReadsWithoutCreatingStructuredDetails() async {
        let server = MigraineFixtureServer(scenario: "calendar-summary-unstructured")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let store = MigraineEpisodeSummaryStore(api: api, accountScope: { "a" })
        for _ in 0..<2 {
            await store.load(episodeID: first, scope: "a", timeZone: zone)
            #expect(store.summary?.revision == 0 && store.summary?.notes == "Saved manual migraine note.")
            #expect(store.summary?.medicines.isEmpty == true && store.errorMessage == nil)
        }
        #expect(server.requests.count == 2)
        #expect(server.requests.allSatisfy { $0.httpMethod == "GET" && $0.url?.path == "/v1/symptoms/current/\(first)/migraine-detail" })
    }

    @Test
    func acknowledgedCanonicalNoteReopensWithUnchangedStructuredLifecycle() async throws {
        let server = MigraineFixtureServer(scenario: "calendar-summary-edit")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let beforeEnvelope = try await api.fetchMigraineEpisodeDetail(episodeId: second)
        let before = try #require(beforeEnvelope.payload)
        let store = MigraineEpisodeSummaryStore(api: api, accountScope: { "a" })
        await store.load(episodeID: second, scope: "a", timeZone: zone)
        #expect(store.summary?.notes == MigraineCalendarFixture.summaryLongNotes)
        store.invalidate()
        let intended = "G016 acknowledged saved episode note."
        let acknowledgement = try await api.updateCurrentSymptom(episodeId: second, noteText: intended)
        #expect(acknowledgement.ok == true && acknowledgement.payload?.notePreview == intended)
        let afterEnvelope = try await api.fetchMigraineEpisodeDetail(episodeId: second)
        let after = try #require(afterEnvelope.payload)
        #expect(after.revision == before.revision && after.episode.lifecycle == before.episode.lifecycle)
        #expect(after.episode.notes == intended)
        await store.load(episodeID: second, scope: "a", timeZone: zone)
        #expect(store.summary?.notes == intended && store.summary?.revision == before.revision)
        #expect(server.requests.filter { $0.httpMethod == "POST" }.count == 1)
        #expect(server.requests.allSatisfy { $0.url?.path == "/v1/symptoms/current/\(second)/migraine-detail"
            || ($0.httpMethod == "POST" && $0.url?.path == "/v1/symptoms/current/\(second)/updates") })
    }

    @Test
    func orderedRepeatedMedicinesExactDoseFullNotesAndPrivacy() throws {
        let saved = try detail { episode in
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines.append(medicines[0]); episode["medicines"] = medicines
            episode["notes"] = MigraineCalendarFixture.summaryLongNotes
            var provenance = episode["provenance"] as! [String: Any]
            provenance["source_file_hash"] = "private-file-marker"
            provenance["import_run_id"] = "private-import-marker"; episode["provenance"] = provenance
        }
        let before = saved
        let summary = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone, locale: Locale(identifier: "en_US_POSIX"))
        #expect(summary.medicines.map(\.title) == ["1. Test medicine", "2. Test medicine", "3. Third synthetic medicine", "4. Test medicine"])
        #expect(Set(summary.medicines.map(\.id)).count == 4)
        #expect(summary.medicines[1].lines.contains("Dose: 2.500000000000000001 mg"))
        #expect(summary.medicines[1].lines.contains("Reported relief: Not sure yet"))
        #expect(summary.medicines[2].lines.contains("Reported relief: Not recorded"))
        #expect(summary.medicines[2].lines.contains("Note: Keep third metadata"))
        #expect(summary.notes == MigraineCalendarFixture.summaryLongNotes)
        #expect(summary.earlySigns.count == saved.episode.earlySigns.count && summary.contexts.count == saved.episode.contexts.count)
        #expect(summary.displayTimezone == "America/Chicago")
        let rendered = ([summary.notes] + summary.medicines.flatMap { [$0.title] + $0.lines }).joined(separator: "\n")
        #expect(!rendered.contains("private-file-marker") && !rendered.contains("private-import-marker") && !rendered.contains(first))
        #expect(saved == before)
    }

    @Test(arguments: ["none", "a_little", "some", "a_lot", "complete", "unknown", "missing"])
    func reliefLabelsPreserveEveryRecordedMeaning(value: String) throws {
        let saved = try detail { episode in
            var medicines = episode["medicines"] as! [[String: Any]]
            medicines[0]["reported_relief"] = value == "missing" ? NSNull() : value as Any
            episode["medicines"] = medicines
        }
        let summary = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone)
        let labels = ["none": "No relief", "a_little": "A little", "some": "Some", "a_lot": "A lot",
                      "complete": "Complete", "unknown": "Not sure yet", "missing": "Not recorded"]
        #expect(summary.medicines[0].lines[2] == "Reported relief: \(labels[value]!)")
    }

    @Test
    func emptyUnknownAndZeroSeverityDoNotInventAnswers() throws {
        let saved = try detail { episode in
            for key in ["early_signs", "contexts", "medicines"] { episode[key] = [] }
            episode["notes"] = NSNull(); episode["severity"] = NSNull(); episode["end"] = NSNull()
            episode["state"] = "resolved"
        }
        let summary = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone)
        #expect(summary.medicines.isEmpty && summary.earlySigns.isEmpty && summary.contexts.isEmpty)
        #expect(summary.notes == "Not recorded")
        #expect(summary.timing.first { $0.id == "severity" }?.lines == ["Not recorded"])
        #expect(summary.timing.first { $0.id == "end" }?.lines == ["Not recorded"])
        #expect(summary.timing.first { $0.id == "duration" }?.lines == ["Not available without a recorded end time"])
        let zero = try detail { $0["severity"] = 0 }
        let zeroSummary = try MigraineEpisodeSummary(detail: zero, episodeID: first, timeZone: zone)
        #expect(zeroSummary.timing.first { $0.id == "severity" }?.lines == ["0/10"])
    }

    @Test(arguments: [("2026-03-08T06:00:00Z", "2026-03-09T05:00:00Z", "23 hours"),
                      ("2026-11-01T05:00:00Z", "2026-11-02T06:00:00Z", "25 hours")])
    func canonicalTimingAndElapsedDurationCrossDST(start: String, end: String, duration: String) throws {
        let saved = try detail { episode in
            episode["start"] = ["utc": start, "timezone_source": "unknown"]
            episode["end"] = ["utc": end, "timezone_source": "unknown"]; episode["state"] = "resolved"
        }
        let summary = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone, locale: Locale(identifier: "en_US_POSIX"))
        #expect(summary.timing.first { $0.id == "duration" }?.lines == [duration])
        #expect(summary.timing[0].lines[0].contains("12:00:00 AM"))
        #expect(summary.timing[1].lines[0].contains("12:00:00 AM"))
        #expect(summary.timing[0].lines[0].suffix(3) != summary.timing[1].lines[0].suffix(3))
    }

    @Test(arguments: ["wrong-id", "revision", "state", "severity", "start", "end-order", "end-on-open", "medicine-date",
                      "dose-pair", "negative-dose", "relief", "updated", "schema", "deleted"])
    func malformedOrDeletedSavedDataCannotBecomeASummary(failure: String) throws {
        let saved = try detail { episode in
            switch failure {
            case "wrong-id": episode["episode_id"] = second
            case "revision": var life = episode["lifecycle"] as! [String: Any]; life["revision"] = 9; episode["lifecycle"] = life
            case "state": episode["state"] = "invented"
            case "severity": episode["severity"] = 11
            case "start": episode["start"] = ["utc": "bad-time", "timezone_source": "unknown"]
            case "end-order": episode["end"] = ["utc": "2020-01-01T00:00:00Z", "timezone_source": "unknown"]; episode["state"] = "resolved"
            case "end-on-open": episode["end"] = episode["start"]
            case "updated": var life = episode["lifecycle"] as! [String: Any]; life["updated_at"] = "bad-time"; episode["lifecycle"] = life
            case "schema": episode["schema_version"] = "2.0"
            case "deleted": var life = episode["lifecycle"] as! [String: Any]; life["deleted_at"] = "2026-09-10T12:00:00Z"; life["deletion_scope"] = "episode"; episode["lifecycle"] = life
            default:
                var medicines = episode["medicines"] as! [[String: Any]]
                switch failure {
                case "medicine-date": medicines[0]["taken_at"] = ["utc": "bad-time", "timezone_source": "unknown"]
                case "dose-pair": medicines[0]["dose_unit"] = NSNull()
                case "negative-dose": medicines[0]["dose_amount"] = "-1"
                default: medicines[0]["reported_relief"] = "invented"
                }
                episode["medicines"] = medicines
            }
        }
        do {
            _ = try MigraineEpisodeSummary(detail: saved, episodeID: first, timeZone: zone)
            Issue.record("Malformed/deleted data should be rejected: \(failure)")
        } catch {}
    }

    @Test(arguments: ["calendar-summary-retry", "calendar-summary-deleted", "calendar-summary-malformed", "calendar-summary-wrong"])
    func actualAPIErrorsNeverBecomeEmptySuccess(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let store = MigraineEpisodeSummaryStore(api: api, accountScope: { "a" })
        await store.load(episodeID: first, scope: "a", timeZone: zone)
        #expect(store.summary == nil && store.errorMessage != nil && !store.isLoading)
        if scenario == "calendar-summary-retry" {
            await store.load(episodeID: first, scope: "a", timeZone: zone)
            #expect(store.summary?.medicines.count == 4 && store.errorMessage == nil)
        }
        #expect(server.requests.allSatisfy { $0.httpMethod == "GET" && $0.url?.path == "/v1/symptoms/current/\(first)/migraine-detail" })
    }

    @Test
    func accountChangeDuringAuthorizationPreventsDetailRequest() async {
        let server = MigraineFixtureServer(scenario: "calendar-summary-full")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        var account = "a"
        api.bearerProvider = { account = "b"; return "synthetic-token" }
        let store = MigraineEpisodeSummaryStore(api: api, accountScope: { account })
        await store.load(episodeID: first, scope: "a", timeZone: zone)
        #expect(store.summary == nil && server.requests.isEmpty)
    }

    @Test(arguments: ["episode", "refresh", "account", "dismiss", "cancel"])
    func lateResponsesCannotReplaceCurrentSavedSnapshot(action: String) async throws {
        var account = "a"
        var pending: [CheckedContinuation<MigraineEpisodeDetail, Never>] = []
        let store = MigraineEpisodeSummaryStore(accountScope: { account }) { _, validate in
            try validate(); return await withCheckedContinuation { pending.append($0) }
        }
        let old = Task { await store.load(episodeID: first, scope: "a", timeZone: zone) }
        for _ in 0..<200 where pending.isEmpty { await Task.yield() }
        #expect(pending.count == 1)
        guard pending.count == 1 else { old.cancel(); return }
        if action == "episode" || action == "refresh" {
            let id = action == "episode" ? second : first
            let latest = Task { await store.load(episodeID: id, scope: "a", timeZone: zone) }
            for _ in 0..<200 where pending.count < 2 { await Task.yield() }
            #expect(pending.count == 2 && store.summary == nil)
            guard pending.count == 2 else { latest.cancel(); old.cancel(); return }
            pending[1].resume(returning: try detail(id: id, revision: 3) { $0["notes"] = "Newest saved snapshot" })
            await latest.value
            #expect(store.summary?.notes == "Newest saved snapshot" && store.summary?.revision == 3)
        } else if action == "account" {
            account = "b"; store.invalidate()
        } else if action == "dismiss" { store.invalidate() }
        else { old.cancel() }
        pending[0].resume(returning: try detail { $0["notes"] = "Old saved snapshot" })
        await old.value
        if action == "episode" || action == "refresh" {
            #expect(store.summary?.notes == "Newest saved snapshot" && store.summary?.revision == 3)
        } else { #expect(store.summary == nil && !store.isLoading) }
        if action == "cancel" { #expect(store.errorMessage?.contains("cancelled") == true) }
    }

    @Test
    func refreshFailureClearsOldSnapshotAndRetryLoadsOneNewRevision() async throws {
        var attempt = 0
        let store = MigraineEpisodeSummaryStore(accountScope: { "a" }) { id, validate in
            try validate(); attempt += 1
            if attempt == 2 { throw URLError(.notConnectedToInternet) }
            return try detail(id: id, revision: attempt == 1 ? 2 : 3) { $0["notes"] = "Saved attempt \(attempt)" }
        }
        await store.load(episodeID: first, scope: "a", timeZone: zone)
        #expect(store.summary?.revision == 2)
        await store.load(episodeID: first, scope: "a", timeZone: zone)
        #expect(store.summary == nil && store.errorMessage != nil)
        await store.load(episodeID: first, scope: "a", timeZone: zone)
        #expect(store.summary?.revision == 3 && store.summary?.notes == "Saved attempt 3" && store.errorMessage == nil)
    }
}
