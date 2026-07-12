import Foundation

struct HomePossibleSymptomMatch: Equatable {
    let label: String
    let isMatched: Bool
}

enum HomePossibleSymptomLabels {
    static func labels(forOutcomeKey raw: String) -> [String] {
        switch raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() {
        case "HEADACHE_DAY":
            return ["Migraine", "Head / sinus pressure", "Headache"]
        case "PAIN_FLARE_DAY":
            return ["Pain flare", "Body aches"]
        case "FATIGUE_DAY":
            return ["Fatigue", "Energy dip"]
        case "ANXIETY_DAY", "RESTLESSNESS_DAY":
            return ["Restlessness", "Wired"]
        case "POOR_SLEEP_DAY":
            return ["Poor sleep", "Restless sleep"]
        case "FOCUS_FOG_DAY":
            return ["Brain fog", "Focus shifts"]
        case "HRV_DIP_DAY":
            return ["Low energy"]
        case "HIGH_HR_DAY":
            return ["Heart awareness", "Body strain"]
        case "SHORT_SLEEP_DAY":
            return ["Low energy"]
        default:
            return []
        }
    }

    static func ranked(
        candidates: [String],
        activeLabels: [String],
        limit: Int = 6
    ) -> [HomePossibleSymptomMatch] {
        let activeKeys = Set(activeLabels.map(normalizedKey).filter { !$0.isEmpty })
        var seen: Set<String> = []
        var matched: [HomePossibleSymptomMatch] = []
        var unmatched: [HomePossibleSymptomMatch] = []

        for raw in candidates {
            let label = canonicalDisplayLabel(raw)
            let key = normalizedKey(label)
            guard !label.isEmpty, !seen.contains(key) else { continue }
            seen.insert(key)
            let item = HomePossibleSymptomMatch(label: label, isMatched: activeKeys.contains(key))
            if item.isMatched {
                matched.append(item)
            } else {
                unmatched.append(item)
            }
        }

        return Array((matched + unmatched).prefix(max(0, limit)))
    }

    private static func normalizedKey(_ raw: String) -> String {
        let key = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return key == "tired" ? "low energy" : key
    }

    private static func canonicalDisplayLabel(_ raw: String) -> String {
        let label = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalizedKey(label) == "low energy" ? "Low energy" : label
    }
}

struct HomeFeedEnvelope: Decodable {
    let ok: Bool?
    let item: HomeFeedItem?
    let reason: String?
}

struct HomeFeedItem: Codable, Equatable, Identifiable {
    let id: String
    let slug: String?
    let mode: String?
    let kind: String?
    let title: String?
    let body: String?
    let linkLabel: String?
    let linkUrl: String?
    let updatedAt: String?

    var trimmedID: String {
        id.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var displayTitle: String? {
        title?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var displayBody: String? {
        body?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var displayKind: String {
        let raw = kind?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        switch raw {
        case "tip":
            return "Tip"
        case "message":
            return "Message"
        default:
            return "Fact"
        }
    }

    var displayLinkLabel: String? {
        linkLabel?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var link: URL? {
        guard let raw = linkUrl?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return nil
        }
        return URL(string: raw)
    }
}

struct HomeFeedSeenRequest: Encodable {
    let itemID: String
    let dismissed: Bool

    enum CodingKeys: String, CodingKey {
        case itemID = "item_id"
        case dismissed
    }
}

struct HomeFeedSeenEnvelope: Decodable {
    let ok: Bool?
    let seen: Bool?
    let reason: String?
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
