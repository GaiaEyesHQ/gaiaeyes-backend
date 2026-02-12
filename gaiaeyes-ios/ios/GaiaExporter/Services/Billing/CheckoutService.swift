import Foundation

struct CheckoutService {
    let apiBase: URL

    init() throws {
        guard let base = Bundle.main.object(forInfoDictionaryKey: "GAIA_API_BASE") as? String,
              let url = URL(string: base) else {
            throw CheckoutError.missingConfig
        }
        apiBase = url
    }

    func startCheckout(plan: String, accessToken: String) async throws -> URL {
        let endpoint = apiBase.appendingPathComponent("v1/billing/checkout")
        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let body = ["plan": plan]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw CheckoutError.unexpectedResponse
        }

        let decoded = try? JSONDecoder().decode(CheckoutResponse.self, from: data)
        guard (200...299).contains(http.statusCode), decoded?.ok == true else {
            throw CheckoutError.remote(decoded?.error ?? decoded?.detail ?? "Checkout failed")
        }
        guard let urlStr = decoded?.url, let url = URL(string: urlStr) else {
            throw CheckoutError.remote("Checkout URL missing")
        }
        return url
    }

    func fetchEntitlements(accessToken: String) async throws -> EntitlementsResponse {
        let endpoint = apiBase.appendingPathComponent("v1/billing/entitlements")
        var req = URLRequest(url: endpoint)
        req.httpMethod = "GET"
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = CheckoutService.extractMessage(from: data) ?? "Failed to load entitlements"
            throw CheckoutError.remote(msg)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(EntitlementsResponse.self, from: data)
    }

    private static func extractMessage(from data: Data) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return json["error"] as? String ?? json["detail"] as? String
    }
}

private struct CheckoutResponse: Decodable {
    let ok: Bool?
    let url: String?
    let sessionId: String?
    let error: String?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case url
        case sessionId = "session_id"
        case error
        case detail
    }
}

enum CheckoutError: LocalizedError {
    case missingConfig
    case unexpectedResponse
    case remote(String)

    var errorDescription: String? {
        switch self {
        case .missingConfig:
            return "Missing GAIA_API_BASE in Info.plist."
        case .unexpectedResponse:
            return "Unexpected response from billing API."
        case .remote(let msg):
            return msg
        }
    }
}
