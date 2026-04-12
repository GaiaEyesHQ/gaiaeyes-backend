import Foundation
#if canImport(UIKit)
import UIKit
#endif

struct AppAnalyticsEvent: Codable, Equatable {
    let clientEventId: String
    let eventName: String
    let eventTsUtc: String
    let platform: String
    let appVersion: String?
    let deviceModel: String?
    let sessionId: String
    let surface: String?
    let properties: [String: String]

    enum CodingKeys: String, CodingKey {
        case clientEventId = "client_event_id"
        case eventName = "event_name"
        case eventTsUtc = "event_ts_utc"
        case platform
        case appVersion = "app_version"
        case deviceModel = "device_model"
        case sessionId = "session_id"
        case surface
        case properties
    }
}

private actor AppAnalyticsStore {
    private let storageKey = "gaia.analytics.pending_events"
    private let maxStoredEvents = 300
    private let batchSize = 40
    private var uploader: (([AppAnalyticsEvent]) async throws -> Void)?
    private var isFlushing = false

    func configure(uploader: @escaping ([AppAnalyticsEvent]) async throws -> Void) {
        self.uploader = uploader
    }

    func record(_ event: AppAnalyticsEvent) async {
        var events = loadEvents()
        events.append(event)
        if events.count > maxStoredEvents {
            events.removeFirst(events.count - maxStoredEvents)
        }
        saveEvents(events)
        if events.count >= batchSize {
            await flush()
        }
    }

    func flush() async {
        guard !isFlushing, let uploader else { return }
        var events = loadEvents()
        guard !events.isEmpty else { return }
        isFlushing = true
        let batch = Array(events.prefix(batchSize))
        do {
            try await uploader(batch)
            let sentIds = Set(batch.map(\.clientEventId))
            events.removeAll { sentIds.contains($0.clientEventId) }
            saveEvents(events)
        } catch {
            appLog("[ANALYTICS] upload_failed \(error.localizedDescription)")
        }
        isFlushing = false
    }

    private func loadEvents() -> [AppAnalyticsEvent] {
        guard let data = UserDefaults.standard.data(forKey: storageKey) else { return [] }
        return (try? JSONDecoder().decode([AppAnalyticsEvent].self, from: data)) ?? []
    }

    private func saveEvents(_ events: [AppAnalyticsEvent]) {
        if events.isEmpty {
            UserDefaults.standard.removeObject(forKey: storageKey)
            return
        }
        guard let data = try? JSONEncoder().encode(events) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }
}

enum AppAnalytics {
    private static let store = AppAnalyticsStore()
    private static let sessionId = UUID().uuidString

    static func configure(uploader: @escaping ([AppAnalyticsEvent]) async throws -> Void) {
        Task {
            await store.configure(uploader: uploader)
            await store.flush()
        }
    }

    static func track(_ name: String, properties: [String: String] = [:]) {
        let normalized = properties
            .map { key, value in "\(key)=\(value)" }
            .sorted()
            .joined(separator: " ")
        if normalized.isEmpty {
            appLog("[ANALYTICS] \(name)")
        } else {
            appLog("[ANALYTICS] \(name) \(normalized)")
        }

        let event = AppAnalyticsEvent(
            clientEventId: UUID().uuidString,
            eventName: name,
            eventTsUtc: isoString(Date()),
            platform: "ios",
            appVersion: appVersion(),
            deviceModel: deviceModel(),
            sessionId: sessionId,
            surface: properties["surface"],
            properties: properties
        )
        Task {
            await store.record(event)
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await store.flush()
        }
    }

    static func flush() {
        Task {
            await store.flush()
        }
    }

    private static func isoString(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    private static func appVersion() -> String? {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        switch (version?.isEmpty == false ? version : nil, build?.isEmpty == false ? build : nil) {
        case let (version?, build?):
            return "\(version) (\(build))"
        case let (version?, nil):
            return version
        case let (nil, build?):
            return build
        default:
            return nil
        }
    }

    private static func deviceModel() -> String? {
        #if canImport(UIKit)
        return "\(UIDevice.current.model) \(UIDevice.current.systemName) \(UIDevice.current.systemVersion)"
        #else
        return nil
        #endif
    }
}
