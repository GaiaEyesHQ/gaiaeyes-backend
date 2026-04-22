import Foundation

/// Minimal envelope to fetch diagnostics without deserializing the whole features payload.
struct FeaturesTodayDiagEnvelope: Decodable {
    let ok: Bool
    let diagnostics: Diagnostics?
    let error: String?
}

struct Diagnostics: Decodable {
    // Identity / timing
    let branch: String?
    let day: String?
    let dayUsed: String?
    let tz: String?
    let updatedAt: String?
    let maxDay: String?
    let totalRows: Int?
    let statementTimeoutMs: Int?
    let requestedUserId: String?
    let userId: String?

    // Source decision
    let source: String?
    let martRow: Bool?
    let freshened: Bool?

    // Cache telemetry
    let cacheHit: Bool?
    let cacheFallback: Bool?
    let cacheRehydrated: Bool?
    let cacheUpdated: Bool?
    let cacheAgeSeconds: Double?

    // Snapshots & summary
    let cacheSnapshotInitial: PresenceMap?
    let cacheSnapshotFinal: PresenceMap?
    let payloadSummary: PresenceMap?

    // Refresh scheduling
    let refreshAttempted: Bool?
    let refreshScheduled: Bool?
    let refreshReason: String?
    let refreshForced: Bool?

    // Errors / trace
    let poolTimeout: Bool?
    let lastError: String?
    let error: String?
    let enrichmentErrors: [String]?
    let trace: [String]?

    // Hints
    let requestedDiag: Bool?
}

struct PresenceMap: Decodable {
    let health: Bool?
    let sleep: Bool?
    let spaceWeather: Bool?
    let schumann: Bool?
    let postCopy: Bool?

    private enum CodingKeys: String, CodingKey {
        case health
        case sleep
        case spaceWeather = "space_weather"
        case schumann
        case postCopy = "post_copy"
        case sections
    }

    private enum SectionsCodingKeys: String, CodingKey {
        case health
        case sleep
        case spaceDaily = "space_daily"
        case spaceCurrent = "space_current"
        case schumann
        case post = "post"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        if container.contains(.sections) {
            let sections = try container.nestedContainer(keyedBy: SectionsCodingKeys.self, forKey: .sections)
            health = try sections.decodeIfPresent(Bool.self, forKey: .health)
            sleep = try sections.decodeIfPresent(Bool.self, forKey: .sleep)
            let spaceDaily = try sections.decodeIfPresent(Bool.self, forKey: .spaceDaily)
            let spaceCurrent = try sections.decodeIfPresent(Bool.self, forKey: .spaceCurrent)
            spaceWeather = spaceDaily ?? spaceCurrent
            schumann = try sections.decodeIfPresent(Bool.self, forKey: .schumann)
            postCopy = try sections.decodeIfPresent(Bool.self, forKey: .post)
            return
        }

        health = try container.decodeIfPresent(Bool.self, forKey: .health)
        sleep = try container.decodeIfPresent(Bool.self, forKey: .sleep)
        spaceWeather = try container.decodeIfPresent(Bool.self, forKey: .spaceWeather)
        schumann = try container.decodeIfPresent(Bool.self, forKey: .schumann)
        postCopy = try container.decodeIfPresent(Bool.self, forKey: .postCopy)
    }
}
