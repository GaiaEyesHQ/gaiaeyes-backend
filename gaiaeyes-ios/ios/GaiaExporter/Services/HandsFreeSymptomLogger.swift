import AppIntents
import Foundation

enum HandsFreeSymptomLogResult: Equatable {
    case submitted
    case queued
    case duplicate
    case signedOut
    case failed
}

struct HandsFreeSymptomLogRequest: Equatable {
    let symptomCode: String
    let severity: Int

    static let migraine = HandsFreeSymptomLogRequest(symptomCode: "MIGRAINE", severity: 5)

    func event(at date: Date = Date()) -> SymptomQueuedEvent {
        SymptomQueuedEvent(symptomCode: symptomCode, tsUtc: date, severity: severity)
    }
}

actor HandsFreeSymptomLogger {
    static let shared = HandsFreeSymptomLogger()

    typealias TokenProvider = @MainActor () async -> String?
    typealias Submitter = (SymptomQueuedEvent, String) async throws -> Void
    typealias Enqueuer = (SymptomQueuedEvent) async -> Void

    private let duplicateWindow: TimeInterval
    private let defaults: UserDefaults
    private let now: () -> Date
    private let tokenProvider: TokenProvider
    private let submitter: Submitter
    private let enqueuer: Enqueuer
    private var inFlightCodes = Set<String>()

    init(
        duplicateWindow: TimeInterval = 30,
        defaults: UserDefaults = .standard,
        now: @escaping () -> Date = Date.init,
        tokenProvider: @escaping TokenProvider = {
            await AuthManager.shared.validAccessToken()
        },
        submitter: @escaping Submitter = { event, token in
            let storedBase = UserDefaults.standard.string(forKey: "baseURL")?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let baseURL = storedBase.flatMap { $0.isEmpty ? nil : $0 }
                ?? DeveloperAuthDefaults.baseURL
            let client = APIClient(
                config: APIConfig(
                    baseURLString: baseURL,
                    bearer: token,
                    timeout: 20
                )
            )
            _ = try await client.postSymptomEvent(from: event)
        },
        enqueuer: @escaping Enqueuer = { event in
            SymptomLogQueue.shared.enqueue(event)
        }
    ) {
        self.duplicateWindow = duplicateWindow
        self.defaults = defaults
        self.now = now
        self.tokenProvider = tokenProvider
        self.submitter = submitter
        self.enqueuer = enqueuer
    }

    func log(_ request: HandsFreeSymptomLogRequest) async -> HandsFreeSymptomLogResult {
        let code = normalize(request.symptomCode)
        let timestamp = now()
        guard !isDuplicate(code: code, at: timestamp), !inFlightCodes.contains(code) else {
            return .duplicate
        }

        inFlightCodes.insert(code)
        defer { inFlightCodes.remove(code) }

        guard let token = await tokenProvider()?
            .trimmingCharacters(in: .whitespacesAndNewlines),
              !token.isEmpty else {
            return .signedOut
        }

        let event = HandsFreeSymptomLogRequest(
            symptomCode: code,
            severity: request.severity
        ).event(at: timestamp)

        do {
            try await submitter(event, token)
            recordInvocation(code: code, at: timestamp)
            NotificationCenter.default.post(name: .featuresShouldRefresh, object: nil)
            NotificationCenter.default.post(name: .dashboardShouldRefresh, object: nil)
            AppAnalytics.track(
                "symptom_logged",
                properties: ["status": "submitted", "count": "1", "source": "siri_app_intent"]
            )
            return .submitted
        } catch {
            guard Self.isOffline(error) else {
                AppAnalytics.track(
                    "symptom_log_failed",
                    properties: ["status": "failed", "count": "1", "source": "siri_app_intent"]
                )
                return .failed
            }
            await enqueuer(event)
            recordInvocation(code: code, at: timestamp)
            AppAnalytics.track(
                "symptom_logged",
                properties: ["status": "queued", "count": "1", "source": "siri_app_intent"]
            )
            return .queued
        }
    }

    private func isDuplicate(code: String, at date: Date) -> Bool {
        guard let previous = defaults.object(forKey: duplicateKey(for: code)) as? Date else {
            return false
        }
        return date.timeIntervalSince(previous) >= 0
            && date.timeIntervalSince(previous) < duplicateWindow
    }

    private func recordInvocation(code: String, at date: Date) {
        defaults.set(date, forKey: duplicateKey(for: code))
    }

    private func duplicateKey(for code: String) -> String {
        "gaia.hands_free_symptom.last_success.\(code.lowercased())"
    }

    private static func isOffline(_ error: Error) -> Bool {
        let offlineCodes: Set<URLError.Code> = [
            .timedOut,
            .cannotFindHost,
            .cannotConnectToHost,
            .networkConnectionLost,
            .dnsLookupFailed,
            .notConnectedToInternet,
        ]
        if let urlError = error as? URLError {
            return offlineCodes.contains(urlError.code)
        }
        return false
    }
}

enum HandsFreeMigraineResolutionResult: Equatable {
    case resolved
    case duplicate
    case notFound
    case signedOut
    case failed
}

actor HandsFreeMigraineResolver {
    static let shared = HandsFreeMigraineResolver()

    typealias TokenProvider = @MainActor () async -> String?
    typealias SnapshotFetcher = (String) async throws -> CurrentSymptomsSnapshot
    typealias EpisodeResolver = (String, String, Date) async throws -> Void

    private let duplicateWindow: TimeInterval
    private let defaults: UserDefaults
    private let now: () -> Date
    private let tokenProvider: TokenProvider
    private let snapshotFetcher: SnapshotFetcher
    private let episodeResolver: EpisodeResolver
    private var isResolving = false

    init(
        duplicateWindow: TimeInterval = 30,
        defaults: UserDefaults = .standard,
        now: @escaping () -> Date = Date.init,
        tokenProvider: @escaping TokenProvider = {
            await AuthManager.shared.validAccessToken()
        },
        snapshotFetcher: @escaping SnapshotFetcher = { token in
            let client = HandsFreeMigraineResolver.apiClient(token: token)
            let response = try await client.fetchCurrentSymptoms(windowHours: 48)
            guard response.ok != false, let snapshot = response.payload else {
                throw NSError(
                    domain: "HandsFreeMigraineResolver",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not load current symptoms"]
                )
            }
            return snapshot
        },
        episodeResolver: @escaping EpisodeResolver = { episodeId, token, timestamp in
            let client = HandsFreeMigraineResolver.apiClient(token: token)
            let response = try await client.updateCurrentSymptom(
                episodeId: episodeId,
                state: .resolved,
                tsUtc: timestamp
            )
            guard response.ok != false, response.payload != nil else {
                throw NSError(
                    domain: "HandsFreeMigraineResolver",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: response.error ?? "Could not end migraine"]
                )
            }
        }
    ) {
        self.duplicateWindow = duplicateWindow
        self.defaults = defaults
        self.now = now
        self.tokenProvider = tokenProvider
        self.snapshotFetcher = snapshotFetcher
        self.episodeResolver = episodeResolver
    }

    func resolveLatestMigraine() async -> HandsFreeMigraineResolutionResult {
        let timestamp = now()
        guard !wasRecentlyResolved(at: timestamp), !isResolving else {
            return .duplicate
        }

        isResolving = true
        defer { isResolving = false }

        guard let token = await tokenProvider()?
            .trimmingCharacters(in: .whitespacesAndNewlines),
              !token.isEmpty else {
            return .signedOut
        }

        do {
            let snapshot = try await snapshotFetcher(token)
            guard let migraine = snapshot.items
                .filter({ normalize($0.symptomCode) == "MIGRAINE" && $0.currentState != .resolved })
                .max(by: { $0.loggedAt < $1.loggedAt }) else {
                return .notFound
            }

            try await episodeResolver(migraine.id, token, timestamp)
            defaults.set(timestamp, forKey: duplicateKey)
            NotificationCenter.default.post(name: .featuresShouldRefresh, object: nil)
            NotificationCenter.default.post(name: .dashboardShouldRefresh, object: nil)
            AppAnalytics.track(
                "symptom_followup_answered",
                properties: [
                    "source": "siri_app_intent",
                    "status": "resolved",
                    "symptom_code": "MIGRAINE",
                ]
            )
            return .resolved
        } catch {
            return .failed
        }
    }

    private var duplicateKey: String {
        "gaia.hands_free_migraine.last_resolution"
    }

    private func wasRecentlyResolved(at date: Date) -> Bool {
        guard let previous = defaults.object(forKey: duplicateKey) as? Date else {
            return false
        }
        return date.timeIntervalSince(previous) >= 0
            && date.timeIntervalSince(previous) < duplicateWindow
    }

    private static func apiClient(token: String) -> APIClient {
        let storedBase = UserDefaults.standard.string(forKey: "baseURL")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let baseURL = storedBase.flatMap { $0.isEmpty ? nil : $0 }
            ?? DeveloperAuthDefaults.baseURL
        return APIClient(
            config: APIConfig(
                baseURLString: baseURL,
                bearer: token,
                timeout: 20
            )
        )
    }
}

struct LogMigraineIntent: AppIntent {
    static let title: LocalizedStringResource = "Log a Migraine"
    static let description = IntentDescription(
        "Logs a migraine in Gaia Eyes with the default severity."
    )
    static let authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed
    static let openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await HandsFreeSymptomLogger.shared.log(.migraine) {
        case .submitted:
            return .result(dialog: IntentDialog(
                full: "Migraine logged in Gaia Eyes. Rest; you can add details later.",
                supporting: "Migraine logged"
            ))
        case .queued:
            return .result(dialog: IntentDialog(
                full: "Migraine saved in Gaia Eyes and will sync when you’re back online. Rest; you can add details later.",
                supporting: "Migraine saved for sync"
            ))
        case .duplicate:
            return .result(dialog: IntentDialog(
                full: "That migraine was already logged in Gaia Eyes.",
                supporting: "Migraine already logged"
            ))
        case .signedOut:
            return .result(dialog: IntentDialog(
                full: "Open Gaia Eyes and sign in before logging a migraine with Siri.",
                supporting: "Sign in to Gaia Eyes"
            ))
        case .failed:
            return .result(dialog: IntentDialog(
                full: "Gaia Eyes couldn’t save the migraine. Please open the app and try again.",
                supporting: "Migraine not saved"
            ))
        }
    }
}

struct EndMigraineIntent: AppIntent {
    static let title: LocalizedStringResource = "End a Migraine"
    static let description = IntentDescription(
        "Marks the most recently logged active migraine as resolved in Gaia Eyes."
    )
    static let authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed
    static let openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await HandsFreeMigraineResolver.shared.resolveLatestMigraine() {
        case .resolved:
            return .result(dialog: IntentDialog(
                full: "Migraine ended in Gaia Eyes.",
                supporting: "Migraine ended"
            ))
        case .duplicate:
            return .result(dialog: IntentDialog(
                full: "That migraine was already ended in Gaia Eyes.",
                supporting: "Migraine already ended"
            ))
        case .notFound:
            return .result(dialog: IntentDialog(
                full: "I couldn’t find an active migraine in Gaia Eyes.",
                supporting: "No active migraine found"
            ))
        case .signedOut:
            return .result(dialog: IntentDialog(
                full: "Open Gaia Eyes and sign in before ending a migraine with Siri.",
                supporting: "Sign in to Gaia Eyes"
            ))
        case .failed:
            return .result(dialog: IntentDialog(
                full: "Gaia Eyes couldn’t end the migraine. Please try again when you’re connected.",
                supporting: "Migraine not ended"
            ))
        }
    }
}

struct GaiaEyesAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: LogMigraineIntent(),
            phrases: [
                "Log a migraine in \(.applicationName)",
                "Start a migraine in \(.applicationName)",
                "Log my migraine in \(.applicationName)",
                "Start my migraine in \(.applicationName)",
                "\(.applicationName), log my migraine",
                "\(.applicationName) migraine now",
                "Start my \(.applicationName) migraine",
            ],
            shortTitle: "Log Migraine",
            systemImageName: "waveform.path.ecg"
        )
        AppShortcut(
            intent: EndMigraineIntent(),
            phrases: [
                "My migraine stopped in \(.applicationName)",
                "End my migraine in \(.applicationName)",
                "Resolve my migraine in \(.applicationName)",
                "\(.applicationName), my migraine is over",
            ],
            shortTitle: "End Migraine",
            systemImageName: "checkmark.circle"
        )
    }
}
