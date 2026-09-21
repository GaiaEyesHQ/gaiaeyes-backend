#if DEBUG && GAIA_MIGRAINE_APP_VERIFICATION
import Foundation
import SwiftUI

// Compiled only in MigraineVerification, never Debug/Release/MigraineCandidate.
// Real ContentView and episode views use the same API decoding/save/navigation code.
enum MigraineAppVerification {
    static let bundleID = "com.gaiaeyes.g038.synthetic"
    static var isActive: Bool {
        Bundle.main.bundleIdentifier == bundleID
            && ProcessInfo.processInfo.arguments.contains("-gaia-verify-normal-app")
    }
    static var scenario: String {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-gaia-app-scenario"), args.indices.contains(index + 1) else { return "success" }
        return args[index + 1]
    }
    static var largeText: Bool { ProcessInfo.processInfo.arguments.contains("-gaia-app-large-text") }
    static let server = MigraineAppVerificationServer(scenario: scenario)
    @MainActor static let api: APIClient = {
        let api = APIClient(config: APIConfig(baseURLString: "https://gaia-app-verification.invalid", bearer: "synthetic-local-token"))
        api.devUserId = "fixture-account"
        return api
    }()

    @MainActor static func bootstrap() {
#if targetEnvironment(simulator)
        precondition(Bundle.main.bundleIdentifier == bundleID, "Verification must use its own simulator bundle")
        // Only this disposable bundle's defaults; no shared suite or keychain access.
        UserDefaults.standard.removePersistentDomain(forName: bundleID)
        URLProtocol.registerClass(MigraineAppVerificationProtocol.self)
        _ = server
#else
        fatalError("MigraineVerification is restricted to an owned simulator")
#endif
    }
    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MigraineAppVerificationProtocol.self]
        config.urlCache = nil; config.httpCookieStorage = nil; config.urlCredentialStorage = nil
        return URLSession(configuration: config)
    }
}

final class MigraineAppVerificationServer: @unchecked Sendable {
    private let lock = NSLock()
    private let scenario: String
    private let fixture: MigraineTimeFixture
    private var detailReads = 0
    private var detailWrites = 0
    private var timeWrites = 0
    private var captured: [[String: Any]] = []
    private var held: [@Sendable () -> Void] = []
    private var released = false
    private var responded = false
    init(scenario: String) {
        self.scenario = scenario
        let behavior = scenario == "time-uncertain" ? "time-lost-entries"
            : scenario == "detail-uncertain" ? "time-detail-lost-entries" : "time-entries"
        fixture = MigraineTimeFixture(scenario: behavior, activeEpisode: true)
    }
    var receipt: String {
        lock.withLock {
            let data = try! JSONSerialization.data(withJSONObject: captured, options: [.sortedKeys, .prettyPrinted])
            return String(decoding: data, as: UTF8.self)
        }
    }
    func deliver(_ reply: @escaping @Sendable () -> Void, request: URLRequest) {
        let delayed = lock.withLock {
            if scenario == "delayed-account", request.httpMethod == "PATCH", !released {
                held.append(reply); return true
            }
            return false
        }
        if !delayed { reply() }
    }
    func release() {
        let replies = lock.withLock { released = true; let result = held; held.removeAll(); return result }
        replies.forEach { $0() }
    }
    func response(_ original: URLRequest) throws -> (Int, Data) {
        try lock.withLock {
            var request = original
            if request.httpBody == nil, let stream = request.httpBodyStream {
                stream.open(); defer { stream.close() }
                var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    guard count > 0 else { break }; data.append(contentsOf: buffer.prefix(count))
                }
                request.httpBody = data
            }
            let path = request.url?.path ?? ""
            let method = request.httpMethod ?? "GET"
            let id = MigraineTimeFixture.episodeID
            let episodePath = "/v1/symptoms/current/" + id
            let allowed = method == "GET" && ["/health", "/v1/symptoms/current", "/v1/symptoms/current/timeline", "/v1/symptoms/migraine/history", episodePath, episodePath + "/migraine-detail", episodePath + "/migraine-times"].contains(path)
                || method == "PATCH" && [episodePath + "/migraine-detail", episodePath + "/migraine-times"].contains(path)
                || method == "POST" && [episodePath + "/updates", episodePath + "/migraine-times", "/v1/symptoms/follow-ups/fixture-prompt/respond"].contains(path)
            let accepted = request.url?.host == "gaia-app-verification.invalid" && allowed
            var record: [String: Any] = ["method": method, "path": path, "accepted": accepted,
                "scope": request.value(forHTTPHeaderField: "X-Dev-UserId") ?? "none"]
            if accepted, let body = request.httpBody {
                record["body"] = try JSONSerialization.jsonObject(with: body)
                // Keep original synthetic bytes for exact Decimal decoding in request assertions.
                record["body_utf8"] = String(decoding: body, as: UTF8.self)
            }
            captured.append(record)
            guard accepted else { throw URLError(.unsupportedURL) } // Never open a socket or redirect.
            func json(_ value: Any) throws -> (Int, Data) {
                (200, try JSONSerialization.data(withJSONObject: ["ok": true, "data": value], options: .sortedKeys))
            }
            func error(_ status: Int, _ detail: String) throws -> (Int, Data) {
                (status, try JSONSerialization.data(withJSONObject: ["detail": detail]))
            }
            if path == "/health" { return (200, Data(#"{"ok":true}"#.utf8)) }
            var prompt: [String: Any] = ["id": "fixture-prompt", "episode_id": id,
                "symptom_code": "MIGRAINE", "symptom_label": "Migraine", "question_text": "How is your migraine now?",
                "detail_focus": "pain", "status": "pending", "push_delivery_enabled": false]
            let otherAccount = request.value(forHTTPHeaderField: "X-Dev-UserId") == "different-fixture-account"
            if otherAccount, path.hasPrefix(episodePath) { return try error(404, "Migraine episode not found") }
            if path == "/v1/symptoms/follow-ups/fixture-prompt/respond" {
                guard !otherAccount, ["followup", "followup-uncertain"].contains(scenario), !responded, let body = request.httpBody,
                      let value = try JSONSerialization.jsonObject(with: body) as? [String: Any],
                      value["state"] as? String == "ongoing", let edit = value["migraine"] as? [String: Any] else {
                    throw URLError(.unsupportedURL)
                }
                var save = request; save.url = URL(string: "https://gaia-app-verification.invalid" + episodePath + "/migraine-detail")
                save.httpMethod = "PATCH"; save.httpBody = try JSONSerialization.data(withJSONObject: edit)
                let saved = try fixture.response(save)
                guard saved.0 == 200 else { return saved }
                let detail = (try JSONSerialization.jsonObject(with: saved.1) as! [String: Any])["data"]!
                save.url = URL(string: "https://gaia-app-verification.invalid" + episodePath); save.httpMethod = "GET"; save.httpBody = nil
                let item = (try JSONSerialization.jsonObject(with: fixture.response(save).1) as! [String: Any])["data"]!
                responded = true; prompt["status"] = "answered"
                if scenario == "followup-uncertain" { throw URLError(.networkConnectionLost) }
                return try json(["prompt": prompt, "episode": item, "migraine_detail": detail])
            }
            if path == "/v1/symptoms/current" {
                var itemRequest = request; itemRequest.url = request.url!.deletingLastPathComponent().appendingPathComponent("current/" + id)
                let data = try fixture.response(itemRequest).1
                var item = (try JSONSerialization.jsonObject(with: data) as! [String: Any])["data"] as! [String: Any]
                if ["followup", "followup-uncertain"].contains(scenario), !responded { item["pending_follow_up"] = prompt }
                return try json(["generated_at": ISO8601DateFormatter().string(from: Date()), "window_hours": 24,
                    "summary": ["active_count": otherAccount ? 0 : 1, "new_count": 0, "ongoing_count": otherAccount ? 0 : 1,
                                "improving_count": 0, "worse_count": 0, "follow_up_available": false],
                    "items": otherAccount ? [] : [item], "contributing_drivers": [], "pattern_context": [],
                    "follow_up_settings": ["notifications_enabled": false, "enabled": false, "notification_family_enabled": false,
                        "push_enabled": false, "cadence": "off", "states": [], "symptom_codes": []]])
            }
            if path == "/v1/symptoms/current/timeline" {
                return try json(otherAccount ? [] : [["id": "synthetic-update", "episode_id": id, "symptom_code": "MIGRAINE",
                    "label": "Migraine", "update_kind": "logged", "state": "ongoing", "severity": 5, "occurred_at": "2026-09-09T04:30:00Z"]])
            }
            if path == "/v1/symptoms/migraine/history", scenario == "calendar-unavailable" {
                return try error(503, "migraine calendar history is not enabled")
            }
            if path.hasSuffix("/migraine-detail") {
                if method == "GET" { detailReads += 1 } else { detailWrites += 1 }
                if scenario == "detail-old-route" { return try error(404, "Not Found") }
                if scenario == "detail-missing" { return try error(404, "Migraine episode not found") }
                if scenario == "detail-unavailable" || scenario == "detail-retry" && detailReads == 1 && method == "GET"
                    || scenario == "detail-uncertain" && (detailWrites > 1 || method == "GET" && detailWrites > 0) {
                    return try error(503, "structured migraine detail storage is not installed")
                }
            }
            if path.hasSuffix("/migraine-times") {
                if method != "GET" { timeWrites += 1 }
                if scenario == "time-unavailable" || scenario == "time-uncertain" && (timeWrites > 1 || method == "GET" && timeWrites > 0) {
                    return try error(503, "Migraine time editing is not enabled")
                }
            }
            return try fixture.response(request)
        }
    }
}

final class MigraineAppVerificationProtocol: URLProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let server = MigraineAppVerification.server
        let result = Result { try server.response(request) }
        server.deliver({ [weak self] in
            guard let self, !self.lock.withLock({ self.stopped }) else { return }
            switch result {
            case .success(let (code, data)):
                let response = HTTPURLResponse(url: self.request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
                self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                self.client?.urlProtocol(self, didLoad: data)
                self.client?.urlProtocolDidFinishLoading(self)
            case .failure(let error): self.client?.urlProtocol(self, didFailWithError: error)
            }
        }, request: request)
    }
    override func stopLoading() { lock.withLock { stopped = true } }
}

struct MigraineAppVerificationControls: View {
    @State private var receipt: String?
    var body: some View {
        HStack {
            Button("Test account") {
                MigraineAppVerification.api.devUserId = "different-fixture-account"
                AuthManager.shared.replaceVerificationAccount()
                MigraineAppVerification.server.release()
            }.accessibilityIdentifier("g038-switch-account")
            Button("Test receipt") { receipt = MigraineAppVerification.server.receipt }
                .accessibilityIdentifier("g038-receipt-open")
            Button("Release test reply") { MigraineAppVerification.server.release() }
                .accessibilityIdentifier("g038-release-reply")
        }
        .font(.caption)
        .sheet(isPresented: Binding(get: { receipt != nil }, set: { if !$0 { receipt = nil } })) {
            NavigationStack {
                ScrollView { Text(receipt ?? "").font(.caption.monospaced()).accessibilityIdentifier("g038-request-receipt") }
                    .toolbar { Button("Close receipt") { receipt = nil } }
            }
        }
    }
}
#endif
