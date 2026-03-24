import Foundation
import UserNotifications
#if canImport(UIKit)
import UIKit
#endif

extension Notification.Name {
    static let gaiaPushTokenDidChange = Notification.Name("gaia.push.token.did.change")
    static let gaiaPushAuthorizationDidChange = Notification.Name("gaia.push.authorization.did.change")
    static let gaiaPushDeepLinkReceived = Notification.Name("gaia.push.deep-link.received")
}

struct AppNotificationFamilies: Codable, Equatable {
    var geomagnetic: Bool = true
    var solarWind: Bool = true
    var flareCmeSep: Bool = true
    var schumann: Bool = true
    var pressure: Bool = true
    var aqi: Bool = true
    var temp: Bool = true
    var gaugeSpikes: Bool = true
    var symptomFollowups: Bool = false

    private enum CodingKeys: String, CodingKey {
        case geomagnetic
        case solarWind = "solar_wind"
        case flareCmeSep = "flare_cme_sep"
        case schumann
        case pressure
        case aqi
        case temp
        case gaugeSpikes = "gauge_spikes"
        case symptomFollowups = "symptom_followups"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        geomagnetic = try container.decodeIfPresent(Bool.self, forKey: .geomagnetic) ?? true
        solarWind = try container.decodeIfPresent(Bool.self, forKey: .solarWind) ?? true
        flareCmeSep = try container.decodeIfPresent(Bool.self, forKey: .flareCmeSep) ?? true
        schumann = try container.decodeIfPresent(Bool.self, forKey: .schumann) ?? true
        pressure = try container.decodeIfPresent(Bool.self, forKey: .pressure) ?? true
        aqi = try container.decodeIfPresent(Bool.self, forKey: .aqi) ?? true
        temp = try container.decodeIfPresent(Bool.self, forKey: .temp) ?? true
        gaugeSpikes = try container.decodeIfPresent(Bool.self, forKey: .gaugeSpikes) ?? true
        symptomFollowups = try container.decodeIfPresent(Bool.self, forKey: .symptomFollowups) ?? false
    }
}

struct AppNotificationPreferences: Codable, Equatable {
    var enabled: Bool = false
    var signalAlertsEnabled: Bool = true
    var localConditionAlertsEnabled: Bool = true
    var personalizedGaugeAlertsEnabled: Bool = true
    var symptomFollowupsEnabled: Bool = false
    var symptomFollowupCadence: String = "balanced"
    var symptomFollowupStates: [String] = ["new", "ongoing", "improving"]
    var symptomFollowupSymptomCodes: [String] = []
    var quietHoursEnabled: Bool = false
    var quietStart: String = "22:00"
    var quietEnd: String = "08:00"
    var timeZone: String = TimeZone.current.identifier
    var sensitivity: String = "normal"
    var families: AppNotificationFamilies = AppNotificationFamilies()

    static let `default` = AppNotificationPreferences()

    private enum CodingKeys: String, CodingKey {
        case enabled
        case signalAlertsEnabled = "signal_alerts_enabled"
        case localConditionAlertsEnabled = "local_condition_alerts_enabled"
        case personalizedGaugeAlertsEnabled = "personalized_gauge_alerts_enabled"
        case symptomFollowupsEnabled = "symptom_followups_enabled"
        case symptomFollowupCadence = "symptom_followup_cadence"
        case symptomFollowupStates = "symptom_followup_states"
        case symptomFollowupSymptomCodes = "symptom_followup_symptom_codes"
        case quietHoursEnabled = "quiet_hours_enabled"
        case quietStart = "quiet_start"
        case quietEnd = "quiet_end"
        case timeZone = "time_zone"
        case sensitivity
        case families
    }

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
        signalAlertsEnabled = try container.decodeIfPresent(Bool.self, forKey: .signalAlertsEnabled) ?? true
        localConditionAlertsEnabled = try container.decodeIfPresent(Bool.self, forKey: .localConditionAlertsEnabled) ?? true
        personalizedGaugeAlertsEnabled = try container.decodeIfPresent(Bool.self, forKey: .personalizedGaugeAlertsEnabled) ?? true
        symptomFollowupsEnabled = try container.decodeIfPresent(Bool.self, forKey: .symptomFollowupsEnabled) ?? false
        symptomFollowupCadence = try container.decodeIfPresent(String.self, forKey: .symptomFollowupCadence) ?? "balanced"
        symptomFollowupStates = try container.decodeIfPresent([String].self, forKey: .symptomFollowupStates) ?? ["new", "ongoing", "improving"]
        symptomFollowupSymptomCodes = try container.decodeIfPresent([String].self, forKey: .symptomFollowupSymptomCodes) ?? []
        quietHoursEnabled = try container.decodeIfPresent(Bool.self, forKey: .quietHoursEnabled) ?? false
        quietStart = try container.decodeIfPresent(String.self, forKey: .quietStart) ?? "22:00"
        quietEnd = try container.decodeIfPresent(String.self, forKey: .quietEnd) ?? "08:00"
        timeZone = try container.decodeIfPresent(String.self, forKey: .timeZone) ?? TimeZone.current.identifier
        sensitivity = try container.decodeIfPresent(String.self, forKey: .sensitivity) ?? "normal"
        families = try container.decodeIfPresent(AppNotificationFamilies.self, forKey: .families) ?? AppNotificationFamilies()
    }
}

private struct NotificationPreferencesEnvelope: Codable {
    let ok: Bool?
    let preferences: AppNotificationPreferences?
    let error: String?
    let detail: String?
}

private struct PushTokenRegistrationPayload: Codable {
    let platform: String
    let deviceToken: String
    let appVersion: String?
    let environment: String
    let enabled: Bool

    private enum CodingKeys: String, CodingKey {
        case platform
        case deviceToken = "device_token"
        case appVersion = "app_version"
        case environment
        case enabled
    }
}

private struct PushTokenDisablePayload: Codable {
    let deviceToken: String

    private enum CodingKeys: String, CodingKey {
        case deviceToken = "device_token"
    }
}

struct GaiaPushRoute: Equatable {
    let family: String
    let eventKey: String
    let targetType: String
    let targetKey: String
    let asof: String?

    init?(url: URL) {
        guard url.scheme?.lowercased() == "gaiaeyes" else { return nil }
        let host = (url.host ?? "").lowercased()
        let path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")).lowercased()
        guard host == "mission-control" || path == "mission-control" else { return nil }
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        let items = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        let family = items["family"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let eventKey = items["event_key"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let targetType = items["target_type"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let targetKey = items["target_key"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !family.isEmpty, !eventKey.isEmpty, !targetType.isEmpty, !targetKey.isEmpty else { return nil }
        self.family = family
        self.eventKey = eventKey
        self.targetType = targetType
        self.targetKey = targetKey
        self.asof = items["asof"]
    }

    init?(userInfo: [AnyHashable: Any]) {
        if let deepLink = userInfo["deep_link"] as? String,
           let url = URL(string: deepLink),
           let route = GaiaPushRoute(url: url) {
            self = route
            return
        }

        guard
            let family = (userInfo["family"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            let eventKey = (userInfo["event_key"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            let targetType = (userInfo["target_type"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            let targetKey = (userInfo["target_key"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            !family.isEmpty,
            !eventKey.isEmpty,
            !targetType.isEmpty,
            !targetKey.isEmpty
        else {
            return nil
        }
        self.family = family
        self.eventKey = eventKey
        self.targetType = targetType
        self.targetKey = targetKey
        self.asof = (userInfo["asof"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var userInfo: [AnyHashable: Any] {
        [
            "family": family,
            "event_key": eventKey,
            "target_type": targetType,
            "target_key": targetKey,
            "asof": asof ?? ""
        ]
    }
}

@MainActor
enum PushNotificationService {
    private static let deviceTokenKey = "gaia.push.device_token"
    private static let permissionGrantedKey = "gaia.push.permission_granted"
    private static let pendingRouteKey = "gaia.push.pending_route_json"
    private static let tokenSyncCooldownSeconds: TimeInterval = 15
    private static let registrationThrottleSeconds: TimeInterval = 5
    private static let requestTimeout: TimeInterval = 60
    private static let resourceTimeout: TimeInterval = 90
    private static var lastRemoteRegistrationRequestAt: Date?
    private static var lastTokenSyncAt: Date?
    private static var lastSyncedDeviceToken: String?
    private static var tokenSyncTask: Task<Bool, Never>?

    static func currentPreferencesDefault() -> AppNotificationPreferences {
        var defaults = AppNotificationPreferences.default
        defaults.timeZone = TimeZone.current.identifier
        return defaults
    }

    static func storedDeviceToken() -> String? {
        let token = UserDefaults.standard.string(forKey: deviceTokenKey)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (token?.isEmpty == false) ? token : nil
    }

    @discardableResult
    static func storeDeviceToken(_ token: String) -> Bool {
        let cleaned = token.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !cleaned.isEmpty else { return false }
        if storedDeviceToken() == cleaned {
            return false
        }
        UserDefaults.standard.set(cleaned, forKey: deviceTokenKey)
        NotificationCenter.default.post(name: .gaiaPushTokenDidChange, object: nil, userInfo: ["device_token": cleaned])
        return true
    }

    static func storedPermissionGranted() -> Bool {
        UserDefaults.standard.bool(forKey: permissionGrantedKey)
    }

    static func refreshAuthorizationState() async {
        let status = await currentAuthorizationStatus()
        let granted = authorizationGranted(status)
        UserDefaults.standard.set(granted, forKey: permissionGrantedKey)
        NotificationCenter.default.post(name: .gaiaPushAuthorizationDidChange, object: nil, userInfo: ["granted": granted])
        if granted {
            registerForRemoteNotifications()
        }
    }

    static func currentAuthorizationStatus() async -> UNAuthorizationStatus {
        await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    static func authorizationGranted(_ status: UNAuthorizationStatus) -> Bool {
        switch status {
        case .authorized, .provisional, .ephemeral:
            return true
        default:
            return false
        }
    }

    @discardableResult
    static func requestAuthorization() async -> Bool {
        let granted = await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, _ in
                continuation.resume(returning: granted)
            }
        }
        UserDefaults.standard.set(granted, forKey: permissionGrantedKey)
        if granted {
            registerForRemoteNotifications()
        }
        NotificationCenter.default.post(name: .gaiaPushAuthorizationDidChange, object: nil, userInfo: ["granted": granted])
        return granted
    }

    static func registerForRemoteNotifications() {
#if canImport(UIKit)
        let now = Date()
        if let lastRemoteRegistrationRequestAt, now.timeIntervalSince(lastRemoteRegistrationRequestAt) < registrationThrottleSeconds {
            return
        }
        lastRemoteRegistrationRequestAt = now
        DispatchQueue.main.async {
            UIApplication.shared.registerForRemoteNotifications()
        }
#endif
    }

    static func fetchPreferences(auth: AuthManager? = nil) async throws -> AppNotificationPreferences {
        let req = try await makeRequest(path: "v1/profile/notifications", method: "GET", body: nil, auth: auth)
        let (data, response) = try await performRequest(req, label: "notification-preferences-fetch")
        try validate(response: response, data: data)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        var prefs = try decodeNotificationPreferencesEnvelope(
            data: data,
            responseStatus: status,
            fallback: currentPreferencesDefault()
        )
        prefs.timeZone = prefs.timeZone.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines).isEmpty ? TimeZone.current.identifier : prefs.timeZone
        return prefs
    }

    static func savePreferences(_ preferences: AppNotificationPreferences, auth: AuthManager? = nil) async throws -> AppNotificationPreferences {
        let payload = normalized(preferences)
        let body = try JSONEncoder().encode(payload)
        let req = try await makeRequest(path: "v1/profile/notifications", method: "PUT", body: body, auth: auth)
        let (data, response) = try await performRequest(req, label: "notification-preferences-save")
        try validate(response: response, data: data)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        return try decodeNotificationPreferencesEnvelope(data: data, responseStatus: status, fallback: payload)
    }

    @discardableResult
    static func syncTokenRegistration(preferences: AppNotificationPreferences, auth: AuthManager? = nil) async -> Bool {
        guard let deviceToken = storedDeviceToken() else { return false }
        if let tokenSyncTask {
            return await tokenSyncTask.value
        }
        if preferences.enabled,
           storedPermissionGranted(),
           lastSyncedDeviceToken == deviceToken,
           let lastTokenSyncAt,
           Date().timeIntervalSince(lastTokenSyncAt) < tokenSyncCooldownSeconds {
            return true
        }
        let task = Task<Bool, Never> {
            let result = await performTokenSync(preferences: preferences, auth: auth, deviceToken: deviceToken)
            await MainActor.run {
                tokenSyncTask = nil
                if result {
                    lastTokenSyncAt = Date()
                    lastSyncedDeviceToken = deviceToken
                }
            }
            return result
        }
        tokenSyncTask = task
        return await task.value
    }

    private static func performTokenSync(
        preferences: AppNotificationPreferences,
        auth: AuthManager?,
        deviceToken: String
    ) async -> Bool {
        if preferences.enabled && storedPermissionGranted() {
            do {
                let payload = PushTokenRegistrationPayload(
                    platform: "ios",
                    deviceToken: deviceToken,
                    appVersion: appVersionString(),
                    environment: appEnvironment(),
                    enabled: true
                )
                let body = try JSONEncoder().encode(payload)
                let req = try await makeRequest(path: "v1/profile/push-tokens", method: "POST", body: body, auth: auth)
                let (_, response) = try await performRequest(req, label: "push-token-upsert")
                try validate(response: response, data: Data())
                return true
            } catch {
                appLog("[PUSH] token sync failed: \(error.localizedDescription)")
                return false
            }
        }
        return await disableStoredToken(auth: auth)
    }

    @discardableResult
    static func disableStoredToken(
        auth: AuthManager? = nil,
        bearerTokenOverride: String? = nil,
        devUserIdOverride: String? = nil
    ) async -> Bool {
        guard let deviceToken = storedDeviceToken() else { return false }
        do {
            let payload = PushTokenDisablePayload(deviceToken: deviceToken)
            let body = try JSONEncoder().encode(payload)
            let req = try await makeRequest(
                path: "v1/profile/push-tokens/disable",
                method: "POST",
                body: body,
                auth: auth,
                bearerTokenOverride: bearerTokenOverride,
                devUserIdOverride: devUserIdOverride
            )
            let (_, response) = try await performRequest(req, label: "push-token-disable")
            try validate(response: response, data: Data())
            return true
        } catch {
            appLog("[PUSH] token disable failed: \(error.localizedDescription)")
            return false
        }
    }

    static func handleNotificationUserInfo(_ userInfo: [AnyHashable: Any]) {
        guard let route = GaiaPushRoute(userInfo: userInfo) else { return }
        storePendingRoute(route)
        NotificationCenter.default.post(name: .gaiaPushDeepLinkReceived, object: nil, userInfo: route.userInfo)
    }

    static func consumePendingRoute() -> GaiaPushRoute? {
        defer { UserDefaults.standard.removeObject(forKey: pendingRouteKey) }
        guard let raw = UserDefaults.standard.string(forKey: pendingRouteKey),
              let data = raw.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: String] else {
            return nil
        }
        return GaiaPushRoute(userInfo: json)
    }

    private static func normalized(_ preferences: AppNotificationPreferences) -> AppNotificationPreferences {
        var payload = preferences
        payload.timeZone = TimeZone.current.identifier
        if payload.quietStart.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload.quietStart = "22:00"
        }
        if payload.quietEnd.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload.quietEnd = "08:00"
        }
        if payload.sensitivity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload.sensitivity = "normal"
        }
        if payload.symptomFollowupCadence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload.symptomFollowupCadence = "balanced"
        }
        payload.symptomFollowupStates = payload.symptomFollowupStates.isEmpty ? ["new", "ongoing", "improving"] : payload.symptomFollowupStates
        return payload
    }

    private static func appVersionString() -> String? {
        let short = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        switch (short?.trimmingCharacters(in: .whitespacesAndNewlines), build?.trimmingCharacters(in: .whitespacesAndNewlines)) {
        case let (short?, build?) where !short.isEmpty && !build.isEmpty:
            return "\(short) (\(build))"
        case let (short?, _) where !short.isEmpty:
            return short
        case let (_, build?) where !build.isEmpty:
            return build
        default:
            return nil
        }
    }

    private static func appEnvironment() -> String {
#if DEBUG
        return "dev"
#else
        return "prod"
#endif
    }

    private static func makeRequest(
        path: String,
        method: String,
        body: Data?,
        auth: AuthManager?,
        bearerTokenOverride: String? = nil,
        devUserIdOverride: String? = nil
    ) async throws -> URLRequest {
        guard var base = backendBaseURL() else {
            throw PushNotificationError.missingBaseURL
        }
        let cleanPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        base.appendPathComponent(cleanPath)
        var req = URLRequest(url: base)
        req.httpMethod = method
        req.timeoutInterval = requestTimeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let authManager = auth ?? AuthManager.shared
        if let bearerTokenOverride, !bearerTokenOverride.isEmpty {
            req.setValue("Bearer \(bearerTokenOverride)", forHTTPHeaderField: "Authorization")
            if let devUserIdOverride, !devUserIdOverride.isEmpty {
                req.setValue(devUserIdOverride, forHTTPHeaderField: "X-Dev-UserId")
            }
        } else if let accessToken = await authManager.validAccessToken(), !accessToken.isEmpty {
            req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        } else if let bearer = developerBearer() {
            req.setValue("Bearer \(bearer.token)", forHTTPHeaderField: "Authorization")
            if let devUserId = devUserIdOverride ?? bearer.devUserId {
                req.setValue(devUserId, forHTTPHeaderField: "X-Dev-UserId")
            }
        } else {
            throw PushNotificationError.missingAuthorization
        }

        req.httpBody = body
        return req
    }

    private static func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw PushNotificationError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            throw PushNotificationError.server(message)
        }
    }

    private static func performRequest(_ request: URLRequest, label: String) async throws -> (Data, URLResponse) {
        let session = pushURLSession()
        let maxAttempts = 2
        var lastError: Error?
        for attempt in 1...maxAttempts {
            do {
                return try await session.data(for: request)
            } catch {
                lastError = error
                guard attempt < maxAttempts, isTransientNetworkError(error) else {
                    throw error
                }
                appLog("[PUSH] retrying \(label) after transient error: \(error.localizedDescription)")
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
        throw lastError ?? PushNotificationError.invalidResponse
    }

    private static func pushURLSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = requestTimeout
        config.timeoutIntervalForResource = resourceTimeout
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }

    private static func isTransientNetworkError(_ error: Error) -> Bool {
        let nsError = error as NSError
        guard nsError.domain == NSURLErrorDomain else { return false }
        return [
            NSURLErrorTimedOut,
            NSURLErrorNetworkConnectionLost,
            NSURLErrorCannotConnectToHost,
            NSURLErrorNotConnectedToInternet,
            NSURLErrorCannotFindHost,
            NSURLErrorDNSLookupFailed,
        ].contains(nsError.code)
    }

    private static func decodeNotificationPreferencesEnvelope(
        data: Data,
        responseStatus: Int,
        fallback: AppNotificationPreferences
    ) throws -> AppNotificationPreferences {
        if data.isEmpty {
            appLog("[PUSH] notification preferences response empty status=\(responseStatus)")
            return fallback
        }

        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let envelope = try decoder.decode(NotificationPreferencesEnvelope.self, from: data)
            if envelope.ok == false {
                let message = (envelope.error ?? envelope.detail ?? "Notification settings request failed")
                    .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines)
                throw PushNotificationError.server(message.isEmpty ? "Notification settings request failed" : message)
            }
            if let error = envelope.error ?? envelope.detail, !(error.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) {
                appLog("[PUSH] notification preferences server note: \(error)")
            }
            return envelope.preferences ?? fallback
        } catch {
            let body = String(data: data, encoding: .utf8) ?? "<non-utf8 body>"
            appLog("[PUSH] notification preferences decode failed status=\(responseStatus) body=\(body)")
            throw error
        }
    }

    private static func backendBaseURL() -> URL? {
        let raw = UserDefaults.standard.string(forKey: "baseURL")?.trimmingCharacters(in: .whitespacesAndNewlines)
        let base: String
        if let raw, !raw.isEmpty {
            base = raw
        } else {
            base = DeveloperAuthDefaults.baseURL
        }
        return URL(string: base)
    }

    private static func storePendingRoute(_ route: GaiaPushRoute) {
        let payload: [String: String] = [
            "family": route.family,
            "event_key": route.eventKey,
            "target_type": route.targetType,
            "target_key": route.targetKey,
            "asof": route.asof ?? ""
        ]
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
              let raw = String(data: data, encoding: .utf8) else {
            return
        }
        UserDefaults.standard.set(raw, forKey: pendingRouteKey)
    }

    private static func developerBearer() -> (token: String, devUserId: String?)? {
        let defaults = UserDefaults.standard
        let token = defaults.string(forKey: "bearer")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !token.isEmpty else { return nil }
        let userId = defaults.string(forKey: "userId")?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedUserId: String?
        if let userId, !userId.isEmpty, userId.lowercased() != "anonymous" {
            resolvedUserId = userId
        } else if token.lowercased() == DeveloperAuthDefaults.bearer.lowercased() {
            resolvedUserId = DeveloperAuthDefaults.userId
        } else {
            resolvedUserId = nil
        }
        return (token, resolvedUserId)
    }
}

final class PushNotificationAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        Task {
            await PushNotificationService.refreshAuthorizationState()
        }
        if let remote = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
            PushNotificationService.handleNotificationUserInfo(remote)
        }
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        let changed = PushNotificationService.storeDeviceToken(token)
        if changed {
            appLog("[PUSH] APNs token updated")
        }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        appLog("[PUSH] APNs registration failed: \(error.localizedDescription)")
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound, .badge])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        PushNotificationService.handleNotificationUserInfo(response.notification.request.content.userInfo)
        completionHandler()
    }
}

private enum PushNotificationError: LocalizedError {
    case missingBaseURL
    case missingAuthorization
    case invalidResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .missingBaseURL:
            return "Backend base URL missing."
        case .missingAuthorization:
            return "Sign in or configure backend auth before syncing push settings."
        case .invalidResponse:
            return "Unexpected push settings response."
        case .server(let message):
            return message
        }
    }
}
