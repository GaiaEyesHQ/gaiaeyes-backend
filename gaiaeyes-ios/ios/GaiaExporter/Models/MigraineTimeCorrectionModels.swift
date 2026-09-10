import Foundation

enum MigraineTimeEditingFeature {
    static func resolve(isDebugBuild: Bool, arguments: [String]) -> Bool {
        isDebugBuild && arguments.contains("-gaia-enable-migraine-time-editing")
    }
    static var isEnabled: Bool { resolve(isDebugBuild: _isDebugAssertConfiguration(), arguments: ProcessInfo.processInfo.arguments) }
}

struct MigraineTimeContext: Decodable {
    let episode: MigraineEpisode
    let revision: Int
    let canonicalUpdatedAt: String
    let rawEndUtc: String?
    let inconsistentEnd: Bool
    let requestId: String?
    let appliedRevision: Int?
    let currentRevision: Int?
    let currentCanonicalUpdatedAt: String?
    let replayed: Bool?
    let refresh: Refresh?
    struct Refresh: Decodable { let status: String }
}

enum MigraineTimeError: Error, LocalizedError {
    case invalid(String)
    var errorDescription: String? { if case .invalid(let message) = self { return message }; return nil }
}

struct MigraineWallTime: Hashable {
    var dateText: String
    var timeText: String
    var zoneName: String
    var offsetChoice: Int?

    init(timestamp: MigraineEpisodeTimestamp) {
        let zone = TimeZone(identifier: timestamp.timezoneName ?? "") ?? .current
        let date = MigraineFollowUpDraft.parseDate(timestamp.utc) ?? Date()
        zoneName = zone.identifier
        dateText = Self.format(date, zone: zone, pattern: "yyyy-MM-dd")
        timeText = Self.format(date, zone: zone, pattern: "HH:mm:ss")
        offsetChoice = zone.secondsFromGMT(for: date) / 60
    }
    static func format(_ date: Date, zone: TimeZone, pattern: String) -> String {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian); f.timeZone = zone; f.dateFormat = pattern
        return f.string(from: date)
    }
    var wallText: String { dateText + "T" + (timeText.count == 5 ? timeText + ":00" : timeText) }

    func candidates() throws -> [MigraineEpisodeTimestamp] {
        guard let zone = TimeZone(identifier: zoneName) else { throw MigraineTimeError.invalid("Choose a valid timezone, such as America/Chicago.") }
        let zero = TimeZone(secondsFromGMT: 0)!
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian); formatter.timeZone = zero
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"; formatter.isLenient = false
        guard let naive = formatter.date(from: wallText), formatter.string(from: naive) == wallText else {
            throw MigraineTimeError.invalid("Enter a date as YYYY-MM-DD and a 24-hour time as HH:mm or HH:mm:ss.")
        }
        // Collect the zone's offsets on both sides of the selected local day,
        // then round-trip each candidate. A gap yields zero; a fold yields two.
        let offsets = Set(stride(from: -172800, through: 172800, by: 21600).map {
            zone.secondsFromGMT(for: naive.addingTimeInterval(Double($0)))
        })
        let instants = offsets.compactMap { offset -> Date? in
            let instant = naive.addingTimeInterval(-Double(offset))
            guard zone.secondsFromGMT(for: instant) == offset,
                  Self.format(instant, zone: zone, pattern: "yyyy-MM-dd'T'HH:mm:ss") == wallText,
                  offset % 60 == 0 else { return nil }
            return instant
        }.sorted()
        guard !instants.isEmpty else { throw MigraineTimeError.invalid("That local time does not exist in this timezone. Enter a valid time; it has not been adjusted automatically.") }
        return instants.map {
            MigraineEpisodeTimestamp(utc: ISO8601DateFormatter().string(from: $0), originalTime: wallText,
                timezoneName: zoneName, utcOffsetMinutes: zone.secondsFromGMT(for: $0) / 60, timezoneSource: "user")
        }
    }
    func timestamp() throws -> MigraineEpisodeTimestamp {
        let options = try candidates()
        if options.count == 1 { return options[0] }
        guard let selected = options.first(where: { $0.utcOffsetMinutes == offsetChoice }) else {
            throw MigraineTimeError.invalid("That local time occurs twice. Choose the first or second occurrence.")
        }
        return selected
    }
}

enum MigraineEndCorrection: Hashable { case retain, set(MigraineEpisodeTimestamp), clear }

struct MigraineTimeRequest: Encodable, Hashable {
    let requestId: String
    let expectedRevision: Int
    let expectedCanonicalUpdatedAt: String
    let start: MigraineEpisodeTimestamp?
    let end: MigraineEndCorrection
    let state: String?
    enum CodingKeys: String, CodingKey {
        case requestId = "request_id", expectedRevision = "expected_revision", expectedCanonicalUpdatedAt = "expected_canonical_updated_at"
        case start, end, state
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(requestId, forKey: .requestId); try c.encode(expectedRevision, forKey: .expectedRevision)
        try c.encode(expectedCanonicalUpdatedAt, forKey: .expectedCanonicalUpdatedAt)
        try c.encodeIfPresent(start, forKey: .start); try c.encodeIfPresent(state, forKey: .state)
        switch end { case .retain: break; case .clear: try c.encodeNil(forKey: .end); case .set(let time): try c.encode(time, forKey: .end) }
    }
    func confirms(_ saved: MigraineTimeContext, base: MigraineTimeContext) -> Bool {
        let original = base.episode, updated = saved.episode
        guard saved.requestId == requestId, saved.revision == expectedRevision + 1,
              saved.appliedRevision == saved.revision, (saved.currentRevision ?? -1) >= saved.revision,
              updated.episodeId == original.episodeId, updated.symptomEventId == original.symptomEventId,
              updated.lifecycle.revision == saved.revision, updated.state == (state ?? original.state),
              (start ?? original.start).matches(updated.start), updated.notes == original.notes,
              updated.severity == original.severity, updated.provenance == original.provenance,
              updated.earlySigns.elementsEqual(original.earlySigns, by: { $0.matches($1) }),
              updated.medicines.elementsEqual(original.medicines, by: { $0.matches($1) }),
              updated.contexts.elementsEqual(original.contexts, by: { $0.matches($1) }),
              MigraineFollowUpDraft.parseDate(saved.canonicalUpdatedAt) != nil else { return false }
        switch end {
        case .set(let timestamp): return updated.end.map { timestamp.matches($0) } ?? false
        case .clear: return updated.end == nil
        case .retain:
            if base.inconsistentEnd, let raw = base.rawEndUtc {
                return MigraineFollowUpDraft.parseDate(raw) == updated.end.flatMap { MigraineFollowUpDraft.parseDate($0.utc) }
            }
            return MigraineEpisodeTimestamp.matches(original.end, updated.end)
        }
    }
}

struct MigraineTimeDraft: Hashable {
    var correctStart = false
    var endMode = "retain"
    var state = "retain"
    var start: MigraineWallTime
    var end: MigraineWallTime
    var hasIntent: Bool { correctStart || endMode != "retain" || state != "retain" }
    init(context: MigraineTimeContext) {
        start = MigraineWallTime(timestamp: context.episode.start)
        let fallback = context.episode.end ?? context.rawEndUtc.map {
            MigraineEpisodeTimestamp(utc: $0, originalTime: nil, timezoneName: context.episode.start.timezoneName,
                                     utcOffsetMinutes: nil, timezoneSource: "unknown")
        } ?? context.episode.start
        end = MigraineWallTime(timestamp: fallback)
    }
    func request(base: MigraineTimeContext, requestId: String = UUID().uuidString.lowercased()) throws -> MigraineTimeRequest {
        guard hasIntent else { throw MigraineTimeError.invalid("Choose a start, end or status correction first.") }
        let newStart = correctStart ? try start.timestamp() : nil
        let newEnd: MigraineEndCorrection = endMode == "set" ? .set(try end.timestamp()) : endMode == "clear" ? .clear : .retain
        let finalState = state == "retain" ? base.episode.state : state
        let startDate = MigraineFollowUpDraft.parseDate((newStart ?? base.episode.start).utc)!
        let endDate: Date?
        switch newEnd {
        case .set(let timestamp): endDate = MigraineFollowUpDraft.parseDate(timestamp.utc)
        case .clear: endDate = nil
        case .retain: endDate = base.rawEndUtc.flatMap(MigraineFollowUpDraft.parseDate)
        }
        if let endDate {
            guard finalState == "resolved" else { throw MigraineTimeError.invalid("Choose Resolved when recording an end, or clear the end to reopen the episode.") }
            guard endDate >= startDate else { throw MigraineTimeError.invalid("The end cannot be earlier than the start. Your changes are still here.") }
        }
        guard startDate <= Date().addingTimeInterval(300), endDate.map({ $0 <= Date().addingTimeInterval(300) }) ?? true else {
            throw MigraineTimeError.invalid("The corrected start or end cannot be in the future.")
        }
        return MigraineTimeRequest(requestId: requestId, expectedRevision: base.revision,
            expectedCanonicalUpdatedAt: base.canonicalUpdatedAt, start: newStart, end: newEnd,
            state: state == "retain" ? nil : state)
    }
}
