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

struct SymptomQueuedEvent: Codable, Identifiable {
    let id: UUID
    let symptomCode: String
    let tsUtc: Date
    var severity: Int?
    var freeText: String?
    var tags: [String]?

    init(id: UUID = UUID(), symptomCode: String, tsUtc: Date = Date(), severity: Int? = nil, freeText: String? = nil, tags: [String]? = nil) {
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
