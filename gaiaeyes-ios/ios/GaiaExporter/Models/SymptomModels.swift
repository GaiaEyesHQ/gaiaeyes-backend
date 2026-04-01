import Foundation

func normalize(_ s: String) -> String {
    s.trimmingCharacters(in: .whitespacesAndNewlines)
        .replacingOccurrences(of: "-", with: "_")
        .replacingOccurrences(of: " ", with: "_")
        .uppercased()
}

enum SymptomCodeHelper {
    static let fallbackCode = normalize("OTHER")
}

struct SymptomEventToday: Decodable, Identifiable {
    let symptomCode: String
    let tsUtc: String
    let severity: Int?
    let freeText: String?

    var id: String { "\(symptomCode)|\(tsUtc)" }
}

struct SymptomDailySummary: Decodable, Identifiable {
    let day: String
    let symptomCode: String
    let events: Int
    let meanSeverity: Double?
    let lastTs: String?

    var id: String { "\(symptomCode)|\(day)" }
}

struct SymptomDiagSummary: Decodable, Identifiable {
    let symptomCode: String
    let events: Int
    let lastTs: String?

    var id: String { symptomCode }
}

struct SymptomPostResponse: Decodable {
    let ok: Bool?
    let id: Int?
    let tsUtc: String?
}

struct SymptomCodeDefinition: Decodable {
    let symptomCode: String
    let label: String
    let description: String?
    let isActive: Bool
    let systemImage: String?
    let tags: [String]?
}

enum CurrentSymptomState: String, Codable, CaseIterable, Hashable {
    case new
    case ongoing
    case improving
    case worse
    case resolved
}

struct CurrentSymptomFollowUpPrompt: Decodable, Identifiable, Hashable {
    let id: String
    let episodeId: String
    let symptomCode: String
    let symptomLabel: String
    let questionText: String
    let detailFocus: String?
    let trigger: String?
    let scheduledFor: String?
    let deliveredAt: String?
    let status: String?
    let pushDeliveryEnabled: Bool
}

struct CurrentSymptomDriver: Decodable, Identifiable, Hashable {
    let key: String
    let label: String
    let severity: String?
    let state: String?
    let display: String?
    let relation: String?
    let relatedSymptoms: [String]
    let confidence: String?
    let patternHint: String?

    var id: String { key }
}

struct CurrentSymptomPatternHint: Decodable, Identifiable, Hashable {
    let id: String
    let signalKey: String
    let signal: String
    let outcomeKey: String
    let outcome: String
    let confidence: String?
    let text: String?
}

struct CurrentSymptomItem: Decodable, Identifiable, Hashable {
    let id: String
    let symptomCode: String
    let label: String
    let severity: Int?
    let originalSeverity: Int?
    let loggedAt: String
    let lastInteractionAt: String?
    let currentState: CurrentSymptomState
    let notePreview: String?
    let noteCount: Int
    let likelyDrivers: [CurrentSymptomDriver]
    let patternHint: CurrentSymptomPatternHint?
    let gaugeKeys: [String]
    let currentContextBadge: String?
    let pendingFollowUp: CurrentSymptomFollowUpPrompt?
}

struct CurrentSymptomsSummary: Decodable, Hashable {
    let activeCount: Int
    let newCount: Int
    let ongoingCount: Int
    let improvingCount: Int
    let worseCount: Int
    let lastUpdatedAt: String?
    let followUpAvailable: Bool
}

struct CurrentSymptomsFollowUpSettings: Decodable, Hashable {
    let notificationsEnabled: Bool
    let enabled: Bool
    let notificationFamilyEnabled: Bool
    let pushEnabled: Bool
    let cadence: String
    let states: [String]
    let symptomCodes: [String]
}

struct CurrentSymptomsVoiceSemanticFacts: Decodable, Hashable {
    let activeCount: Int?
    let activeLabels: [String]?
    let contributingDriverLabels: [String]?
    let patternTexts: [String]?
    let followUpEnabled: Bool?
}

struct CurrentSymptomsVoiceSemanticInterpretation: Decodable, Hashable {
    let headerSummary: String?
    let activeSummary: String?
    let emptyState: String?
    let contributingEmpty: String?
    let patternEmpty: String?
    let followUpSummary: String?
}

struct CurrentSymptomsVoiceSemanticAction: Decodable, Hashable {
    let label: String?
}

struct CurrentSymptomsVoiceSemanticActions: Decodable, Hashable {
    let primary: [CurrentSymptomsVoiceSemanticAction]?
}

struct CurrentSymptomsVoiceSemantic: Decodable, Hashable {
    let kind: String?
    let facts: CurrentSymptomsVoiceSemanticFacts?
    let interpretation: CurrentSymptomsVoiceSemanticInterpretation?
    let actions: CurrentSymptomsVoiceSemanticActions?
}

struct CurrentSymptomsSnapshot: Decodable, Hashable {
    let generatedAt: String
    let windowHours: Int
    let summary: CurrentSymptomsSummary
    let items: [CurrentSymptomItem]
    let contributingDrivers: [CurrentSymptomDriver]
    let patternContext: [CurrentSymptomPatternHint]
    let followUpSettings: CurrentSymptomsFollowUpSettings
    let voiceSemantic: CurrentSymptomsVoiceSemantic?
}

private extension String {
    var nilIfTrimmedEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

extension CurrentSymptomsSnapshot {
    var semanticHeaderSummary: String? {
        voiceSemantic?.interpretation?.headerSummary?.nilIfTrimmedEmpty
    }

    var semanticActiveSummary: String? {
        voiceSemantic?.interpretation?.activeSummary?.nilIfTrimmedEmpty
    }

    var semanticEmptyStateSummary: String? {
        voiceSemantic?.interpretation?.emptyState?.nilIfTrimmedEmpty
    }

    var semanticContributingEmptySummary: String? {
        voiceSemantic?.interpretation?.contributingEmpty?.nilIfTrimmedEmpty
    }

    var semanticPatternEmptySummary: String? {
        voiceSemantic?.interpretation?.patternEmpty?.nilIfTrimmedEmpty
    }

    var semanticFollowUpSummary: String? {
        voiceSemantic?.interpretation?.followUpSummary?.nilIfTrimmedEmpty
    }

    var semanticActiveLabelPreview: [String] {
        let semanticLabels = (voiceSemantic?.facts?.activeLabels ?? []).compactMap(\.nilIfTrimmedEmpty)
        if !semanticLabels.isEmpty {
            return semanticLabels
        }
        return items.compactMap { $0.label.nilIfTrimmedEmpty }
    }

    var semanticActiveLabelSummary: String? {
        let labels = Array(semanticActiveLabelPreview.prefix(2))
        guard !labels.isEmpty else { return nil }
        return labels.joined(separator: " • ")
    }
}

struct CurrentSymptomTimelineEntry: Decodable, Identifiable, Hashable {
    let id: String
    let episodeId: String
    let symptomCode: String
    let label: String
    let updateKind: String
    let state: CurrentSymptomState?
    let severity: Int?
    let noteText: String?
    let occurredAt: String
}

struct CurrentSymptomDeleteResult: Decodable, Hashable {
    let episodeId: String
    let symptomCode: String
    let deletedAt: String?
}

struct SymptomQueuedEvent: Codable, Identifiable {
    let id: UUID
    let symptomCode: String
    let tsUtc: Date
    var severity: Int?
    var freeText: String?
    var tags: [String]?

    init(id: UUID = UUID(), symptomCode: String, tsUtc: Date = Date(), severity: Int? = 5, freeText: String? = nil, tags: [String]? = nil) {
        self.id = id
        self.symptomCode = normalize(symptomCode)
        self.tsUtc = tsUtc
        self.severity = severity
        self.freeText = freeText
        self.tags = tags
    }
}

extension SymptomQueuedEvent {
    private enum CodingKeys: String, CodingKey {
        case id
        case symptomCode
        case tsUtc
        case severity
        case freeText
        case tags
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        let rawCode = try container.decode(String.self, forKey: .symptomCode)
        symptomCode = normalize(rawCode)
        tsUtc = try container.decode(Date.self, forKey: .tsUtc)
        severity = try container.decodeIfPresent(Int.self, forKey: .severity)
        freeText = try container.decodeIfPresent(String.self, forKey: .freeText)
        tags = try container.decodeIfPresent([String].self, forKey: .tags)
    }

    func replacingSymptomCode(with code: String, keepId: Bool = true) -> SymptomQueuedEvent {
        SymptomQueuedEvent(id: keepId ? id : UUID(),
                           symptomCode: code,
                           tsUtc: tsUtc,
                           severity: severity,
                           freeText: freeText,
                           tags: tags)
    }

    func normalized() -> SymptomQueuedEvent {
        SymptomQueuedEvent(id: id,
                           symptomCode: symptomCode,
                           tsUtc: tsUtc,
                           severity: severity,
                           freeText: freeText,
                           tags: tags)
    }
}
