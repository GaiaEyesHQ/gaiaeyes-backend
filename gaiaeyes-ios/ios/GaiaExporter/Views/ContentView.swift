import SwiftUI
import AVKit
#if canImport(UIKit)
import UIKit
#endif
import Foundation
import WebKit
import Charts
#if canImport(SDWebImage)
import SDWebImage
#endif

// MARK: - Forecast + Space Models
private struct ForecastSummary: Decodable {
    let fetched_at: String?
    let headline: String?
    let lines: [String]?
    let body: String?
}

private struct SpaceSeries: Codable {
    let spaceWeather: [SpacePoint]?
    let schumannDaily: [SchumannDay]?
    let hrDaily: [HRDay]?
    let hrTimeseries: [HRPointTS]?
}
// Empty factory for SpaceSeries
private extension SpaceSeries {
    static var empty: SpaceSeries {
        SpaceSeries(spaceWeather: [], schumannDaily: [], hrDaily: [], hrTimeseries: [])
    }
}
private struct HRPointTS: Codable {
    let ts: String?
    let hr: Double?
}
private struct HRDay: Codable {
    let day: String?
    let hr_min: Double?
    let hr_max: Double?
}
private struct SpacePoint: Codable {
    let ts: String?
    let kp: Double?
    let bz: Double?
    let sw: Double?
}
private struct SchumannDay: Codable {
    let day: String?
    let station_id: String?
    let f0: Double?
    let f1: Double?
    let f2: Double?
}

private struct SpaceOutlookEntry: Codable, Identifiable, Hashable {
    let id: String
    let title: String?
    let summary: String?
    let probability: Double?
    let confidence: String?
    let severity: String?
    let region: String?
    let windowStart: String?
    let windowEnd: String?
    let issuedAt: String?
    let driver: String?
    let metric: String?
    let value: Double?
    let unit: String?
    let source: String?
    let meta: [String: String]?

    init(id: String = UUID().uuidString,
         title: String? = nil,
         summary: String? = nil,
         probability: Double? = nil,
         confidence: String? = nil,
         severity: String? = nil,
         region: String? = nil,
         windowStart: String? = nil,
         windowEnd: String? = nil,
         issuedAt: String? = nil,
         driver: String? = nil,
         metric: String? = nil,
         value: Double? = nil,
         unit: String? = nil,
         source: String? = nil,
         meta: [String: String]? = nil) {
        self.id = id
        self.title = title
        self.summary = summary
        self.probability = probability
        self.confidence = confidence
        self.severity = severity
        self.region = region
        self.windowStart = windowStart
        self.windowEnd = windowEnd
        self.issuedAt = issuedAt
        self.driver = driver
        self.metric = metric
        self.value = value
        self.unit = unit
        self.source = source
        self.meta = meta
    }

    private enum CodingKeys: String, CodingKey {
        case title, summary, probability, confidence, severity, region, windowStart, windowEnd, issuedAt, driver, metric, value, unit, source, meta
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.title = try container.decodeIfPresent(String.self, forKey: .title)
        self.summary = try container.decodeIfPresent(String.self, forKey: .summary)
        self.probability = try container.decodeIfPresent(Double.self, forKey: .probability)
        self.confidence = try container.decodeIfPresent(String.self, forKey: .confidence)
        self.severity = try container.decodeIfPresent(String.self, forKey: .severity)
        self.region = try container.decodeIfPresent(String.self, forKey: .region)
        self.windowStart = try container.decodeIfPresent(String.self, forKey: .windowStart)
        self.windowEnd = try container.decodeIfPresent(String.self, forKey: .windowEnd)
        self.issuedAt = try container.decodeIfPresent(String.self, forKey: .issuedAt)
        self.driver = try container.decodeIfPresent(String.self, forKey: .driver)
        self.metric = try container.decodeIfPresent(String.self, forKey: .metric)
        self.value = try container.decodeIfPresent(Double.self, forKey: .value)
        self.unit = try container.decodeIfPresent(String.self, forKey: .unit)
        self.source = try container.decodeIfPresent(String.self, forKey: .source)
        self.meta = try container.decodeIfPresent([String: String].self, forKey: .meta)
        let explicitID = self.meta?["id"] ?? self.meta?["pk"] ?? self.meta?["key"]
        self.id = explicitID ?? self.windowStart ?? self.windowEnd ?? UUID().uuidString
    }
}

private struct SpaceOutlookSection: Identifiable, Hashable, Codable {
    let id: String
    let title: String
    let entries: [SpaceOutlookEntry]
}

private struct SpaceForecastOutlook: Codable {
    let issuedAt: String?
    let sections: [SpaceOutlookSection]
    let notes: [String]?

    private struct DynamicKey: CodingKey {
        var stringValue: String
        init?(stringValue: String) { self.stringValue = stringValue }
        var intValue: Int?
        init?(intValue: Int) { return nil }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)
        var tmpSections: [SpaceOutlookSection] = []
        var issued: String? = nil
        var notes: [String]? = nil

        for key in container.allKeys {
            switch key.stringValue {
            case "issuedAt":
                issued = try container.decodeIfPresent(String.self, forKey: key)
            case "notes":
                notes = try container.decodeIfPresent([String].self, forKey: key)
            default:
                if let entries = try? container.decode([SpaceOutlookEntry].self, forKey: key), !entries.isEmpty {
                    let title = key.stringValue.replacingOccurrences(of: "_", with: " ").capitalized
                    tmpSections.append(SpaceOutlookSection(id: key.stringValue, title: title, entries: entries))
                }
            }
        }

        self.issuedAt = issued
        self.sections = tmpSections.sorted { $0.title < $1.title }
        self.notes = notes
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        if let issuedAt, let issuedKey = DynamicKey(stringValue: "issuedAt") {
            try container.encode(issuedAt, forKey: issuedKey)
        }
        if let notes, let notesKey = DynamicKey(stringValue: "notes") {
            try container.encode(notes, forKey: notesKey)
        }
        for section in sections {
            guard let key = DynamicKey(stringValue: section.id) else { continue }
            try container.encode(section.entries, forKey: key)
        }
    }
}

private enum SpaceDetailSection: Hashable {
    case aurora
    case visuals
    case earthquakes
}

struct ContentView: View {
#if os(iOS)
    private struct FeatureFetchState {
        var ok: Bool? = nil
        var source: String? = nil
        var cacheFallback: String? = nil
        var poolTimeout: String? = nil
        var error: String? = nil

        var hasInfo: Bool {
            ok != nil || source != nil || cacheFallback != nil || poolTimeout != nil || error != nil
        }

        var cacheFallbackActive: Bool { cacheFallback != nil }
        var poolTimeoutActive: Bool { poolTimeout != nil }
        var errorActive: Bool { error != nil }

        var okText: String {
            guard let ok else { return "-" }
            return ok ? "true" : "false"
        }
    }

    // Throttle / circuit-breaker for features refresh loops
    @State private var featuresRefreshBusy: Bool = false
    @State private var featuresRefreshGuardUntil: Date = .distantPast
    @State private var featuresConsecutiveFailures: Int = 0
    @State private var lastFeaturesAttemptAt: Date = .distantPast
    @State private var lastFeaturesSuccessAt: Date = .distantPast
    @StateObject private var state = AppState()
    @AppStorage("features_cache_json") private var featuresCacheJSON: String = ""
    @AppStorage("series_cache_json") private var seriesCacheJSON: String = ""
    @AppStorage("symptom_codes_cache_json") private var symptomCodesCacheJSON: String = ""
    @AppStorage("space_visuals_cache_json") private var spaceVisualsCacheJSON: String = ""
    @AppStorage("space_outlook_cache_json") private var spaceOutlookCacheJSON: String = ""
    @Environment(\.scenePhase) private var scenePhase
    @State private var showConnections: Bool = false
    @State private var expandLog: Bool = false
    @State private var showDebug: Bool = false
    @State private var showTools: Bool = false
    @State private var showActions: Bool = false
    @State private var showBle: Bool = false
    @State private var showPolar: Bool = false
    @State private var didRunInitialTasks = false

    @State private var featuresDiagnosticsLoading: Bool = false
    @State private var featuresDiagnosticsError: String?
    @State private var featuresDiagnostics: Diagnostics?

    @State private var pendingRefreshTask: Task<Void, Never>? = nil
    @State private var pendingRefreshToken: UInt64 = 0

    @State private var features: FeaturesToday? = nil
    @State private var lastKnownFeatures: FeaturesToday? = nil
    @State private var featuresLastEnvelopeOk: Bool? = nil
    @State private var featuresLastEnvelopeSource: String? = nil
    @State private var featuresShowingCachedSnapshot: Bool = false
    @State private var featuresCacheFallbackActive: Bool = false
    @State private var featuresPoolTimeoutActive: Bool = false
    @State private var featuresErrorDiagnosticActive: Bool = false
    @State private var featureFetchState: FeatureFetchState = FeatureFetchState()
    @State private var featuresRetryWorkItem: DispatchWorkItem? = nil
    @State private var featuresCancellations: [String] = []
    @State private var didAutoSleepSyncToday: Bool = false
    @State private var forecast: ForecastSummary? = nil
    @State private var series: SpaceSeries? = nil
    @State private var lastKnownSeries: SpaceSeries? = nil
    @State private var spaceVisuals: SpaceVisualsPayload? = nil
    @State private var lastKnownSpaceVisuals: SpaceVisualsPayload? = nil
    @State private var spaceOutlook: SpaceForecastOutlook? = nil
    @State private var lastKnownSpaceOutlook: SpaceForecastOutlook? = nil
    
    @State private var symptomsToday: [SymptomEventToday] = []
    @State private var symptomDaily: [SymptomDailySummary] = []
    @State private var symptomDiagnostics: [SymptomDiagSummary] = []
    @State private var showSymptomSheet: Bool = false
    @State private var isSubmittingSymptom: Bool = false
    @State private var symptomToastMessage: String? = nil
    @State private var symptomPresets: [SymptomPreset] = SymptomPreset.defaults
    @State private var didHydrateSymptomPresets: Bool = false
    @State private var isSymptomServiceOffline: Bool = false
    @State private var didLogSymptomTimeout: Bool = false
    @State private var showSpaceWeatherDetail: Bool = false
    @State private var spaceDetailFocus: SpaceDetailSection? = nil
    @State private var interactiveVisualItem: SpaceVisualItem? = nil
    @State private var interactiveOverlaySeries: [OverlaySeries] = []
    @State private var interactiveBaseURL: URL? = nil
    @State private var showInteractiveViewer: Bool = false
    
    private func chicagoTodayString() -> String {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.timeZone = TimeZone(identifier: "America/Chicago")
        return df.string(from: Date())
    }
    
    private static let symptomDayFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.timeZone = TimeZone(secondsFromGMT: 0)
        return df
    }()
    
    private func symptomSparkPoints() -> [SymptomSparkPoint] {
        let df = ContentView.symptomDayFormatter
        return symptomDaily.compactMap { summary in
            guard let date = df.date(from: summary.day) else { return nil }
            return SymptomSparkPoint(date: date, events: summary.events, meanSeverity: summary.meanSeverity)
        }.sorted { $0.date < $1.date }
    }
    
    private func symptomHighlights(threshold: Int = 3) -> [SymptomHighlight] {
        let df = ContentView.symptomDayFormatter
        return symptomDaily.compactMap { summary in
            guard summary.events >= threshold, let date = df.date(from: summary.day) else { return nil }
            return SymptomHighlight(date: date, events: summary.events)
        }
    }
    
    @MainActor
    private func hydrateSymptomPresetsFromCache() {
        guard !didHydrateSymptomPresets else { return }
        didHydrateSymptomPresets = true
        guard !symptomCodesCacheJSON.isEmpty,
              let data = symptomCodesCacheJSON.data(using: .utf8) else { return }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let definitions = try? decoder.decode([SymptomCodeDefinition].self, from: data) {
            let presets = SymptomPreset.fromDefinitions(definitions)
            if !presets.isEmpty {
                symptomPresets = presets
                appLog("[UI] symptom presets restored from cache (\(presets.count))")
            }
        }
    }
    
    private func encodeSymptomDefinitionsJSON(_ definitions: [SymptomCodeDefinition]) -> String? {
        let payload: [[String: Any]] = definitions.map { definition in
            var object: [String: Any] = [
                "symptom_code": definition.symptomCode,
                "label": definition.label,
                "is_active": definition.isActive
            ]
            if let description = definition.description, !description.isEmpty {
                object["description"] = description
            }
            if let systemImage = definition.systemImage, !systemImage.isEmpty {
                object["system_image"] = systemImage
            }
            if let tags = definition.tags, !tags.isEmpty {
                object["tags"] = tags
            }
            return object
        }
        
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
              let json = String(data: data, encoding: .utf8) else {
            return nil
        }
        return json
    }
    
    private func refreshSymptomPresets(api override: APIClient? = nil) async {
        let api = override ?? state.apiWithAuth()
        do {
            let resp: Envelope<[SymptomCodeDefinition]> = try await api.getJSON("v1/symptoms/codes", as: Envelope<[SymptomCodeDefinition]>.self)
            let definitions = resp.payload ?? []
            if resp.ok == false && definitions.isEmpty {
                appLog("[UI] symptom presets fetch ok=false; keeping previous list")
                await MainActor.run { self.isSymptomServiceOffline = true }
                return
            }
            guard !definitions.isEmpty else {
                appLog("[UI] symptom presets fetch returned empty; keeping defaults")
                await MainActor.run {
                    if self.symptomPresets.isEmpty {
                        self.symptomPresets = SymptomPreset.defaults
                    }
                    self.isSymptomServiceOffline = true
                }
                return
            }
            let presets = SymptomPreset.fromDefinitions(definitions)
            if let json = encodeSymptomDefinitionsJSON(definitions) {
                await MainActor.run {
                    self.symptomPresets = presets
                    self.symptomCodesCacheJSON = json
                }
            } else {
                await MainActor.run {
                    self.symptomPresets = presets
                }
            }
            appLog("[UI] symptom presets updated from server (\(presets.count))")
        } catch is CancellationError {
            return
        } catch let uerr as URLError {
            if uerr.code == .cancelled { return }
            appLog("[UI] symptom presets fetch error: \(uerr.localizedDescription)")
            await MainActor.run {
                if self.symptomPresets.isEmpty {
                    self.symptomPresets = SymptomPreset.defaults
                }
                self.isSymptomServiceOffline = true
            }
        } catch {
            appLog("[UI] symptom presets fetch error: \(error.localizedDescription)")
            await MainActor.run {
                if self.symptomPresets.isEmpty {
                    self.symptomPresets = SymptomPreset.defaults
                }
                self.isSymptomServiceOffline = true
            }
        }
    }
    
    private func symptomDisplayName(for code: String) -> String {
        let normalizedCode = normalize(code)
        if let preset = symptomPresets.first(where: { $0.code == normalizedCode }) {
            return preset.label
        }
        return normalizedCode.replacingOccurrences(of: "_", with: " ").capitalized
    }
    
    private func topSymptomSummary() -> String? {
        guard let top = symptomDiagnostics.sorted(by: { $0.events > $1.events }).first, top.events > 0 else {
            return nil
        }
        let label = symptomDisplayName(for: top.symptomCode)
        if let ts = top.lastTs {
            let isoFull = ISO8601DateFormatter()
            isoFull.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let isoSimple = ISO8601DateFormatter()
            if let date = isoFull.date(from: ts) ?? isoSimple.date(from: ts) {
                let formatter = DateFormatter()
                formatter.dateStyle = .medium
                formatter.timeStyle = .short
                let stamp = formatter.string(from: date)
                return "Top: \(label) (\(stamp)) — \(top.events) events"
            }
        }
        return "Top: \(label) — \(top.events) events"
    }
    
    private func showSymptomToast(_ message: String) {
        withAnimation {
            symptomToastMessage = message
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [self] in
            withAnimation {
                if self.symptomToastMessage == message {
                    self.symptomToastMessage = nil
                }
            }
        }
    }

    // MARK: - Features diagnostics helpers
    @MainActor
    private func fetchFeaturesDiagnostics() async {
        featuresDiagnosticsError = nil
        featuresDiagnosticsLoading = true
        defer { featuresDiagnosticsLoading = false }

        let api = state.apiWithAuth()
        do {
            let envelope = try await api.fetchFeaturesDiagnostics(tz: "America/Chicago")
            if let diagnostics = envelope.diagnostics {
                featuresDiagnostics = diagnostics
                let src = diagnostics.source ?? "-"
                appLog("[UI] features diagnostics refreshed (source=\(src))")
            }
            if envelope.ok {
                if envelope.diagnostics == nil {
                    featuresDiagnosticsError = "Diagnostics missing from response"
                }
            } else {
                featuresDiagnosticsError = envelope.error ?? "Diagnostics unavailable"
            }
        } catch {
            featuresDiagnosticsError = error.localizedDescription
        }
    }

    @MainActor
    private func copyTrace(_ lines: [String]) {
        let ordered = Array(lines.reversed())
        let text = ordered.joined(separator: "\n")
#if canImport(UIKit)
        UIPasteboard.general.string = text
#endif
        let count = ordered.count
        appLog("[UI] diagnostics trace copied (\(count) lines)")
        showSymptomToast(count == 1 ? "Copied 1 trace line" : "Copied \(count) trace lines")
    }

    @MainActor
    private func shareTrace(_ lines: [String]) {
#if canImport(UIKit)
        let ordered = Array(lines.reversed())
        let text = ordered.joined(separator: "\n")
        let activity = UIActivityViewController(activityItems: [text], applicationActivities: nil)
        if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let window = scene.windows.first,
           let root = window.rootViewController {
            if let popover = activity.popoverPresentationController {
                popover.sourceView = root.view
                popover.sourceRect = CGRect(x: root.view.bounds.midX, y: root.view.bounds.midY, width: 0, height: 0)
            }
            root.present(activity, animated: true)
        }
#endif
        appLog("[UI] diagnostics trace share sheet presented")
    }

    @MainActor
    private func appendTraceToStatus(_ lines: [String]) {
        let ordered = Array(lines.reversed())
        let payload = ordered.isEmpty ? ["(no trace lines)"] : ordered
        state.statusLines.append(contentsOf: payload)
        appLog("[UI] diagnostics trace appended to status (\(payload.count) lines)")
        showSymptomToast("Trace appended to Status")
    }
    
    private func formatISO(_ iso: String) -> Date? {
        let fmt = ISO8601DateFormatter(); return fmt.date(from: iso)
    }
    
    private func formatUpdated(_ iso: String) -> String? {
        let fmt = ISO8601DateFormatter()
        guard let d = fmt.date(from: iso) else { return nil }
        let out = DateFormatter()
        out.dateStyle = .none
        out.timeStyle = .short
        return out.string(from: d)
    }

    private func decodeSpaceVisuals(from json: String) -> SpaceVisualsPayload? {
        guard !json.isEmpty, let data = json.data(using: .utf8) else { return nil }
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        if let env = try? dec.decode(Envelope<SpaceVisualsPayload>.self, from: data), let payload = env.payload {
            return payload
        }
        return try? dec.decode(SpaceVisualsPayload.self, from: data)
    }

    private func decodeSpaceOutlook(from json: String) -> SpaceForecastOutlook? {
        guard !json.isEmpty, let data = json.data(using: .utf8) else { return nil }
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        if let env = try? dec.decode(Envelope<SpaceForecastOutlook>.self, from: data), let payload = env.payload {
            return payload
        }
        return try? dec.decode(SpaceForecastOutlook.self, from: data)
    }

    private static var mediaBaseURL: URL? {
        let envBase = ProcessInfo.processInfo.environment["MEDIA_BASE_URL"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let envBase, !envBase.isEmpty {
            return URL(string: envBase.hasSuffix("/") ? String(envBase.dropLast()) : envBase)
        }
        return URL(string: "https://gaiaeyeshq.github.io/gaiaeyes-media")
    }

    private static func resolvedVisualURL(for image: SpaceVisualImage) -> URL? {
        func normalizedURL(from raw: String) -> URL? {
            guard !raw.isEmpty else { return nil }
            if let direct = URL(string: raw), direct.scheme != nil { return direct }
            if let base = mediaBaseURL { return URL(string: raw.hasPrefix("/") ? String(raw.dropFirst()) : raw, relativeTo: base)?.absoluteURL }
            return nil
        }

        if let urlStr = image.url?.trimmingCharacters(in: .whitespacesAndNewlines), let url = normalizedURL(from: urlStr) { return url }
        if let thumb = image.thumb?.trimmingCharacters(in: .whitespacesAndNewlines), let url = normalizedURL(from: thumb) { return url }
        if let metaPath = image.meta?["image_path"] ?? image.meta?["path"], let url = normalizedURL(from: metaPath) { return url }
        if let keyPath = image.key, let url = normalizedURL(from: keyPath) { return url }
        return nil
    }

    @MainActor
    private func applySpaceVisuals(_ payload: SpaceVisualsPayload) {
        spaceVisuals = payload
        lastKnownSpaceVisuals = payload
        if let encoded = try? JSONEncoder().encode(payload), let json = String(data: encoded, encoding: .utf8) {
            spaceVisualsCacheJSON = json
        }
    }

    @MainActor
    private func applySpaceOutlook(_ payload: SpaceForecastOutlook) {
        spaceOutlook = payload
        lastKnownSpaceOutlook = payload
        if let encoded = try? JSONEncoder().encode(payload), let json = String(data: encoded, encoding: .utf8) {
            spaceOutlookCacheJSON = json
        }
    }

    private func fetchSpaceVisuals() async {
        if let payload = await state.fetchSpaceVisuals() {
            await MainActor.run { applySpaceVisuals(payload) }
        } else if let cached = decodeSpaceVisuals(from: spaceVisualsCacheJSON) {
            await MainActor.run { lastKnownSpaceVisuals = cached }
        }
    }

    private func fetchSpaceOutlook() async {
        let api = state.apiWithAuth()
        do {
            let env: Envelope<SpaceForecastOutlook> = try await api.getJSON("v1/space/forecast/outlook", as: Envelope<SpaceForecastOutlook>.self, perRequestTimeout: 30)
            if let payload = env.payload {
                await MainActor.run { applySpaceOutlook(payload) }
            } else {
                appLog("[UI] space outlook payload missing; keeping last snapshot")
            }
        } catch is CancellationError {
            return
        } catch let uerr as URLError where uerr.code == .cancelled {
            return
        } catch {
            appLog("[UI] space outlook error: \(error.localizedDescription)")
            if let cached = decodeSpaceOutlook(from: spaceOutlookCacheJSON) {
                await MainActor.run { lastKnownSpaceOutlook = cached }
                return
            }
            do {
                let payload: SpaceForecastOutlook = try await api.getJSON("v1/space/forecast/outlook", as: SpaceForecastOutlook.self, perRequestTimeout: 30)
                await MainActor.run { applySpaceOutlook(payload) }
            } catch {
                appLog("[UI] space outlook fallback decode failed: \(error.localizedDescription)")
            }
        }
    }

    private func filteredVisuals(_ visuals: SpaceVisualsPayload?) -> [SpaceVisualImage] {
        visuals?.images?.filter { img in
            let key = img.key?.lowercased() ?? ""
            return !key.contains("tomsk")
        } ?? []
    }

    private func visualOverlayCount(_ visuals: SpaceVisualsPayload?) -> Int {
        filteredVisuals(visuals).count
    }

    private func latestVisualTimestamp(_ visuals: SpaceVisualsPayload?) -> String? {
        let fmt = ISO8601DateFormatter()
        let dates = filteredVisuals(visuals).compactMap { img -> Date? in
            guard let cap = img.capturedAt else { return nil }
            return fmt.date(from: cap)
        }
        guard let latest = dates.max() else { return nil }
        let out = DateFormatter()
        out.dateStyle = .short
        out.timeStyle = .short
        return out.string(from: latest)
    }

    private func latestAuroraPower(from visuals: SpaceVisualsPayload?) -> Double? {
        visuals?.series?.first(where: { ($0.name ?? $0.label ?? "").lowercased().contains("aurora") })?.latestValue
    }

    private var visualsBaseURL: URL? {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return URL(string: trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed)
            }
        }
        return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
    }

    private func overlaySeries(from item: SpaceVisualItem) -> [OverlaySeries] {
        guard let series = item.series else { return [] }
        func makeDate(_ value: Double) -> Date {
            let secs = value > 10_000_000_000 ? value / 1000.0 : value
            return Date(timeIntervalSince1970: secs)
        }
        return series.compactMap { key, points in
            let overlayPoints: [OverlaySeries.OverlayPoint] = points.compactMap { pair in
                guard pair.count >= 2 else { return nil }
                let ts = pair[0]
                let val = pair[1]
                return OverlaySeries.OverlayPoint(date: makeDate(ts), value: val)
            }.sorted { $0.date < $1.date }
            guard !overlayPoints.isEmpty else { return nil }
            return OverlaySeries(name: key, unit: nil, points: overlayPoints)
        }.sorted { $0.name < $1.name }
    }

    private func prepareInteractiveViewer(for item: SpaceVisualItem) {
        interactiveBaseURL = visualsBaseURL
        interactiveOverlaySeries = overlaySeries(from: item)
        interactiveVisualItem = item
    }

    private static func auroraProbabilityText(from features: FeaturesToday?) -> String? {
        if let prob = features?.auroraProbability?.value {
            return String(format: "%.0f%%", prob)
        }
        if let north = features?.auroraProbabilityNh?.value, let south = features?.auroraProbabilitySh?.value {
            return String(format: "NH %.0f%% / SH %.0f%%", north, south)
        }
        if let north = features?.auroraProbabilityNh?.value {
            return String(format: "NH %.0f%%", north)
        }
        if let south = features?.auroraProbabilitySh?.value {
            return String(format: "SH %.0f%%", south)
        }
        return nil
    }
    
    private enum FeaturesFetchTrigger {
        case initial
        case refresh
        case upload
    }

    @MainActor
    private func updateFeaturesDiagnostics(from envelope: Envelope<FeaturesToday>?, fallback: Bool) {
        let diagnostics = envelope?.diagnostics
        let diagnosticsCacheFallbackActive = diagnostics?.cacheFallback?.isActive ?? false
        let showingCachedFallback = diagnosticsCacheFallbackActive || fallback
        let poolTimeoutActive = diagnostics?.poolTimeout?.isActive ?? false
        let errorActive = diagnostics?.error?.isActive ?? false
        let okValue = envelope?.ok ?? (fallback ? false : true)
        let source = envelope?.source ?? ""

        featuresCacheFallbackActive = diagnosticsCacheFallbackActive
        featuresPoolTimeoutActive = poolTimeoutActive
        featuresErrorDiagnosticActive = errorActive
        featuresShowingCachedSnapshot = showingCachedFallback || poolTimeoutActive || errorActive || !okValue || source == "snapshot"

        var newFetchState = featureFetchState
        if let ok = envelope?.ok {
            newFetchState.ok = ok
        } else if fallback, newFetchState.ok == nil {
            newFetchState.ok = false
        }

        if let src = envelope?.source {
            newFetchState.source = src.isEmpty ? nil : src
        } else if fallback {
            newFetchState.source = newFetchState.source ?? "cache"
        } else if !diagnosticsCacheFallbackActive {
            newFetchState.source = nil
        }

        if showingCachedFallback {
            if diagnosticsCacheFallbackActive, let text = diagnostics?.cacheFallback?.displayText {
                newFetchState.cacheFallback = text
            } else if fallback {
                newFetchState.cacheFallback = "cache"
            } else {
                newFetchState.cacheFallback = "true"
            }
        } else {
            newFetchState.cacheFallback = nil
        }

        if poolTimeoutActive {
            newFetchState.poolTimeout = diagnostics?.poolTimeout?.displayText ?? "true"
        } else {
            newFetchState.poolTimeout = nil
        }

        if errorActive {
            if let text = diagnostics?.error?.displayText, !text.isEmpty {
                newFetchState.error = text
            } else {
                newFetchState.error = "error"
            }
        } else {
            newFetchState.error = nil
        }

        featureFetchState = newFetchState

        if diagnosticsCacheFallbackActive {
            let hadDbError = (envelope?.diagnostics?.poolTimeout?.isActive == true) || (envelope?.diagnostics?.error?.isActive == true)
            if hadDbError {
                // Retry soon if the backend really was down
                scheduleCacheFallbackRetry(after: 10)
            } else {
                // Don’t hold the UI hostage for long when we only hit a transient cache path
                cancelCacheFallbackRetry()
            }
        } else {
            cancelCacheFallbackRetry()
        }
    }

    @MainActor
    private func scheduleCacheFallbackRetry(after seconds: TimeInterval) {
        let hadWorkItem = featuresRetryWorkItem != nil
        featuresRetryWorkItem?.cancel()

        let workItem = DispatchWorkItem { [self] in
            Task {
                await self.fetchFeaturesToday(trigger: .refresh)
            }
        }

        workItem.notify(queue: .main) { [self] in
            if self.featuresRetryWorkItem === workItem {
                self.featuresRetryWorkItem = nil
            }
        }

        featuresRetryWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: workItem)

        let secondsInt = max(1, Int(seconds.rounded()))
        if hadWorkItem {
            appLog("[UI] features: cache fallback rescheduled; retrying in ~\(secondsInt)s")
        } else {
            appLog("[UI] features: cache fallback detected; retrying in ~\(secondsInt)s")
        }
    }

    @MainActor
    private func cancelCacheFallbackRetry() {
        guard let workItem = featuresRetryWorkItem else { return }
        workItem.cancel()
        featuresRetryWorkItem = nil
        appLog("[UI] features: cache fallback cleared; cancelling retry guard")
    }

    private func featuresGuardDuration(for envelope: Envelope<FeaturesToday>?, fallback: Bool) -> TimeInterval {
        // Default: very short debounce to keep UI responsive
        var guardSeconds: TimeInterval = 6.0
        if let diagnostics = envelope?.diagnostics {
            let hadDbError = diagnostics.poolTimeout?.isActive == true || ((diagnostics.error?.isActive ?? false) && ((diagnostics.error?.displayText ?? "").contains("db_")))
            if hadDbError {
                // Only hold a short guard on genuine DB errors
                guardSeconds = max(guardSeconds, 10.0)
            }
            // Do NOT stretch the guard for mere cacheFallback — server may go live within seconds
        } else if fallback {
            // If we fell back to cache without diagnostics, keep a brief guard
            guardSeconds = max(guardSeconds, 10.0)
        }
        return guardSeconds
    }

    private func diagnosticsFlags(from diagnostics: EnvelopeDiagnostics?) -> [String] {
        guard let diagnostics else { return [] }
        var flags: [String] = []
        if diagnostics.cacheFallback?.isActive == true {
            if let text = diagnostics.cacheFallback?.displayText {
                flags.append("cacheFallback(\(text))")
            } else {
                flags.append("cacheFallback")
            }
        }
        if diagnostics.poolTimeout?.isActive == true {
            if let text = diagnostics.poolTimeout?.displayText {
                flags.append("poolTimeout(\(text))")
            } else {
                flags.append("poolTimeout")
            }
        }
        if diagnostics.error?.isActive == true {
            if let text = diagnostics.error?.displayText {
                flags.append("error=\(text)")
            } else {
                flags.append("error")
            }
        }
        return flags
    }

    private var featuresCachedBannerText: String? {
        guard featuresCacheFallbackActive || featuresShowingCachedSnapshot else { return nil }
        if featuresCacheFallbackActive {
            return "Showing cached data while the network recovers"
        }
        if featuresPoolTimeoutActive {
            return "Showing cached stats while the server catches up…"
        }
        if featuresErrorDiagnosticActive {
            return "Showing cached stats while we retry after an error…"
        }
        return "Showing cached stats while we refresh…"
    }

    @MainActor
    private func decodeCachedFeatures() -> FeaturesToday? {
        guard !featuresCacheJSON.isEmpty,
              let data = featuresCacheJSON.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(FeaturesToday.self, from: data)
    }
    
    private func decodeFeatures(from json: String) -> FeaturesToday? {
        guard let data = json.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(FeaturesToday.self, from: data)
    }
    
    private func fallbackFeaturesFromCache() async -> FeaturesToday? {
        await MainActor.run {
            if let latest = self.lastKnownFeatures { return latest }
            return self.decodeCachedFeatures()
        }
    }
    
    @MainActor
    private func applyFeaturesResponse(_ data: FeaturesToday, envelope: Envelope<FeaturesToday>, trigger: FeaturesFetchTrigger) {
        // If the server indicates a live snapshot, clear any prior guard so the UI can update immediately
        if (envelope.source ?? "") == "live" {
            self.featuresRefreshGuardUntil = Date()
        }
        updateFeaturesDiagnostics(from: envelope, fallback: false)
        self.features = data
        self.lastKnownFeatures = data
        self.featuresLastEnvelopeOk = envelope.ok
        self.featuresLastEnvelopeSource = envelope.source
        self.featuresCancellations = envelope.cancellations ?? []
        if let encoded = try? JSONEncoder().encode(data),
           let json = String(data: encoded, encoding: .utf8) {
            self.featuresCacheJSON = json
        }
        let okText = envelope.ok.map { $0 ? "true" : "false" } ?? "nil"
        let sourceText = envelope.source ?? "live"
        let triggerText = String(describing: trigger)
        appLog("[UI] features ok: day=\(data.day) ok=\(okText) source=\(sourceText) trigger=\(triggerText)")
        if let cancels = envelope.cancellations, !cancels.isEmpty {
            appLog("[UI] features cancellations: \(cancels.joined(separator: ", "))")
        }
    }
    
    @MainActor
    private func applyFallbackFeatures(_ fallback: FeaturesToday, envelope: Envelope<FeaturesToday>?) {
        updateFeaturesDiagnostics(from: envelope, fallback: true)
        self.features = fallback
        self.lastKnownFeatures = fallback
        self.featuresLastEnvelopeOk = envelope?.ok ?? false
        self.featuresLastEnvelopeSource = envelope?.source ?? "cache"
        self.featuresCancellations = envelope?.cancellations ?? []
        if let cancels = envelope?.cancellations, !cancels.isEmpty {
            appLog("[UI] features cancellations (fallback): \(cancels.joined(separator: ", "))")
        }
    }
    
    private func fetchFeaturesToday(trigger: FeaturesFetchTrigger = .refresh, bypassGuard: Bool = false) async {
        // Circuit breaker: skip if a fetch is already running, guard active, or request is too soon
        let now = Date()
        if featuresRefreshBusy {
            appLog("[UI] features: refresh already in progress; skipping")
            return
        }
        if !bypassGuard && now < featuresRefreshGuardUntil {
            let remain = Int(featuresRefreshGuardUntil.timeIntervalSince(now))
            appLog("[UI] features: guard active (\(remain)s remaining); skipping")
            return
        }
        if (trigger == .upload || trigger == .refresh), now.timeIntervalSince(lastFeaturesAttemptAt) < 6 {
            let triggerText = String(describing: trigger)
            appLog("[UI] features: skipping \(triggerText) trigger (<6s since last attempt)")
            return
        }
        if now.timeIntervalSince(lastFeaturesAttemptAt) < 6 {
            if now.timeIntervalSince(lastFeaturesSuccessAt) > 6 {
                appLog("[UI] features: debounced (<6s since last attempt); skipping")
                return
            }
        }
        let backendAvailable = await MainActor.run { state.backendDBAvailable }
        guard backendAvailable else {
            appLog("[UI] refresh skipped; backend DB=false")
            await MainActor.run {
                state.append("[BG] refresh blocked: backend DB unavailable")
            }
            return
        }

        featuresRefreshBusy = true
        defer { featuresRefreshBusy = false }

        let api = state.apiWithAuth()
        if trigger == .upload {
            if Date() >= featuresRefreshGuardUntil {
                let delaySeconds = Double.random(in: 1.5...2.0)
                let delayText = String(format: "%.1f", delaySeconds)
                appLog("[UI] upload-triggered features refresh after ~\(delayText)s backoff…")
                let nanos = UInt64(delaySeconds * 1_000_000_000)
                try? await Task.sleep(nanoseconds: nanos)
            }
        }

        lastFeaturesAttemptAt = Date()

        var attempt = 0
        let maxAttempts = 3
        var lastEnvelope: Envelope<FeaturesToday>?
        var loggedRetryAttempts = Set<Int>()
        var loggedSnapshotBreadcrumb = false
        var loggedOkFalseEnvelope = false
        var loggedMissingPayload = false
        
        while attempt < maxAttempts {
            attempt += 1
            do {
                let env: Envelope<FeaturesToday> = try await api.getJSON("v1/features/today", as: Envelope<FeaturesToday>.self)
                lastEnvelope = env

                let diagFlags = diagnosticsFlags(from: env.diagnostics)
                if !diagFlags.isEmpty {
                    appLog("[UI] features diagnostics: \(diagFlags.joined(separator: ", "))")
                }

                if (env.ok == false || (env.source ?? "") == "snapshot") && !loggedSnapshotBreadcrumb {
                    appLog("[UI] features snapshot fallback (source=\(env.source ?? "-") ok=\(env.ok ?? false))")
                    loggedSnapshotBreadcrumb = true
                }

                let okValue = env.ok ?? false
                if !okValue && !loggedOkFalseEnvelope {
                    let src = env.source ?? "-"
                    appLog("[UI] features ok=false; keeping previous snapshot (source=\(src))")
                    loggedOkFalseEnvelope = true
                }
                if okValue && env.data == nil && !loggedMissingPayload {
                    appLog("[UI] features ok=true but payload missing; keeping previous snapshot")
                    loggedMissingPayload = true
                }
                if okValue, let data = env.data {
                    await MainActor.run { applyFeaturesResponse(data, envelope: env, trigger: trigger) }

                    let guardAlreadyExpired = Date() >= featuresRefreshGuardUntil
                    let guardSeconds = featuresGuardDuration(for: env, fallback: false)
                    featuresConsecutiveFailures = 0
                    featuresRefreshGuardUntil = Date().addingTimeInterval(guardSeconds)
                    lastFeaturesSuccessAt = Date()
                    if guardSeconds > 6.5 {
                        let reason = diagFlags.isEmpty ? "guard" : diagFlags.joined(separator: ", ")
                        appLog("[UI] features: guard set for ~\(Int(guardSeconds))s (\(reason))")
                    }

                    if let sleepTotalValue = data.sleepTotalMinutes?.value {
                        let todayTotal = Int(sleepTotalValue.rounded())
                        if data.day == chicagoTodayString(), todayTotal == 0, !didAutoSleepSyncToday {
                            didAutoSleepSyncToday = true
                            appLog("[UI] today has 0 sleep — running sleep sync (2 days)…")
                            await state.syncSleep7d()
                            let delaySeconds = Double.random(in: 1.0...1.2)
                            let delayText = String(format: "%.1f", delaySeconds)
                            appLog("[UI] sleep sync complete, refetching features after ~\(delayText)s backoff…")
                            let nanos = UInt64(delaySeconds * 1_000_000_000)
                            try? await Task.sleep(nanoseconds: nanos)
                            // schedule a single follow-up after short delay only if outside guard
                            if guardAlreadyExpired {
                                Task {
                                    let nanos2 = UInt64(0.8 * 1_000_000_000)
                                    try? await Task.sleep(nanoseconds: nanos2)
                                    if !Task.isCancelled && !featuresRefreshBusy {
                                        await fetchFeaturesToday(trigger: .refresh, bypassGuard: true)
                                    }
                                }
                            }
                            return
                        }
                        if data.day == chicagoTodayString(), data.sleepTotalMinutes?.value == nil, !didAutoSleepSyncToday {
                            appLog("[UI] today sleep total missing — skipping auto sleep sync trigger")
                        }
                    }
                    // Success path: return after applying response
                    return
                }
            } catch is CancellationError {
                return
            } catch let uerr as URLError where uerr.code == .cancelled {
                return
            } catch {
                appLog("[UI] featuresToday error: \(error.localizedDescription)")
            }
            
            // Fallback to cache on failure
            if let fallback = await fallbackFeaturesFromCache() {
                if !loggedSnapshotBreadcrumb {
                    appLog("[UI] features snapshot fallback (cached)")
                    loggedSnapshotBreadcrumb = true
                }
                await MainActor.run { applyFallbackFeatures(fallback, envelope: lastEnvelope) }
                featuresConsecutiveFailures = 0
                lastFeaturesSuccessAt = Date()
                let fallbackGuard = featuresGuardDuration(for: lastEnvelope, fallback: true)
                featuresRefreshGuardUntil = Date().addingTimeInterval(fallbackGuard)
                if fallbackGuard > 6.5 {
                    let reasonFlags = diagnosticsFlags(from: lastEnvelope?.diagnostics ?? nil)
                    let reason = reasonFlags.isEmpty ? "cache fallback" : reasonFlags.joined(separator: ", ")
                    appLog("[UI] features: guard set for ~\(Int(fallbackGuard))s (\(reason))")
                }
                return
            }
            
            // Retry backoff with exponential delay; open circuit if attempts exhausted
            if attempt < maxAttempts {
                if !loggedRetryAttempts.contains(attempt) {
                    appLog("[UI] features retry #\(attempt)/\(maxAttempts)")
                    loggedRetryAttempts.insert(attempt)
                }
                let delay = min(5.0 * pow(1.6, Double(attempt - 1)), 12.0)
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            } else {
                featuresConsecutiveFailures += 1
                let guardSeconds = min(300.0, pow(2.0, Double(featuresConsecutiveFailures)) * 15.0)
                featuresRefreshGuardUntil = Date().addingTimeInterval(guardSeconds)
                appLog("[UI] features: opening circuit for ~\(Int(guardSeconds))s after repeated failures")
            }
        }
        
        // No data and no cache after retries: record envelope meta if available
        if let env = lastEnvelope {
            await MainActor.run {
                self.featuresLastEnvelopeOk = env.ok
                self.featuresLastEnvelopeSource = env.source
                updateFeaturesDiagnostics(from: env, fallback: false)
                self.featuresCancellations = env.cancellations ?? []
            }
        }
        // On hard miss, set a short guard to avoid UI freeze loops
        featuresConsecutiveFailures += 1
        let guardSecondsFinal = min(60.0, pow(1.6, Double(featuresConsecutiveFailures)) * 6.0)
        featuresRefreshGuardUntil = Date().addingTimeInterval(guardSecondsFinal)
        appLog("[UI] features: guard set for \(Int(guardSecondsFinal))s to prevent loops")
        appLog("[UI] featuresToday: no data and no cache; keeping previous snapshot")
    }
    
    private func fetchForecastSummary() async {
        let backendAvailable = await MainActor.run { state.backendDBAvailable }
        guard backendAvailable else {
            appLog("[UI] forecast: backend DB=false; keeping previous snapshot")
            await MainActor.run {
                state.append("[BG] refresh blocked: backend DB unavailable")
            }
            return
        }
        let api = state.apiWithAuth()
        do {
            let envelope: Envelope<ForecastSummary> = try await api.getJSON("v1/space/forecast/summary", as: Envelope<ForecastSummary>.self)
            if let summary = envelope.payload {
                await MainActor.run { self.forecast = summary }
            } else if envelope.ok == false {
                appLog("[UI] forecast ok=false; keeping previous snapshot")
            }
        } catch is CancellationError {
            return
        } catch let e as URLError where e.code == .cancelled {
            return
        } catch {
            appLog("[UI] forecast error: \(error.localizedDescription)")
        }
    }

    private func fetchSpaceSeries(days: Int = 7) async {
        let backendAvailable = await MainActor.run { state.backendDBAvailable }
        guard backendAvailable else {
            appLog("[UI] series: backend DB=false; keeping previous charts")
            await MainActor.run {
                state.append("[BG] refresh blocked: backend DB unavailable")
            }
            return
        }
        let api = state.apiWithAuth()
        do {
            // Primary (new) endpoint
            let envelope: Envelope<SpaceSeries> = try await api.getJSON("v1/space/series?days=\(days)", as: Envelope<SpaceSeries>.self)
            let swCount = envelope.payload?.spaceWeather?.count ?? 0
            let schCount = envelope.payload?.schumannDaily?.count ?? 0
            let hrtsCount = envelope.payload?.hrTimeseries?.count ?? 0
            appLog("[UI] series ok: sw=\(swCount) sch=\(schCount) hrts=\(hrtsCount)")
            if swCount == 0 && schCount == 0 && hrtsCount == 0 {
                appLog("[UI] series RAW: (no points) — space_weather=0 schumann_daily=0 hr_timeseries=0")
            }
            // Keep existing charts if server returned empty arrays
            if (swCount + schCount + hrtsCount) == 0 {
                appLog("[UI] series empty; keeping previous charts")
                return
            }
            if let data = envelope.payload {
                if let encoded = try? JSONEncoder().encode(data),
                   let json = String(data: encoded, encoding: .utf8) {
                    seriesCacheJSON = json
                }
                await MainActor.run {
                    self.series = data
                    self.lastKnownSeries = data
                }
                return
            }
        } catch {
            // If the server uses the legacy path, retry there on 404
            if let apiErr = error as? LocalizedError, apiErr.errorDescription?.contains("HTTP 404") == true {
                appLog("[UI] series 404 on /v1/space/series — retrying legacy /v1/series…")
                do {
                    let decoded: Envelope<SpaceSeries> = try await api.getJSON("v1/series?days=\(days)", as: Envelope<SpaceSeries>.self)
                    let swCount = decoded.payload?.spaceWeather?.count ?? 0
                    let schCount = decoded.payload?.schumannDaily?.count ?? 0
                    let hrtsCount = decoded.payload?.hrTimeseries?.count ?? 0
                    appLog("[UI] series ok (legacy): sw=\(swCount) sch=\(schCount) hrts=\(hrtsCount)")
                    // Keep existing charts if server returned empty arrays
                    if (swCount + schCount + hrtsCount) == 0 {
                        appLog("[UI] series empty; keeping previous charts")
                        return
                    }
                    if let data = decoded.payload {
                        if let encoded = try? JSONEncoder().encode(data),
                           let json = String(data: encoded, encoding: .utf8) {
                            seriesCacheJSON = json
                        }
                        await MainActor.run {
                            self.series = data
                            self.lastKnownSeries = data
                        }
                        return
                    }
                } catch {
                    if let e = error as? URLError, e.code == .cancelled { return }
                    appLog("[UI] series error (legacy failed): \(error.localizedDescription)")
                    // Fallback to cache if error
                    if let cached = lastKnownSeries {
                        await MainActor.run { self.series = cached }
                        appLog("[UI] series fallback to last-known snapshot")
                    } else if let cachedData = seriesCacheJSON.data(using: .utf8),
                              let cached = try? JSONDecoder().decode(SpaceSeries.self, from: cachedData) {
                        await MainActor.run { self.series = cached; self.lastKnownSeries = cached }
                        appLog("[UI] series fallback to persisted snapshot")
                    }
                }
            } else {
                if let e = error as? URLError, e.code == .cancelled { return }
                appLog("[UI] series error: \(error.localizedDescription)")
                // Fallback to cache if error
                if let cached = lastKnownSeries {
                    await MainActor.run { self.series = cached }
                    appLog("[UI] series fallback to last-known snapshot")
                } else if let cachedData = seriesCacheJSON.data(using: .utf8),
                          let cached = try? JSONDecoder().decode(SpaceSeries.self, from: cachedData) {
                    await MainActor.run { self.series = cached; self.lastKnownSeries = cached }
                    appLog("[UI] series fallback to persisted snapshot")
                }
            }
        }
    }
    
    private func fetchSymptoms(api override: APIClient? = nil) async {
        let api = override ?? state.apiWithAuth()
        do {
            async let todayEnv: Envelope<[SymptomEventToday]> = api.getJSON("v1/symptoms/today", as: Envelope<[SymptomEventToday]>.self)
            async let dailyEnv: Envelope<[SymptomDailySummary]> = api.getJSON("v1/symptoms/daily?days=30", as: Envelope<[SymptomDailySummary]>.self)
            let diagTask = Task { () -> Result<Envelope<[SymptomDiagSummary]>, Error> in
                do {
                    return .success(try await api.getJSON("v1/symptoms/diag?days=30", as: Envelope<[SymptomDiagSummary]>.self))
                } catch {
                    return .failure(error)
                }
            }

            let todayResp = try await todayEnv
            let dailyResp = try await dailyEnv
            let diagOutcome = await diagTask.value

            var diagResp: Envelope<[SymptomDiagSummary]>?
            var diagFailure: Error?
            switch diagOutcome {
            case .success(let resp):
                diagResp = resp
            case .failure(let error):
                if let uerr = error as? URLError, uerr.code == .cancelled {
                    break
                }
                if error is CancellationError { break }
                diagFailure = error
            }

            let today = todayResp.payload ?? []
            let daily = dailyResp.payload ?? []
            let diag = diagResp?.payload ?? []

            let keepToday = (todayResp.ok == false && today.isEmpty)
            let keepDaily = (dailyResp.ok == false && daily.isEmpty)
            let keepDiag = (diagResp?.ok == false && diag.isEmpty)
            let shouldFlagOffline = keepToday || keepDaily || keepDiag || diagFailure != nil

            if let cancels = todayResp.cancellations, !cancels.isEmpty {
                appLog("[UI] symptoms cancellations: \(cancels.joined(separator: ", "))")
            }

            if let diagFailure {
                appLog("[UI] symptoms diag fetch error: \(diagFailure.localizedDescription)")
            }

            let counts = await MainActor.run { () -> (Int, Int, Int) in
                if !keepToday { self.symptomsToday = today }
                if !keepDaily { self.symptomDaily = daily }
                if diagResp != nil && !keepDiag { self.symptomDiagnostics = diag }
                if shouldFlagOffline {
                    self.isSymptomServiceOffline = true
                } else {
                    self.isSymptomServiceOffline = false
                    self.didLogSymptomTimeout = false
                }
                return (self.symptomsToday.count, self.symptomDaily.count, self.symptomDiagnostics.count)
            }

            if keepToday || keepDaily || keepDiag {
                let message = "[UI] symptoms fetch ok=false; kept previous data (today=\(counts.0) daily=\(counts.1) diag=\(counts.2))"
                appLog(message)
            } else {
                appLog("[UI] symptoms ok: today=\(counts.0) daily=\(counts.1) diag=\(counts.2)")
            }
        } catch is CancellationError {
            return
        } catch let uerr as URLError {
            if uerr.code == .cancelled { return }
            let timeoutCodes: Set<URLError.Code> = [.timedOut, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed]
            let alreadyLogged = await MainActor.run { () -> Bool in
                let logged = self.didLogSymptomTimeout
                if timeoutCodes.contains(uerr.code) {
                    self.didLogSymptomTimeout = true
                }
                self.isSymptomServiceOffline = true
                return logged
            }
            if timeoutCodes.contains(uerr.code) {
                if !alreadyLogged {
                    appLog("[UI] symptoms fetch timeout: \(uerr.localizedDescription)")
                }
            } else {
                appLog("[UI] symptoms fetch error: \(uerr.localizedDescription)")
            }
        } catch {
            appLog("[UI] symptoms fetch error: \(error.localizedDescription)")
            await MainActor.run { self.isSymptomServiceOffline = true }
        }
    }
    
    private func logSymptomEvent(_ event: SymptomQueuedEvent) async -> Bool {
        let api = state.apiWithAuth()
        do {
            struct SymptomPostBody: Encodable {
                let symptomCode: String
                let severity: Int?
                let freeText: String?
                let tags: [String]?
            }
            let body = SymptomPostBody(
                symptomCode: event.symptomCode,
                severity: event.severity,
                freeText: event.freeText,
                tags: event.tags
            )
            guard let base = URL(string: state.baseURLString) else {
                throw URLError(.badURL)
            }
            let url = base.appendingPathComponent("v1/symptoms")
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.addValue("application/json", forHTTPHeaderField: "Content-Type")
            if !state.bearer.isEmpty {
                req.addValue("Bearer \(state.bearer)", forHTTPHeaderField: "Authorization")
                // Always attach a developer user id for dev/service tokens so the backend
                // can populate request.state.user_id for user-scoped symptom routes.
                let trimmedUID = state.userId.trimmingCharacters(in: .whitespacesAndNewlines)
                let effUID = (trimmedUID.isEmpty || trimmedUID.lowercased() == "anonymous") ? DeveloperAuthDefaults.userId : trimmedUID
                req.addValue(effUID, forHTTPHeaderField: "X-Dev-UserId")
            }
            req.addValue("application/json", forHTTPHeaderField: "Accept")
            let enc = JSONEncoder()
            enc.keyEncodingStrategy = .convertToSnakeCase
            req.httpBody = try enc.encode(body)
            appLog("[SYM] POST /v1/symptoms X-Dev-UserId=\(req.value(forHTTPHeaderField: "X-Dev-UserId") ?? "nil") bearerEmpty=\(state.bearer.isEmpty)")

            // Use tuned APIClient session (not URLSession.shared)
            let (data, resp) = try await api.send(req)
            guard let http = resp as? HTTPURLResponse else {
                throw URLError(.badServerResponse)
            }

            if (200..<300).contains(http.statusCode) {
                showSymptomToast("Symptom logged")
                await fetchSymptoms(api: api)
                await state.refreshSymptomQueueCount()
                return true
            } else if (400..<500).contains(http.statusCode) {
                // Client/validation/auth errors — do not queue
                let preview = String(data: data, encoding: .utf8) ?? ""
                appLog("[SYM] server rejected (\(http.statusCode)): \(preview.prefix(160))")
                showSymptomToast("Couldn’t log symptom (\(http.statusCode))")
                await state.refreshSymptomQueueCount()
                return false
            } else {
                // 5xx — transient; queue for retry
                let preview = String(data: data, encoding: .utf8) ?? ""
                appLog("[SYM] server error (\(http.statusCode)): \(preview.prefix(160)) — queued")
                await state.enqueueSymptom(event)
                showSymptomToast("Offline — queued symptom")
                await MainActor.run { self.isSymptomServiceOffline = true }
                await state.refreshSymptomQueueCount()
                return true
            }
        } catch let uerr as URLError {
            // Queue only for connectivity-related errors; otherwise show and do not queue
            let offline: Set<URLError.Code> = [
                .timedOut, .cannotFindHost, .cannotConnectToHost,
                .networkConnectionLost, .dnsLookupFailed, .notConnectedToInternet
            ]
            if offline.contains(uerr.code) {
                await state.enqueueSymptom(event)
                showSymptomToast("Offline — queued symptom")
                appLog("[SYM] POST queued (\(uerr.code.rawValue))")
                await MainActor.run { self.isSymptomServiceOffline = true }
                await state.refreshSymptomQueueCount()
                return true
            } else if uerr.code == .cancelled {
                appLog("[SYM] upload cancelled")
            } else {
                showSymptomToast("Couldn’t log symptom")
                appLog("[SYM] POST error: \(uerr.localizedDescription)")
            }
            await state.refreshSymptomQueueCount()
            return false
        } catch {
            showSymptomToast("Couldn’t log symptom")
            appLog("[UI] symptom log error: \(error.localizedDescription)")
        }
        await state.refreshSymptomQueueCount()
        return false
    }
    
    // Decide which Features snapshot to display (today or fallback to yesterday)
    private func selectDisplayFeatures(for f: FeaturesToday) -> (FeaturesToday, Bool) {
        let todayStr = chicagoTodayString()
        var candidate = f
        var usingYesterday = false
        let todayTotal = Int((f.sleepTotalMinutes?.value ?? 0).rounded())
        if f.day == todayStr && todayTotal == 0 {
            var updatedRecently = false
            if let iso = f.updatedAt, let ts = formatISO(iso) {
                updatedRecently = ts.addingTimeInterval(600) > Date()
            }
            if !updatedRecently {
                if let prev = lastKnownFeatures, prev.day != todayStr {
                    candidate = prev
                    usingYesterday = true
                } else if let data = featuresCacheJSON.data(using: .utf8) {
                    let dec = JSONDecoder(); dec.keyDecodingStrategy = .convertFromSnakeCase
                    if let cached = try? dec.decode(FeaturesToday.self, from: data), cached.day != todayStr {
                        candidate = cached
                        usingYesterday = true
                    }
                }
            }
        }
        return (candidate, usingYesterday)
    }
    
    #endif

    private enum AppConfig {
        /// Toggle the temporary Solar Visuals (Preview) section on the dashboard (default OFF).
        static let showVisualsPreview = false
    }

    var body: some View {
#if os(iOS)
        contentViewBody
#else
        Text("ContentView is only available on iOS.")
#endif
    }

#if os(iOS)
    // Extracted to avoid scope/brace ambiguity during recent merges
    @State private var showTrends: Bool = false
    private var contentViewBody: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    
                    if let f = (features ?? lastKnownFeatures) {
                        let todayStr = chicagoTodayString()
                        let (current, usingYesterdayFallback) = selectDisplayFeatures(for: f)
                        let total = Int((current.sleepTotalMinutes?.value ?? 0).rounded())
                        let isToday = (current.day == todayStr)
                        let titleText = isToday ? "Sleep (Today)" : "Sleep (\(current.day))"
                        SleepCard(
                            title: titleText,
                            totalMin: total,
                            remMin: Int((current.remM?.value ?? 0).rounded()),
                            coreMin: Int((current.coreM?.value ?? 0).rounded()),
                            deepMin: Int((current.deepM?.value ?? 0).rounded()),
                            awakeMin: Int((current.awakeM?.value ?? 0).rounded()),
                            inbedMin: Int((current.inbedM?.value ?? 0).rounded()),
                            efficiency: current.sleepEfficiency?.value
                        )
                        .padding(.horizontal)
                        
                        if let banner = featuresCachedBannerText {
                            Label {
                                Text(banner)
                            } icon: {
                                Image(systemName: "clock.arrow.circlepath")
                            }
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.12))
                            .cornerRadius(10)
                            .padding(.horizontal)
                        }
                        
                        if usingYesterdayFallback {
                            Text("Showing yesterday’s data while today updates…")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .padding(.horizontal)
                        }
                        
                        // Live HR badge (if available)


                        // Health Stats card (steps, HR min, HR max, HRV, SpO2, BP)
                        HealthStatsCard(
                            steps: Int((current.stepsTotal?.value ?? 0).rounded()),
                            hrMin: Int((current.hrMin?.value ?? 0).rounded()),
                            hrMax: Int((current.hrMax?.value ?? 0).rounded()),
                            hrvAvg: Int((current.hrvAvg?.value ?? 0).rounded()),
                            spo2Avg: current.spo2AvgDisplay,
                            bpSys: Int((current.bpSysAvg?.value ?? 0).rounded()),
                            bpDia: Int((current.bpDiaAvg?.value ?? 0).rounded())
                        )
                        .padding(.horizontal)
                        .overlay(alignment: .bottomLeading) {
                            if let ts = current.updatedAt, let txt = formatUpdated(ts) {
                                Text("Updated: \(txt)")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .padding(.leading, 12)
                                    .padding(.bottom, 6)
                            }
                        }
                        // Live HR badge (shows current BPM if available)

 
    // MARK: - Subviews

    // Live HR badge (shows current BPM if available) ---

                        
                        SymptomsTileView(
                            todayCount: symptomsToday.count,
                            queuedCount: state.symptomQueueCount,
                            sparklinePoints: symptomSparkPoints(),
                            topSummary: topSymptomSummary(),
                            onLogTap: { showSymptomSheet = true }
                        )
                        .padding(.horizontal)
                        
                        if usingYesterdayFallback {
                            Text("Showing yesterday’s data while today updates…")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .padding(.horizontal)
                        }
                        
                        // Space Weather card
                        let visualsSnapshot = spaceVisuals ?? lastKnownSpaceVisuals
                        let overlayCount = visualOverlayCount(visualsSnapshot)
                        let overlayUpdated = latestVisualTimestamp(visualsSnapshot)
                        let auroraPowerValue = current.auroraPowerGw?.value ?? current.auroraPowerNhGw?.value ?? current.auroraPowerShGw?.value ?? latestAuroraPower(from: visualsSnapshot)
                        let earthquakeCount = current.earthquakeCount?.value.map { Int($0.rounded()) }
                        let earthquakeMag = current.earthquakeMaxMag?.value
                        SpaceWeatherCard(
                            kpMax: Int((current.kpMax?.value ?? 0).rounded()),
                            kpCurrent: current.kpCurrent?.value,
                            bzMin: current.bzMin?.value,
                            swSpeedAvg: current.swSpeedAvg?.value,
                            flares: Int((current.flaresCount?.value ?? 0).rounded()),
                            cmes: Int((current.cmesCount?.value ?? 0).rounded()),
                            schStation: current.schStation,
                            schF0: current.schF0Hz?.value,
                            schF1: current.schF1Hz?.value,
                            schF2: current.schF2Hz?.value,
                            auroraProbability: Self.auroraProbabilityText(from: current),
                            auroraPower: auroraPowerValue,
                            overlayCount: overlayCount,
                            overlayUpdated: overlayUpdated,
                            earthquakeCount: earthquakeCount,
                            earthquakeMaxMag: earthquakeMag,
                            onOpenDetail: { section in
                                spaceDetailFocus = section
                                showSpaceWeatherDetail = true
                            }
                        )
                        .navigationDestination(isPresented: $showSpaceWeatherDetail) {
                            SpaceWeatherDetailView(
                                features: current,
                                visuals: visualsSnapshot ?? lastKnownSpaceVisuals,
                                outlook: spaceOutlook ?? lastKnownSpaceOutlook,
                                series: series ?? lastKnownSeries,
                                initialSection: spaceDetailFocus
                            )
                        }
                        .padding(.horizontal)
                        .overlay(alignment: .bottomLeading) {
                            if let ts = current.updatedAt, let txt = formatUpdated(ts) {
                                Text("Updated: \(txt)")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .padding(.leading, 12)
                                    .padding(.bottom, 6)
                            }
                        }
                        // Aurora images (Nowcast / Tonight / Tomorrow)
                        do {
                            let nowNorth = appResolveMediaURL("aurora/nowcast/nowcast-north.png")
                            let tonightU = appResolveMediaURL("aurora/viewline/tonight.png")
                            let tomorrowU = appResolveMediaURL("aurora/viewline/tomorrow.png")
                            if nowNorth != nil || tonightU != nil || tomorrowU != nil {
                                GroupBox {
                                    VStack(alignment: .leading, spacing: 8) {
                                        // Small summary row
                                        HStack(spacing: 8) {
                                            if let gw = auroraPowerValue {
                                                Text(String(format: "Power: %.0f GW", gw)).font(.subheadline)
                                            } else {
                                                Text("Aurora status").font(.subheadline)
                                            }
                                            Spacer()
                                        }
                                        // Thumbnails row
                                        HStack(spacing: 10) {
                                            if let u = nowNorth {
                                                AsyncImage(url: u) { phase in
                                                    switch phase {
                                                    case .empty: ProgressView().frame(width: 110, height: 90)
                                                    case .success(let img): img.resizable().scaledToFit().frame(width: 110, height: 90).clipShape(RoundedRectangle(cornerRadius: 8))
                                                    case .failure: Image(systemName: "exclamationmark.triangle").frame(width: 110, height: 90)
                                                    @unknown default: EmptyView().frame(width: 110, height: 90)
                                                    }
                                                }
                                                .accessibilityLabel("Aurora nowcast (north)")
                                            }
                                            if let u = tonightU {
                                                AsyncImage(url: u) { phase in
                                                    switch phase {
                                                    case .empty: ProgressView().frame(width: 110, height: 90)
                                                    case .success(let img): img.resizable().scaledToFit().frame(width: 110, height: 90).clipShape(RoundedRectangle(cornerRadius: 8))
                                                    case .failure: Image(systemName: "exclamationmark.triangle").frame(width: 110, height: 90)
                                                    @unknown default: EmptyView().frame(width: 110, height: 90)
                                                    }
                                                }
                                                .accessibilityLabel("Aurora forecast (tonight)")
                                            }
                                            if let u = tomorrowU {
                                                AsyncImage(url: u) { phase in
                                                    switch phase {
                                                    case .empty: ProgressView().frame(width: 110, height: 90)
                                                    case .success(let img): img.resizable().scaledToFit().frame(width: 110, height: 90).clipShape(RoundedRectangle(cornerRadius: 8))
                                                    case .failure: Image(systemName: "exclamationmark.triangle").frame(width: 110, height: 90)
                                                    @unknown default: EmptyView().frame(width: 110, height: 90)
                                                    }
                                                }
                                                .accessibilityLabel("Aurora forecast (tomorrow)")
                                            }
                                        }
                                    }
                                } label: { Label("Aurora Now & Forecast", systemImage: "sparkles") }
                                .padding(.horizontal)
                            }
                        }
                        if AppConfig.showVisualsPreview, let vs = visualsSnapshot {
                            GroupBox {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Solar Visuals (Preview)").font(.headline)
                                    VisualsPreviewGrid(visuals: vs, maxCount: 24) { item in
                                        prepareInteractiveViewer(for: item)
                                        showInteractiveViewer = true
                                    }
                                }
                            } label: { Label("Visuals", systemImage: "photo.on.rectangle") }
                            .padding(.horizontal)
                        }
                        if usingYesterdayFallback {
                            Text("Showing yesterday’s data while today updates…")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .padding(.horizontal)
                        }
                        
                        if (current.kpAlert ?? false) || (current.flareAlert ?? false) {
                            SpaceAlertsCard(kpAlert: current.kpAlert ?? false, flareAlert: current.flareAlert ?? false)
                                .padding(.horizontal)
                        }
                        
                        if let fc = forecast {
                            ForecastCard(summary: fc).padding(.horizontal)
                        }
                        DisclosureGroup(isExpanded: $showTrends) {
                            SpaceChartsCard(series: series ?? .empty, highlights: symptomHighlights())
                                .padding(.horizontal)
                        } label: {
                            HStack {
                                Image(systemName: "chart.line.uptrend.xyaxis")
                                Text("Weekly Trends (Kp, Bz, f0, HR)")
                                Spacer()
                            }
                        }
                        .padding(.horizontal)
                        
                        EarthscopeCardV2(title: current.postTitle, caption: current.postCaption, images: current.earthscopeImages, bodyMarkdown: current.postBody)
                            .padding(.horizontal)
                        
                        DisclosureGroup(isExpanded: $showTools) {
                            VStack(spacing: 12) {
                                ConnectionSettingsSection(state: state, isExpanded: $showConnections)
                                DisclosureGroup(isExpanded: $showActions) {
                                    ActionsSection(state: state, onFetchVisuals: { Task { await fetchSpaceVisuals() } })
                                } label: { HStack { Image(systemName: "arrow.triangle.2.circlepath"); Text("HealthKit Sync & Actions"); Spacer() } }
                                DisclosureGroup(isExpanded: $showBle) {
                                    BleStatusSection(state: state)
                                } label: { HStack { Image(systemName: "antenna.radiowaves.left.and.right"); Text("Bluetooth / BLE"); Spacer() } }
                                DisclosureGroup(isExpanded: $showPolar) {
                                    PolarStatusSection(state: state)
                                } label: { HStack { Image(systemName: "waveform.path.ecg"); Text("Polar ECG"); Spacer() } }
                            }
                            .padding(.top, 8)
                        } label: { HStack { Image(systemName: "gearshape"); Text("Tools & Settings"); Spacer() } }
                            .padding(.horizontal)
                    } else {
                        GroupBox {
                            Text("No features for today yet. Pull to refresh after the rollup, or try again in a minute.")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } label: { Text("Status") }
                            .padding(.horizontal)
                        DisclosureGroup(isExpanded: $showTools) {
                            VStack(spacing: 12) {
                                ConnectionSettingsSection(state: state, isExpanded: $showConnections)
                                DisclosureGroup(isExpanded: $showActions) { ActionsSection(state: state, onFetchVisuals: { Task { await fetchSpaceVisuals() } }) } label: { HStack { Image(systemName: "arrow.triangle.2.circlepath"); Text("HealthKit Sync & Actions"); Spacer() } }
                                DisclosureGroup(isExpanded: $showBle) { BleStatusSection(state: state) } label: { HStack { Image(systemName: "antenna.radiowaves.left.and.right"); Text("Bluetooth / BLE"); Spacer() } }
                                DisclosureGroup(isExpanded: $showPolar) { PolarStatusSection(state: state) } label: { HStack { Image(systemName: "waveform.path.ecg"); Text("Polar ECG"); Spacer() } }
                            }
                            .padding(.top, 8)
                        } label: { HStack { Image(systemName: "gearshape"); Text("Tools & Settings"); Spacer() } }
                            .padding(.horizontal)
                    }
                    let debugFeaturesState = self.featureFetchState
                    if showDebug { DebugPanel(state: state, expandLog: $expandLog, featuresState: debugFeaturesState) }

                    GroupBox {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Label("Features Diagnostics", systemImage: "wrench.and.screwdriver")
                                Spacer()
                                if featuresDiagnosticsLoading {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                }
                                Button("Refresh") {
                                    Task { await fetchFeaturesDiagnostics() }
                                }
                                .disabled(featuresDiagnosticsLoading)
                            }
                            if let error = featuresDiagnosticsError {
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.orange)
                            }
                            if let diagnostics = featuresDiagnostics {
                                FeaturesDiagnosticsPanel(
                                    diag: diagnostics,
                                    onCopyTrace: { copyTrace(diagnostics.trace ?? []) },
                                    onShareTrace: { shareTrace(diagnostics.trace ?? []) },
                                    onCopyToStatus: { appendTraceToStatus(diagnostics.trace ?? []) }
                                )
                            } else if !featuresDiagnosticsLoading {
                                Text("No diagnostics yet. Tap Refresh.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    } label: {
                        Text("Diagnostics")
                    }
                    .padding(.horizontal)

                    Spacer(minLength: 10)
                }
                .padding(.bottom, 12)
            }
            .transaction { $0.disablesAnimations = true }
            .overlay(alignment: .top) {
                if let toast = symptomToastMessage { SymptomToastView(message: toast).padding(.top, 12).transition(.move(edge: .top).combined(with: .opacity)) }
            }
            .task {
                guard !didRunInitialTasks else { return }
                didRunInitialTasks = true
                await state.updateBackendDBFlag()
                let api = state.apiWithAuth()
                async let a: Void = fetchFeaturesToday(trigger: .initial)
                async let b: Void = fetchForecastSummary()
                async let c: Void = fetchSpaceSeries(days: 30)
                async let d: Void = fetchSymptoms(api: api)
                async let e: Void = state.flushQueuedSymptoms(api: api)
                async let f: Void = refreshSymptomPresets(api: api)
                async let g: Void = fetchSpaceVisuals()
                async let h: Void = fetchSpaceOutlook()
                _ = await (a, b, c, d, e, f, g, h)
            }
            .refreshable {
                await state.updateBackendDBFlag()
                let api = state.apiWithAuth()
                let guardRemaining = await MainActor.run { featuresRefreshGuardUntil.timeIntervalSinceNow }
                async let b: Void = fetchForecastSummary()
                async let c: Void = fetchSpaceSeries(days: 30)
                async let d: Void = fetchSymptoms(api: api)
                async let e: Void = state.flushQueuedSymptoms(api: api)
                async let f: Void = refreshSymptomPresets(api: api)
                async let g: Void = fetchSpaceVisuals()
                async let h: Void = fetchSpaceOutlook()
                if guardRemaining > 0 {
                    let remaining = max(1, Int(ceil(guardRemaining)))
                    appLog("[UI] pull-to-refresh: guard active (~\(remaining)s); skipping features refresh")
                    _ = await (b, c, d, e, f, g, h)
                    return
                }
                async let a: Void = fetchFeaturesToday(trigger: .refresh)
                _ = await (a, b, c, d, e, f, g, h)
            }
            .onAppear {
                state.refreshStatus()
                if features == nil, let cached = decodeCachedFeatures() {
                    features = cached
                    lastKnownFeatures = cached
                    featuresLastEnvelopeOk = nil
                    featuresLastEnvelopeSource = "cache"
                    updateFeaturesDiagnostics(from: nil, fallback: true)
                    appLog("[UI] preloaded features from persisted snapshot")
                }
                if series == nil, let data = seriesCacheJSON.data(using: .utf8) {
                    let dec = JSONDecoder(); if let cached = try? dec.decode(SpaceSeries.self, from: data) { series = cached; lastKnownSeries = cached; appLog("[UI] preloaded series from persisted snapshot") }
                }
                if spaceVisuals == nil, let cached = decodeSpaceVisuals(from: spaceVisualsCacheJSON) {
                    spaceVisuals = cached
                    lastKnownSpaceVisuals = cached
                    appLog("[UI] preloaded space visuals from persisted snapshot")
                }
                if spaceOutlook == nil, let cached = decodeSpaceOutlook(from: spaceOutlookCacheJSON) {
                    spaceOutlook = cached
                    lastKnownSpaceOutlook = cached
                    appLog("[UI] preloaded space outlook from persisted snapshot")
                }
                hydrateSymptomPresetsFromCache()
            }
            .onChange(of: scenePhase, initial: false) { _, newPhase in
                if newPhase == .active { state.refreshStatus(); Task { await HealthKitBackgroundSync.shared.kickOnce(reason: "became active") } }
            }
            .onChange(of: featuresCacheJSON, initial: false) { oldValue, newValue in
                guard newValue != oldValue, !newValue.isEmpty, let decoded = decodeFeatures(from: newValue) else { return }
                lastKnownFeatures = decoded
                if features == nil {
                    features = decoded
                    featuresLastEnvelopeOk = nil
                    featuresLastEnvelopeSource = "cache"
                    updateFeaturesDiagnostics(from: nil, fallback: true)
                    appLog("[UI] features updated from cache change day=\(decoded.day)")
                }
            }
            .onChange(of: spaceVisualsCacheJSON, initial: false) { oldValue, newValue in
                guard newValue != oldValue, !newValue.isEmpty, let decoded = decodeSpaceVisuals(from: newValue) else { return }
                lastKnownSpaceVisuals = decoded
                if spaceVisuals == nil {
                    spaceVisuals = decoded
                    appLog("[UI] space visuals updated from cache change")
                }
            }
            .onChange(of: spaceOutlookCacheJSON, initial: false) { oldValue, newValue in
                guard newValue != oldValue, !newValue.isEmpty, let decoded = decodeSpaceOutlook(from: newValue) else { return }
                lastKnownSpaceOutlook = decoded
                if spaceOutlook == nil {
                    spaceOutlook = decoded
                    appLog("[UI] space outlook updated from cache change")
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .featuresShouldRefresh).receive(on: RunLoop.main)) { _ in
                pendingRefreshTask?.cancel()
                pendingRefreshToken &+= 1
                let token = pendingRefreshToken
                pendingRefreshTask = Task {
                    do {
                        try await Task.sleep(nanoseconds: 1_000_000_000)
                    } catch {
                        return
                    }
                    if Task.isCancelled { return }
                    await state.updateBackendDBFlag()
                    let backendAvailable = await MainActor.run { state.backendDBAvailable }
                    guard backendAvailable else {
                        appLog("[UI] refresh skipped; backend DB=false")
                        await MainActor.run {
                            state.append("[BG] refresh blocked: backend DB unavailable")
                            if pendingRefreshToken == token {
                                pendingRefreshTask = nil
                            }
                        }
                        return
                    }
                    await fetchFeaturesToday(trigger: .upload)
                    await MainActor.run {
                        if pendingRefreshToken == token {
                            pendingRefreshTask = nil
                        }
                    }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("AppLogLine")).receive(on: RunLoop.main)) { note in
                guard let line = note.object as? String else { return }
                let now = Date()
                // Drop if any line was appended in the last 0.30s to avoid UI reflow storms
                if now.timeIntervalSince(state.lastLogAppendAt) < 0.30 { return }
                // De-dup immediate repeats
                if let last = state.log.last, last == line { return }
                state.log.append(line)
                state.lastLogAppendAt = now
                // Keep only the last 300 lines to minimize layout cost
                if state.log.count > 300 {
                    state.log.removeFirst(state.log.count - 300)
                }
            }
            .toolbar {
                ToolbarItem(placement: .principal) {
                    VStack(spacing: 0) { Text("Gaia Eyes").font(.title2).fontWeight(.semibold); Text("Decode the unseen.").font(.footnote).foregroundColor(.secondary).padding(.top, 1) }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { showDebug.toggle() } label: { Image(systemName: "wrench.and.screwdriver") }.accessibilityLabel("Toggle Debug Panel")
                }
            }
            .onDisappear {
                pendingRefreshTask?.cancel()
                pendingRefreshTask = nil
            }
        }
        .sheet(isPresented: $showSymptomSheet) {
            SymptomsLogSheet(
                presets: symptomPresets,
                queuedCount: state.symptomQueueCount,
                isOffline: isSymptomServiceOffline,
                isSubmitting: $isSubmittingSymptom,
                onSubmit: { event in
                    isSubmittingSymptom = true
                    Task {
                        let shouldDismiss = await logSymptomEvent(event)
                        await MainActor.run { isSubmittingSymptom = false; if shouldDismiss { showSymptomSheet = false } }
                    }
                }
            )
        }
        .fullScreenCover(isPresented: $showInteractiveViewer) {
            if let item = interactiveVisualItem {
                VisualsInteractiveViewer(
                    item: item,
                    baseURL: interactiveBaseURL,
                    overlaySeries: interactiveOverlaySeries,
                    onClose: {
                        showInteractiveViewer = false
                        interactiveVisualItem = nil
                    }
                )
                .ignoresSafeArea()
            }
        }
    }
    
    
    // Resolve MEDIA_BASE_URL from Info.plist; default to Supabase public bucket
    private func appMediaBaseURL() -> URL? {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
            let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
        }
        return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
    }
    private func appResolveMediaURL(_ path: String?) -> URL? {
        guard let s = path?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
        if let u = URL(string: s), u.scheme != nil { return u }
        guard let base = appMediaBaseURL() else { return URL(string: s) }
        return URL(string: s.hasPrefix("/") ? String(s.dropFirst()) : s, relativeTo: base)
    }

    // MARK: - Subviews
    
    private struct SymptomSparkPoint: Identifiable {
        let id: Date
        let date: Date
        let events: Int
        let meanSeverity: Double?
        
        init(date: Date, events: Int, meanSeverity: Double?) {
            self.id = date
            self.date = date
            self.events = events
            self.meanSeverity = meanSeverity
        }
    }
    
    private struct SymptomHighlight: Identifiable {
        let id = UUID()
        let date: Date
        let events: Int
    }
    
    private struct SymptomPreset: Identifiable, Hashable {
        let id: String
        let code: String
        let label: String
        let systemImage: String
        let tags: [String]?
        
        init(code: String, label: String, systemImage: String? = nil, tags: [String]? = nil) {
            let normalizedCode = normalize(code)
            self.id = normalizedCode
            self.code = normalizedCode
            self.label = label
            self.systemImage = systemImage ?? SymptomPreset.defaultSystemImage(for: normalizedCode)
            self.tags = tags
        }
        
        init(definition: SymptomCodeDefinition) {
            let normalizedCode = normalize(definition.symptomCode)
            id = normalizedCode
            code = normalizedCode
            let trimmedLabel = definition.label.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedLabel.isEmpty {
                label = normalizedCode.replacingOccurrences(of: "_", with: " ").capitalized
            } else {
                label = trimmedLabel
            }
            let icon = definition.systemImage?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            systemImage = icon.isEmpty ? SymptomPreset.defaultSystemImage(for: normalizedCode) : icon
            tags = definition.tags
        }
        
        private static func defaultSystemImage(for code: String) -> String {
            switch code {
            case "NERVE_PAIN": return "bolt.heart"
            case "ZAPS": return "bolt"
            case "DRAINED": return "battery.25"
            case "HEADACHE": return "brain.head.profile"
            case "ANXIOUS": return "exclamationmark.triangle"
            case "INSOMNIA": return "moon.zzz"
            default: return "ellipsis"
            }
        }
        
        static func fromDefinitions(_ definitions: [SymptomCodeDefinition]) -> [SymptomPreset] {
            var seen: Set<String> = []
            let mapped = definitions.filter { $0.isActive }.compactMap { definition -> SymptomPreset? in
                let preset = SymptomPreset(definition: definition)
                if seen.insert(preset.code).inserted {
                    return preset
                }
                return nil
            }
            return ensureFallback(in: mapped)
        }
        
        static func ensureFallback(in presets: [SymptomPreset]) -> [SymptomPreset] {
            var filtered = presets.filter { $0.code != SymptomCodeHelper.fallbackCode }
            if let existing = presets.first(where: { $0.code == SymptomCodeHelper.fallbackCode }) {
                filtered.append(existing)
            } else {
                filtered.append(SymptomPreset(code: SymptomCodeHelper.fallbackCode, label: "Other", systemImage: "ellipsis"))
            }
            return filtered
        }
        
        static let defaults: [SymptomPreset] = ensureFallback(in: [
            SymptomPreset(code: "NERVE_PAIN", label: "Nerve pain", systemImage: "bolt.heart"),
            SymptomPreset(code: "ZAPS", label: "Zaps", systemImage: "bolt"),
            SymptomPreset(code: "DRAINED", label: "Drained", systemImage: "battery.25"),
            SymptomPreset(code: "HEADACHE", label: "Headache", systemImage: "brain.head.profile"),
            SymptomPreset(code: "ANXIOUS", label: "Anxious", systemImage: "exclamationmark.triangle"),
            SymptomPreset(code: "INSOMNIA", label: "Insomnia", systemImage: "moon.zzz"),
            SymptomPreset(code: "OTHER", label: "Other", systemImage: "ellipsis")
        ])
    }
    
    @available(iOS 16.0, *)
    private struct SymptomSparklineView: View {
        let points: [SymptomSparkPoint]
        
        private func severityColor(_ value: Double) -> Color {
            let clamped = max(1.0, min(5.0, value))
            let t = (clamped - 1.0) / 4.0
            return Color(red: 0.2 + 0.6 * t, green: 0.8 - 0.6 * t, blue: 0.3)
        }
        
        private var gradient: LinearGradient? {
            guard points.count > 1 else { return nil }
            let stops = points.enumerated().compactMap { index, point -> Gradient.Stop? in
                guard let severity = point.meanSeverity else { return nil }
                let location = Double(index) / Double(points.count - 1)
                return Gradient.Stop(color: severityColor(severity), location: location)
            }
            guard stops.count >= 2 else { return nil }
            return LinearGradient(gradient: Gradient(stops: stops), startPoint: .leading, endPoint: .trailing)
        }
        
        var body: some View {
            if points.isEmpty {
                Text("No symptom entries yet")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Chart {
                    ForEach(points) { point in
                        LineMark(x: .value("Day", point.date), y: .value("Events", point.events))
                            .interpolationMethod(.catmullRom)
                            .foregroundStyle(Color.accentColor)
                        AreaMark(x: .value("Day", point.date), y: .value("Events", point.events))
                            .interpolationMethod(.catmullRom)
                            .foregroundStyle(Color.accentColor.opacity(0.18))
                        if let severity = point.meanSeverity {
                            PointMark(x: .value("Day", point.date), y: .value("Events", point.events))
                                .foregroundStyle(severityColor(severity))
                                .symbolSize(30)
                        }
                    }
                }
                .chartYAxis { AxisMarks(preset: .automatic, position: .leading) }
                .frame(height: 120)
                .background {
                    if let gradient {
                        gradient
                            .opacity(0.28)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
        }
    }
    
    private struct SymptomsTileView: View {
        let todayCount: Int
        let queuedCount: Int
        let sparklinePoints: [SymptomSparkPoint]
        let topSummary: String?
        let onLogTap: () -> Void
        
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Button(action: onLogTap) {
                            Label("Log a symptom", systemImage: "plus.circle.fill")
                                .labelStyle(.titleAndIcon)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        
                        Spacer()
                        
                        VStack(alignment: .trailing, spacing: 4) {
                            Text("Today: \(todayCount)")
                                .font(.headline)
                            if queuedCount > 0 {
                                Text("Queued: \(queuedCount)")
                                    .font(.caption2)
                                    .foregroundColor(.orange)
                            }
                        }
                    }
                    
                    if let topSummary {
                        Text(topSummary)
                            .font(.footnote)
                            .foregroundColor(.secondary)
                    }
                    
                    if #available(iOS 16.0, *) {
                        SymptomSparklineView(points: sparklinePoints)
                    } else {
                        Text("Sparkline requires iOS 16+")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                HStack {
                    Image(systemName: "waveform.path.ecg")
                    Text("Symptoms")
                }
            }
        }
    }

    // Renders a small grid of the latest space visuals using relative URLs resolved via Info.plist MEDIA_BASE_URL
    private struct VisualsPreviewGrid: View {
        let visuals: SpaceVisualsPayload
        /// Optional cap on number of thumbnails (nil = unlimited)
        var maxCount: Int? = 24
        /// Called when a SpaceVisualItem is selected (if present in payload)
        var onSelect: ((SpaceVisualItem) -> Void)? = nil

        private struct Thumb: Identifiable {
            let id = UUID()
            let title: String
            let credit: String?
            let capturedAtISO: String?
            let urlString: String
            let isVideo: Bool
            let item: SpaceVisualItem?
        }

        // Read MEDIA_BASE_URL from Info.plist and normalize (no trailing slash)
        private var legacyMediaBaseURL: URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
            }
            // Hard fallback to Supabase public bucket base so tiles render even if Info.plist is missing/mis-targeted
            return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
        }

        @State private var previewPlayingURL: URL? = nil
        @State private var previewShowPlayer: Bool = false

        // Resolve either absolute or relative paths (e.g., "/drap/latest.png") to a full URL
        private func resolveMediaURL(_ path: String?) -> URL? {
            guard let s = path?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
            if let u = URL(string: s), u.scheme != nil { return u }  // already absolute
            guard let base = legacyMediaBaseURL else { return URL(string: s) }
            return URL(string: s, relativeTo: base)
        }

        private func normalizedKey(_ s: String) -> String {
            s.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        }
        private func normalizedRelURL(_ s: String) -> String {
            if let u = URL(string: s), let host = u.host, !host.isEmpty {
                var path = u.path.isEmpty ? s : u.path
                if path.hasPrefix("/") { path.removeFirst() }
                return path.lowercased()
            }
            return s.trimmingCharacters(in: CharacterSet(charactersIn: "/")).lowercased()
        }

        // Build thumbnails from visuals.items ∪ visuals.images; de-duplicate by id and URL
        private var thumbs: [Thumb] {
            var collected: [Thumb] = []
            var seenIds = Set<String>()
            var seenUrls = Set<String>()

            // 1) Items first (preferred for interactive viewer)
            if let items = visuals.items {
                for item in items {
                    guard let path = item.url, !path.isEmpty else { continue }
                    let isVideo = path.lowercased().hasSuffix(".mp4") || path.lowercased().contains(".mp4?")
                    let idKey = normalizedKey(item.id ?? item.title ?? path)
                    let urlKey = normalizedRelURL(path)
                    if seenIds.contains(idKey) || seenUrls.contains(urlKey) { continue }
                    seenIds.insert(idKey); seenUrls.insert(urlKey)
                    collected.append(
                        Thumb(
                            title: item.title ?? item.id ?? "Visual",
                            credit: item.credit,
                            capturedAtISO: nil,
                            urlString: path,
                            isVideo: isVideo,
                            item: item
                        )
                    )
                }
            }

            // 2) Then images, skipping anything already covered by items
            let fmt = ISO8601DateFormatter()
            let imagesSorted = (visuals.images ?? []).sorted { a, b in
                guard let ia = a.capturedAt, let da = fmt.date(from: ia),
                      let ib = b.capturedAt, let db = fmt.date(from: ib) else {
                    return (a.key ?? "") > (b.key ?? "")
                }
                return da > db
            }
            let itemByKey: [String: SpaceVisualItem] = {
                var map: [String: SpaceVisualItem] = [:]
                for it in visuals.items ?? [] {
                    let k = normalizedKey(it.id ?? it.title ?? "")
                    if !k.isEmpty { map[k] = it }
                }
                return map
            }()

            for img in imagesSorted {
                guard let path = img.url, !path.isEmpty else { continue }
                let urlKey = normalizedRelURL(path)
                if seenUrls.contains(urlKey) { continue }

                let titleKey = normalizedKey(img.key ?? img.caption ?? path)
                let mappedItem = itemByKey[titleKey]
                let isVideo = path.lowercased().hasSuffix(".mp4") || path.lowercased().contains(".mp4?")
                seenUrls.insert(urlKey)
                if let k = (img.key ?? img.caption), !k.isEmpty { seenIds.insert(normalizedKey(k)) }

                collected.append(
                    Thumb(
                        title: img.key ?? "Visual",
                        credit: img.credit,
                        capturedAtISO: img.capturedAt,
                        urlString: path,
                        isVideo: isVideo,
                        item: mappedItem
                    )
                )
            }

            // 3) Ensure ENLIL tile appears even if API didn't include it (temporary baseline)
            let enlilUrlKey = normalizedRelURL("/nasa/enlil/latest.mp4")
            if !seenUrls.contains(enlilUrlKey) && !seenIds.contains("enlil_cme") {
                collected.insert(
                    Thumb(
                        title: "ENLIL CME Propagation",
                        credit: "NOAA/WSA–ENLIL+Cone",
                        capturedAtISO: nil,
                        urlString: "/nasa/enlil/latest.mp4",
                        isVideo: true,
                        item: nil
                    ),
                    at: 0
                )
                seenUrls.insert(enlilUrlKey)
            }

            if let cap = maxCount { return Array(collected.prefix(cap)) }
            return collected
        }

        private func shortCapture(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let inFmt = ISO8601DateFormatter()
            let outFmt = DateFormatter(); outFmt.dateStyle = .short; outFmt.timeStyle = .short
            if let d = inFmt.date(from: iso) { return outFmt.string(from: d) }
            return nil
        }

        var body: some View {
            let items = thumbs
            if items.isEmpty {
                Text("No visuals yet. Check again soon.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                let cols = [GridItem(.adaptive(minimum: 140), spacing: 12)]
                LazyVGrid(columns: cols, spacing: 12) {
                    ForEach(items) { t in
                        VStack(alignment: .leading, spacing: 6) {
                            if let u = resolveMediaURL(t.urlString) {
                                if t.isVideo {
                                    ZStack {
                                        Rectangle().opacity(0.08)
                                        Image(systemName: "play.circle.fill").font(.system(size: 36))
                                    }
                                    .frame(height: 120)
                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                                } else {
                                    AsyncImage(url: u) { phase in
                                        switch phase {
                                        case .empty:
                                            ZStack { Rectangle().opacity(0.08); ProgressView().scaleEffect(0.9) }
                                                .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                        case .success(let image):
                                            image
                                                .resizable()
                                                .scaledToFill()
                                                .frame(height: 120)
                                                .clipped()
                                                .clipShape(RoundedRectangle(cornerRadius: 10))
                                        case .failure:
                                            ZStack { Rectangle().opacity(0.08); Image(systemName: "exclamationmark.triangle").foregroundColor(.secondary) }
                                                .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                        @unknown default:
                                            EmptyView().frame(height: 120)
                                        }
                                    }
                                }
                            } else {
                                ZStack { Rectangle().opacity(0.08); Image(systemName: "questionmark").foregroundColor(.secondary) }
                                    .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                            }
                            HStack {
                                Text(t.title).font(.footnote).lineLimit(1)
                                Spacer()
                                if let ts = shortCapture(t.capturedAtISO) {
                                    Text(ts).font(.caption2).foregroundColor(.secondary)
                                }
                            }
                            if let c = t.credit, !c.isEmpty {
                                Text(c).font(.caption2).foregroundColor(.secondary).lineLimit(1)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            if let item = t.item {
                                onSelect?(item)                 // open VisualsInteractiveViewer
                            } else if let u = resolveMediaURL(t.urlString) {
                                if t.isVideo {
                                    // fallback player when no item to pass upstream
                                    previewPlayingURL = u
                                    previewShowPlayer = true
                                } else {
                                    // synthesize minimal item so the parent viewer can open
                                    let tmp = SpaceVisualItem(
                                        id: t.title,
                                        title: t.title,
                                        credit: t.credit,
                                        url: t.urlString,
                                        meta: nil,
                                        series: nil
                                    )
                                    onSelect?(tmp)
                                }
                            }
                        }
                    }
                }
                .sheet(isPresented: $previewShowPlayer) {
                    if let url = previewPlayingURL {
                        VideoPlayer(player: AVPlayer(url: url)).ignoresSafeArea()
                    }
                }
            }
        }
    }

    private struct SymptomToastView: View {
        let message: String
        
        var body: some View {
            Text(message)
                .font(.footnote)
                .padding(.vertical, 8)
                .padding(.horizontal, 18)
                .background(.ultraThinMaterial, in: Capsule())
                .shadow(radius: 3)
        }
    }
    
    private struct SymptomsLogSheet: View {
        @Environment(\.dismiss) private var dismiss
        
        let presets: [SymptomPreset]
        let queuedCount: Int
        let isOffline: Bool
        @Binding var isSubmitting: Bool
        let onSubmit: (SymptomQueuedEvent) -> Void
        
        @State private var selectedPreset: SymptomPreset?
        @State private var includeSeverity: Bool = false
        @State private var severityValue: Double = 3
        @State private var freeText: String = ""
        @FocusState private var notesFocused: Bool
        
        private var trimmedFreeText: String {
            freeText.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        
        private var isSubmitDisabled: Bool {
            (selectedPreset == nil && trimmedFreeText.isEmpty) || isSubmitting
        }
        
        var body: some View {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        if queuedCount > 0 {
                            Text("\(queuedCount) symptom(s) waiting to send")
                                .font(.caption)
                                .foregroundColor(.orange)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(8)
                                .background(Color.orange.opacity(0.1))
                                .cornerRadius(8)
                        }
                        
                        if isOffline {
                            Label("Temporarily offline — showing last known symptoms.", systemImage: "wifi.slash")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        
                        Text("Choose a symptom")
                            .font(.headline)
                        
                        let columns = [GridItem(.adaptive(minimum: 110), spacing: 12)]
                        LazyVGrid(columns: columns, spacing: 12) {
                            ForEach(presets) { preset in
                                Button {
                                    if selectedPreset == preset {
                                        selectedPreset = nil
                                        includeSeverity = false
                                    } else {
                                        selectedPreset = preset
                                    }
                                } label: {
                                    VStack(spacing: 8) {
                                        Image(systemName: preset.systemImage)
                                            .font(.title2)
                                        Text(preset.label)
                                            .font(.subheadline)
                                    }
                                    .frame(maxWidth: .infinity, minHeight: 70)
                                }
                                .buttonStyle(.bordered)
                                .tint(selectedPreset == preset ? .accentColor : .secondary)
                            }
                        }
                        
                        if let preset = selectedPreset {
                            Divider()
                            
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Details for \(preset.label)")
                                    .font(.headline)
                                
                                Toggle("Include severity", isOn: $includeSeverity.animation())
                                    .tint(.accentColor)
                                
                                if includeSeverity {
                                    VStack(alignment: .leading) {
                                        Slider(value: $severityValue, in: 1...5, step: 1) {
                                            Text("Severity")
                                        } minimumValueLabel: {
                                            Text("1")
                                        } maximumValueLabel: {
                                            Text("5")
                                        }
                                        Text("Selected: \(Int(severityValue))")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                
                                TextField("Optional notes", text: $freeText, axis: .vertical)
                                    .textFieldStyle(.roundedBorder)
                                    .lineLimit(2...4)
                                    .focused($notesFocused)
                            }
                        }
                    }
                    .padding()
                }
                .navigationTitle("Log Symptom")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { dismiss() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Save") {
                            let code = selectedPreset?.code ?? SymptomCodeHelper.fallbackCode
                            var event = SymptomQueuedEvent(symptomCode: code)
                            if includeSeverity { event.severity = Int(severityValue) }
                            if !trimmedFreeText.isEmpty { event.freeText = trimmedFreeText }
                            if let tags = selectedPreset?.tags { event.tags = tags }
                            onSubmit(event)
                        }
                        .disabled(isSubmitDisabled)
                    }
                }
            }
            .interactiveDismissDisabled(isSubmitting)
            .onDisappear {
                includeSeverity = false
                severityValue = 3
                freeText = ""
                notesFocused = false
                selectedPreset = nil
            }
        }
    }
    
    private struct ConnectionSettingsSection: View {
        @ObservedObject var state: AppState
        @Binding var isExpanded: Bool
        
        var body: some View {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(spacing: 8) {
                    TextField("Base URL (e.g. https://gaiaeyes-backend.onrender.com)", text: $state.baseURLString)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)

                    TextField("Bearer (e.g. devtoken123)", text: $state.bearer)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)

                    TextField("User ID (UUID)", text: $state.userId)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)

                    Button {
                        state.applyDeveloperCredentials()
                    } label: {
                        Label("Use Developer Credentials", systemImage: "key.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)

                    if state.developerCredentialsAreMissingUserId {
                        Label {
                            Text("Developer bearer requests need X-Dev-UserId. Tap the button above to populate the recommended test user.")
                        } icon: {
                            Image(systemName: "exclamationmark.triangle.fill")
                        }
                        .foregroundColor(.orange)
                        .font(.footnote)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding(.top, 6)
            } label: {
                HStack {
                    Image(systemName: "network")
                    Text("Connection Settings")
                    Spacer()
                    if !isExpanded { Text("Hidden").foregroundColor(.secondary).font(.footnote) }
                }
            }
            .padding(.horizontal)
        }
    }
    
    private struct ActionsSection: View {
        @ObservedObject var state: AppState
        var onFetchVisuals: (() -> Void)? = nil
        
        var body: some View {
            VStack(spacing: 12) {
                Button {
                    Task { await state.requestHealthPermissions() }
                } label: { Text("Request Health Permissions").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .padding(.horizontal)
                
                Button {
                    Task { await state.pingAPI() }
                } label: { Text("Ping API").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .padding(.horizontal)

                Button {
                    onFetchVisuals?()
                } label: { Text("Fetch Visuals (Diag)").frame(maxWidth: .infinity) }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .padding(.horizontal)
                
                HStack {
                    Button { Task { await state.syncSteps7d() } } label: { Text("Sync Steps (7d)").frame(maxWidth: .infinity) }
                    Button { Task { await state.syncHR7d() } }    label: { Text("Sync HR (7d)").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
                
                HStack {
                    Button { Task { await state.syncHRV7d() } } label: { Text("Sync HRV (7d)").frame(maxWidth: .infinity) }
                    Button { Task { await state.syncSpO27d() } } label: { Text("Sync SpO₂ (7d)").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
                
                HStack {
                    Button { Task { await state.syncBP30d() } } label: { Text("Sync BP (30d)").frame(maxWidth: .infinity) }
                    Button { Task { await state.syncSleep7d() } } label: { Text("Sync Sleep (7d)").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
            }
        }
    }
    
    private struct StatusSection: View {
        @ObservedObject var state: AppState
        
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 6) {
                    if state.statusLines.isEmpty {
                        Text("No status yet").foregroundColor(.secondary)
                    } else {
                        ForEach(Array(state.statusLines.enumerated()), id: \.offset) { _, row in
                            Text(row)
                                .font(.footnote)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    HStack {
                        Button("Refresh Status") { state.refreshStatus() }
                        Spacer()
                        Button("Copy") {
#if canImport(UIKit)
                            UIPasteboard.general.string = state.statusLines.joined(separator: "\n")
#endif
                        }
                    }
                }
                .padding(.vertical, 4)
            } label: {
                Text("Status")
            }
            .padding(.horizontal)
        }
    }
    
    private struct BleStatusSection: View {
        @ObservedObject var state: AppState
        
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Device: \(state.bleConnected?.name ?? "Not connected")")
                        .font(.footnote)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    HStack(spacing: 16) {
                        Text("Last BPM: \(state.lastBPM.map(String.init) ?? "-")")
                        let rrText = state.lastRRTime.map {
                            DateFormatter.localizedString(from: $0, dateStyle: .none, timeStyle: .short)
                        } ?? "-"
                        Text("Last RR: \(rrText)")
                    }
                    .font(.footnote)
                    
                    HStack(spacing: 12) {
                        if state.bleConnected != nil {
                            Button("Disconnect") { state.disconnectBle() }
                                .buttonStyle(.bordered)
                        } else {
                            NavigationLink(destination: BleSettingsView(app: state)) {
                                Text("Scan & Connect")
                            }
                            .buttonStyle(.bordered)
                        }
                        
                        Spacer()
                        
                        Toggle("Auto-upload", isOn: $state.bleAutoUpload)
                            .labelsHidden()
                            .toggleStyle(.switch)
                    }
                }
                .padding(.vertical, 4)
            } label: {
                Text("BLE Sensor")
            }
            .padding(.horizontal)
        }
    }
    
    // MARK: - Placeholder Cards (temporary stubs to satisfy build)
    private struct HealthStatsCard: View {
        let steps: Int
        let hrMin: Int
        let hrMax: Int
        let hrvAvg: Int
        let spo2Avg: Double?
        let bpSys: Int
        let bpDia: Int

        /// Formats SpO₂ for display; tolerates 0–1.0 fractions and filters obvious outliers.
        private func formattedSpO2() -> String {
            guard let v = spo2Avg else { return "-" }
            // Normalize if backend sent fraction (e.g., 0.97 -> 97%)
            let n = (v > 0 && v <= 1.0) ? (v * 100.0) : v
            // Filter implausible values; clamp to 100
            if n < 60 { return "-" }
            return String(format: "%.0f%%", min(100.0, n))
        }

        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Health Stats").font(.headline)
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Steps: \(steps)")
                            Text("HR Min: \(hrMin)  Max: \(hrMax)")
                            Text("HRV Avg: \(hrvAvg)")
                        }
                        Spacer()
                        VStack(alignment: .leading) {
                            Text("SpO₂ Avg: \(formattedSpO2())")
                            Text("BP Avg: \(bpSys)/\(bpDia)")
                        }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Health", systemImage: "heart.fill") }
        }
    }

    private struct SpaceStatRow: View {
        let title: String
        let subtitle: String
        let badge: String?
        let icon: String
        let action: () -> Void

        var body: some View {
            Button(action: action) {
                HStack(alignment: .center, spacing: 10) {
                    Image(systemName: icon)
                        .foregroundColor(.accentColor)
                        .frame(width: 20)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title)
                            .font(.subheadline)
                            .foregroundColor(.primary)
                        Text(subtitle)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }
                    Spacer()
                    if let badgeText = badge {
                        Text(badgeText)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.12))
                            .cornerRadius(12)
                    }
                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }

    private struct SpaceWeatherCard: View {
        let kpMax: Int
        let kpCurrent: Double?
        let bzMin: Double?
        let swSpeedAvg: Double?
        let flares: Int
        let cmes: Int
        let schStation: String?
        let schF0: Double?
        let schF1: Double?
        let schF2: Double?
        let auroraProbability: String?
        let auroraPower: Double?
        let overlayCount: Int
        let overlayUpdated: String?
        let earthquakeCount: Int?
        let earthquakeMaxMag: Double?
        let onOpenDetail: (SpaceDetailSection) -> Void
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Space Weather").font(.headline)
                    Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
                        GridRow { Text("Kp Max"); Text("\(kpMax)") }
                        GridRow { Text("Kp Now"); Text(kpCurrent.map { String(format: "%.1f", $0) } ?? "-") }
                        GridRow { Text("Bz Min"); Text(bzMin.map { String(format: "%.1f nT", $0) } ?? "-") }
                        GridRow { Text("SW Speed"); Text(swSpeedAvg.map { String(format: "%.0f km/s", $0) } ?? "-") }
                        GridRow { Text("Flares"); Text("\(flares)") }
                        GridRow { Text("CMEs"); Text("\(cmes)") }
                        GridRow { Text("Schumann"); Text("\(schStation ?? "-")  f0 \(schF0.map { String(format: "%.2f", $0) } ?? "-")") }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                    Divider()
                    VStack(spacing: 8) {
                        SpaceStatRow(
                            title: "Aurora",
                            subtitle: "Kp \(kpMax) · Power \(auroraPower.map { String(format: "%.1f GW", $0) } ?? "–")",
                            badge: auroraProbability,
                            icon: "sparkles",
                            action: { onOpenDetail(.aurora) }
                        )
                        SpaceStatRow(
                            title: "Solar Visuals",
                            subtitle: "\(overlayCount) overlays · \(overlayUpdated ?? "Latest unknown")",
                            badge: nil,
                            icon: "photo.on.rectangle",
                            action: { onOpenDetail(.visuals) }
                        )
                        SpaceStatRow(
                            title: "Earthquakes",
                            subtitle: quakeSubtitle,
                            badge: nil,
                            icon: "waveform.path",
                            action: { onOpenDetail(.earthquakes) }
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Space", systemImage: "sparkles") }
        }

        private var quakeSubtitle: String {
            let countText: String
            if let count = earthquakeCount {
                countText = count == 1 ? "1 quake" : "\(count) quakes"
            } else {
                countText = "Quakes"
            }
            if let mag = earthquakeMaxMag {
                return "\(countText) · max M\(String(format: "%.1f", mag))"
            }
            return countText
        }
    }

    private struct SpaceWeatherDetailView: View {
        let features: FeaturesToday?
        let visuals: SpaceVisualsPayload?
        let outlook: SpaceForecastOutlook?
        let series: SpaceSeries?
        let initialSection: SpaceDetailSection?

        @Environment(\.dismiss) private var dismiss
        @State private var selectedSection: SpaceDetailSection = .aurora
        @State private var sourceFilter: String = "all"
        @State private var showSeriesOverlay: Bool = true
        @State private var showCredits: Bool = false
        @State private var detailPlayingURL: URL? = nil
        @State private var detailShowPlayer: Bool = false

        private var overlayImages: [SpaceVisualImage] {
            let imgs = visuals?.images ?? []
            let filtered = imgs.filter { img in
                let key = img.key?.lowercased() ?? ""
                if key.contains("tomsk") { return false }
                if sourceFilter == "all" { return true }
                let source = img.source?.lowercased() ?? key
                return source.contains(sourceFilter)
            }
            let fmt = ISO8601DateFormatter()
            return filtered.sorted { a, b in
                guard let ta = a.capturedAt.flatMap({ fmt.date(from: $0) }),
                      let tb = b.capturedAt.flatMap({ fmt.date(from: $0) }) else { return (a.key ?? "") < (b.key ?? "") }
                return ta > tb
            }
        }

        private var overlaySeriesSummaries: [String] {
            (visuals?.series ?? []).compactMap { series in
                let name = series.label ?? series.name ?? "Series"
                let latest = series.latestValue.map { String(format: "%.2f", $0) } ?? "–"
                if let unit = series.unit, !unit.isEmpty {
                    return "\(name): \(latest) \(unit)"
                }
                return "\(name): \(latest)"
            }
        }

        // MARK: - Media Resolution (match dashboard preview behavior)
        private var mediaBaseURL_Detail: URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
            }
            // Hard fallback to Supabase bucket base
            return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
        }
        private var legacyMediaBaseURL_Detail: URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "LEGACY_MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
            }
            return URL(string: "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main")
        }
        private func resolveMediaURL_Detail(_ path: String?) -> URL? {
            guard let raw0 = path?.trimmingCharacters(in: .whitespacesAndNewlines), !raw0.isEmpty else { return nil }
            if let u = URL(string: raw0), u.scheme != nil { return u }
            var s = raw0.hasPrefix("/") ? raw0 : "/" + raw0
            // Short-key mapping
            if !s.contains("/") || (s.first == "/" && !s.dropFirst().contains("/")) {
                let key = s.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                let map: [String: String] = [
                    // DRAP
                    "drap": "/drap/latest.png",
                    "drap_global": "/drap/latest.png",
                    "drap_n_pole": "/drap/latest.png",
                    "drap_s_pole": "/drap/latest.png",
                    // NASA AIA / LASCO / HMI / SOHO
                    "aia_primary": "/nasa/aia_304/latest.jpg",
                    "aia_304": "/nasa/aia_304/latest.jpg",
                    "lasco_c2": "/nasa/lasco_c2/latest.jpg",
                    "soho_c2": "/nasa/lasco_c2/latest.jpg",
                    "ccor1_jpeg": "/nasa/lasco_c2/latest.jpg",
                    "hmi_intensity": "/nasa/hmi_intensity/latest.jpg",
                    "enlil": "/nasa/enlil/latest.mp4",
                    "enlil_cme": "/nasa/enlil/latest.mp4",
                    // Aurora aliases
                    "a_station": "/aurora/viewline/tonight-north.png",
                    "ovation_nh": "/aurora/viewline/tonight-north.png",
                    "ovation_sh": "/aurora/viewline/tonight-south.png",
                    // SWPC overview placeholder
                    "swx_overview_small": "/nasa/aia_304/latest.jpg"
                ]
                if let mapped = map[key] { s = mapped }
                // Cumiana short keys → legacy GitHub path until Supabase upload exists
                if map[key] == nil, key.hasPrefix("cumiana") {
                    s = "/images/space/\(key).png"
                }
            }
            func join(base: URL, path: String) -> URL {
                let rel = path.hasPrefix("/") ? String(path.dropFirst()) : path
                return rel.split(separator: "/").reduce(base) { url, seg in url.appendingPathComponent(String(seg)) }
            }
            if s.hasPrefix("/images/space/") {
                if let base = legacyMediaBaseURL_Detail { return join(base: base, path: s) }
                return URL(string: s)
            }
            if let base = mediaBaseURL_Detail { return join(base: base, path: s) }
            return URL(string: s)
        }

        private var outlookSections: [SpaceOutlookSection] { outlook?.sections ?? [] }

        private func outlookEntries(containing keywords: [String]) -> [SpaceOutlookEntry] {
            let lower = keywords.map { $0.lowercased() }
            return outlookSections.flatMap { section in
                let key = section.title.lowercased()
                let sectionMatch = lower.contains(where: { key.contains($0) })
                let entries = section.entries.filter { entry in
                    guard !sectionMatch else { return true }
                    let text = (entry.title ?? entry.summary ?? entry.driver ?? "").lowercased()
                    return lower.contains(where: { text.contains($0) })
                }
                return sectionMatch ? section.entries : entries
            }
        }

        private var outlookNotes: [String] { outlook?.notes ?? [] }

        private var auroraPowerText: String {
            if let power = features?.auroraPowerGw?.value ?? features?.auroraPowerNhGw?.value ?? features?.auroraPowerShGw?.value {
                return String(format: "%.1f GW", power)
            }
            if let latest = visuals?.series?.first(where: { ($0.name ?? $0.label ?? "").lowercased().contains("aurora") })?.latestValue {
                return String(format: "%.1f GW", latest)
            }
            return "–"
        }

        private func formattedCapture(_ iso: String?) -> String {
            guard let iso else { return "" }
            let fmt = ISO8601DateFormatter()
            guard let d = fmt.date(from: iso) else { return "" }
            let out = DateFormatter()
            out.dateStyle = .short
            out.timeStyle = .short
            return out.string(from: d)
        }

        private func formattedOutlookWindow(start: String?, end: String?) -> String? {
            let fmt = ISO8601DateFormatter()
            fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let fallbackFmt = ISO8601DateFormatter()
            let short = DateFormatter()
            short.dateStyle = .short
            short.timeStyle = .short
            if let start, let ds = fmt.date(from: start) ?? fallbackFmt.date(from: start), let end, let de = fmt.date(from: end) ?? fallbackFmt.date(from: end) {
                return "\(short.string(from: ds)) → \(short.string(from: de))"
            }
            if let start, let ds = fmt.date(from: start) ?? fallbackFmt.date(from: start) {
                return short.string(from: ds)
            }
            if let end, let de = fmt.date(from: end) ?? fallbackFmt.date(from: end) {
                return short.string(from: de)
            }
            return nil
        }

        private func outlookMetaParts(_ entry: SpaceOutlookEntry) -> [String] {
            var metaParts: [String] = []
            if let window = formattedOutlookWindow(start: entry.windowStart, end: entry.windowEnd) { metaParts.append(window) }
            if let region = entry.region { metaParts.append(region) }
            if let value = entry.value {
                if let metric = entry.metric, let unit = entry.unit {
                    metaParts.append("\(metric): \(String(format: "%.1f", value)) \(unit)")
                } else if let unit = entry.unit {
                    metaParts.append(String(format: "%.1f %@", value, unit))
                }
            }
            if let conf = entry.confidence { metaParts.append(conf) }
            if let source = entry.source { metaParts.append(source) }
            return metaParts
        }

        @ViewBuilder
        private func outlookEntryRow(_ entry: SpaceOutlookEntry) -> some View {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(entry.title ?? entry.driver ?? "Forecast")
                        .font(.subheadline)
                    if let severity = entry.severity { Text(severity.capitalized).font(.caption2).foregroundColor(.secondary) }
                    if let prob = entry.probability {
                        Text(String(format: "%.0f%%", prob)).font(.caption2).foregroundColor(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.1))
                            .cornerRadius(8)
                    }
                }
                if let summary = entry.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                let metaParts = outlookMetaParts(entry)
                if !metaParts.isEmpty {
                    Text(metaParts.joined(separator: " · "))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.vertical, 4)
        }

        private var earthquakeSubtitle: String {
            let count = features?.earthquakeCount?.value.map { Int($0.rounded()) }
            let mag = features?.earthquakeMaxMag?.value
            let region = features?.earthquakeMaxRegion
            var parts: [String] = []
            if let count { parts.append(count == 1 ? "1 quake" : "\(count) quakes") }
            if let mag { parts.append(String(format: "max M%.1f", mag)) }
            if let region, !region.isEmpty { parts.append(region) }
            return parts.isEmpty ? "Live quake feed" : parts.joined(separator: " · ")
        }

        var body: some View {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Button { dismiss() } label: { Label("Close", systemImage: "xmark.circle") }
                                .buttonStyle(.bordered)
                            Spacer()
                            Text("Cached payloads reused for offline view")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        scrollChips(proxy: proxy)
                        auroraSection
                            .id(SpaceDetailSection.aurora)
                        visualsSection
                            .id(SpaceDetailSection.visuals)
                        earthquakesSection
                            .id(SpaceDetailSection.earthquakes)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 20)
                }
                .navigationTitle("Space Weather Detail")
                .navigationBarTitleDisplayMode(.inline)
                .onAppear {
                    if let initial = initialSection {
                        selectedSection = initial
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                            withAnimation { proxy.scrollTo(initial, anchor: .top) }
                        }
                    }
                }
            }
        }

        @ViewBuilder
        private func scrollChips(proxy: ScrollViewProxy) -> some View {
            HStack(spacing: 8) {
                ForEach([SpaceDetailSection.aurora, .visuals, .earthquakes], id: \.self) { section in
                    Button {
                        selectedSection = section
                        withAnimation { proxy.scrollTo(section, anchor: .top) }
                    } label: {
                        Text(label(for: section))
                            .font(.caption)
                            .foregroundColor(selectedSection == section ? .white : .accentColor)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(selectedSection == section ? Color.accentColor : Color.accentColor.opacity(0.12))
                            .cornerRadius(14)
                    }
                    .buttonStyle(.plain)
                }
            }
        }

        private var auroraSection: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    let kpNow = features?.kpCurrent?.value.map { String(format: "%.1f", $0) } ?? "–"
                    let prob = ContentView.auroraProbabilityText(from: features) ?? "Probability pending"
                    let caption = features?.auroraProbability ?? features?.auroraProbabilityNh ?? features?.auroraProbabilitySh
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Kp now: \(kpNow)")
                            Text("Hemispheric power: \(auroraPowerText)")
                            Text(prob)
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                        Spacer()
                    }
                    if let caption, caption.value != nil {
                        Text("Aurora outlook cached from SWPC feeds; probability badge shows NH/SH split when available.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    let auroraEntries = outlookEntries(containing: ["aurora", "kp", "hemispheric", "ovation"])
                    if !auroraEntries.isEmpty {
                        Divider()
                        ForEach(auroraEntries, id: \.self) { entry in
                            outlookEntryRow(entry)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Aurora", systemImage: "sparkles")
            }
        }

        private var visualsSection: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Sources")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                        Picker("Source", selection: $sourceFilter) {
                            Text("All").tag("all")
                            Text("NASA").tag("nasa")
                            Text("Cumiana").tag("cumiana")
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                    }
                    if showSeriesOverlay, !overlaySeriesSummaries.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Overlay series")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            ForEach(overlaySeriesSummaries, id: \.self) { line in
                                Text(line)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    Toggle("Show overlay series", isOn: $showSeriesOverlay)
                        .font(.caption)
                        .toggleStyle(.switch)
                    Toggle("Show credits", isOn: $showCredits)
                        .font(.caption)
                        .toggleStyle(.switch)
                    // Grid of visuals (detail view), reusing the same resolver as dashboard preview
                    let cols = [GridItem(.adaptive(minimum: 140), spacing: 12)]
                    LazyVGrid(columns: cols, spacing: 12) {
                        ForEach(Array(overlayImages.prefix(12).enumerated()), id: \.offset) { _, img in
                            VStack(alignment: .leading, spacing: 6) {
                                if let u = resolveMediaURL_Detail(img.url) {
                                    AsyncImage(url: u) { phase in
                                        switch phase {
                                        case .empty:
                                            ZStack { Rectangle().opacity(0.08); ProgressView().scaleEffect(0.9) }
                                                .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                        case .success(let image):
                                            image
                                                .resizable()
                                                .scaledToFill()
                                                .frame(height: 120)
                                                .clipped()
                                                .clipShape(RoundedRectangle(cornerRadius: 10))
                                        case .failure:
                                            ZStack { Rectangle().opacity(0.08); Image(systemName: "exclamationmark.triangle").foregroundColor(.orange) }
                                                .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                        @unknown default:
                                            EmptyView().frame(height: 120)
                                        }
                                    }
                                } else {
                                    ZStack { Rectangle().opacity(0.08); Image(systemName: "questionmark").foregroundColor(.secondary) }
                                        .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                }
                                HStack {
                                    Text(img.key ?? "Visual").font(.footnote).lineLimit(1)
                                    Spacer()
                                    Text(formattedCapture(img.capturedAt)).font(.caption2).foregroundColor(.secondary)
                                }
                                if showCredits, let c = img.credit, !c.isEmpty {
                                    Text(c).font(.caption2).foregroundColor(.secondary).lineLimit(1)
                                }
                            }
                        }
                    }
                    let solarEntries = Array(outlookEntries(containing: ["solar", "cme", "coronal", "flare", "enlil"]).prefix(5))
                    let radiationEntries = Array(outlookEntries(containing: ["radiation", "sep", "belt"]).prefix(5))
                    let absorptionEntries = Array(outlookEntries(containing: ["d-rap", "drap", "absorption"]).prefix(5))
                    let magnetometerEntries = Array(outlookEntries(containing: ["magnetometer", "symh", "dst", "supermag"]).prefix(5))
                    if !solarEntries.isEmpty || !radiationEntries.isEmpty || !absorptionEntries.isEmpty || !magnetometerEntries.isEmpty {
                        Divider()
                        VStack(alignment: .leading, spacing: 8) {
                            if !solarEntries.isEmpty {
                                Text("Solar & CME outlook").font(.caption).foregroundColor(.secondary)
                                ForEach(solarEntries, id: \.self) { outlookEntryRow($0) }
                            }
                            if !radiationEntries.isEmpty {
                                Text("Radiation/SEP").font(.caption).foregroundColor(.secondary)
                                ForEach(radiationEntries, id: \.self) { outlookEntryRow($0) }
                            }
                            if !absorptionEntries.isEmpty {
                                Text("D-RAP / absorption").font(.caption).foregroundColor(.secondary)
                                ForEach(absorptionEntries, id: \.self) { outlookEntryRow($0) }
                            }
                            if !magnetometerEntries.isEmpty {
                                Text("Magnetometer / geomagnetic").font(.caption).foregroundColor(.secondary)
                                ForEach(magnetometerEntries, id: \.self) { outlookEntryRow($0) }
                            }
                        }
                    }
                    if !outlookNotes.isEmpty {
                        Divider()
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(outlookNotes, id: \.self) { note in
                                Text(note)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    if overlayImages.isEmpty {
                        Text("No overlays available yet. Cached gallery will appear here.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        let cols = [GridItem(.adaptive(minimum: 160), spacing: 12)]
                        LazyVGrid(columns: cols, spacing: 16) {
                            ForEach(Array(overlayImages.prefix(12).enumerated()), id: \.offset) { _, image in
                                VStack(alignment: .leading, spacing: 6) {
                                    if let url = resolveMediaURL_Detail(image) {
                                        let urlStr = url.absoluteString.lowercased()
                                        if urlStr.hasSuffix(".mp4") || urlStr.contains(".mp4?") {
                                            ZStack {
                                                Rectangle().opacity(0.08)
                                                Image(systemName: "play.circle.fill").font(.system(size: 44))
                                            }
                                            .frame(height: 150)
                                            .clipShape(RoundedRectangle(cornerRadius: 10))
                                            .onTapGesture { detailPlayingURL = url; detailShowPlayer = true }
                                        } else {
                                            AsyncImage(url: url) { phase in
                                                switch phase {
                                                case .empty:
                                                    ZStack {
                                                        Rectangle().opacity(0.08)
                                                        ProgressView().scaleEffect(0.9)
                                                    }
                                                    .frame(height: 150)
                                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                                                case .success(let img):
                                                    img
                                                        .resizable()
                                                        .scaledToFill()
                                                        .frame(height: 150)
                                                        .clipped()
                                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                                case .failure:
                                                    ZStack {
                                                        Rectangle().opacity(0.08)
                                                        Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                                                    }
                                                    .frame(height: 150)
                                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                                                @unknown default:
                                                    EmptyView().frame(height: 150)
                                                }
                                            }
                                        }
                                    } else {
                                        ZStack {
                                            Rectangle().opacity(0.08)
                                            Image(systemName: "questionmark").foregroundColor(.secondary)
                                        }
                                        .frame(height: 150)
                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                    }
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(image.caption ?? image.key ?? "Overlay")
                                            .font(.subheadline)
                                        Text(formattedCapture(image.capturedAt))
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                        if showCredits, let credit = image.credit {
                                            Text(credit)
                                                .font(.caption2)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                            }
                        }
                        .sheet(isPresented: $detailShowPlayer) {
                            if let url = detailPlayingURL {
                                VideoPlayer(player: AVPlayer(url: url)).ignoresSafeArea()
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Solar Visuals", systemImage: "photo.on.rectangle")
            }
        }

        private func resolveMediaURL_Detail(_ image: SpaceVisualImage) -> URL? {
            ContentView.resolvedVisualURL(for: image)
        }

        private var earthquakesSection: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 6) {
                    Text(earthquakeSubtitle)
                        .font(.subheadline)
                    if let sch = series?.schumannDaily?.first?.station_id {
                        Text("Schumann context: \(sch)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Text("Tap Earthscope on the dashboard for the full journal and quake context.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Earthquakes", systemImage: "waveform.path")
            }
        }

        private func label(for section: SpaceDetailSection) -> String {
            switch section {
            case .aurora: return "Aurora"
            case .visuals: return "Visuals"
            case .earthquakes: return "Earthquakes"
            }
        }
    }

    private struct SpaceAlertsCard: View {
        let kpAlert: Bool
        let flareAlert: Bool
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 6) {
                    if kpAlert { Label("Kp Alert", systemImage: "exclamationmark.triangle.fill").foregroundColor(.orange) }
                    if flareAlert { Label("Flare Alert", systemImage: "sun.max.trianglebadge.exclamationmark.fill").foregroundColor(.orange) }
                    if !kpAlert && !flareAlert {
                        Text("No current alerts").foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Alerts", systemImage: "bell.badge.fill") }
        }
    }

    private struct EarthscopeCardV2: View {
        let title: String?
        let caption: String?
        let images: Any?
        let bodyMarkdown: String?
        @State private var showFull: Bool = false

        // Extract URLs from multiple possible shapes
        private func extractImageURLs() -> [URL] {
            var urls: [URL] = []
            // 1) Direct dictionary [String:String]
            if let dict = images as? [String:String] {
                ["caption","stats","affects","playbook"].forEach { k in
                    if let s = dict[k]?.trimmingCharacters(in: .whitespacesAndNewlines), let u = URL(string: s) { urls.append(u) }
                }
            }
            // 2) Dictionary [String:Any]
            else if let dict = images as? [String:Any] {
                ["caption","stats","affects","playbook"].forEach { k in
                    if let s = (dict[k] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), let u = URL(string: s) { urls.append(u) }
                }
            }
            // 3) Reflect a struct with properties caption/stats/affects/playbook
            else if let imgs = images {
                let m = Mirror(reflecting: imgs)
                var map: [String:String] = [:]
                for child in m.children {
                    guard let label = child.label else { continue }
                    if let s = child.value as? String { map[label] = s }
                }
                ["caption","stats","affects","playbook"].forEach { k in
                    if let s = map[k]?.trimmingCharacters(in: .whitespacesAndNewlines), let u = URL(string: s) { urls.append(u) }
                }
            }
            // De-duplicate while preserving order
            var seen: Set<URL> = []
            return urls.filter { seen.insert($0).inserted }
        }

        var body: some View {
            let urls = extractImageURLs()
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    if let t = title, !t.isEmpty { Text(t).font(.headline) }
                    if let c = caption, !c.isEmpty {
                        Text(c)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .padding(8)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }

                    if !urls.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                ForEach(urls, id: \.self) { url in
                                    AsyncImage(url: url) { phase in
                                        switch phase {
                                        case .empty:
                                            ZStack { RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15)); ProgressView() }
                                                .frame(width: 160, height: 100)
                                                .transaction { $0.disablesAnimations = true }
                                        case .success(let img):
                                            img.resizable().scaledToFill()
                                                .frame(width: 160, height: 100)
                                                .clipped()
                                                .cornerRadius(8)
                                                .transaction { $0.disablesAnimations = true }
                                        case .failure:
                                            RoundedRectangle(cornerRadius: 8)
                                                .fill(Color.gray.opacity(0.12))
                                                .overlay { Image(systemName: "photo").foregroundColor(.secondary) }
                                                .frame(width: 160, height: 100)
                                                .transaction { $0.disablesAnimations = true }
                                        @unknown default:
                                            EmptyView()
                                        }
                                    }
                                }
                            }
                            .padding(.vertical, 2)
                        }
                        .frame(height: 110)
                    }

                    if let body = bodyMarkdown, !body.isEmpty {
                        Text(body)
                            .font(.footnote)
                            .foregroundColor(.secondary)
                            .lineLimit(6)
                            .padding(8)
                            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))

                        Button("Read more") { showFull = true }
                            .font(.caption)
                            .underline()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("EarthScope", systemImage: "globe.americas.fill") }
            .sheet(isPresented: $showFull) {
                EarthscopeFullSheetV2(title: title, caption: caption, bodyText: bodyMarkdown, urls: urls)
            }
        }
    }

    private struct EarthscopeFullSheetV2: View {
        let title: String?
        let caption: String?
        let bodyText: String?
        let urls: [URL]
        @Environment(\.dismiss) private var dismiss
        var body: some View {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let t = title, !t.isEmpty { Text(t).font(.title3).bold() }
                        if let c = caption, !c.isEmpty { Text(c).font(.subheadline).foregroundColor(.secondary) }
                        if !urls.isEmpty {
                            VStack(spacing: 12) {
                                ForEach(urls, id: \.self) { url in
                                    AsyncImage(url: url) { phase in
                                        switch phase {
                                        case .empty: ZStack { RoundedRectangle(cornerRadius: 10).fill(Color.gray.opacity(0.15)); ProgressView() }.frame(height: 180)
                                        case .success(let img): img.resizable().scaledToFit().cornerRadius(10)
                                        case .failure: RoundedRectangle(cornerRadius: 10).fill(Color.gray.opacity(0.12)).overlay { Image(systemName: "photo").foregroundColor(.secondary) }.frame(height: 180)
                                        @unknown default: EmptyView()
                                        }
                                    }
                                }
                            }
                        }
                        if let b = bodyText, !b.isEmpty { Text(b).font(.body) }
                    }
                    .padding()
                }
                .navigationTitle("EarthScope")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
            }
        }
    }

    private struct DebugPanel: View {
        @ObservedObject var state: AppState
        @Binding var expandLog: Bool
        let featuresState: FeatureFetchState
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    if featuresState.hasInfo {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Features Diagnostics")
                                .font(.headline)
                            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
                                GridRow { Text("OK"); Text(featuresState.okText) }
                                GridRow { Text("Source"); Text(featuresState.source ?? "-") }
                                if let fallback = featuresState.cacheFallback {
                                    GridRow { Text("cacheFallback"); Text(fallback).lineLimit(3) }
                                }
                                if let pool = featuresState.poolTimeout {
                                    GridRow { Text("poolTimeout"); Text(pool).lineLimit(3) }
                                }
                                if let error = featuresState.error {
                                    GridRow { Text("error"); Text(error).lineLimit(4) }
                                }
                            }
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        }
                        Divider()
                    }
                    Toggle("Expand Log", isOn: $expandLog)
                    if expandLog {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 4) {
                                let tail = Array(state.log.suffix(200))
                                ForEach(Array(tail.enumerated()), id: \.offset) { _, line in
                                    Text(line).font(.caption2).frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        }
                        .frame(maxHeight: 240)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Debug", systemImage: "wrench.and.screwdriver") }
        }
    }

    private struct PolarStatusSection: View {
        @ObservedObject var state: AppState
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Polar ECG").font(.headline)
                    if !state.polarDeviceId.isEmpty {
                        Text("Device ID: \(state.polarDeviceId)").font(.caption)
                    } else {
                        Text("No Polar device connected").font(.caption).foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Polar ECG", systemImage: "waveform.path.ecg") }
            .padding(.horizontal)
        }
    }

    private struct ForecastCard: View {
        let summary: ForecastSummary
        @State private var showDetail = false
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text("3‑Day Geomagnetic Forecast").font(.headline)
                    if let h = summary.headline, !h.isEmpty {
                        Text(h).font(.subheadline).fontWeight(.semibold)
                    }
                    if let lines = summary.lines, !lines.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(Array(lines.prefix(4).enumerated()), id: \.offset) { _, line in
                                Text("• \(line)").font(.caption)
                            }
                        }
                    } else if let body = summary.body, !body.isEmpty {
                        Text(body).font(.caption).lineLimit(5)
                    } else {
                        Text("No forecast available.").font(.caption).foregroundColor(.secondary)
                    }
                    Button("Read full forecast") { showDetail = true }
                        .font(.caption)
                        .underline()
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .sheet(isPresented: $showDetail) {
                ForecastFullView(summary: summary)
            }
        }
    }
    
    private struct ForecastFullView: View {
        let summary: ForecastSummary
        var body: some View {
            NavigationView {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if let h = summary.headline, !h.isEmpty {
                            Text(h).font(.title3).bold()
                        }
                        if let body = summary.body, !body.isEmpty {
                            Text(body)
                                .font(.body)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else if let lines = summary.lines, !lines.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                                    Text("• \(line)")
                                        .font(.body)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        } else {
                            Text("No forecast available.")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding()
                }
                .navigationTitle("Forecast")
                .navigationBarTitleDisplayMode(.inline)
            }
        }
    }
    
    private struct SpaceChartsCard: View {
        let series: SpaceSeries
        let highlights: [SymptomHighlight]
        
        // Helper structs for chart points (nested, not inside body)
        private struct SWPoint: Identifiable {
            let id: Date
            let date: Date
            let kp: Double?
            let bz: Double?
            init(date: Date, kp: Double?, bz: Double?) { self.id = date; self.date = date; self.kp = kp; self.bz = bz }
        }
        
        private struct SchPoint: Identifiable {
            let id: String
            let day: String
            let f0: Double?
            init(day: String, f0: Double?) { self.id = day; self.day = day; self.f0 = f0 }
        }
        
        private struct HRTSPoint: Identifiable {
            let id: Date
            let date: Date
            let hr: Double
        }
        
        // Static ISO8601 formatter with fractional seconds
        private static let isoFmt: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f
        }()
        // Tolerant ISO8601 parsing: with and without fractional seconds
        private static let isoFmtSimple: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            return f
        }()
        private static func parseISODate(_ s: String) -> Date? {
            return SpaceChartsCard.isoFmt.date(from: s) ?? SpaceChartsCard.isoFmtSimple.date(from: s)
        }
        
        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    if #available(iOS 16.0, *) {
                        // Simple legend
                        HStack(spacing: 12) {
                            Label("Kp", systemImage: "circle.fill").foregroundColor(.green).font(.caption)
                            Label("Bz", systemImage: "circle.fill").foregroundColor(.blue).font(.caption)
                            Label("f0", systemImage: "circle.fill").foregroundColor(.purple).font(.caption)
                            Label("HR", systemImage: "circle.fill").foregroundColor(.gray).font(.caption)
                        }
                        
                        // Debug counts line
                        let swCount = series.spaceWeather?.count ?? 0
                        let schCount = series.schumannDaily?.count ?? 0
                        let hrtsCount = series.hrTimeseries?.count ?? 0
                        Text("Counts — sw: \(swCount) sch: \(schCount) hrts: \(hrtsCount)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        
                        // Row 1: Kp
                        if let sw = series.spaceWeather, !sw.isEmpty {
                            let pts: [SWPoint] = sw.compactMap { pt in
                                guard let ts = pt.ts, let d = SpaceChartsCard.parseISODate(ts) else { return nil }
                                return SWPoint(date: d, kp: pt.kp, bz: pt.bz)
                            }
                            let kpPts = pts.compactMap { $0.kp }
                            if kpPts.isEmpty {
                                Text("No Kp samples (last 14 days)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Chart {
                                    ForEach(highlights) { highlight in
                                        RuleMark(x: .value("Symptom", highlight.date))
                                            .foregroundStyle(.pink.opacity(0.2))
                                            .lineStyle(StrokeStyle(lineWidth: 14, lineCap: .round))
                                            .annotation(position: .top) {
                                                Text("▲ \(highlight.events)")
                                                    .font(.caption2)
                                                    .foregroundColor(.pink)
                                            }
                                    }
                                    ForEach(pts) { item in
                                        if let kp = item.kp {
                                            LineMark(x: .value("Date", item.date), y: .value("Kp", kp))
                                                .interpolationMethod(.catmullRom)
                                                .foregroundStyle(.green)
                                        }
                                    }
                                }
                                .chartYScale(domain: 0...9)
                                .frame(height: 120)
                                if let last = pts.last?.date {
                                    Text("Updated: \(DateFormatter.localizedString(from: last, dateStyle: .none, timeStyle: .short))")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                            }
                        } else {
                            Text("No Kp samples (last 14 days)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        // Row 2: Bz
                        if let sw = series.spaceWeather, !sw.isEmpty {
                            let pts: [SWPoint] = sw.compactMap { pt in
                                guard let ts = pt.ts, let d = SpaceChartsCard.parseISODate(ts) else { return nil }
                                return SWPoint(date: d, kp: pt.kp, bz: pt.bz)
                            }
                            let bzPts = pts.compactMap { $0.bz }
                            if bzPts.isEmpty {
                                Text("No Bz samples (last 14 days)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Chart {
                                    ForEach(highlights) { highlight in
                                        RuleMark(x: .value("Symptom", highlight.date))
                                            .foregroundStyle(.pink.opacity(0.18))
                                            .lineStyle(StrokeStyle(lineWidth: 12, lineCap: .round))
                                    }
                                    ForEach(pts) { item in
                                        if let bz = item.bz {
                                            LineMark(x: .value("Date", item.date), y: .value("Bz nT", bz))
                                                .interpolationMethod(.catmullRom)
                                                .foregroundStyle(.blue)
                                        }
                                    }
                                }
                                .frame(height: 120)
                            }
                        } else {
                            Text("No Bz samples (last 14 days)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        // Row 3: Schumann f0 (daily)
                        if let sch = series.schumannDaily, !sch.isEmpty {
                            let schPts: [SchPoint] = sch.compactMap { d in
                                guard let day = d.day else { return nil }
                                return SchPoint(day: day, f0: d.f0)
                            }
                            if schPts.isEmpty {
                                Text("No Schumann f0 (last 14 days)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Chart(schPts) { item in
                                    if let f0 = item.f0 {
                                        PointMark(x: .value("Day", item.day), y: .value("f0 Hz", f0))
                                            .foregroundStyle(.purple)
                                    }
                                }
                                .frame(height: 100)
                            }
                        } else {
                            Text("No Schumann f0 (last 14 days)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        // Row 4: HR time series (5-min buckets)
                        if let hrts = series.hrTimeseries, !hrts.isEmpty {
                            let pts: [HRTSPoint] = hrts.compactMap { p in
                                guard let ts = p.ts, let d = SpaceChartsCard.parseISODate(ts), let v = p.hr else { return nil }
                                return HRTSPoint(id: d, date: d, hr: v)
                            }
                            if pts.isEmpty {
                                Text("No HR samples (last 14 days)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Chart(pts) { p in
                                    LineMark(x: .value("Time", p.date), y: .value("HR", p.hr))
                                        .interpolationMethod(.catmullRom)
                                        .foregroundStyle(.gray)
                                }
                                .frame(height: 100)
                            }
                        }
                    }
                }
            }
            .transaction { $0.disablesAnimations = true }
        }
    }
#endif
}
