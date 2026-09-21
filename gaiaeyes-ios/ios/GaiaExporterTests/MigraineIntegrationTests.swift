import Foundation
import Testing
@testable import GaiaEyes

@Suite(.serialized)
@MainActor
struct MigraineIntegrationTests {
    @Test(arguments: Array(0...7))
    func unconfirmedEditorCanExitAfterIO(mask: Int) {
        let state = MigraineEditorNavigationState(requestInFlight: mask & 1 != 0,
            detailPending: mask & 2 != 0, timePending: mask & 4 != 0)
        #expect(state.canClose == (mask & 1 == 0))
        #expect(state.requiresConfirmation == (mask & 6 != 0))
    }
    @Test(arguments: [false, true], [false, true])
    func explicitCandidateAndOrdinaryRelease(isDebug: Bool, candidate: Bool) {
        #expect(MigraineStructuredFollowUpFeature.resolve(isDebugBuild: isDebug, arguments: [],
            environment: [:], releaseCandidateEnabled: candidate) == candidate)
        #expect(MigraineCalendarFeature.resolve(isDebugBuild: isDebug, arguments: [],
            releaseCandidateEnabled: candidate) == candidate)
        #expect(MigraineTimeEditingFeature.resolve(isDebugBuild: isDebug, arguments: [],
            releaseCandidateEnabled: candidate) == candidate)
        // Process flags can enable ordinary Debug only; a candidate needs no process overrides.
        #expect(MigraineStructuredFollowUpFeature.resolve(isDebugBuild: isDebug,
            arguments: [MigraineStructuredFollowUpFeature.launchArgument],
            environment: [MigraineStructuredFollowUpFeature.environmentKey: "1"],
            releaseCandidateEnabled: candidate) == (isDebug || candidate))
    }

    @Test(arguments: Array(0...7))
    func debugFeaturesRemainIndependent(mask: Int) {
        var arguments: [String] = []
        if mask & 1 != 0 { arguments.append(MigraineStructuredFollowUpFeature.launchArgument) }
        if mask & 2 != 0 { arguments.append("-gaia-enable-migraine-calendar") }
        if mask & 4 != 0 { arguments.append("-gaia-enable-migraine-time-editing") }
        #expect(MigraineStructuredFollowUpFeature.resolve(isDebugBuild: true, arguments: arguments, environment: [:]) == (mask & 1 != 0))
        #expect(MigraineCalendarFeature.resolve(isDebugBuild: true, arguments: arguments) == (mask & 2 != 0))
        #expect(MigraineTimeEditingFeature.resolve(isDebugBuild: true, arguments: arguments) == (mask & 4 != 0))
        #expect(!MigraineStructuredFollowUpFeature.resolve(isDebugBuild: false, arguments: arguments, environment: [:]))
        #expect(!MigraineCalendarFeature.resolve(isDebugBuild: false, arguments: arguments))
        #expect(!MigraineTimeEditingFeature.resolve(isDebugBuild: false, arguments: arguments))
    }

    private func error(_ status: Int, _ detail: String) -> APIError {
        let data = try! JSONSerialization.data(withJSONObject: ["detail": detail])
        return .server(code: status, body: String(decoding: data, as: UTF8.self))
    }

    @Test func capabilityRequiresTheSpecificServerSignal() {
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "structured migraine detail storage is not installed")))
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "migraine calendar history is not enabled"), for: .calendar))
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "canonical migraine history storage is not installed"), for: .calendar))
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "Migraine time editing is not enabled"), for: .timeEditing))
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "migraine time correction storage is not installed"), for: .timeEditing))
        #expect(MigraineFollowUpWorkflow.isUnsupportedCapability(error(404, "Not Found"), for: .timeEditing))
        #expect(!MigraineFollowUpWorkflow.isUnsupportedCapability(error(404, "Migraine episode not found")))
        #expect(!MigraineFollowUpWorkflow.isUnsupportedCapability(error(503, "temporarily overloaded"), for: .calendar))
        #expect(!MigraineFollowUpWorkflow.isUnsupportedCapability(error(401, "Not Found")))
        #expect(!MigraineFollowUpWorkflow.isUnsupportedCapability(URLError(.notConnectedToInternet)))
    }

    @Test(arguments: ["unavailable", "temporary", "missing-episode"])
    func calendarDoesNotCallEveryFailureAnUnsupportedFeature(reason: String) async {
        let failure = reason == "unavailable" ? error(503, "migraine calendar history is not enabled")
            : reason == "temporary" ? error(503, "temporarily overloaded") : error(404, "Migraine episode not found")
        let store = MigraineHistoryStore(accountScope: { "account-a" }, fetch: { _, _, validate in
            try validate(); throw failure
        })
        await store.load(range: DateInterval(start: Date(timeIntervalSince1970: 1_788_220_800), duration: 86400), scope: "account-a")
        #expect(!store.complete)
        #expect(store.items.isEmpty)
        #expect((store.errorMessage?.contains("not available on this server yet") == true) == (reason == "unavailable"))
    }

    @Test(arguments: ["current", "timeline", "episode", "detail"])
    func normalEntryReadsValidateAccountBeforePrivateTransport(endpoint: String) async throws {
        let server = MigraineFixtureServer(scenario: "success")
        let api = MigraineFixtureURLProtocol.makeAPI(server: server)
        let validate: @MainActor () throws -> Void = {
            try MigraineFollowUpWorkflow.checkAccount("account-a", current: { "account-b" })
        }
        do {
            switch endpoint {
            case "current": _ = try await api.fetchCurrentSymptoms(validateRequest: validate)
            case "timeline": _ = try await api.fetchCurrentSymptomTimeline(validateRequest: validate)
            case "episode": _ = try await api.fetchCurrentSymptom(episodeId: "11111111-1111-4111-8111-111111111111", validateRequest: validate)
            default: _ = try await api.fetchMigraineEpisodeDetail(episodeId: "11111111-1111-4111-8111-111111111111", validateRequest: validate)
            }
            Issue.record("Changed account reached a private read")
        } catch { #expect(error is MigraineDraftError) }
        // APIClient's public health preflight is allowed; no private route is sent.
        #expect(server.requests.allSatisfy { $0.url?.path == "/health" && $0.httpMethod == "GET" })
    }

    @Test(arguments: ["Note typed during the outage", ""])
    func detailsReturningAfterAnOutageKeepLocalNoteAndSavedMedicines(visibleNote: String) throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode(MigraineEpisodeDetail.self, from: MigraineFixtureServer.detailData)
        var draft = MigraineFollowUpDraft(accountScope: "account-a", promptId: "history", episodeId: detail.episode.episodeId)
        try draft.applyInitialDetail(detail, currentAccountScope: "account-a", visibleNote: visibleNote, originalVisibleNote: "Original preview")
        #expect(draft.noteText == visibleNote)
        #expect(draft.expectedRevision == detail.revision)
        #expect(draft.originalMedicines == detail.episode.medicines)
        #expect(draft.medicineRows.count == detail.episode.medicines.count)
        #expect(throws: MigraineDraftError.self) {
            try draft.applyInitialDetail(detail, currentAccountScope: "account-b", visibleNote: "different account", originalVisibleNote: "")
        }
        #expect(draft.noteText == visibleNote)
    }

    @Test func timeCapabilityLossRetainsDraftAndUnconfirmedRequest() async throws {
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/migraine_time_backend_context.json")
        let data = try Data(contentsOf: source)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let context = try #require(decoder.decode(Envelope<MigraineTimeContext>.self, from: data).payload)
        IntegrationTimeURLProtocol.contextData = data
        IntegrationTimeURLProtocol.available = true
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [IntegrationTimeURLProtocol.self]
        let api = APIClient(config: APIConfig(baseURLString: "https://gaia-integration.invalid", bearer: "synthetic"),
            session: URLSession(configuration: configuration))
        let store = MigraineTimeEditorStore(api: api, episodeId: context.episode.episodeId, accountScope: { "account-a" })
        await store.load()
        store.edit { $0.correctStart = true; $0.start.dateText = "2026-08-31" }
        let retainedDraft = try #require(store.draft)
        IntegrationTimeURLProtocol.available = false
        #expect(await store.save() == nil)
        let pending = try #require(store.pendingRequest)
        #expect(store.draft == retainedDraft)
        #expect(store.message?.contains("has not been confirmed") == true)
        await store.load(preservingDraft: true)
        #expect(store.pendingRequest == pending)
        #expect(store.draft == retainedDraft)
        #expect(store.needsReload)
        #expect(store.message?.contains("Time editing is not available yet") == true)
    }
}

// Test-target-only transport; no production host, global registration or socket.
private final class IntegrationTimeURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var contextData = Data()
    nonisolated(unsafe) static var available = true
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard request.url?.host == "gaia-integration.invalid" else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL)); return
        }
        let health = request.url?.path == "/health"
        let code = health || Self.available ? 200 : 503
        let data = health ? Data("{\"ok\":true}".utf8) : Self.available ? Self.contextData
            : Data("{\"detail\":\"Migraine time editing is not enabled\"}".utf8)
        let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: ["Content-Type":"application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
