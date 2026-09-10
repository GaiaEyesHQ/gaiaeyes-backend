import Foundation

#if DEBUG
// Called only under MigraineFixtureServer's lock; all records are synthetic.
final class MigraineCalendarFixture {
    let scenario: String
    private var failed = false
    private var notes: [String: String] = [:]
    static let firstID = "11111111-1111-4111-8111-111111111111"
    static let secondID = "33333333-3333-4333-8333-333333333333"
    init(scenario: String) { self.scenario = scenario }

    func response(_ request: URLRequest) throws -> (Int, Data) {
        let path = request.url!.path
        func json(_ data: Any) throws -> (Int, Data) {
            (200, try JSONSerialization.data(withJSONObject: ["ok": true, "data": data], options: .sortedKeys))
        }
        if path == "/health" { return (200, Data(#"{"ok":true}"#.utf8)) }
        if path == "/v1/symptoms/current/timeline" {
            return try json([["id": "synthetic-update", "episode_id": Self.firstID,
                "symptom_code": "FATIGUE", "label": "Fatigue", "update_kind": "logged",
                "state": "new", "severity": 4, "occurred_at": "2026-09-09T12:00:00Z"]])
        }
        let ids = [Self.firstID, Self.secondID]
        if path == "/v1/symptoms/migraine/history" {
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            let start = query.first(where: { $0.name == "start" })!.value!
            let end = query.first(where: { $0.name == "end" })!.value!
            let cursor = query.first(where: { $0.name == "cursor" })?.value
            if scenario == "calendar-unsupported" { return (503, Data(#"{"detail":"migraine calendar history is not enabled"}"#.utf8)) }
            if scenario == "calendar-error" && !failed { failed = true; return (500, Data(#"{"detail":"temporary"}"#.utf8)) }
            if cursor != nil && !failed && ["calendar-pagination", "calendar-conflict"].contains(scenario) {
                failed = true
                return (scenario == "calendar-conflict" ? 409 : 500, Data(#"{"detail":"retry"}"#.utf8))
            }
            let empty = scenario == "calendar-empty" || !start.hasPrefix("2026-09")
                || request.value(forHTTPHeaderField: "X-Dev-UserId") == "different-fixture-account"
            let index = cursor == nil ? 0 : 1
            let entries: [[String: Any]] = empty ? [] : [["id": ids[index],
                "started_at": index == 0 ? "2026-09-09T16:00:00Z" : "2026-09-09T04:30:00Z",
                "ended_at": index == 0 ? NSNull() : "2026-09-09T07:30:00Z",
                "state": index == 0 ? "ongoing" : "resolved", "end_status": index == 0 ? "open" : "recorded",
                "severity": 5, "note_preview": notes[ids[index]] ?? "Synthetic episode \(index + 1)"]]
            return try json(["items": entries, "start": start, "end": end, "as_of": "2026-09-10T12:00:00Z",
                "snapshot": "fixture-month", "next_cursor": empty || cursor != nil ? NSNull() : "second-page",
                "complete": empty || cursor != nil])
        }
        guard let id = ids.first(where: { path.contains($0) }) else { throw URLError(.unsupportedURL) }
        if path.hasSuffix("/migraine-detail") {
            var detail = try JSONSerialization.jsonObject(with: MigraineFixtureServer.detailData) as! [String: Any]
            var episode = detail["episode"] as! [String: Any]
            episode["episode_id"] = id; episode["notes"] = notes[id] ?? "Synthetic episode \(id == ids[0] ? 1 : 2)"
            episode["state"] = id == ids[0] ? "ongoing" : "resolved"
            detail["episode"] = episode
            return try json(detail)
        }
        if request.httpMethod == "POST" {
            let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            notes[id] = body["note_text"] as? String
        }
        return try json(["id": id, "symptom_code": "MIGRAINE", "label": "Migraine",
            "severity": 5, "logged_at": "2026-09-09T16:00:00Z", "current_state": id == ids[0] ? "ongoing" : "resolved",
            "note_preview": notes[id] ?? "Synthetic episode \(id == ids[0] ? 1 : 2)",
            "note_count": 1, "likely_drivers": [], "gauge_keys": []])
    }
}
#endif
