import Foundation

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
