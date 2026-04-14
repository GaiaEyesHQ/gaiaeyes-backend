import Foundation

struct AppNoticeEnvelope: Decodable {
    let ok: Bool?
    let notice: AppNotice?
}

enum AppNoticePlacement: String, Decodable, Equatable {
    case topBanner = "top_banner"
    case guideCard = "guide_card"
    case homeTip = "home_tip"
    case all

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let rawValue = (try? container.decode(String.self)) ?? Self.topBanner.rawValue
        self = Self(rawValue: rawValue) ?? .topBanner
    }

    func includes(_ placement: AppNoticePlacement) -> Bool {
        self == .all || self == placement
    }
}

struct AppNotice: Decodable, Equatable, Identifiable {
    let id: String
    let type: String?
    let placement: AppNoticePlacement
    let title: String?
    let message: String?
    let linkLabel: String?
    let linkURL: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case placement
        case title
        case message
        case linkLabel = "link_label"
        case linkURL = "link_url"
        case updatedAt = "updated_at"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try container.decodeIfPresent(String.self, forKey: .id)) ?? ""
        type = try container.decodeIfPresent(String.self, forKey: .type)
        placement = (try? container.decodeIfPresent(AppNoticePlacement.self, forKey: .placement)) ?? .topBanner
        title = try container.decodeIfPresent(String.self, forKey: .title)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        linkLabel = try container.decodeIfPresent(String.self, forKey: .linkLabel)
        linkURL = try container.decodeIfPresent(String.self, forKey: .linkURL)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
    }

    var trimmedID: String {
        id.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var dismissalKey: String {
        let updated = updatedAt?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        guard let updated else { return trimmedID }
        return "\(trimmedID)|\(updated)"
    }

    var trimmedTitle: String? {
        title?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var trimmedMessage: String? {
        message?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var trimmedLinkLabel: String? {
        linkLabel?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var hasDisplayContent: Bool {
        trimmedTitle != nil || trimmedMessage != nil
    }

    var link: URL? {
        guard let raw = linkURL?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return nil
        }
        return URL(string: raw)
    }

    func isVisible(in target: AppNoticePlacement) -> Bool {
        hasDisplayContent && placement.includes(target)
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
