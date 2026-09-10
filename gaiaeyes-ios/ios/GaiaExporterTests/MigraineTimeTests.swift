import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineTimeTests {
    private func data(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/migraine_time_backend_\(name).json"))
    }
    private func context() throws -> MigraineTimeContext {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Envelope<MigraineTimeContext>.self, from: data("context")).payload!
    }
    private func wall(_ local: String, zone: String = "America/Chicago", offset: Int? = nil) throws -> MigraineWallTime {
        var wall = MigraineWallTime(timestamp: try context().episode.start)
        wall.dateText = String(local.prefix(10)); wall.timeText = String(local.dropFirst(11))
        wall.zoneName = zone; wall.offsetChoice = offset; return wall
    }
    private func edit(_ store: MigraineTimeEditorStore) {
        store.edit { $0.correctStart = true; $0.start.dateText = "2026-08-31" }
    }
    @Test func featureGate() {
        #expect(!MigraineTimeEditingFeature.resolve(isDebugBuild: true, arguments: []))
        #expect(!MigraineTimeEditingFeature.resolve(isDebugBuild: false, arguments: ["-gaia-enable-migraine-time-editing"]))
        #expect(MigraineTimeEditingFeature.resolve(isDebugBuild: true, arguments: ["-gaia-enable-migraine-time-editing"]))
    }
    @Test(arguments: ["2026-03-08T02:30:00", "2026-02-30T10:00:00", "2026-09-01T25:00:00"])
    func rejectsNonexistentLocalTime(local: String) throws {
        let value = try wall(local)
        #expect(throws: MigraineTimeError.self) { try value.timestamp() }
    }
    @Test func repeatedTimeRequiresExplicitOccurrence() throws {
        var value = try wall("2025-11-02T01:30:00")
        #expect(try value.candidates().count == 2)
        #expect(throws: MigraineTimeError.self) { try value.timestamp() }
        value.offsetChoice = -300; #expect(try value.timestamp().utc == "2025-11-02T06:30:00Z")
        value.offsetChoice = -360; #expect(try value.timestamp().utc == "2025-11-02T07:30:00Z")
        #expect(try wall("2026-03-08T03:30:00").timestamp().utc == "2026-03-08T08:30:00Z")
    }
    @Test func actualBackendJSONAndSwiftRequestRetainClearAndFullProvenance() async throws {
        let base = try context()
        let input = try JSONSerialization.jsonObject(with: data("request")) as! [String: Any]
        var draft = MigraineTimeDraft(context: base)
        draft.correctStart = true; draft.start = try wall("2026-08-31T23:30:00")
        draft.endMode = "set"; draft.end = try wall("2026-09-01T02:30:00")
        let request = try draft.request(base: base, requestId: input["request_id"] as! String)
        let encoded = try JSONEncoder().encode(request)
        try encoded.write(to: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("g013-swift-time-request.json"))
        let server = MigraineFixtureServer(scenario: "time-backend-json")
        server.timeResponseData = try data("ack")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let ack = try #require(try await api.correctMigraineTimes(episodeId: base.episode.episodeId, correction: request, validateRequest: {}).payload)
        #expect(request.confirms(ack, base: base))
        #expect(ack.episode.medicines[0].doseAmount == Decimal(string: "2.5"))
        #expect(ack.refresh?.status == "pending")
        let body = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        #expect(body["state"] == nil)
        #expect((body["start"] as? [String: Any])?["original_time"] as? String == "2026-08-31T23:30:00")
        let clear = MigraineTimeRequest(requestId: request.requestId, expectedRevision: 1,
            expectedCanonicalUpdatedAt: base.canonicalUpdatedAt, start: nil, end: .clear, state: nil)
        let clearBody = try JSONSerialization.jsonObject(with: JSONEncoder().encode(clear)) as! [String: Any]
        #expect(clearBody["end"] is NSNull && clearBody["start"] == nil && clearBody["state"] == nil)
        let retain = MigraineTimeRequest(requestId: request.requestId, expectedRevision: 1,
            expectedCanonicalUpdatedAt: base.canonicalUpdatedAt, start: request.start, end: .retain, state: nil)
        #expect((try JSONSerialization.jsonObject(with: JSONEncoder().encode(retain)) as! [String: Any])["end"] == nil)
        var medicine = MigraineFollowUpDraft(accountScope: "a", promptId: "history", episodeId: base.episode.episodeId)
        try medicine.apply(MigraineEpisodeDetail(revision: base.revision, changed: false, episode: base.episode), forAccountScope: "a")
        medicine.noteText = "Unsaved note"; medicine.medicineName = "Unsaved medicine"
        medicine.advanceAfterTimeCorrection(ack, currentAccountScope: "a")
        #expect(medicine.expectedRevision == 2 && medicine.noteText == "Unsaved note" && medicine.medicineName == "Unsaved medicine")
    }
    @Test func stateAndOrderingValidation() throws {
        let base = try context(); var draft = MigraineTimeDraft(context: base)
        draft.state = "ongoing"
        #expect(throws: MigraineTimeError.self) { try draft.request(base: base) }
        draft.endMode = "clear"; #expect(try draft.request(base: base).state == "ongoing")
        draft.state = "retain"; #expect(try draft.request(base: base).state == nil)
        draft.endMode = "set"; draft.end = try wall("2026-08-01T00:00:00")
        #expect(throws: MigraineTimeError.self) { try draft.request(base: base) }
    }
    @Test(arguments: ["time-history-success", "time-history-lost", "time-history-conflict", "time-history-invalid", "time-history-wrong-ack", "time-history-refresh-pending"])
    func actualStoreTransportRecovery(scenario: String) async throws {
        let server = MigraineFixtureServer(scenario: scenario), scope = "a"
        let store = MigraineTimeEditorStore(api: MigraineFixtureURLProtocol.makeAPI(server: server), episodeId: MigraineTimeFixture.episodeID, accountScope: { scope })
        await store.load(); let base = try #require(store.context); edit(store)
        let draft = store.draft
        let saved = await store.save()
        if scenario.contains("lost") || scenario.contains("wrong-ack") {
            #expect(saved == nil && store.pendingRequest != nil && store.draft == draft)
            let pending = store.pendingRequest
            store.edit { $0.start.dateText = "2026-01-01" }; #expect(store.draft == draft)
            let retry = await store.save()
            #expect(retry?.replayed == true && retry?.revision == base.revision + 1)
            let posts = server.requests.filter { $0.httpMethod == "POST" }
            #expect(posts.count == 2)
            let firstBody = try JSONSerialization.jsonObject(with: posts[0].httpBody!) as! NSDictionary
            let secondBody = try JSONSerialization.jsonObject(with: posts[1].httpBody!) as! NSDictionary
            #expect(firstBody == secondBody && pending?.requestId == retry?.requestId)
        } else if scenario.contains("conflict") || scenario.contains("invalid") {
            #expect(saved == nil && store.draft == draft && store.pendingRequest == nil)
            if scenario.contains("conflict") {
                #expect(store.needsReload); await store.load(preservingDraft: true)
                #expect(store.draft == draft && !store.needsReload)
            }
            #expect(await store.save() != nil)
        } else {
            #expect(saved?.revision == 2 && store.pendingRequest == nil && store.draft?.hasIntent == false)
            #expect(store.message?.contains(scenario.contains("pending") ? "still need refresh" : "times saved") == true)
        }
    }
    @Test(arguments: ["GET", "POST"])
    func accountChangeDuringAuthorizationSendsNothing(method: String) async {
        let server = MigraineFixtureServer(scenario: "time-history-success")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server); var scope = "a"
        let store = MigraineTimeEditorStore(api: api, episodeId: MigraineTimeFixture.episodeID, accountScope: { scope })
        if method == "POST" { await store.load(); edit(store) }
        let count = server.requests.filter { $0.url?.path.hasSuffix("/migraine-times") == true }.count
        api.bearerProvider = { scope = "b"; return "synthetic-token" }
        if method == "POST" { _ = await store.save() } else { await store.load() }
        #expect(server.requests.filter { $0.url?.path.hasSuffix("/migraine-times") == true }.count == count && store.context == nil && store.draft == nil)
    }
    @Test(arguments: ["account-load", "account-save", "cancel-save", "locks-save"])
    func delayedResponseCannotMutateAnotherAccountOrLockedDraft(action: String) async throws {
        let scenario = action.contains("load") ? "time-delayed-load-history" : "time-delayed-history"
        let server = MigraineFixtureServer(scenario: scenario)
        let api = MigraineFixtureURLProtocol.makeAPI(server: server); var scope = "a"
        let store = MigraineTimeEditorStore(api: api, episodeId: MigraineTimeFixture.episodeID, accountScope: { scope })
        if !action.contains("load") { await store.load(); edit(store) }
        let original = store.draft
        let pending = Task { if action.contains("load") { await store.load() } else { _ = await store.save() } }
        while !server.requests.contains(where: { $0.url?.path.hasSuffix("/migraine-times") == true && $0.httpMethod == (action.contains("load") ? "GET" : "POST") }) { await Task.yield() }
        if action.contains("account") { scope = "b" }
        else if action.contains("cancel") { pending.cancel() }
        else { store.edit { $0.start.dateText = "2026-01-01" }; #expect(store.draft == original && store.isSaving) }
        server.releaseReplies(); await pending.value
        if action.contains("account") { #expect(store.context == nil && store.draft == nil) }
        else if action.contains("cancel") {
            #expect(store.pendingRequest != nil && store.draft == original && !store.isSaving)
            #expect(await store.save()?.replayed == true)
        } else { #expect(store.pendingRequest == nil && !store.isSaving) }
    }
    @Test func anotherSaveRequiresExplicitRebaseAndLocksAllTimeBindings() async {
        let server = MigraineFixtureServer(scenario: "time-history-success")
        let store = MigraineTimeEditorStore(api: MigraineFixtureURLProtocol.makeAPI(server: server), episodeId: MigraineTimeFixture.episodeID, accountScope: { "a" })
        await store.load(); let clean = store.draft
        store.externalBusy = true; edit(store); let blocked = await store.save(); #expect(store.draft == clean && blocked == nil)
        store.externalBusy = false; edit(store); let dirty = store.draft
        await store.otherDetailsSaved(); #expect(store.needsReload && store.draft == dirty)
        await store.load(preservingDraft: true); #expect(!store.needsReload && store.draft == dirty)
    }
    @Test(arguments: ["request", "episode", "notes", "medicine", "current-revision", "newer"])
    func receiptIdentityAndNewerVersionsAreNotConfused(change: String) throws {
        let base = try context()
        let input = try JSONSerialization.jsonObject(with: data("request")) as! [String: Any]
        var draft = MigraineTimeDraft(context: base)
        draft.correctStart = true; draft.start = try wall("2026-08-31T23:30:00")
        draft.endMode = "set"; draft.end = try wall("2026-09-01T02:30:00")
        let request = try draft.request(base: base, requestId: input["request_id"] as! String)
        var raw = (try JSONSerialization.jsonObject(with: data("ack")) as! [String: Any])["data"] as! [String: Any]
        var episode = raw["episode"] as! [String: Any]
        switch change {
        case "request": raw["request_id"] = UUID().uuidString
        case "episode": episode["episode_id"] = UUID().uuidString
        case "notes": episode["notes"] = "An unrelated edit"
        case "medicine": episode["medicines"] = []
        case "current-revision": raw["current_revision"] = 0
        default: raw["current_revision"] = 3; raw["current_canonical_updated_at"] = "2026-09-10T05:00:00Z"
        }
        raw["episode"] = episode
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let changed = try decoder.decode(MigraineTimeContext.self, from: JSONSerialization.data(withJSONObject: raw))
        #expect(request.confirms(changed, base: base) == (change == "newer"))
        if change == "newer" {
            var details = MigraineFollowUpDraft(accountScope: "a", promptId: "history", episodeId: base.episode.episodeId)
            try details.apply(MigraineEpisodeDetail(revision: base.revision, changed: false, episode: base.episode), forAccountScope: "a")
            details.advanceAfterTimeCorrection(changed, currentAccountScope: "a")
            #expect(details.expectedRevision == 1)
        }
    }

}
