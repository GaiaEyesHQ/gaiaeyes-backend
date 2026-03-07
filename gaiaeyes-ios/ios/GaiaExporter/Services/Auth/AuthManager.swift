import Foundation
import Security

@MainActor
final class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published private(set) var supabaseAccessToken: String?
    @Published private(set) var supabaseRefreshToken: String?
    @Published private(set) var supabaseUserId: String?
    @Published private(set) var supabaseEmail: String?
    @Published private(set) var supabaseExpiresAt: Date?
    @Published private(set) var lastError: String?

    private let keychain = KeychainStore(service: "com.gaiaeyes.supabase")
    private let config = SupabaseConfig.load()

    var isConfigured: Bool {
        config != nil
    }

    func loadFromKeychain() {
        supabaseAccessToken = keychain.read("access_token")
        supabaseRefreshToken = keychain.read("refresh_token")
        supabaseUserId = keychain.read("user_id")
        supabaseEmail = keychain.read("email")
        if let exp = keychain.read("expires_at"), let ts = TimeInterval(exp) {
            supabaseExpiresAt = Date(timeIntervalSince1970: ts)
        }

        if supabaseRefreshToken != nil {
            Task { await refreshSessionIfNeeded() }
        }
    }

    func signInSupabase(email rawEmail: String) async throws {
        lastError = nil
        guard let config else {
            throw AuthError.missingConfig
        }
        let email = rawEmail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !email.isEmpty else {
            throw AuthError.invalidEmail
        }

        var otpURL = config.url.appendingPathComponent("auth/v1/otp")
        if let redirect = config.magicLinkRedirect {
            otpURL = otpURL.appending(queryItems: ["redirect_to": redirect])
        }
        var req = URLRequest(url: otpURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")

        var body: [String: Any] = [
            "email": email,
            "create_user": true,
        ]
        if let redirect = config.magicLinkRedirect {
            // Some GoTrue versions expect top-level redirect_to on /otp.
            // Keep options.email_redirect_to for compatibility with older behavior.
            body["redirect_to"] = redirect
            body["email_redirect_to"] = redirect
            body["options"] = ["email_redirect_to": redirect]
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        appLog("[AUTH] sending magic-link otp redirect=\(config.magicLinkRedirect ?? "nil") url=\(req.url?.absoluteString ?? "-")")

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw AuthError.unexpectedResponse
        }
        appLog("[AUTH] otp response status=\(http.statusCode)")
        guard (200...299).contains(http.statusCode) else {
            let msg = Self.extractMessage(from: data) ?? "Supabase sign-in failed"
            throw AuthError.remote(msg)
        }

        supabaseEmail = email
        keychain.write(email, key: "email")
    }

    func handleMagicLink(_ url: URL) async -> Bool {
        lastError = nil
        appLog("[AUTH] received magic-link callback: \(url.absoluteString)")
        let params = Self.parseParams(from: url)
        if let err = params["error_description"] ?? params["error"] {
            lastError = err.replacingOccurrences(of: "+", with: " ")
            appLog("[AUTH] callback error: \(lastError ?? "unknown")")
            return false
        }

        guard let access = params["access_token"], let refresh = params["refresh_token"] else {
            appLog("[AUTH] callback missing tokens")
            return false
        }

        let expiresAt = Self.expiresAt(from: params)
        persistSession(
            accessToken: access,
            refreshToken: refresh,
            expiresAt: expiresAt,
            userId: Self.jwtSubject(from: access)
        )
        appLog("[AUTH] session established from callback")
        return true
    }

    func signOutSupabase() {
        lastError = nil
        supabaseAccessToken = nil
        supabaseRefreshToken = nil
        supabaseUserId = nil
        supabaseEmail = nil
        supabaseExpiresAt = nil
        keychain.delete("access_token")
        keychain.delete("refresh_token")
        keychain.delete("user_id")
        keychain.delete("email")
        keychain.delete("expires_at")
    }

    private func persistSession(accessToken: String, refreshToken: String, expiresAt: Date?, userId: String?) {
        supabaseAccessToken = accessToken
        supabaseRefreshToken = refreshToken
        supabaseUserId = userId ?? Self.jwtSubject(from: accessToken)
        supabaseExpiresAt = expiresAt

        keychain.write(accessToken, key: "access_token")
        keychain.write(refreshToken, key: "refresh_token")
        if let supabaseUserId {
            keychain.write(supabaseUserId, key: "user_id")
        } else {
            keychain.delete("user_id")
        }
        if let email = supabaseEmail {
            keychain.write(email, key: "email")
        }
        if let expiresAt {
            keychain.write(String(expiresAt.timeIntervalSince1970), key: "expires_at")
        }
    }

    private func refreshSessionIfNeeded() async {
        guard let config else { return }
        guard let refreshToken = supabaseRefreshToken else { return }

        if let exp = supabaseExpiresAt, exp.timeIntervalSinceNow > 300, supabaseAccessToken != nil {
            return
        }

        var req = URLRequest(url: config.url.appendingPathComponent("auth/v1/token").appending(queryItems: ["grant_type": "refresh_token"]))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")

        let body = ["refresh_token": refreshToken]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                lastError = Self.extractMessage(from: data) ?? "Supabase refresh failed"
                return
            }
            let decoded = try JSONDecoder().decode(SupabaseSessionResponse.self, from: data)
            supabaseEmail = decoded.user?.email
            let expiresAt = Date().addingTimeInterval(TimeInterval(decoded.expiresIn))
            persistSession(
                accessToken: decoded.accessToken,
                refreshToken: decoded.refreshToken,
                expiresAt: expiresAt,
                userId: decoded.user?.id
            )
        } catch {
            lastError = error.localizedDescription
        }
    }

    func validAccessToken() async -> String? {
        if supabaseAccessToken == nil && supabaseRefreshToken == nil {
            loadFromKeychain()
        }
        await refreshSessionIfNeeded()
        return supabaseAccessToken
    }

    func currentSupabaseUserId() -> String? {
        if let supabaseUserId, !supabaseUserId.isEmpty {
            return supabaseUserId
        }
        guard let token = supabaseAccessToken else { return nil }
        return Self.jwtSubject(from: token)
    }

    func resolveSupabaseUserId() async -> String? {
        if let current = currentSupabaseUserId(), !current.isEmpty {
            return current
        }
        guard let config else { return nil }
        guard let token = await validAccessToken(), !token.isEmpty else { return nil }

        if let parsed = Self.jwtSubject(from: token), !parsed.isEmpty {
            supabaseUserId = parsed
            keychain.write(parsed, key: "user_id")
            return parsed
        }

        var req = URLRequest(url: config.url.appendingPathComponent("auth/v1/user"))
        req.httpMethod = "GET"
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return nil
            }
            let user = try JSONDecoder().decode(SupabaseUser.self, from: data)
            if let id = user.id, !id.isEmpty {
                supabaseUserId = id
                keychain.write(id, key: "user_id")
                if let email = user.email, !email.isEmpty {
                    supabaseEmail = email
                    keychain.write(email, key: "email")
                }
                return id
            }
        } catch {
            lastError = error.localizedDescription
        }
        return nil
    }

    private static func parseParams(from url: URL) -> [String: String] {
        var params: [String: String] = [:]
        if let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems {
            for item in items {
                if let value = item.value {
                    params[item.name] = value
                }
            }
        }
        if let fragment = url.fragment {
            for pair in fragment.split(separator: "&") {
                let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
                guard let key = parts.first else { continue }
                let value = parts.count > 1 ? parts[1] : ""
                params[key] = value.removingPercentEncoding ?? value
            }
        }
        return params
    }

    private static func expiresAt(from params: [String: String]) -> Date? {
        if let exp = params["expires_at"], let ts = TimeInterval(exp) {
            return Date(timeIntervalSince1970: ts)
        }
        if let exp = params["expires_in"], let seconds = TimeInterval(exp) {
            return Date().addingTimeInterval(seconds)
        }
        return nil
    }

    private static func extractMessage(from data: Data) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let msg = json["msg"] as? String { return msg }
        if let msg = json["error_description"] as? String { return msg }
        if let msg = json["error"] as? String { return msg }
        return nil
    }

    private static func jwtSubject(from token: String) -> String? {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return nil }
        var payload = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while !payload.count.isMultiple(of: 4) {
            payload.append("=")
        }
        guard let data = Data(base64Encoded: payload),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sub = json["sub"] as? String,
              !sub.isEmpty else {
            return nil
        }
        return sub
    }
}

private enum AuthError: LocalizedError {
    case missingConfig
    case invalidEmail
    case unexpectedResponse
    case remote(String)

    var errorDescription: String? {
        switch self {
        case .missingConfig:
            return "Supabase config missing from Info.plist."
        case .invalidEmail:
            return "Enter a valid email address."
        case .unexpectedResponse:
            return "Unexpected response from Supabase."
        case .remote(let msg):
            return msg
        }
    }
}

private struct SupabaseSessionResponse: Decodable {
    let accessToken: String
    let refreshToken: String
    let expiresIn: Int
    let tokenType: String
    let user: SupabaseUser?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case expiresIn = "expires_in"
        case tokenType = "token_type"
        case user
    }
}

private struct SupabaseUser: Decodable {
    let id: String?
    let email: String?
}

private struct SupabaseConfig {
    let url: URL
    let anonKey: String
    let magicLinkRedirect: String?
    private static let defaultRedirect = "gaiaeyes://auth/callback"

    static func load() -> SupabaseConfig? {
        guard let urlString = Bundle.main.object(forInfoDictionaryKey: "SUPABASE_URL") as? String,
              let url = URL(string: urlString),
              let anon = Bundle.main.object(forInfoDictionaryKey: "SUPABASE_ANON_KEY") as? String,
              !anon.isEmpty else {
            return nil
        }
        let configuredRedirect = (Bundle.main.object(forInfoDictionaryKey: "GAIA_MAGICLINK_REDIRECT") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let redirect: String?
        if let configuredRedirect, !configuredRedirect.isEmpty, !configuredRedirect.contains("*") {
            redirect = configuredRedirect
        } else {
            redirect = defaultRedirect
        }
        return SupabaseConfig(url: url, anonKey: anon, magicLinkRedirect: redirect)
    }
}

private struct KeychainStore {
    let service: String

    func read(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var item: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    func write(_ value: String, key: String) {
        delete(key)
        let data = value.data(using: .utf8) ?? Data()
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    func delete(_ key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}

private extension URL {
    func appending(queryItems: [String: String]) -> URL {
        guard var components = URLComponents(url: self, resolvingAgainstBaseURL: false) else {
            return self
        }
        var items = components.queryItems ?? []
        for (key, value) in queryItems {
            items.append(URLQueryItem(name: key, value: value))
        }
        components.queryItems = items
        return components.url ?? self
    }
}
