import Foundation

enum DriverCategory: String, Codable, CaseIterable, Hashable, Identifiable {
    case all
    case space
    case earth
    case local
    case bodyContext = "body_context"

    var id: String { rawValue }
}

enum DriverRole: String, Codable, Hashable {
    case leading
    case supporting
    case background
}

enum PatternStatus: String, Codable, Hashable {
    case strong
    case moderate
    case emerging
    case noClearPatternYet = "no_clear_pattern_yet"
}

struct DriverPatternReference: Decodable, Hashable, Identifiable {
    let id: String
    let driverKey: String?
    let signalKey: String?
    let signal: String?
    let outcomeKey: String?
    let outcome: String?
    let confidence: String?
    let lagHours: Int?
    let relativeLift: Double?
    let lastSeenAt: String?
    let relevanceScore: Double?
    let explanation: String?
}

struct DriverFilterOption: Decodable, Hashable, Identifiable {
    let key: DriverCategory
    let label: String

    var id: String { key.rawValue }
}

struct DriverSetupHint: Decodable, Hashable, Identifiable {
    let key: String
    let label: String
    let reason: String

    var id: String { key }
}

struct DriverPageSummary: Decodable, Hashable {
    let activeDriverCount: Int
    let totalCount: Int
    let strongestCategory: String?
    let primaryState: String?
    let note: String?
    let hasPersonalPatterns: Bool?
}

struct DriverDetailItem: Decodable, Identifiable, Hashable {
    let id: String
    let key: String
    let sourceKey: String?
    let aliases: [String]
    let label: String
    let category: DriverCategory
    let categoryLabel: String?
    let role: DriverRole
    let roleLabel: String?
    let state: String
    let stateLabel: String?
    let severity: String?
    let reading: String?
    let readingValue: Double?
    let readingUnit: String?
    let shortReason: String
    let personalReason: String?
    let currentSymptoms: [String]
    let historicalSymptoms: [String]
    let patternStatus: PatternStatus?
    let patternStatusLabel: String?
    let patternSummary: String?
    let patternEvidenceCount: Int?
    let patternLagHours: Int?
    let patternRefs: [DriverPatternReference]
    let outlookRelevance: String?
    let outlookSummary: String?
    let updatedAt: String?
    let asof: String?
    let whatItIs: String?
    let activeNowText: String?
    let scienceNote: String?
    let sourceHint: String?
    let signalStrength: Double?
    let personalRelevanceScore: Double?
    let displayScore: Double?
    let isObjectivelyActive: Bool?

    func matches(focusKey raw: String?) -> Bool {
        guard let raw else { return false }
        let normalized = raw
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "-", with: "_")
            .lowercased()
        guard !normalized.isEmpty else { return false }
        let candidates = [key] + aliases + (sourceKey.map { [$0] } ?? [])
        return candidates
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "-", with: "_").lowercased() }
            .contains(normalized)
    }
}

struct AllDriversSnapshot: Decodable, Hashable {
    let generatedAt: String?
    let asof: String?
    let day: String?
    let summary: DriverPageSummary
    let hasPersonalPatterns: Bool?
    let filters: [DriverFilterOption]
    let drivers: [DriverDetailItem]
    let setupHints: [DriverSetupHint]
}
