import Foundation
import Combine

// All synthetic transport and launch fixtures are excluded from Release.
#if DEBUG
@MainActor
final class MigraineFixtureSession: ObservableObject {
    let server: MigraineFixtureServer
    let api: APIClient
    init(scenario: String) {
        server = MigraineFixtureServer(scenario: scenario)
        api = MigraineFixtureURLProtocol.makeAPI(server: server)
    }
}

enum MigraineLocalVerification {
    static var isActive: Bool {
        ProcessInfo.processInfo.arguments.contains("-gaia-preview-migraine-follow-up-fixture")
            || ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
            || NSClassFromString("XCTestCase") != nil
    }
}

final class MigraineFixtureServer: @unchecked Sendable {
    let lock = NSLock()
    let scenario: String
    private var captured: [URLRequest] = []
    private var savedBody: NSDictionary?
    private var savedResult: [String: Any]?
    private var writeCount = 0
    var requests: [URLRequest] { lock.withLock { captured } }
    private var heldReplies: [@Sendable () -> Void] = []
    private var repliesReleased = false
    private lazy var calendarFixture = MigraineCalendarFixture(scenario: scenario)
    private lazy var timeFixture = MigraineTimeFixture(scenario: scenario)
    var timeResponseData: Data?
    var historyPageData: Data?

    // Deterministic test gate: no timer or sleeping URLProtocol thread.
    func deliverOrHold(_ reply: @escaping @Sendable () -> Void, for request: URLRequest) {
        let held = lock.withLock {
            let pendingCalendar = scenario.hasPrefix("calendar-pending")
                && request.url?.path == "/v1/symptoms/migraine/history"
                && request.url?.query?.contains("2026-09") == true
                && request.value(forHTTPHeaderField: "X-Dev-UserId") != "different-fixture-account"
            let pendingTime = scenario.contains("time-delayed")
                && (scenario.contains("load") ? request.url?.path.hasSuffix("/migraine-times") == true && request.httpMethod == "GET" : request.httpMethod != "GET")
            let pendingCalendarSave = scenario == "calendar-save-pending" && request.httpMethod == "POST"
            if !repliesReleased && (pendingTime || pendingCalendar || pendingCalendarSave || (scenario.hasPrefix("delayed-") && request.httpMethod != "GET")) {
                heldReplies.append(reply)
                return true
            }
            return false
        }
        if !held { reply() }
    }

    func releaseReplies() {
        let replies = lock.withLock {
            repliesReleased = true
            let pending = heldReplies
            heldReplies.removeAll()
            return pending
        }
        replies.forEach { $0() }
    }

    var submittedNote: String {
        guard let request = requests.last(where: { $0.httpMethod != "GET" }),
              let data = request.httpBody,
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return "No submitted note" }
        let edit = request.httpMethod == "PATCH" ? object : object["migraine"] as? [String: Any]
        return edit?["notes"] as? String ?? object["note_text"] as? String ?? "No submitted note"
    }

    // Generated through the real backend Pydantic serializer by
    // scripts/check_migraine_ios_roundtrip.py; includes Decimal strings.
    static let detailData = Data(#"""
{
  "revision": 2,
  "changed": false,
  "episode": {
    "schema_version": "1.0",
    "episode_id": "11111111-1111-4111-8111-111111111111",
    "symptom_event_id": "22222222-2222-4222-8222-222222222222",
    "symptom_code": "MIGRAINE",
    "state": "ongoing",
    "start": {
      "utc": "2026-09-08T04:30:00Z",
      "original_time": "2026-09-07 23:30",
      "timezone_name": "America/Chicago",
      "utc_offset_minutes": -300,
      "timezone_source": "device"
    },
    "end": null,
    "severity": 5,
    "early_signs": [
      {
        "label": "Light sensitivity",
        "code": "LIGHT_SENSITIVITY",
        "reported_at": {
          "utc": "2026-09-08T04:45:00Z",
          "original_time": "2026-09-07 23:45",
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "provider"
        },
        "notes": "Keep sign metadata"
      },
      {
        "label": "Neck tension",
        "code": "NECK_TENSION",
        "reported_at": {
          "utc": "2026-09-08T04:45:00Z",
          "original_time": "2026-09-07 23:45",
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "provider"
        },
        "notes": "Second sign note"
      }
    ],
    "contexts": [],
    "medicines": [
      {
        "name": "Test medicine",
        "taken_at": {
          "utc": "2026-09-08T04:45:00Z",
          "original_time": "2026-09-07 23:45",
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "provider"
        },
        "dose_amount": "10",
        "dose_unit": "mg",
        "reported_relief": "some",
        "relief_reported_at": {
          "utc": "2026-09-08T05:30:00Z",
          "original_time": null,
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "device"
        },
        "notes": "Existing medicine-specific note"
      },
      {
        "name": "Second synthetic medicine",
        "taken_at": {
          "utc": "2026-09-08T05:00:00.125000Z",
          "original_time": "2026-09-08 00:00:00.125",
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "provider"
        },
        "dose_amount": "2.5",
        "dose_unit": "mg",
        "reported_relief": "some",
        "relief_reported_at": {
          "utc": "2026-09-08T05:30:00Z",
          "original_time": null,
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "device"
        },
        "notes": "Keep this second entry"
      }
    ],
    "notes": "Resting in a dark room.",
    "provenance": {
      "source_type": "follow_up",
      "source_platform": "ios",
      "source_provider": null,
      "external_event_id": null,
      "source_file_hash": null,
      "import_run_id": null,
      "raw_row_ref": null,
      "mapping_version": null
    },
    "lifecycle": {
      "revision": 2,
      "created_at": "2026-09-08T04:30:00Z",
      "updated_at": "2026-09-08T05:30:00Z",
      "deleted_at": null,
      "deletion_scope": null
    }
  }
}
"""#.utf8)

    init(scenario: String = "success") { self.scenario = scenario }

    static func body(_ request: URLRequest) -> Data {
        if let data = request.httpBody { return data }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }

    func response(_ original: URLRequest) throws -> (Int, Data) {
        try lock.withLock {
            var request = original
            request.httpBody = Self.body(original)
            captured.append(request)
            guard request.url?.host == "gaia-fixture.invalid" else { throw URLError(.unsupportedURL) }
            if scenario.hasPrefix("time-") || scenario.hasPrefix("calendar-time-") {
                if request.url?.path.hasSuffix("/migraine-times") == true, let timeResponseData { return (200, timeResponseData) }
                return try timeFixture.response(request)
            }
            if scenario.hasPrefix("calendar-") {
                if request.url?.path == "/v1/symptoms/migraine/history", let historyPageData { return (200, historyPageData) }
                return try calendarFixture.response(request)
            }
            let path = request.url!.path
            let outcome = scenario.hasPrefix("delayed-") ? String(scenario.split(separator: "-").last!) : scenario
            if path == "/health" { return (200, Data("{}".utf8)) }
            let detail = try JSONSerialization.jsonObject(with: Self.detailData) as! [String: Any]
            let episode = detail["episode"] as! [String: Any]
            let id = episode["episode_id"] as! String
            let prompt: [String: Any] = ["id": "fixture-prompt", "episode_id": id,
                "symptom_code": "MIGRAINE", "symptom_label": "Migraine",
                "question_text": "How is your migraine now?", "detail_focus": "pain",
                "status": "pending", "push_delivery_enabled": false]
            var item: [String: Any] = ["id": id, "symptom_code": "MIGRAINE", "label": "Migraine",
                "severity": 5, "logged_at": "2026-09-08T04:30:00Z", "current_state": "ongoing",
                "note_preview": episode["notes"] ?? NSNull(), "note_count": 1,
                "likely_drivers": [], "gauge_keys": [], "pending_follow_up": prompt]
            func json(_ data: [String: Any]) throws -> (Int, Data) {
                (200, try JSONSerialization.data(withJSONObject: ["ok": true, "data": data], options: .sortedKeys))
            }
            if request.httpMethod == "GET" {
                if path.hasSuffix("/migraine-detail") {
                    if scenario == "unsupported" { return (503, Data(#"{"detail":"structured migraine detail storage is not installed"}"#.utf8)) }
                    if scenario == "old-route" { return (404, Data(#"{"detail":"Not Found"}"#.utf8)) }
                    if scenario == "missing-episode" { return (404, Data(#"{"detail":"Migraine episode not found"}"#.utf8)) }
                    if scenario == "load-failure" { return (500, Data(#"{"detail":"temporary failure"}"#.utf8)) }
                    return try json(detail)
                }
                if path == "/v1/symptoms/current/\(id)" { return try json(item) }
                throw URLError(.unsupportedURL)
            }
            guard path == "/v1/symptoms/follow-ups/fixture-prompt/respond"
                    || path == "/v1/symptoms/current/\(id)/updates"
                    || (request.httpMethod == "PATCH" && path == "/v1/symptoms/current/\(id)/migraine-detail") else {
                throw URLError(.unsupportedURL)
            }
            writeCount += 1
            if outcome == "conflict" { return (409, Data(#"{"detail":"Migraine episode revision conflict"}"#.utf8)) }
            if outcome == "rejected" { return (422, Data(#"{"detail":"Invalid response"}"#.utf8)) }
            if outcome == "cancelled" { throw URLError(.cancelled) }
            if outcome == "timeout", writeCount == 1 { throw URLError(.timedOut) }
            let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            if path.hasSuffix("/updates") {
                item["severity"] = body["severity"]
                item["note_preview"] = body["note_text"]
                return try json(item)
            }
            if let savedResult {
                guard (body as NSDictionary) == savedBody else { return (409, Data(#"{"detail":"Retry payload changed"}"#.utf8)) }
                return try json(savedResult)
            }
            var savedDetail = detail
            var savedEpisode = episode
            let edit = (request.httpMethod == "PATCH" ? body : body["migraine"] as? [String: Any]) ?? [:]
            for key in ["medicines", "early_signs", "contexts", "notes"] {
                if let value = edit[key] { savedEpisode[key] = value }
            }
            let state = body["state"] as? String ?? "ongoing"
            savedEpisode["state"] = scenario == "wrong-detail-state" ? "ongoing" : state
            savedEpisode["episode_id"] = scenario == "wrong-detail-episode" ? "wrong" : id
            savedDetail["revision"] = scenario == "unchanged" ? 2 : 3
            var lifecycle = savedEpisode["lifecycle"] as! [String: Any]
            lifecycle["revision"] = savedDetail["revision"]
            savedEpisode["lifecycle"] = lifecycle
            savedDetail["episode"] = savedEpisode
            savedDetail["changed"] = true
            item["current_state"] = scenario == "wrong-state" ? "ongoing" : state
            item["id"] = scenario == "wrong-episode" ? "wrong" : id
            item["pending_follow_up"] = NSNull()
            item["note_preview"] = savedEpisode["notes"]
            var answered = prompt
            answered["status"] = scenario == "pending" ? "pending" : "answered"
            answered["id"] = scenario == "wrong-prompt" ? "wrong" : "fixture-prompt"
            var result = request.httpMethod == "PATCH" ? savedDetail
                : ["prompt": answered, "episode": item, "migraine_detail": savedDetail]
            if request.httpMethod == "POST", body["migraine"] == nil { result.removeValue(forKey: "migraine_detail") }
            savedResult = result
            savedBody = body as NSDictionary
            if scenario == "committed-timeout", writeCount == 1 { throw URLError(.networkConnectionLost) }
            return try json(result)
        }
    }
}

final class MigraineFixtureURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var server: MigraineFixtureServer?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    private let deliveryLock = NSLock()
    private var stopped = false

    override func startLoading() {
        guard let server = Self.server else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
            return
        }
        let result = Result { try server.response(request) }
        server.deliverOrHold({ [weak self] in
            guard let self, !self.deliveryLock.withLock({ self.stopped }) else { return }
            switch result {
            case .success(let (code, data)):
                let response = HTTPURLResponse(url: self.request.url!, statusCode: code, httpVersion: "HTTP/1.1",
                                               headerFields: ["Content-Type": "application/json"])!
                self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                self.client?.urlProtocol(self, didLoad: data)
                self.client?.urlProtocolDidFinishLoading(self)
            case .failure(let error):
                self.client?.urlProtocol(self, didFailWithError: error)
            }
        }, for: request)
    }
    override func stopLoading() { deliveryLock.withLock { stopped = true } }

    static func makeAPI(server: MigraineFixtureServer) -> APIClient {
        Self.server = server
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [Self.self]
        return APIClient(config: APIConfig(baseURLString: "https://gaia-fixture.invalid", bearer: "synthetic-local-token"),
                         session: URLSession(configuration: config))
    }
}
#else
enum MigraineLocalVerification {
    static let isActive = false
}
#endif
