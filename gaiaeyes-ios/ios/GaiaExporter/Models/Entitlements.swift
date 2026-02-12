import Foundation

struct Entitlement: Decodable {
    let key: String
    let term: String?
    let isActive: Bool?
    let startedAt: Date?
    let expiresAt: Date?
    let updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case key
        case term
        case isActive = "is_active"
        case startedAt = "started_at"
        case expiresAt = "expires_at"
        case updatedAt = "updated_at"
    }
}

struct EntitlementsResponse: Decodable {
    let ok: Bool?
    let userId: String?
    let email: String?
    let entitlements: [Entitlement]

    enum CodingKeys: String, CodingKey {
        case ok
        case userId = "user_id"
        case email
        case entitlements
    }
}
