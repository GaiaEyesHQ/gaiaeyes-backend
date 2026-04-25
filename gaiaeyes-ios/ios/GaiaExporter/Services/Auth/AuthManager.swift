import Foundation
import Security

@MainActor
final class AuthManager: ObservableObject {
    static let shared = AuthManager()
    static let continuityEmailDefaultsKey = "gaia.auth.last_signed_in_email"
    static let diagnosticsLastEventKey = "gaia.auth.last_event"
    static let diagnosticsLastDetailKey = "gaia.auth.last_detail"
    static let diagnosticsLastAtKey = "gaia.auth.last_at"
    static let diagnosticsLastUserIdKey = "gaia.auth.last_user_id"

    @Published private(set) var supabaseAccessToken: String?
    @Published private(set) var supabaseRefreshToken: String?
    @Published private(set) var supabaseUserId: String?
    @Published private(set) var supabaseEmail: String?
    @Published private(set) var supabaseExpiresAt: Date?
    @Published private(set) var lastError: String?

    private let keychain = KeychainStore(service: "com.gaiaeyes.supabase")
    private let config = SupabaseConfig.load()
    private var tokenRefreshInFlight = false
    private var tokenRefreshWaiters: [CheckedContinuation<Bool, Never>] = []
    private var forcedRefreshBlockedUntil: Date?
    private var lastKeychainLoadDiagnosticSignature: String?

    var isConfigured: Bool {
        config != nil
    }

    var signedInEmail: String? {
        guard supabaseAccessToken?.isEmpty == false else { return nil }
        let email = supabaseEmail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return email.isEmpty ? nil : email
    }

    var hasSignedInAccount: Bool {
        signedInEmail != nil
    }

    var hasStoredAuthContinuity: Bool {
        hasNonEmptyStoredValue(supabaseAccessToken, key: "access_token") ||
        hasNonEmptyStoredValue(supabaseRefreshToken, key: "refresh_token") ||
        hasNonEmptyStoredValue(supabaseUserId, key: "user_id") ||
        hasNonEmptyStoredValue(supabaseEmail, key: "email") ||
        continuityEmailHint() != nil
    }

    var hasAppOnlyProfile: Bool {
        supabaseAccessToken?.isEmpty == false && signedInEmail == nil
    }

    func loadFromKeychain() {
        let storedAccessToken = keychain.read("access_token")
        let storedRefreshToken = keychain.read("refresh_token")
        let storedUserId = keychain.read("user_id")
        let storedEmail = keychain.read("email")
        let storedExpiresAt = keychain.read("expires_at")
        let continuityEmail = continuityEmailHint()

        supabaseAccessToken = storedAccessToken
        supabaseRefreshToken = storedRefreshToken
        supabaseUserId = storedUserId
        supabaseEmail = storedEmail
        if let exp = storedExpiresAt, let ts = TimeInterval(exp) {
            supabaseExpiresAt = Date(timeIntervalSince1970: ts)
        } else if let token = storedAccessToken {
            supabaseExpiresAt = Self.jwtExpiration(from: token)
        } else {
            supabaseExpiresAt = nil
        }
        if let email = supabaseEmail?.trimmingCharacters(in: .whitespacesAndNewlines), !email.isEmpty {
            persistContinuityEmail(email)
        }

        let hasTokenPair = !(storedAccessToken?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
            || !(storedRefreshToken?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
        let hasContinuity = !(storedUserId?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
            || !(storedEmail?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
            || continuityEmail != nil
        if hasTokenPair {
            mirrorSessionToBackendDefaults(accessToken: supabaseAccessToken, userId: supabaseUserId)
        } else if hasContinuity {
            clearMirroredBackendDefaultsForMissingSession(reason: "keychain load without tokens")
        }
        recordKeychainLoadDiagnostic(
            accessToken: storedAccessToken,
            refreshToken: storedRefreshToken,
            userId: storedUserId,
            email: storedEmail,
            continuityEmail: continuityEmail
        )

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

    func signInWithPassword(email rawEmail: String, password: String) async throws {
        lastError = nil
        guard let config else {
            throw AuthError.missingConfig
        }
        let email = rawEmail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !email.isEmpty else {
            throw AuthError.invalidEmail
        }
        guard !password.isEmpty else {
            throw AuthError.invalidPassword
        }

        var req = URLRequest(url: config.url.appendingPathComponent("auth/v1/token").appending(queryItems: ["grant_type": "password"]))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email,
            "password": password,
        ])

        let decoded = try await submitAuthRequest(req, fallbackMessage: "Supabase password sign-in failed")
        guard let accessToken = decoded.accessToken,
              let refreshToken = decoded.refreshToken,
              let expiresIn = decoded.expiresIn else {
            throw AuthError.unexpectedResponse
        }
        supabaseEmail = decoded.user?.email ?? email
        keychain.write(supabaseEmail ?? email, key: "email")
        persistSession(
            accessToken: accessToken,
            refreshToken: refreshToken,
            expiresAt: Date().addingTimeInterval(TimeInterval(expiresIn)),
            userId: decoded.user?.id
        )
        recordDiagnosticsEvent(
            "password_session_established",
            detail: supabaseEmail ?? email,
            userId: decoded.user?.id
        )
        appLog("[AUTH] password session established")
    }

    func createAccountWithPassword(email rawEmail: String, password: String) async throws -> Bool {
        lastError = nil
        guard let config else {
            throw AuthError.missingConfig
        }
        let email = rawEmail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !email.isEmpty else {
            throw AuthError.invalidEmail
        }
        guard password.count >= 8 else {
            throw AuthError.weakPassword
        }

        var req = URLRequest(url: config.url.appendingPathComponent("auth/v1/signup"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email,
            "password": password,
            "data": [
                "source": "gaiaeyes_ios",
                "auth_mode": "password",
            ],
        ])

        let decoded = try await submitAuthRequest(req, fallbackMessage: "Supabase account creation failed")
        supabaseEmail = decoded.user?.email ?? email
        keychain.write(supabaseEmail ?? email, key: "email")

        guard let accessToken = decoded.accessToken,
              let refreshToken = decoded.refreshToken,
              let expiresIn = decoded.expiresIn else {
            appLog("[AUTH] password account created; waiting for email verification")
            return false
        }

        persistSession(
            accessToken: accessToken,
            refreshToken: refreshToken,
            expiresAt: Date().addingTimeInterval(TimeInterval(expiresIn)),
            userId: decoded.user?.id
        )
        recordDiagnosticsEvent(
            "password_account_created",
            detail: supabaseEmail ?? email,
            userId: decoded.user?.id
        )
        appLog("[AUTH] password account created and session established")
        return true
    }

    func signInAnonymously() async throws {
        lastError = nil
        guard let config else {
            throw AuthError.missingConfig
        }

        var req = URLRequest(url: config.url.appendingPathComponent("auth/v1/signup"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(config.anonKey)", forHTTPHeaderField: "Authorization")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "data": [
                "source": "gaiaeyes_ios",
                "auth_mode": "anonymous",
            ],
        ])

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw AuthError.unexpectedResponse
        }
        appLog("[AUTH] anonymous signup response status=\(http.statusCode)")
        guard (200...299).contains(http.statusCode) else {
            let msg = Self.extractMessage(from: data) ?? "Supabase anonymous sign-in failed"
            throw AuthError.remote(msg)
        }

        let decoded = try JSONDecoder().decode(SupabaseSessionResponse.self, from: data)
        supabaseEmail = decoded.user?.email
        if let email = decoded.user?.email, !email.isEmpty {
            keychain.write(email, key: "email")
        } else {
            keychain.delete("email")
        }
        persistSession(
            accessToken: decoded.accessToken,
            refreshToken: decoded.refreshToken,
            expiresAt: Date().addingTimeInterval(TimeInterval(decoded.expiresIn)),
            userId: decoded.user?.id
        )
        recordDiagnosticsEvent("anonymous_session_established", userId: decoded.user?.id)
        appLog("[AUTH] anonymous session established")
    }

    private func submitAuthRequest(_ req: URLRequest, fallbackMessage: String) async throws -> SupabaseAuthResponse {
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw AuthError.unexpectedResponse
        }
        appLog("[AUTH] auth response status=\(http.statusCode)")
        guard (200...299).contains(http.statusCode) else {
            let msg = Self.extractMessage(from: data) ?? fallbackMessage
            throw AuthError.remote(msg)
        }
        return try JSONDecoder().decode(SupabaseAuthResponse.self, from: data)
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
        recordDiagnosticsEvent("magic_link_session_established", userId: Self.jwtSubject(from: access))
        appLog("[AUTH] session established from callback")
        return true
    }

    func signOutSupabase() {
        lastError = nil
        let accessToken = supabaseAccessToken
        let currentUserId = supabaseUserId
        Task {
            _ = await PushNotificationService.disableStoredToken(
                auth: nil,
                bearerTokenOverride: accessToken,
                devUserIdOverride: currentUserId
            )
        }
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
        clearContinuityEmail()
        clearMirroredBackendDefaults(accessToken: accessToken, userId: currentUserId)
        clearMirroredBackendDefaultsForMissingSession(reason: "manual sign out")
        recordDiagnosticsEvent("manual_sign_out", userId: currentUserId)
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
            persistContinuityEmail(email)
        }
        if let expiresAt {
            keychain.write(String(expiresAt.timeIntervalSince1970), key: "expires_at")
        }
        mirrorSessionToBackendDefaults(accessToken: accessToken, userId: supabaseUserId)
    }

    private func mirrorSessionToBackendDefaults(accessToken: String?, userId: String?) {
        let token = accessToken?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let userId = userId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !token.isEmpty, !userId.isEmpty else { return }
        let defaults = UserDefaults.standard
        defaults.set(token, forKey: "bearer")
        defaults.set(userId, forKey: "userId")
    }

    private func clearMirroredBackendDefaults(accessToken: String?, userId: String?) {
        let defaults = UserDefaults.standard
        let storedBearer = defaults.string(forKey: "bearer")
        guard storedBearer == accessToken else { return }
        defaults.removeObject(forKey: "bearer")
        if defaults.string(forKey: "userId") == userId {
            defaults.removeObject(forKey: "userId")
        }
    }

    private func clearMirroredBackendDefaultsForMissingSession(reason: String) {
        let defaults = UserDefaults.standard
        let storedBearer = defaults.string(forKey: "bearer")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let storedUserId = defaults.string(forKey: "userId")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !storedBearer.isEmpty || !storedUserId.isEmpty else { return }
        defaults.removeObject(forKey: "bearer")
        defaults.removeObject(forKey: "userId")
        appLog("[AUTH] cleared mirrored backend auth defaults reason=\(reason) bearer=\(!storedBearer.isEmpty) user=\(!storedUserId.isEmpty)")
    }

    private func recordKeychainLoadDiagnostic(
        accessToken: String?,
        refreshToken: String?,
        userId: String?,
        email: String?,
        continuityEmail: String?
    ) {
        let hasAccess = !(accessToken?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
        let hasRefresh = !(refreshToken?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
        let hasUser = !(userId?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
        let hasEmail = !(email?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
        let hasContinuityEmail = continuityEmail != nil
        let signature = "\(hasAccess)|\(hasRefresh)|\(hasUser)|\(hasEmail)|\(hasContinuityEmail)"
        guard signature != lastKeychainLoadDiagnosticSignature else { return }
        lastKeychainLoadDiagnosticSignature = signature

        let detail = "access=\(hasAccess) refresh=\(hasRefresh) user=\(hasUser) email=\(hasEmail) continuity=\(hasContinuityEmail)"
        if !hasAccess && !hasRefresh && (hasUser || hasEmail || hasContinuityEmail) {
            recordDiagnosticsEvent("stored_session_missing_tokens", detail: detail, userId: userId)
            notifyReauthenticationNeeded(reason: "stored_session_missing_tokens", detail: detail)
            appLog("[AUTH] keychain continuity without usable tokens \(detail)")
        } else {
            appLog("[AUTH] keychain session loaded \(detail)")
        }
    }

    private func notifyReauthenticationNeeded(reason: String, detail: String? = nil) {
        var userInfo: [String: String] = ["reason": reason]
        if let detail, !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            userInfo["detail"] = detail
        }
        NotificationCenter.default.post(name: .gaiaAuthNeedsReauthentication, object: nil, userInfo: userInfo)
    }

    private func hasNonEmptyStoredValue(_ inMemoryValue: String?, key: String) -> Bool {
        let inMemory = inMemoryValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !inMemory.isEmpty {
            return true
        }
        let stored = keychain.read(key)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return !stored.isEmpty
    }

    private func refreshSessionIfNeeded() async {
        _ = await refreshSessionCoalesced(force: false)
    }

    func forceRefreshAccessToken() async -> String? {
        if let blockedUntil = forcedRefreshBlockedUntil, blockedUntil > Date() {
            return nil
        }

        if supabaseAccessToken == nil && supabaseRefreshToken == nil {
            loadFromKeychain()
        }
        let refreshed = await refreshSessionCoalesced(force: true)
        return refreshed ? supabaseAccessToken : nil
    }

    private func refreshSessionCoalesced(force: Bool) async -> Bool {
        if tokenRefreshInFlight {
            return await withCheckedContinuation { continuation in
                tokenRefreshWaiters.append(continuation)
            }
        }

        tokenRefreshInFlight = true
        let refreshed = await refreshSession(force: force)
        let waiters = tokenRefreshWaiters
        tokenRefreshWaiters.removeAll()
        tokenRefreshInFlight = false
        waiters.forEach { $0.resume(returning: refreshed) }
        return refreshed
    }

    private func refreshSession(force: Bool) async -> Bool {
        guard let config else { return isAccessTokenUsable(leeway: 0) }
        guard let refreshToken = supabaseRefreshToken else {
            if !isAccessTokenUsable(leeway: 0), supabaseAccessToken != nil {
                invalidateSupabaseSession(
                    reason: "Session expired. Please sign in again.",
                    preserveEmail: true,
                    diagnosticDetail: "Access token expired with no refresh token available."
                )
            }
            return isAccessTokenUsable(leeway: 0)
        }

        if !force, isAccessTokenUsable(leeway: 300) {
            return true
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
                let message = Self.extractMessage(from: data) ?? "Supabase refresh failed"
                lastError = message
                if force {
                    appLog("[AUTH] forced refresh failed: \(message)")
                }
                if Self.isFatalRefreshFailure(message) {
                    forcedRefreshBlockedUntil = Date().addingTimeInterval(300)
                    invalidateSupabaseSession(
                        reason: "Session expired. Please sign in again.",
                        preserveEmail: true,
                        diagnosticDetail: message
                    )
                } else if force {
                    forcedRefreshBlockedUntil = Date().addingTimeInterval(30)
                } else if isAccessTokenUsable(leeway: 0) {
                    appLog("[AUTH] refresh failed but existing access token remains usable: \(message)")
                    return true
                }
                return false
            }
            let decoded = try JSONDecoder().decode(SupabaseSessionResponse.self, from: data)
            supabaseEmail = decoded.user?.email
            let expiresAt = Date().addingTimeInterval(TimeInterval(decoded.expiresIn))
            forcedRefreshBlockedUntil = nil
            persistSession(
                accessToken: decoded.accessToken,
                refreshToken: decoded.refreshToken,
                expiresAt: expiresAt,
                userId: decoded.user?.id
            )
            return true
        } catch {
            lastError = error.localizedDescription
            if force {
                appLog("[AUTH] forced refresh error: \(error.localizedDescription)")
                forcedRefreshBlockedUntil = Date().addingTimeInterval(15)
            } else if isAccessTokenUsable(leeway: 0) {
                appLog("[AUTH] refresh error but existing access token remains usable: \(error.localizedDescription)")
                return true
            }
            return false
        }
    }

    func validAccessToken() async -> String? {
        if supabaseAccessToken == nil && supabaseRefreshToken == nil {
            loadFromKeychain()
        }
        guard await refreshSessionCoalesced(force: false) else {
            return nil
        }
        return isAccessTokenUsable(leeway: 0) ? supabaseAccessToken : nil
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

    private static func isFatalRefreshFailure(_ message: String) -> Bool {
        let lower = message.lowercased()
        return lower.contains("invalid refresh token")
            || lower.contains("refresh token not found")
            || lower.contains("invalid grant")
    }

    private func isAccessTokenUsable(leeway: TimeInterval) -> Bool {
        guard supabaseAccessToken?.isEmpty == false else { return false }
        if supabaseExpiresAt == nil, let token = supabaseAccessToken {
            supabaseExpiresAt = Self.jwtExpiration(from: token)
        }
        guard let supabaseExpiresAt else { return true }
        return supabaseExpiresAt.timeIntervalSinceNow > leeway
    }

    private func invalidateSupabaseSession(reason: String, preserveEmail: Bool, diagnosticDetail: String? = nil) {
        let accessToken = supabaseAccessToken
        let currentUserId = supabaseUserId
        let email = supabaseEmail ?? keychain.read("email")
        supabaseAccessToken = nil
        supabaseRefreshToken = nil
        supabaseUserId = nil
        supabaseExpiresAt = nil
        if preserveEmail {
            supabaseEmail = email
        } else {
            supabaseEmail = nil
        }
        keychain.delete("access_token")
        keychain.delete("refresh_token")
        keychain.delete("user_id")
        keychain.delete("expires_at")
        if let email, preserveEmail {
            keychain.write(email, key: "email")
            persistContinuityEmail(email)
        } else {
            keychain.delete("email")
            clearContinuityEmail()
        }
        clearMirroredBackendDefaults(accessToken: accessToken, userId: currentUserId)
        clearMirroredBackendDefaultsForMissingSession(reason: "session invalidated")
        lastError = reason
        recordDiagnosticsEvent("session_invalidated", detail: diagnosticDetail ?? reason, userId: currentUserId)
        if preserveEmail {
            notifyReauthenticationNeeded(reason: "session_invalidated", detail: diagnosticDetail ?? reason)
        }
        appLog("[AUTH] cleared invalid Supabase session: \(reason)")
    }

    private func continuityEmailHint() -> String? {
        let raw = UserDefaults.standard.string(forKey: Self.continuityEmailDefaultsKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return raw.isEmpty ? nil : raw
    }

    private func persistContinuityEmail(_ email: String) {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        UserDefaults.standard.set(trimmed, forKey: Self.continuityEmailDefaultsKey)
    }

    private func clearContinuityEmail() {
        UserDefaults.standard.removeObject(forKey: Self.continuityEmailDefaultsKey)
    }

    private func recordDiagnosticsEvent(_ event: String, detail: String? = nil, userId: String? = nil) {
        let defaults = UserDefaults.standard
        defaults.set(event, forKey: Self.diagnosticsLastEventKey)
        defaults.set(Self.isoString(Date()), forKey: Self.diagnosticsLastAtKey)
        let trimmedDetail = detail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmedDetail.isEmpty {
            defaults.removeObject(forKey: Self.diagnosticsLastDetailKey)
        } else {
            defaults.set(trimmedDetail, forKey: Self.diagnosticsLastDetailKey)
        }
        let resolvedUserId = (userId ?? supabaseUserId)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if resolvedUserId.isEmpty {
            defaults.removeObject(forKey: Self.diagnosticsLastUserIdKey)
        } else {
            defaults.set(resolvedUserId, forKey: Self.diagnosticsLastUserIdKey)
        }
    }

    private static func isoString(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    private static func jwtSubject(from token: String) -> String? {
        jwtPayload(from: token)?["sub"] as? String
    }

    private static func jwtExpiration(from token: String) -> Date? {
        guard let exp = jwtPayload(from: token)?["exp"] as? TimeInterval else { return nil }
        return Date(timeIntervalSince1970: exp)
    }

    private static func jwtPayload(from token: String) -> [String: Any]? {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return nil }
        var payload = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while !payload.count.isMultiple(of: 4) {
            payload.append("=")
        }
        guard let data = Data(base64Encoded: payload),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return json
    }
}

private enum AuthError: LocalizedError {
    case missingConfig
    case invalidEmail
    case invalidPassword
    case weakPassword
    case unexpectedResponse
    case remote(String)

    var errorDescription: String? {
        switch self {
        case .missingConfig:
            return "Supabase config missing from Info.plist."
        case .invalidEmail:
            return "Enter a valid email address."
        case .invalidPassword:
            return "Enter your password."
        case .weakPassword:
            return "Use a password with at least 8 characters."
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

private struct SupabaseAuthResponse: Decodable {
    let accessToken: String?
    let refreshToken: String?
    let expiresIn: Int?
    let tokenType: String?
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
