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
}
