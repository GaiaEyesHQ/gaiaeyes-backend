import Foundation

#if DEBUG
// Synthetic backend serializer fixture. Access only under the fixture server lock.
final class MigraineTimeFixture {
    let scenario: String
    static let episodeID = "33333333-3333-4333-8333-333333333333"
    static let contextData = Data(#"""
{
  "episode": {
    "schema_version": "1.0",
    "episode_id": "33333333-3333-4333-8333-333333333333",
    "symptom_event_id": "4320153f-e300-449b-8810-e34b5d1482fe",
    "symptom_code": "MIGRAINE",
    "state": "resolved",
    "start": {
      "utc": "2026-09-09T04:30:00Z",
      "original_time": null,
      "timezone_name": "America/Chicago",
      "utc_offset_minutes": null,
      "timezone_source": "device"
    },
    "end": {
      "utc": "2026-09-09T07:30:00Z",
      "original_time": null,
      "timezone_name": null,
      "utc_offset_minutes": null,
      "timezone_source": "unknown"
    },
    "severity": 5,
    "early_signs": [],
    "contexts": [],
    "medicines": [
      {
        "name": "Synthetic medicine",
        "taken_at": {
          "utc": "2026-09-01T05:30:00Z",
          "original_time": "2026-09-01T00:30:00",
          "timezone_name": "America/Chicago",
          "utc_offset_minutes": -300,
          "timezone_source": "user"
        },
        "dose_amount": "2.5",
        "dose_unit": "mg",
        "reported_relief": null,
        "relief_reported_at": null,
        "notes": null
      }
    ],
    "notes": "Keep notes",
    "provenance": {
      "source_type": "manual",
      "source_platform": "g009_postgres",
      "source_provider": null,
      "external_event_id": null,
      "source_file_hash": null,
      "import_run_id": null,
      "raw_row_ref": null,
      "mapping_version": null
    },
    "lifecycle": {
      "revision": 1,
      "created_at": "2026-09-09T04:30:00Z",
      "updated_at": "2026-09-09T04:30:00Z",
      "deleted_at": null,
      "deletion_scope": null
    }
  },
  "revision": 1,
  "canonical_updated_at": "2026-09-10T03:45:18.614460+00:00",
  "raw_end_utc": "2026-09-09T07:30:00+00:00",
  "inconsistent_end": false
}
"""#.utf8)
    private var context: [String: Any]
    private var receipts: [String: [String: Any]] = [:]
    private var failed = false
    private var externalDetailsChanged = false
    private var detailFailed = false
    private var lastDetailRequest: NSDictionary?
    private var laterDetailChanged = false
    var stored: [String: Any] { context }
    init(scenario: String) {
        self.scenario = scenario
        context = try! JSONSerialization.jsonObject(with: Self.contextData) as! [String: Any]
        if scenario.contains("entries") {
            let detail = try! JSONSerialization.jsonObject(with: MigraineFixtureServer.detailDataForScenario(scenario)) as! [String: Any]
            var episode = context["episode"] as! [String: Any]
            episode["medicines"] = (detail["episode"] as! [String: Any])["medicines"]
            context["episode"] = episode
        }
    }
    func response(_ request: URLRequest) throws -> (Int, Data) {
        let path = request.url!.path
        func json(_ data: Any) throws -> (Int, Data) {
            (200, try JSONSerialization.data(withJSONObject: ["ok": true, "data": data], options: .sortedKeys))
        }
        func error(_ code: Int) -> (Int, Data) { (code, Data(#"{"detail":"synthetic rejection"}"#.utf8)) }
        if path == "/health" { return (200, Data(#"{"ok":true}"#.utf8)) }
        var episode = context["episode"] as! [String: Any]
        if path == "/v1/symptoms/migraine/history" {
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            let start = query.first { $0.name == "start" }!.value!, end = query.first { $0.name == "end" }!.value!
            let onset = (episode["start"] as! [String: Any])["utc"] as! String
            let ended = (episode["end"] as? [String: Any])?["utc"] as? String
            let state = episode["state"] as! String
            let from = MigraineFollowUpDraft.parseDate(start)!, to = MigraineFollowUpDraft.parseDate(end)!
            let at = MigraineFollowUpDraft.parseDate(onset)!
            let last = ended.flatMap(MigraineFollowUpDraft.parseDate) ?? (state == "resolved" ? at : to)
            let visible = at < to && (last > from || at >= from)
                && request.value(forHTTPHeaderField: "X-Dev-UserId") != "different-fixture-account"
            let items: [[String: Any]] = visible ? [["id": Self.episodeID, "started_at": onset,
                "ended_at": ended as Any? ?? NSNull(), "state": state,
                "end_status": ended != nil ? "recorded" : state == "resolved" ? "unknown" : "open",
                "severity": 5, "note_preview": episode["notes"] ?? NSNull()]] : []
            return try json(["items": items, "start": start, "end": end, "as_of": "2026-09-10T12:00:00Z",
                "snapshot": "time-fixture-\(context["revision"]!)", "next_cursor": NSNull(), "complete": true])
        }
        guard path.contains(Self.episodeID) else { return error(404) }
        if path.hasSuffix("/migraine-times") {
            if scenario.contains("unsupported") { return error(503) }
            if request.httpMethod == "GET" { return try json(context) }
            let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            let id = body["request_id"] as! String
            if var receipt = receipts[id] {
                receipt["replayed"] = true
                receipt["current_revision"] = context["revision"]
                receipt["current_canonical_updated_at"] = context["canonical_updated_at"]
                return try json(receipt)
            }
            if scenario.contains("conflict") && !failed { failed = true; context["canonical_updated_at"] = "2026-09-10T04:00:01Z"; return error(409) }
            if scenario.contains("invalid") && !failed { failed = true; return error(422) }
            if body["expected_revision"] as? Int != context["revision"] as? Int
                || body["expected_canonical_updated_at"] as? String != context["canonical_updated_at"] as? String { return error(409) }
            if let start = body["start"] { episode["start"] = start }
            if let end = body["end"] { episode["end"] = end }
            if let state = body["state"] { episode["state"] = state }
            let revision = (context["revision"] as! Int) + 1
            let token = "2026-09-10T04:00:\(String(format: "%02d", revision))Z"
            var lifecycle = episode["lifecycle"] as! [String: Any]
            lifecycle["revision"] = revision; lifecycle["updated_at"] = token; episode["lifecycle"] = lifecycle
            context["episode"] = episode; context["revision"] = revision; context["canonical_updated_at"] = token
            context["raw_end_utc"] = (episode["end"] as? [String: Any])?["utc"] ?? NSNull()
            var receipt = context
            receipt["request_id"] = id; receipt["applied_revision"] = revision; receipt["current_revision"] = revision
            receipt["current_canonical_updated_at"] = token; receipt["replayed"] = false
            receipt["refresh"] = ["status": scenario.contains("refresh-pending") ? "pending" : "complete"]
            receipts[id] = receipt
            if (scenario.contains("lost") || scenario.contains("cancelled")) && !failed {
                failed = true; throw URLError(scenario.contains("cancelled") ? .cancelled : .networkConnectionLost)
            }
            if scenario.contains("wrong-ack") { receipt["request_id"] = UUID().uuidString }
            return try json(receipt)
        }
        if path.hasSuffix("/migraine-detail") {
            if request.httpMethod == "PATCH" {
                let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
                if scenario.contains("detail-before") && !detailFailed {
                    detailFailed = true; throw URLError(.networkConnectionLost)
                }
                if scenario.contains("detail-rejected") && !detailFailed { detailFailed = true; return error(422) }
                if scenario.contains("detail-lost-later") && detailFailed && !laterDetailChanged {
                    laterDetailChanged = true
                    episode["notes"] = "A later saved note"
                    let revision = (context["revision"] as! Int) + 1
                    var lifecycle = episode["lifecycle"] as! [String: Any]; lifecycle["revision"] = revision
                    episode["lifecycle"] = lifecycle; context["revision"] = revision; context["episode"] = episode
                    context["canonical_updated_at"] = "2026-09-10T04:03:00Z"
                }
                if scenario.contains("external-details") && !externalDetailsChanged {
                    externalDetailsChanged = true
                    let revision = (context["revision"] as! Int) + 1
                    episode["notes"] = "External saved note"
                    var medicines = episode["medicines"] as! [[String: Any]]
                    medicines[0]["notes"] = "External medicine metadata"
                    if scenario.contains("ambiguous-entry") { medicines[1]["name"] = "Externally renamed middle" }
                    var additional = medicines[0]; additional["name"] = "External second medicine"
                    medicines.append(additional); episode["medicines"] = medicines
                    var lifecycle = episode["lifecycle"] as! [String: Any]; lifecycle["revision"] = revision
                    episode["lifecycle"] = lifecycle; context["revision"] = revision; context["episode"] = episode
                    context["canonical_updated_at"] = "2026-09-10T04:02:00Z"
                    return error(409)
                }
                if (body["expected_revision"] as? Int).map({ $0 + 1 }) == context["revision"] as? Int,
                   lastDetailRequest == body as NSDictionary {
                    return try json(["episode": episode, "revision": context["revision"]!, "changed": false])
                }
                guard body["expected_revision"] as? Int == context["revision"] as? Int else { return error(409) }
                for key in ["notes", "medicines", "early_signs"] { if let value = body[key] { episode[key] = value } }
                let revision = (context["revision"] as! Int) + 1
                var lifecycle = episode["lifecycle"] as! [String: Any]; lifecycle["revision"] = revision
                episode["lifecycle"] = lifecycle; context["revision"] = revision; context["episode"] = episode
                lastDetailRequest = body as NSDictionary
                if (scenario.contains("detail-lost") || scenario.contains("detail-cancelled")) && !detailFailed {
                    detailFailed = true; throw URLError(scenario.contains("detail-cancelled") ? .cancelled : .networkConnectionLost)
                }
            }
            return try json(["episode": episode, "revision": context["revision"]!, "changed": request.httpMethod == "PATCH"])
        }
        if request.httpMethod == "POST" {
            let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            if let note = body["note_text"] as? String, !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                episode["notes"] = note.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            episode["severity"] = body["severity"] ?? episode["severity"]
            context["episode"] = episode; context["canonical_updated_at"] = "2026-09-10T04:01:00Z"
        }
        return try json(["id": Self.episodeID, "symptom_code": "MIGRAINE", "label": "Migraine",
            "severity": episode["severity"]!, "logged_at": (episode["start"] as! [String: Any])["utc"]!,
            "current_state": episode["state"]!, "note_preview": episode["notes"] ?? NSNull(),
            "note_count": 1, "likely_drivers": [], "gauge_keys": []])
    }
}
#endif
