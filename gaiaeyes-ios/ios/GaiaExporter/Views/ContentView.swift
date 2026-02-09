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

private struct LocalCheckResponse: Codable {
    let ok: Bool?
    let whereInfo: LocalWhere?
    let weather: LocalWeather?
    let air: LocalAir?
    let moon: LocalMoon?
    let asof: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok, weather, air, moon, asof, error
        case whereInfo = "where"
    }
}

private struct LocalWhere: Codable {
    let zip: String?
    let lat: Double?
    let lon: Double?
}

private struct LocalWeather: Codable {
    let tempC: Double?
    let tempDelta24hC: Double?
    let humidityPct: Double?
    let precipProbPct: Double?
    let pressureHpa: Double?
    let baroDelta24hHpa: Double?
    let pressureTrend: String?
    let baroTrend: String?
}

private struct LocalAir: Codable {
    let aqi: Double?
    let category: String?
    let pollutant: String?
}

private struct LocalMoon: Codable {
    let phase: String?
    let illum: Double?
    let cycle: Double?
}

private struct MagnetosphereResponse: Codable {
    let ok: Bool?
    let data: MagnetosphereData?
    let error: String?
}

private struct MagnetosphereData: Codable {
    let ts: String?
    let kpis: MagnetosphereKpis?
    let sw: MagnetosphereSw?
    let trend: MagnetosphereTrend?
    let chart: MagnetosphereChart?
    let series: MagnetosphereSeries?
}

private struct MagnetosphereKpis: Codable {
    let r0Re: Double?
    let geoRisk: String?
    let storminess: String?
    let dbdt: String?
    let lppRe: Double?
    let kp: Double?
}

private struct MagnetosphereSw: Codable {
    let nCm3: Double?
    let vKms: Double?
    let bzNt: Double?
}

private struct MagnetosphereTrend: Codable {
    let r0: String?
}

private struct MagnetosphereChart: Codable {
    let mode: String?
    let amp: Double?
}

private struct MagnetosphereSeries: Codable {
    let r0: [MagnetospherePoint]?
}

private struct MagnetospherePoint: Codable {
    let t: String?
    let v: Double?
}

private struct QuakesLatestResponse: Codable {
    let ok: Bool?
    let item: QuakeDaily?
    let error: String?
}

private struct QuakeDaily: Codable {
    let day: String?
    let allQuakes: Int?
    let m4p: Int?
    let m5p: Int?
    let m6p: Int?
    let m7p: Int?
}

private struct QuakesEventsResponse: Codable {
    let ok: Bool?
    let items: [QuakeEvent]?
    let error: String?
}

private struct QuakeEvent: Codable {
    let timeUtc: String?
    let mag: Double?
    let depthKm: Double?
    let lat: Double?
    let lon: Double?
    let place: String?
    let source: String?
    let url: String?
    let id: String?
}

private struct HazardsBriefResponse: Codable {
    let ok: Bool?
    let generatedAt: String?
    let items: [HazardItem]?
    let error: String?
}

private struct GdacsFullResponse: Codable {
    let ok: Bool?
    let generatedAt: String?
    let items: [GdacsFullItem]?
    let error: String?
}

private struct GdacsFullItem: Codable, Identifiable, Hashable {
    let id: String
    let title: String?
    let url: String?
    let source: String?
    let kind: String?
    let location: String?
    let severity: String?
    let startedAt: String?
    let endedAt: String?
    let ingestedAt: String?
    let details: String?
    let lat: Double?
    let lon: Double?

    private enum CodingKeys: String, CodingKey {
        case id, title, url, source, kind, location, severity, startedAt, endedAt, ingestedAt, details, lat, lon
    }
}

private struct HazardItem: Codable, Identifiable, Hashable {
    let id: String
    let title: String?
    let url: String?
    let source: String?
    let kind: String?
    let location: String?
    let severity: String?
    let startedAt: String?

    private enum CodingKeys: String, CodingKey {
        case title, url, source, kind, location, severity, startedAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        url = try container.decodeIfPresent(String.self, forKey: .url)
        source = try container.decodeIfPresent(String.self, forKey: .source)
        kind = try container.decodeIfPresent(String.self, forKey: .kind)
        location = try container.decodeIfPresent(String.self, forKey: .location)
        severity = try container.decodeIfPresent(String.self, forKey: .severity)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)

        let base = url ?? title ?? location ?? UUID().uuidString
        id = base
    }

    init(id: String = UUID().uuidString,
         title: String? = nil,
         url: String? = nil,
         source: String? = nil,
         kind: String? = nil,
         location: String? = nil,
         severity: String? = nil,
         startedAt: String? = nil) {
        self.id = id
        self.title = title
        self.url = url
        self.source = source
        self.kind = kind
        self.location = location
        self.severity = severity
        self.startedAt = startedAt
    }
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

private struct OutlookKp: Codable, Hashable {
    let now: Double?
    let nowTs: String?
    let gScaleNow: String?
    let last24hMax: Double?
    let gScale24hMax: String?

    private enum CodingKeys: String, CodingKey {
        case now
        case nowTs = "now_ts"
        case gScaleNow = "g_scale_now"
        case last24hMax = "last_24h_max"
        case gScale24hMax = "g_scale_24h_max"
    }
}

private struct OutlookImpacts: Codable, Hashable {
    let gps: String?
    let comms: String?
    let grids: String?
    let aurora: String?
}

private struct OutlookFlares: Codable, Hashable {
    let max24h: String?
    let total24h: Int?
    let bands24h: [String: Int]?

    private enum CodingKeys: String, CodingKey {
        case max24h = "max_24h"
        case total24h = "total_24h"
        case bands24h = "bands_24h"
    }
}

private struct OutlookCmesStats: Codable, Hashable {
    let total72h: Int?
    let earthDirectedCount: Int?
    let maxSpeedKms: Double?

    private enum CodingKeys: String, CodingKey {
        case total72h = "total_72h"
        case earthDirectedCount = "earth_directed_count"
        case maxSpeedKms = "max_speed_kms"
    }
}

private struct OutlookCmes: Codable, Hashable {
    let headline: String?
    let stats: OutlookCmesStats?
}

private struct OutlookSep: Codable, Hashable {
    let ts: String?
    let satellite: String?
    let energyBand: String?
    let flux: Double?
    let sScale: String?
    let sScaleIndex: Double?

    private enum CodingKeys: String, CodingKey {
        case ts
        case satellite
        case energyBand = "energy_band"
        case flux
        case sScale = "s_scale"
        case sScaleIndex = "s_scale_index"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ts = try container.decodeIfPresent(String.self, forKey: .ts)
        satellite = try container.decodeIfPresent(String.self, forKey: .satellite)
        energyBand = try container.decodeIfPresent(String.self, forKey: .energyBand)
        sScale = try container.decodeIfPresent(String.self, forKey: .sScale)
        flux = Self.decodeDouble(container, forKey: .flux)
        sScaleIndex = Self.decodeDouble(container, forKey: .sScaleIndex)
    }

    private static func decodeDouble(_ container: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Double? {
        if let val = try? container.decodeIfPresent(Double.self, forKey: key) { return val }
        if let str = try? container.decodeIfPresent(String.self, forKey: key) {
            return Double(str.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
    }
}

private struct OutlookAurora: Codable, Hashable {
    let validFrom: String?
    let validTo: String?
    let hemisphere: String?
    let headline: String?
    let powerGw: Double?
    let wingKp: Double?
    let confidence: String?

    private enum CodingKeys: String, CodingKey {
        case validFrom = "valid_from"
        case validTo = "valid_to"
        case hemisphere
        case headline
        case powerGw = "power_gw"
        case wingKp = "wing_kp"
        case confidence
    }
}

private struct SwpcBulletin: Codable, Hashable {
    let issued: String?
    let text: String?
}

private struct SwpcTextAlert: Codable, Hashable, Identifiable {
    let id = UUID()
    let ts: String?
    let src: String?
    let message: String?

    private enum CodingKeys: String, CodingKey {
        case ts, src, message
    }
}

private struct OutlookData: Codable, Hashable {
    let sep: OutlookSep?
    let auroraOutlook: [OutlookAurora]?

    private enum CodingKeys: String, CodingKey {
        case sep
        case auroraOutlook = "aurora_outlook"
    }
}

private struct SpaceForecastOutlook: Codable {
    let issuedAt: String?
    let sections: [SpaceOutlookSection]
    let notes: [String]?
    let kp: OutlookKp?
    let bzNow: Double?
    let swSpeedNowKms: Double?
    let swDensityNowCm3: Double?
    let headline: String?
    let confidence: String?
    let summary: String?
    let alerts: [String]?
    let impacts: OutlookImpacts?
    let flares: OutlookFlares?
    let cmes: OutlookCmes?
    let bulletins: [String: SwpcBulletin]?
    let swpcTextAlerts: [SwpcTextAlert]?
    let data: OutlookData?

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
        var kp: OutlookKp? = nil
        var bzNow: Double? = nil
        var swSpeedNowKms: Double? = nil
        var swDensityNowCm3: Double? = nil
        var headline: String? = nil
        var confidence: String? = nil
        var summary: String? = nil
        var alerts: [String]? = nil
        var impacts: OutlookImpacts? = nil
        var flares: OutlookFlares? = nil
        var cmes: OutlookCmes? = nil
        var bulletins: [String: SwpcBulletin]? = nil
        var swpcTextAlerts: [SwpcTextAlert]? = nil
        var data: OutlookData? = nil

        for key in container.allKeys {
            switch key.stringValue {
            case "issuedAt":
                issued = try container.decodeIfPresent(String.self, forKey: key)
            case "notes":
                notes = try container.decodeIfPresent([String].self, forKey: key)
            case "kp":
                kp = try? container.decode(OutlookKp.self, forKey: key)
            case "bz_now":
                bzNow = try? container.decode(Double.self, forKey: key)
            case "sw_speed_now_kms":
                swSpeedNowKms = try? container.decode(Double.self, forKey: key)
            case "sw_density_now_cm3":
                swDensityNowCm3 = try? container.decode(Double.self, forKey: key)
            case "headline":
                headline = try? container.decode(String.self, forKey: key)
            case "confidence":
                confidence = try? container.decode(String.self, forKey: key)
            case "summary":
                summary = try? container.decode(String.self, forKey: key)
            case "alerts":
                alerts = try? container.decode([String].self, forKey: key)
            case "impacts":
                impacts = try? container.decode(OutlookImpacts.self, forKey: key)
            case "flares":
                flares = try? container.decode(OutlookFlares.self, forKey: key)
            case "cmes":
                cmes = try? container.decode(OutlookCmes.self, forKey: key)
            case "bulletins":
                bulletins = try? container.decode([String: SwpcBulletin].self, forKey: key)
            case "swpc_text_alerts":
                swpcTextAlerts = try? container.decode([SwpcTextAlert].self, forKey: key)
            case "data":
                data = try? container.decode(OutlookData.self, forKey: key)
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
        self.kp = kp
        self.bzNow = bzNow
        self.swSpeedNowKms = swSpeedNowKms
        self.swDensityNowCm3 = swDensityNowCm3
        self.headline = headline
        self.confidence = confidence
        self.summary = summary
        self.alerts = alerts
        self.impacts = impacts
        self.flares = flares
        self.cmes = cmes
        self.bulletins = bulletins
        self.swpcTextAlerts = swpcTextAlerts
        self.data = data
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        if let issuedAt, let issuedKey = DynamicKey(stringValue: "issuedAt") {
            try container.encode(issuedAt, forKey: issuedKey)
        }
        if let notes, let notesKey = DynamicKey(stringValue: "notes") {
            try container.encode(notes, forKey: notesKey)
        }
        if let kp, let key = DynamicKey(stringValue: "kp") {
            try container.encode(kp, forKey: key)
        }
        if let bzNow, let key = DynamicKey(stringValue: "bz_now") {
            try container.encode(bzNow, forKey: key)
        }
        if let swSpeedNowKms, let key = DynamicKey(stringValue: "sw_speed_now_kms") {
            try container.encode(swSpeedNowKms, forKey: key)
        }
        if let swDensityNowCm3, let key = DynamicKey(stringValue: "sw_density_now_cm3") {
            try container.encode(swDensityNowCm3, forKey: key)
        }
        if let headline, let key = DynamicKey(stringValue: "headline") {
            try container.encode(headline, forKey: key)
        }
        if let confidence, let key = DynamicKey(stringValue: "confidence") {
            try container.encode(confidence, forKey: key)
        }
        if let summary, let key = DynamicKey(stringValue: "summary") {
            try container.encode(summary, forKey: key)
        }
        if let alerts, let key = DynamicKey(stringValue: "alerts") {
            try container.encode(alerts, forKey: key)
        }
        if let impacts, let key = DynamicKey(stringValue: "impacts") {
            try container.encode(impacts, forKey: key)
        }
        if let flares, let key = DynamicKey(stringValue: "flares") {
            try container.encode(flares, forKey: key)
        }
        if let cmes, let key = DynamicKey(stringValue: "cmes") {
            try container.encode(cmes, forKey: key)
        }
        if let bulletins, let key = DynamicKey(stringValue: "bulletins") {
            try container.encode(bulletins, forKey: key)
        }
        if let swpcTextAlerts, let key = DynamicKey(stringValue: "swpc_text_alerts") {
            try container.encode(swpcTextAlerts, forKey: key)
        }
        if let data, let key = DynamicKey(stringValue: "data") {
            try container.encode(data, forKey: key)
        }
        for section in sections {
            guard let key = DynamicKey(stringValue: section.id) else { continue }
            try container.encode(section.entries, forKey: key)
        }
    }
}

private enum SpaceDetailSection: Hashable {
    case visuals
    case schumann
}

private struct MediaViewerPayload: Identifiable {
    let id: String
    let url: URL
    let title: String?
    let credit: String?
    let isVideo: Bool
}

private struct MediaViewerSheet: View {
    let payload: MediaViewerPayload
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer? = nil

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 12) {
                VStack(spacing: 2) {
                    if let title = payload.title, !title.isEmpty {
                        Text(title).font(.headline).foregroundColor(.white)
                    }
                    if let credit = payload.credit, !credit.isEmpty {
                        Text(credit).font(.caption).foregroundColor(.white.opacity(0.7))
                    }
                }
                .padding(.top, 16)
                .padding(.horizontal, 16)

                if payload.isVideo {
                    VideoPlayer(player: player)
                        .onAppear {
                            if player == nil { player = AVPlayer(url: payload.url) }
                            player?.play()
                        }
                        .onDisappear {
                            player?.pause()
                            player = nil
                        }
                        .scaledToFit()
                        .frame(maxWidth: .infinity, maxHeight: 520)
                } else {
                    AsyncImage(url: payload.url) { phase in
                        switch phase {
                        case .empty:
                            ProgressView().tint(.white)
                        case .success(let image):
                            image
                                .resizable()
                                .scaledToFit()
                                .frame(maxWidth: .infinity, maxHeight: 520)
                        case .failure:
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                        @unknown default:
                            EmptyView()
                        }
                    }
                }
                Spacer()
            }
        }
        .onTapGesture(count: 2) { dismiss() }
        .safeAreaInset(edge: .top) {
            HStack {
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title)
                        .foregroundColor(.white)
                        .padding(10)
                        .background(Color.black.opacity(0.35), in: Circle())
                }
                .padding(.trailing, 12)
            }
        }
    }
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

    @AppStorage("local_health_zip") private var localHealthZip: String = "78209"
    @State private var localHealth: LocalCheckResponse? = nil
    @State private var localHealthLoading: Bool = false
    @State private var localHealthError: String?
    @State private var localZipRefreshTask: Task<Void, Never>? = nil

    @State private var magnetosphere: MagnetosphereData? = nil
    @State private var magnetosphereLoading: Bool = false
    @State private var magnetosphereError: String?
    @State private var showMagnetosphereDetail: Bool = false

    @State private var quakeLatest: QuakeDaily? = nil
    @State private var quakeEvents: [QuakeEvent] = []
    @State private var quakeLoading: Bool = false
    @State private var quakeError: String?
    @State private var hazardsBrief: HazardsBriefResponse? = nil
    @State private var hazardsLoading: Bool = false
    @State private var hazardsError: String?
    
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

    private func isCancellationError(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let uerr = error as? URLError, uerr.code == .cancelled { return true }
        return false
    }

    private static func scrubError(_ error: String?) -> String? {
        guard let raw = error?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if raw.lowercased() == "cancelled" { return nil }
        return raw
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
        if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
            let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
        }
        let envBase = ProcessInfo.processInfo.environment["MEDIA_BASE_URL"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let envBase, !envBase.isEmpty {
            return URL(string: envBase.hasSuffix("/") ? String(envBase.dropLast()) : envBase)
        }
        return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
    }

    private static var legacyMediaBaseURL: URL? {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "LEGACY_MEDIA_BASE_URL") as? String {
            let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
        }
        return URL(string: "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main")
    }

    private static func resolvedVisualURL(for image: SpaceVisualImage) -> URL? {
        func join(base: URL, path: String) -> URL {
            let rel = path.hasPrefix("/") ? String(path.dropFirst()) : path
            return rel.split(separator: "/").reduce(base) { url, seg in
                url.appendingPathComponent(String(seg))
            }
        }
        func normalizedURL(from raw: String) -> URL? {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            if let direct = URL(string: trimmed), direct.scheme != nil { return direct }
            let rel = trimmed.hasPrefix("/") ? String(trimmed.dropFirst()) : trimmed
            if rel.hasPrefix("images/space/"), let legacy = legacyMediaBaseURL {
                return join(base: legacy, path: rel)
            }
            if let base = mediaBaseURL { return join(base: base, path: rel) }
            return URL(string: trimmed)
        }

        if let urlStr = image.url, let url = normalizedURL(from: urlStr) { return url }
        if let thumb = image.thumb, let url = normalizedURL(from: thumb) { return url }
        if let metaPath = image.meta?["image_path"] ?? image.meta?["path"], let url = normalizedURL(from: metaPath) { return url }
        if let keyPath = image.key, let url = normalizedURL(from: keyPath) { return url }
        return nil
    }

    private static func resolvedMediaURL(_ path: String?) -> URL? {
        guard let raw = path?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if let direct = URL(string: raw), direct.scheme != nil { return direct }
        let rel = raw.hasPrefix("/") ? String(raw.dropFirst()) : raw
        guard let base = mediaBaseURL else { return URL(string: raw) }
        return rel.split(separator: "/").reduce(base) { url, seg in
            url.appendingPathComponent(String(seg))
        }
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
            let payload: SpaceForecastOutlook = try await api.getJSON("v1/space/forecast/outlook", as: SpaceForecastOutlook.self, perRequestTimeout: 30)
            await MainActor.run { applySpaceOutlook(payload) }
            return
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
                let env: Envelope<SpaceForecastOutlook> = try await api.getJSON("v1/space/forecast/outlook", as: Envelope<SpaceForecastOutlook>.self, perRequestTimeout: 30)
                if let payload = env.payload {
                    await MainActor.run { applySpaceOutlook(payload) }
                } else {
                    appLog("[UI] space outlook payload missing; keeping last snapshot")
                }
            } catch {
                appLog("[UI] space outlook fallback decode failed: \(error.localizedDescription)")
            }
        }
    }

    private func sanitizedZip(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let filtered = trimmed.filter { $0.isLetter || $0.isNumber }
        return filtered
    }

    private func scheduleLocalHealthRefresh() {
        localZipRefreshTask?.cancel()
        localZipRefreshTask = Task {
            do {
                try await Task.sleep(nanoseconds: 600_000_000)
            } catch {
                return
            }
            await fetchLocalHealth()
        }
    }

    private func fetchLocalHealth() async {
        let zip = sanitizedZip(localHealthZip)
        guard !zip.isEmpty else {
            await MainActor.run {
                localHealth = nil
                localHealthError = "Enter a ZIP code"
            }
            return
        }
        if zip != localHealthZip {
            await MainActor.run { localHealthZip = zip }
        }
        await MainActor.run {
            localHealthLoading = true
            localHealthError = nil
        }
        let api = state.apiWithAuth()
        do {
            let payload: LocalCheckResponse = try await api.getJSON("v1/local/check?zip=\(zip)", as: LocalCheckResponse.self, perRequestTimeout: 30)
            await MainActor.run {
                if payload.ok == true {
                    localHealth = payload
                    localHealthError = nil
                } else {
                    localHealth = nil
                    localHealthError = payload.error ?? "Local health unavailable"
                }
                localHealthLoading = false
            }
        } catch {
            if isCancellationError(error) {
                await MainActor.run {
                    localHealthLoading = false
                }
                return
            }
            await MainActor.run {
                localHealth = nil
                localHealthError = error.localizedDescription
                localHealthLoading = false
            }
        }
    }

    private func fetchMagnetosphere() async {
        await MainActor.run {
            magnetosphereLoading = true
            magnetosphereError = nil
        }
        let api = state.apiWithAuth()
        do {
            let payload: MagnetosphereResponse = try await api.getJSON("v1/space/magnetosphere", as: MagnetosphereResponse.self, perRequestTimeout: 30)
            await MainActor.run {
                if payload.ok == true {
                    magnetosphere = payload.data
                    magnetosphereError = nil
                } else {
                    magnetosphere = nil
                    magnetosphereError = payload.error ?? "Magnetosphere unavailable"
                }
                magnetosphereLoading = false
            }
        } catch {
            if isCancellationError(error) {
                await MainActor.run {
                    magnetosphereLoading = false
                }
                return
            }
            await MainActor.run {
                magnetosphere = nil
                magnetosphereError = error.localizedDescription
                magnetosphereLoading = false
            }
        }
    }

    private func fetchQuakes() async {
        await MainActor.run {
            quakeLoading = true
            quakeError = nil
        }
        let api = state.apiWithAuth()
        var hadError: String? = nil
        do {
            let latest: QuakesLatestResponse = try await api.getJSON("v1/quakes/latest", as: QuakesLatestResponse.self, perRequestTimeout: 30)
            await MainActor.run { quakeLatest = latest.item }
            if latest.ok != true, let err = latest.error { hadError = err }
        } catch {
            if isCancellationError(error) {
                await MainActor.run {
                    quakeLoading = false
                }
                return
            }
            hadError = error.localizedDescription
        }
        do {
            let events: QuakesEventsResponse = try await api.getJSON("v1/quakes/events", as: QuakesEventsResponse.self, perRequestTimeout: 30)
            await MainActor.run { quakeEvents = events.items ?? [] }
            if events.ok != true, let err = events.error { hadError = err }
        } catch {
            if isCancellationError(error) {
                await MainActor.run {
                    quakeLoading = false
                }
                return
            }
            if hadError == nil { hadError = error.localizedDescription }
        }
        await MainActor.run {
            quakeError = hadError
            quakeLoading = false
        }
    }

    private func fetchHazardsBrief() async {
        await MainActor.run {
            hazardsLoading = true
            hazardsError = nil
        }
        let api = state.apiWithAuth()
        var hadError: String? = nil
        do {
            let payload: HazardsBriefResponse = try await api.getJSON("v1/hazards/gdacs/full?since_hours=48&limit=100", as: HazardsBriefResponse.self, perRequestTimeout: 30)
            await MainActor.run { hazardsBrief = payload }
            if payload.ok != true, let err = payload.error { hadError = err }
        } catch {
            if isCancellationError(error) {
                await MainActor.run {
                    hazardsLoading = false
                }
                return
            }
            hadError = error.localizedDescription
        }
        await MainActor.run {
            hazardsError = hadError
            hazardsLoading = false
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
        interactiveOverlaySeries = []
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

    private func dashboardFeaturesView(_ f: FeaturesToday) -> some View {
        let todayStr = chicagoTodayString()
        let (current, usingYesterdayFallback) = selectDisplayFeatures(for: f)
        let updatedText = current.updatedAt.flatMap { formatUpdated($0) }
        let symptomPoints = symptomSparkPoints()
        let symptomSummary = topSymptomSummary()
        let symptomHighlightList = symptomHighlights()

        let visualsSnapshot = spaceVisuals ?? lastKnownSpaceVisuals
        let overlayCount = visualOverlayCount(visualsSnapshot)
        let overlayUpdated = latestVisualTimestamp(visualsSnapshot)
        let outlookAurora = (spaceOutlook ?? lastKnownSpaceOutlook)?
            .data?
            .auroraOutlook?
            .first(where: { ($0.hemisphere ?? "").lowercased() == "north" })
            ?? (spaceOutlook ?? lastKnownSpaceOutlook)?.data?.auroraOutlook?.first
        let outlookPower = outlookAurora?.powerGw
        let auroraPowerValue: Double? = {
            if let v = current.auroraPowerGw?.value { return v }
            if let v = current.auroraPowerNhGw?.value { return v }
            if let v = current.auroraPowerShGw?.value { return v }
            if let v = current.auroraHpNorthGw?.value { return v }
            if let v = current.auroraHpSouthGw?.value { return v }
            if let v = outlookPower { return v }
            return latestAuroraPower(from: visualsSnapshot)
        }()
        let auroraProbability = ContentView.auroraProbabilityText(from: current)
        let auroraWingKp = outlookAurora?.wingKp
        let seriesForCharts = series ?? lastKnownSeries ?? .empty
        let seriesDetail = series ?? lastKnownSeries
        let resolvedOutlook = spaceOutlook ?? lastKnownSpaceOutlook
        let onSelectVisual: (SpaceVisualItem) -> Void = { item in
            prepareInteractiveViewer(for: item)
            showInteractiveViewer = true
        }

        return VStack(spacing: 16) {
            DashboardSleepSectionView(
                current: current,
                todayStr: todayStr,
                usingYesterdayFallback: usingYesterdayFallback,
                bannerText: featuresCachedBannerText
            )
            DashboardHealthStatsSectionView(
                current: current,
                updatedText: updatedText
            )
            DashboardSymptomsSectionView(
                todayCount: symptomsToday.count,
                queuedCount: state.symptomQueueCount,
                sparklinePoints: symptomPoints,
                topSummary: symptomSummary,
                usingYesterdayFallback: usingYesterdayFallback,
                showSymptomSheet: $showSymptomSheet
            )
            DashboardSpaceWeatherSectionView(
                current: current,
                visualsSnapshot: visualsSnapshot,
                overlayCount: overlayCount,
                overlayUpdated: overlayUpdated,
                auroraPowerValue: auroraPowerValue,
                auroraWingKp: auroraWingKp,
                auroraProbabilityText: auroraProbability,
                updatedText: updatedText,
                usingYesterdayFallback: usingYesterdayFallback,
                hazardsBrief: hazardsBrief,
                hazardsLoading: hazardsLoading,
                hazardsError: hazardsError,
                forecast: forecast,
                seriesForCharts: seriesForCharts,
                outlook: resolvedOutlook,
                seriesDetail: seriesDetail,
                quakeLatest: quakeLatest,
                quakeEvents: quakeEvents,
                quakeError: quakeError,
                symptomHighlights: symptomHighlightList,
                showVisualsPreview: AppConfig.showVisualsPreview,
                onSelectVisual: onSelectVisual,
                showSpaceWeatherDetail: $showSpaceWeatherDetail,
                spaceDetailFocus: $spaceDetailFocus,
                showTrends: $showTrends
            )
            DashboardToolsSectionView(
                current: current,
                state: state,
                magnetosphere: magnetosphere,
                magnetosphereLoading: magnetosphereLoading,
                magnetosphereError: magnetosphereError,
                showMagnetosphereDetail: $showMagnetosphereDetail,
                localHealthZip: $localHealthZip,
                localHealth: localHealth,
                localHealthLoading: localHealthLoading,
                localHealthError: localHealthError,
                onRefreshLocalHealth: { Task { await fetchLocalHealth() } },
                showTools: $showTools,
                showConnections: $showConnections,
                showActions: $showActions,
                showBle: $showBle,
                showPolar: $showPolar,
                onFetchVisuals: { Task { await fetchSpaceVisuals() } }
            )
        }
    }

    private struct DashboardSleepSectionView: View {
        let current: FeaturesToday
        let todayStr: String
        let usingYesterdayFallback: Bool
        let bannerText: String?

        var body: some View {
            let total = Int((current.sleepTotalMinutes?.value ?? 0).rounded())
            let isToday = (current.day == todayStr)
            let titleText = isToday ? "Sleep (Today)" : "Sleep (\(current.day))"

            VStack(spacing: 16) {
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

                if let banner = bannerText {
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
            }
        }
    }

    private struct DashboardHealthStatsSectionView: View {
        let current: FeaturesToday
        let updatedText: String?

        var body: some View {
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
                if let txt = updatedText {
                    Text("Updated: \(txt)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.leading, 12)
                        .padding(.bottom, 6)
                }
            }
        }
    }

    private struct DashboardSymptomsSectionView: View {
        let todayCount: Int
        let queuedCount: Int
        let sparklinePoints: [SymptomSparkPoint]
        let topSummary: String?
        let usingYesterdayFallback: Bool
        @Binding var showSymptomSheet: Bool

        var body: some View {
            VStack(spacing: 16) {
                SymptomsTileView(
                    todayCount: todayCount,
                    queuedCount: queuedCount,
                    sparklinePoints: sparklinePoints,
                    topSummary: topSummary,
                    onLogTap: { showSymptomSheet = true }
                )
                .padding(.horizontal)

                if usingYesterdayFallback {
                    Text("Showing yesterday’s data while today updates…")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }
            }
        }
    }

    private struct DashboardSpaceWeatherSectionView: View {
        let current: FeaturesToday
        let visualsSnapshot: SpaceVisualsPayload?
        let overlayCount: Int
        let overlayUpdated: String?
        let auroraPowerValue: Double?
        let auroraWingKp: Double?
        let auroraProbabilityText: String?
        let updatedText: String?
        let usingYesterdayFallback: Bool
        let hazardsBrief: HazardsBriefResponse?
        let hazardsLoading: Bool
        let hazardsError: String?
        let forecast: ForecastSummary?
        let seriesForCharts: SpaceSeries
        let outlook: SpaceForecastOutlook?
        let seriesDetail: SpaceSeries?
        let quakeLatest: QuakeDaily?
        let quakeEvents: [QuakeEvent]
        let quakeError: String?
        let symptomHighlights: [SymptomHighlight]
        let showVisualsPreview: Bool
        let onSelectVisual: (SpaceVisualItem) -> Void
        @Binding var showSpaceWeatherDetail: Bool
        @Binding var spaceDetailFocus: SpaceDetailSection?
        @Binding var showTrends: Bool

        var body: some View {
            VStack(spacing: 16) {
                SpaceWeatherCardSectionView(
                    current: current,
                    visualsSnapshot: visualsSnapshot,
                    overlayCount: overlayCount,
                    overlayUpdated: overlayUpdated,
                    updatedText: updatedText,
                    outlook: outlook,
                    seriesDetail: seriesDetail,
                    showSpaceWeatherDetail: $showSpaceWeatherDetail,
                    spaceDetailFocus: $spaceDetailFocus
                )

                HazardsBriefCard(payload: hazardsBrief, isLoading: hazardsLoading, error: hazardsError)
                    .padding(.horizontal)

                EarthquakesSummaryCard(
                    latest: quakeLatest,
                    events: quakeEvents,
                    error: quakeError
                )
                .padding(.horizontal)

                AuroraThumbsSectionView(
                    auroraPowerValue: auroraPowerValue,
                    auroraWingKp: auroraWingKp,
                    auroraProbabilityText: auroraProbabilityText
                )

                VisualsPreviewSectionView(
                    showVisualsPreview: showVisualsPreview,
                    visualsSnapshot: visualsSnapshot,
                    onSelectVisual: onSelectVisual
                )

                if usingYesterdayFallback {
                    Text("Showing yesterday’s data while today updates…")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }

                AlertsForecastTrendsSectionView(
                    current: current,
                    forecast: forecast,
                    series: seriesForCharts,
                    symptomHighlights: symptomHighlights,
                    showTrends: $showTrends
                )
            }
        }
    }

    private struct SpaceWeatherCardMetrics {
        let kpNow: Double?
        let kpMax: Double?
        let bzNow: Double?
        let swSpeedNow: Double?
        let swSpeedMax: Double?
        let sScale: String?
        let protonFlux: Double?

        private static let isoFmt: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f
        }()

        private static let isoFmtSimple: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            return f
        }()

        private static func parseISO(_ s: String?) -> Date? {
            guard let s else { return nil }
            return isoFmt.date(from: s) ?? isoFmtSimple.date(from: s)
        }

        private static func sScale(for flux: Double?) -> String? {
            guard let f = flux else { return nil }
            if f >= 100000 { return "S5" }
            if f >= 10000 { return "S4" }
            if f >= 1000 { return "S3" }
            if f >= 100 { return "S2" }
            if f >= 10 { return "S1" }
            return "S0"
        }

        init(current: FeaturesToday, outlook: SpaceForecastOutlook?, series: SpaceSeries?) {
            let points = series?.spaceWeather ?? []
            let dated = points.compactMap { point -> (Date, SpacePoint)? in
                guard let d = Self.parseISO(point.ts) else { return nil }
                return (d, point)
            }.sorted { $0.0 < $1.0 }

            let latestPoint = dated.last?.1
            let cutoff = Date().addingTimeInterval(-24 * 3600)
            let last24 = dated.filter { $0.0 >= cutoff }.map { $0.1 }

            let sepFlux = outlook?.data?.sep?.flux
            let sepScaleIndex = outlook?.data?.sep?.sScaleIndex

            kpNow = outlook?.kp?.now
                ?? latestPoint?.kp
                ?? current.kpCurrent?.value
            kpMax = outlook?.kp?.last24hMax
                ?? last24.compactMap { $0.kp }.max()
                ?? current.kpMax?.value
            bzNow = outlook?.bzNow
                ?? latestPoint?.bz
            swSpeedNow = outlook?.swSpeedNowKms
                ?? latestPoint?.sw
                ?? current.swSpeedAvg?.value
            swSpeedMax = last24.compactMap { $0.sw }.max()
                ?? swSpeedNow
                ?? current.swSpeedAvg?.value
            sScale = outlook?.data?.sep?.sScale
                ?? sepScaleIndex.map { "S\(Int($0.rounded()))" }
                ?? Self.sScale(for: sepFlux)
            protonFlux = sepFlux
        }
    }

    private struct SpaceWeatherCardSectionView: View {
        let current: FeaturesToday
        let visualsSnapshot: SpaceVisualsPayload?
        let overlayCount: Int
        let overlayUpdated: String?
        let updatedText: String?
        let outlook: SpaceForecastOutlook?
        let seriesDetail: SpaceSeries?
        @Binding var showSpaceWeatherDetail: Bool
        @Binding var spaceDetailFocus: SpaceDetailSection?

        var body: some View {
            let metrics = SpaceWeatherCardMetrics(current: current, outlook: outlook, series: seriesDetail)
            SpaceWeatherCard(
                kpMax: metrics.kpMax,
                kpCurrent: metrics.kpNow,
                bzNow: metrics.bzNow,
                swSpeedNow: metrics.swSpeedNow,
                swSpeedMax: metrics.swSpeedMax,
                sScale: metrics.sScale,
                protonFlux: metrics.protonFlux,
                flares: Int((current.flaresCount?.value ?? 0).rounded()),
                cmes: Int((current.cmesCount?.value ?? 0).rounded()),
                schStation: current.schStation,
                schF0: current.schF0Hz?.value,
                schF1: current.schF1Hz?.value,
                schF2: current.schF2Hz?.value,
                overlayCount: overlayCount,
                overlayUpdated: overlayUpdated,
                onOpenDetail: { section in
                    spaceDetailFocus = section
                    showSpaceWeatherDetail = true
                }
            )
            .navigationDestination(isPresented: $showSpaceWeatherDetail) {
                SpaceWeatherDetailView(
                    features: current,
                    visuals: visualsSnapshot,
                    outlook: outlook,
                    series: seriesDetail,
                    initialSection: spaceDetailFocus
                )
            }
            .padding(.horizontal)
            .overlay(alignment: .bottomLeading) {
                if let txt = updatedText {
                    Text("Updated: \(txt)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.leading, 12)
                        .padding(.bottom, 6)
                }
            }
        }
    }

    private struct AuroraThumbsSectionView: View {
        let auroraPowerValue: Double?
        let auroraWingKp: Double?
        let auroraProbabilityText: String?
        @State private var viewerPayload: MediaViewerPayload? = nil

        var body: some View {
            let nowNorth = ContentView.resolvedMediaURL("aurora/viewline/tonight-north.png")
            let tonightU = ContentView.resolvedMediaURL("aurora/viewline/tonight.png")
            let tomorrowU = ContentView.resolvedMediaURL("aurora/viewline/tomorrow.png")

            if nowNorth != nil || tonightU != nil || tomorrowU != nil {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Aurora status").font(.subheadline)
                            if let kp = auroraWingKp {
                                Text(String(format: "Wing Kp %.1f", kp))
                            } else {
                                Text("Wing Kp pending")
                            }
                            if let gw = auroraPowerValue {
                                Text(String(format: "Power %.0f GW", gw))
                            }
                            if let prob = auroraProbabilityText {
                                Text("Probability \(prob)")
                            } else {
                                Text("Probability pending")
                            }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
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
                                .onTapGesture {
                                    viewerPayload = MediaViewerPayload(
                                        id: u.absoluteString,
                                        url: u,
                                        title: "Aurora Nowcast",
                                        credit: "NOAA SWPC",
                                        isVideo: false
                                    )
                                }
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
                                .onTapGesture {
                                    viewerPayload = MediaViewerPayload(
                                        id: u.absoluteString,
                                        url: u,
                                        title: "Aurora Forecast (Tonight)",
                                        credit: "NOAA SWPC",
                                        isVideo: false
                                    )
                                }
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
                                .onTapGesture {
                                    viewerPayload = MediaViewerPayload(
                                        id: u.absoluteString,
                                        url: u,
                                        title: "Aurora Forecast (Tomorrow)",
                                        credit: "NOAA SWPC",
                                        isVideo: false
                                    )
                                }
                            }
                        }
                    }
                } label: { Label("Aurora Now & Forecast", systemImage: "sparkles") }
                .padding(.horizontal)
                .fullScreenCover(item: $viewerPayload) { payload in
                    MediaViewerSheet(payload: payload)
                        .ignoresSafeArea()
                }
            }
        }
    }

    private struct VisualsPreviewSectionView: View {
        let showVisualsPreview: Bool
        let visualsSnapshot: SpaceVisualsPayload?
        let onSelectVisual: (SpaceVisualItem) -> Void

        var body: some View {
            if showVisualsPreview, let vs = visualsSnapshot {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Solar Visuals (Preview)").font(.headline)
                        VisualsPreviewGrid(visuals: vs, maxCount: 24) { item in
                            onSelectVisual(item)
                        }
                    }
                } label: { Label("Visuals", systemImage: "photo.on.rectangle") }
                .padding(.horizontal)
            }
        }
    }

    private struct AlertsForecastTrendsSectionView: View {
        let current: FeaturesToday
        let forecast: ForecastSummary?
        let series: SpaceSeries
        let symptomHighlights: [SymptomHighlight]
        @Binding var showTrends: Bool

        var body: some View {
            VStack(spacing: 16) {
                if (current.kpAlert ?? false) || (current.flareAlert ?? false) {
                    SpaceAlertsCard(kpAlert: current.kpAlert ?? false, flareAlert: current.flareAlert ?? false)
                        .padding(.horizontal)
                }

                if let fc = forecast {
                    ForecastCard(summary: fc).padding(.horizontal)
                }
                DisclosureGroup(isExpanded: $showTrends) {
                    SpaceChartsCard(series: series, highlights: symptomHighlights)
                        .padding(.horizontal)
                } label: {
                    HStack {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                        Text("Weekly Trends (Kp, Bz, f0, HR)")
                        Spacer()
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    private struct DashboardToolsSectionView: View {
        let current: FeaturesToday
        @ObservedObject var state: AppState
        let magnetosphere: MagnetosphereData?
        let magnetosphereLoading: Bool
        let magnetosphereError: String?
        @Binding var showMagnetosphereDetail: Bool
        @Binding var localHealthZip: String
        let localHealth: LocalCheckResponse?
        let localHealthLoading: Bool
        let localHealthError: String?
        let onRefreshLocalHealth: () -> Void
        @Binding var showTools: Bool
        @Binding var showConnections: Bool
        @Binding var showActions: Bool
        @Binding var showBle: Bool
        @Binding var showPolar: Bool
        let onFetchVisuals: () -> Void

        var body: some View {
            VStack(spacing: 16) {
                MagnetosphereCard(
                    data: magnetosphere,
                    isLoading: magnetosphereLoading,
                    error: magnetosphereError,
                    onOpenDetail: { showMagnetosphereDetail = true }
                )
                .padding(.horizontal)
                .sheet(isPresented: $showMagnetosphereDetail) {
                    MagnetosphereDetailView(data: magnetosphere)
                }

                EarthscopeCardV2(title: current.postTitle, caption: current.postCaption, images: current.earthscopeImages, bodyMarkdown: current.postBody)
                    .padding(.horizontal)

                LocalHealthCard(
                    zip: $localHealthZip,
                    snapshot: localHealth,
                    isLoading: localHealthLoading,
                    error: localHealthError,
                    onRefresh: onRefreshLocalHealth
                )
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showTools) {
                    VStack(spacing: 12) {
                        ConnectionSettingsSection(state: state, isExpanded: $showConnections)
                        DisclosureGroup(isExpanded: $showActions) {
                            ActionsSection(state: state, onFetchVisuals: onFetchVisuals)
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
            }
        }
    }

    @ViewBuilder
    private var dashboardEmptyView: some View {
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

    private var contentViewBody: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {

                    if let f = (features ?? lastKnownFeatures) {
                        dashboardFeaturesView(f)
                    } else {
                        dashboardEmptyView
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
                async let h: Void = fetchSpaceOutlook()
                async let i: Void = fetchLocalHealth()
                _ = await (a, b, c, h, i)
                try? await Task.sleep(nanoseconds: 350_000_000)
                async let d: Void = fetchSymptoms(api: api)
                async let e: Void = state.flushQueuedSymptoms(api: api)
                async let f: Void = refreshSymptomPresets(api: api)
                async let g: Void = fetchSpaceVisuals()
                async let j: Void = fetchMagnetosphere()
                async let k: Void = fetchQuakes()
                async let l: Void = fetchHazardsBrief()
                _ = await (d, e, f, g, j, k, l)
            }
            .refreshable {
                await state.updateBackendDBFlag()
                let api = state.apiWithAuth()
                let guardRemaining = await MainActor.run { featuresRefreshGuardUntil.timeIntervalSinceNow }
                async let b: Void = fetchForecastSummary()
                async let c: Void = fetchSpaceSeries(days: 30)
                async let h: Void = fetchSpaceOutlook()
                async let i: Void = fetchLocalHealth()
                if guardRemaining > 0 {
                    let remaining = max(1, Int(ceil(guardRemaining)))
                    appLog("[UI] pull-to-refresh: guard active (~\(remaining)s); skipping features refresh")
                    _ = await (b, c, h, i)
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    async let d: Void = fetchSymptoms(api: api)
                    async let e: Void = state.flushQueuedSymptoms(api: api)
                    async let f: Void = refreshSymptomPresets(api: api)
                    async let g: Void = fetchSpaceVisuals()
                    async let j: Void = fetchMagnetosphere()
                    async let k: Void = fetchQuakes()
                    async let l: Void = fetchHazardsBrief()
                    _ = await (d, e, f, g, j, k, l)
                    return
                }
                async let a: Void = fetchFeaturesToday(trigger: .refresh)
                _ = await (a, b, c, h, i)
                try? await Task.sleep(nanoseconds: 300_000_000)
                async let d: Void = fetchSymptoms(api: api)
                async let e: Void = state.flushQueuedSymptoms(api: api)
                async let f: Void = refreshSymptomPresets(api: api)
                async let g: Void = fetchSpaceVisuals()
                async let j: Void = fetchMagnetosphere()
                async let k: Void = fetchQuakes()
                async let l: Void = fetchHazardsBrief()
                _ = await (d, e, f, g, j, k, l)
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
            .onChange(of: localHealthZip, initial: false) { _, newValue in
                let sanitized = sanitizedZip(newValue)
                if sanitized != newValue {
                    localHealthZip = sanitized
                    return
                }
                scheduleLocalHealthRefresh()
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
        private var legacyFallbackBaseURL: URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "LEGACY_MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
            }
            return URL(string: "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main")
        }

        @State private var previewPlayingURL: URL? = nil
        @State private var previewShowPlayer: Bool = false

        // Resolve either absolute or relative paths (e.g., "/drap/latest.png") to a full URL
        private func resolveMediaURL(_ path: String?) -> URL? {
            guard let s = path?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
            if let u = URL(string: s), u.scheme != nil { return u }  // already absolute
            let rel = s.hasPrefix("/") ? String(s.dropFirst()) : s
            func join(base: URL, path: String) -> URL {
                return path.split(separator: "/").reduce(base) { url, seg in
                    url.appendingPathComponent(String(seg))
                }
            }
            if rel.hasPrefix("images/space/"), let legacy = legacyFallbackBaseURL {
                return join(base: legacy, path: rel)
            }
            guard let base = legacyMediaBaseURL else { return URL(string: s) }
            return join(base: base, path: rel)
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
        let kpMax: Double?
        let kpCurrent: Double?
        let bzNow: Double?
        let swSpeedNow: Double?
        let swSpeedMax: Double?
        let sScale: String?
        let protonFlux: Double?
        let flares: Int
        let cmes: Int
        let schStation: String?
        let schF0: Double?
        let schF1: Double?
        let schF2: Double?
        let overlayCount: Int
        let overlayUpdated: String?
        let onOpenDetail: (SpaceDetailSection) -> Void
        var body: some View {
            let kpMaxText = kpMax.map { String(format: "%.1f", $0) } ?? "-"
            let kpNowText = kpCurrent.map { String(format: "%.1f", $0) } ?? "-"
            let bzNowText = bzNow.map { String(format: "%.1f nT", $0) } ?? "-"
            let swNowText = swSpeedNow.map { String(format: "%.0f km/s", $0) } ?? "-"
            let swMaxText = swSpeedMax.map { String(format: "%.0f km/s", $0) } ?? "-"
            let sScaleText = sScale ?? "—"
            let pfuText = protonFlux.map { String(format: "%.1f pfu", $0) } ?? "—"
            let schText = "\(schStation ?? "-") f0 \(schF0.map { String(format: "%.2f", $0) } ?? "-")"
            let schRowSubtitle = "Station \(schStation ?? "—") · f0 \(schF0.map { String(format: "%.2f", $0) } ?? "—")"

            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Space Weather").font(.headline)
                    Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
                        GridRow { Text("Kp Max"); Text(kpMaxText) }
                        GridRow { Text("Kp Now"); Text(kpNowText) }
                        GridRow { Text("Bz Now"); Text(bzNowText) }
                        GridRow { Text("SW Speed Now"); Text(swNowText) }
                        GridRow { Text("SW Speed Max"); Text(swMaxText) }
                        GridRow { Text("S‑Scale"); Text(sScaleText) }
                        GridRow { Text("Proton Flux"); Text(pfuText) }
                        GridRow { Text("Flares"); Text("\(flares)") }
                        GridRow { Text("CMEs"); Text("\(cmes)") }
                        GridRow { Text("Schumann"); Text(schText) }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                    Divider()
                    VStack(spacing: 8) {
                        SpaceStatRow(
                            title: "Solar Visuals",
                            subtitle: "\(overlayCount) visuals · \(overlayUpdated ?? "Latest unknown")",
                            badge: nil,
                            icon: "photo.on.rectangle",
                            action: { onOpenDetail(.visuals) }
                        )
                        SpaceStatRow(
                            title: "Schumann Resonance",
                            subtitle: schRowSubtitle,
                            badge: nil,
                            icon: "waveform.path.ecg",
                            action: { onOpenDetail(.schumann) }
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("Space", systemImage: "sparkles") }
        }
    }

    private struct SpaceWeatherDetailView: View {
        let features: FeaturesToday?
        let visuals: SpaceVisualsPayload?
        let outlook: SpaceForecastOutlook?
        let series: SpaceSeries?
        let initialSection: SpaceDetailSection?

        @Environment(\.dismiss) private var dismiss
        @State private var selectedSection: SpaceDetailSection = .visuals
        @State private var sourceFilter: String = "all"
        @State private var showCredits: Bool = false
        @State private var detailMedia: MediaViewerPayload? = nil

        private var overlayImages: [SpaceVisualImage] {
            let imgs = visuals?.images ?? []
            let filtered = imgs.filter { img in
                let key = img.key?.lowercased() ?? ""
                if key.contains("tomsk") { return false }
                if sourceFilter == "all" { return true }
                let source = img.source?.lowercased() ?? key
                return source.contains(sourceFilter)
            }
            func dedupeKey(_ img: SpaceVisualImage) -> String {
                if let raw = img.url?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty {
                    if let u = URL(string: raw), let host = u.host, !host.isEmpty {
                        return u.path.lowercased()
                    }
                    return raw.lowercased()
                }
                if let path = img.imagePath?.trimmingCharacters(in: .whitespacesAndNewlines), !path.isEmpty {
                    return path.lowercased()
                }
                if let key = img.key?.trimmingCharacters(in: .whitespacesAndNewlines), !key.isEmpty {
                    return key.lowercased()
                }
                return UUID().uuidString
            }
            var seen = Set<String>()
            let deduped = filtered.filter { img in
                let key = dedupeKey(img)
                if seen.contains(key) { return false }
                seen.insert(key)
                return true
            }
            let hasEnlil = deduped.contains { img in
                let key = (img.key ?? "").lowercased()
                let url = (img.url ?? "").lowercased()
                return key.contains("enlil") || url.contains("enlil")
            }
            var enriched = deduped
            if !hasEnlil {
                enriched.insert(
                    SpaceVisualImage(
                        key: "enlil_cme",
                        url: "/nasa/enlil/latest.mp4",
                        capturedAt: nil,
                        caption: "ENLIL CME Propagation",
                        source: "NOAA",
                        credit: "NOAA/WSA–ENLIL+Cone",
                        featureFlags: nil,
                        imagePath: nil,
                        thumb: nil,
                        overlay: nil,
                        mediaType: "video",
                        meta: nil
                    ),
                    at: 0
                )
            }
            let fmt = ISO8601DateFormatter()
            return enriched.sorted { a, b in
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

        private func entryHasContent(_ entry: SpaceOutlookEntry) -> Bool {
            let text = [
                entry.title?.trimmingCharacters(in: .whitespacesAndNewlines),
                entry.summary?.trimmingCharacters(in: .whitespacesAndNewlines),
                entry.driver?.trimmingCharacters(in: .whitespacesAndNewlines),
                entry.metric?.trimmingCharacters(in: .whitespacesAndNewlines)
            ].compactMap { $0 }.filter { !$0.isEmpty }
            let hasMeta = entry.value != nil
                || entry.probability != nil
                || (entry.severity?.isEmpty == false)
                || (entry.region?.isEmpty == false)
                || (entry.windowStart?.isEmpty == false)
                || (entry.windowEnd?.isEmpty == false)
                || (entry.confidence?.isEmpty == false)
                || (entry.metric?.isEmpty == false)
                || (entry.unit?.isEmpty == false)
                || (entry.source?.isEmpty == false)
            return !text.isEmpty || hasMeta
        }

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
                let narrowed = sectionMatch ? section.entries : entries
                return narrowed.filter { entryHasContent($0) }
            }
        }

        private var outlookNotes: [String] {
            (outlook?.notes ?? []).compactMap { note in
                let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
                return trimmed.isEmpty ? nil : trimmed
            }
        }

        private var auroraPowerText: String {
            if let power = features?.auroraPowerGw?.value
                ?? features?.auroraPowerNhGw?.value
                ?? features?.auroraPowerShGw?.value
                ?? features?.auroraHpNorthGw?.value
                ?? features?.auroraHpSouthGw?.value {
                return String(format: "%.1f GW", power)
            }
            if let outlookPower = outlook?.data?.auroraOutlook?
                .first(where: { ($0.hemisphere ?? "").lowercased() == "north" })?.powerGw
                ?? outlook?.data?.auroraOutlook?.first?.powerGw {
                return String(format: "%.1f GW", outlookPower)
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

        private static let detailIsoFmt: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f
        }()
        private static let detailIsoFmtSimple: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            return f
        }()

        private func parseISODate(_ s: String?) -> Date? {
            guard let s else { return nil }
            return Self.detailIsoFmt.date(from: s) ?? Self.detailIsoFmtSimple.date(from: s)
        }

        private func spacePointsWithDates() -> [(Date, SpacePoint)] {
            guard let pts = series?.spaceWeather else { return [] }
            return pts.compactMap { point in
                guard let ts = point.ts, let d = parseISODate(ts) else { return nil }
                return (d, point)
            }.sorted { $0.0 < $1.0 }
        }

        private var latestSpacePoint: SpacePoint? {
            spacePointsWithDates().last?.1
        }

        private var last24hSpacePoints: [SpacePoint] {
            let cutoff = Date().addingTimeInterval(-24 * 3600)
            return spacePointsWithDates().filter { $0.0 >= cutoff }.map { $0.1 }
        }

        private var kpNowValue: Double? {
            outlook?.kp?.now
                ?? latestSpacePoint?.kp
                ?? features?.kpCurrent?.value
        }

        private var kpMax24Value: Double? {
            outlook?.kp?.last24hMax
                ?? last24hSpacePoints.compactMap { $0.kp }.max()
                ?? features?.kpMax?.value
        }

        private var swNowValue: Double? {
            latestSpacePoint?.sw ?? features?.swSpeedAvg?.value
        }

        private var swMax24Value: Double? {
            last24hSpacePoints.compactMap { $0.sw }.max()
        }

        private var bzNowValue: Double? {
            latestSpacePoint?.bz
        }

        private var bzMin24Value: Double? {
            last24hSpacePoints.compactMap { $0.bz }.min()
                ?? features?.bzMin?.value
        }

        private func formatValue(_ value: Double?, decimals: Int = 1, suffix: String = "") -> String {
            guard let value else { return "—" }
            let base = String(format: "%.\(decimals)f", value)
            return suffix.isEmpty ? base : "\(base) \(suffix)"
        }

        private func sScale(for flux: Double?) -> String? {
            guard let f = flux else { return nil }
            if f >= 100000 { return "S5" }
            if f >= 10000 { return "S4" }
            if f >= 1000 { return "S3" }
            if f >= 100 { return "S2" }
            if f >= 10 { return "S1" }
            return "S0"
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
                    Text(entry.title ?? entry.driver ?? entry.metric ?? "Forecast")
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
                        visualsSection
                            .id(SpaceDetailSection.visuals)
                        schumannSection
                            .id(SpaceDetailSection.schumann)
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
                ForEach([SpaceDetailSection.visuals, .schumann], id: \.self) { section in
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
                    Toggle("Show credits", isOn: $showCredits)
                        .font(.caption)
                        .toggleStyle(.switch)
                    if overlayImages.isEmpty {
                        Text("No visuals available yet. Cached gallery will appear here.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        // Grid of visuals (detail view), reusing the same resolver as dashboard preview
                        let cols = [GridItem(.adaptive(minimum: 140), spacing: 12)]
                        LazyVGrid(columns: cols, spacing: 12) {
                            ForEach(Array(overlayImages.prefix(12).enumerated()), id: \.offset) { _, img in
                                VStack(alignment: .leading, spacing: 6) {
                                    if let u = resolveMediaURL_Detail(img) {
                                        let urlStr = u.absoluteString.lowercased()
                                        if urlStr.hasSuffix(".mp4") || urlStr.contains(".mp4?") {
                                            ZStack {
                                                Rectangle().opacity(0.08)
                                                Image(systemName: "play.circle.fill").font(.system(size: 36))
                                            }
                                            .frame(height: 120)
                                            .clipShape(RoundedRectangle(cornerRadius: 10))
                                            .onTapGesture {
                                                detailMedia = MediaViewerPayload(
                                                    id: u.absoluteString,
                                                    url: u,
                                                    title: img.key ?? img.caption ?? "Visual",
                                                    credit: img.credit,
                                                    isVideo: true
                                                )
                                            }
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
                                                    ZStack { Rectangle().opacity(0.08); Image(systemName: "exclamationmark.triangle").foregroundColor(.orange) }
                                                        .frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 10))
                                                @unknown default:
                                                    EmptyView().frame(height: 120)
                                                }
                                            }
                                            .onTapGesture {
                                                detailMedia = MediaViewerPayload(
                                                    id: u.absoluteString,
                                                    url: u,
                                                    title: img.key ?? img.caption ?? "Visual",
                                                    credit: img.credit,
                                                    isVideo: false
                                                )
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
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Solar Visuals", systemImage: "photo.on.rectangle")
            }
            .fullScreenCover(item: $detailMedia) { payload in
                MediaViewerSheet(payload: payload)
                    .ignoresSafeArea()
            }
        }

        private func resolveMediaURL_Detail(_ image: SpaceVisualImage) -> URL? {
            ContentView.resolvedVisualURL(for: image)
        }

        private func resolveMediaPath(_ path: String?) -> URL? {
            guard let raw = path?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
            if let u = URL(string: raw), u.scheme != nil { return u }
            let rel = raw.hasPrefix("/") ? String(raw.dropFirst()) : raw
            func join(base: URL, path: String) -> URL {
                return path.split(separator: "/").reduce(base) { url, seg in
                    url.appendingPathComponent(String(seg))
                }
            }
            if let base = mediaBaseURL_Detail {
                return join(base: base, path: rel)
            }
            return URL(string: raw)
        }

        private var schumannSection: some View {
            let latest = series?.schumannDaily?.last
            let f0 = latest?.f0.map { String(format: "%.2f Hz", $0) } ?? "—"
            let f1 = latest?.f1.map { String(format: "%.2f Hz", $0) } ?? "—"
            let f2 = latest?.f2.map { String(format: "%.2f Hz", $0) } ?? "—"
            let station = latest?.station_id?.capitalized ?? "—"
            let tomskURL = ContentView.resolvedMediaURL("social/earthscope/latest/tomsk_latest.png")
            let cumianaURL = ContentView.resolvedMediaURL("social/earthscope/latest/cumiana_latest.png")
            let schumannURLs = [tomskURL, cumianaURL].compactMap { $0 }

            return GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Schumann Resonance – Scientific Detail")
                        .font(.headline)
                    Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                        GridRow { Text("Station"); Text(station) }
                        GridRow { Text("f0"); Text(f0) }
                        GridRow { Text("f1"); Text(f1) }
                        GridRow { Text("f2"); Text(f2) }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)

                    if !schumannURLs.isEmpty {
                        HStack(spacing: 10) {
                            ForEach(schumannURLs, id: \.self) { url in
                                AsyncImage(url: url) { phase in
                                    switch phase {
                                    case .empty:
                                        ZStack { RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15)); ProgressView() }
                                            .frame(width: 150, height: 100)
                                    case .success(let img):
                                        img.resizable().scaledToFit().frame(width: 150, height: 100).clipShape(RoundedRectangle(cornerRadius: 8))
                                    case .failure:
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(Color.gray.opacity(0.12))
                                            .overlay { Image(systemName: "photo").foregroundColor(.secondary) }
                                            .frame(width: 150, height: 100)
                                    @unknown default:
                                        EmptyView().frame(width: 150, height: 100)
                                    }
                                }
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Health context")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text("• Shifts in EM environment can increase reactivity in sensitives; paced breathing and short outdoor breaks may help.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Keep evenings low‑light and devices dimmed during elevated variability.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Some see HRV dips during geomagnetic activity; hydrate and take short daylight breaks.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Schumann Resonance", systemImage: "waveform.path.ecg")
            }
        }

        private func label(for section: SpaceDetailSection) -> String {
            switch section {
            case .visuals: return "Visuals"
            case .schumann: return "Schumann"
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

    private struct HazardsBriefCard: View {
        let payload: HazardsBriefResponse?
        let isLoading: Bool
        let error: String?

        private func formatUpdated(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            if let d = fmt.date(from: iso) {
                return DateFormatter.localizedString(from: d, dateStyle: .medium, timeStyle: .short)
            }
            return iso
        }

        private func severityCounts(_ items: [HazardItem]) -> (red: Int, orange: Int, yellow: Int, info: Int) {
            var counts = (red: 0, orange: 0, yellow: 0, info: 0)
            for item in items {
                let sev = item.severity?.lowercased() ?? ""
                if sev.contains("red") { counts.red += 1 }
                else if sev.contains("orange") { counts.orange += 1 }
                else if sev.contains("yellow") { counts.yellow += 1 }
                else { counts.info += 1 }
            }
            return counts
        }

        private func typeCounts(_ items: [HazardItem]) -> (quakes: Int, cyclones: Int, volcano: Int, other: Int) {
            var counts = (quakes: 0, cyclones: 0, volcano: 0, other: 0)
            for item in items {
                let kind = item.kind?.lowercased() ?? ""
                if kind.contains("quake") || kind.contains("earth") {
                    counts.quakes += 1
                } else if kind.contains("cyclone") || kind.contains("storm") || kind.contains("severe") {
                    counts.cyclones += 1
                } else if kind.contains("volcano") || kind.contains("ash") {
                    counts.volcano += 1
                } else {
                    counts.other += 1
                }
            }
            return counts
        }

        var body: some View {
            let items = payload?.items ?? []
            let cleanError = ContentView.scrubError(error)
            let sev = severityCounts(items)
            let types = typeCounts(items)

            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Global Hazards Brief")
                            .font(.headline)
                        Spacer()
                        if isLoading { ProgressView().scaleEffect(0.8) }
                    }
                    if let updated = formatUpdated(payload?.generatedAt) {
                        Text("Updated \(updated)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    if let error = cleanError, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    if items.isEmpty && !isLoading && (cleanError == nil || cleanError?.isEmpty == true) {
                        Text("Global Hazards unavailable at the moment.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if !items.isEmpty {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Severity (48h)").font(.subheadline)
                                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
                                    GridRow { Text("RED"); Text("\(sev.red)") }
                                    GridRow { Text("ORANGE"); Text("\(sev.orange)") }
                                    GridRow { Text("YELLOW"); Text("\(sev.yellow)") }
                                    GridRow { Text("INFO"); Text("\(sev.info)") }
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                Text("By Type (48h)").font(.subheadline)
                                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
                                    GridRow { Text("Earthquakes"); Text("\(types.quakes)") }
                                    GridRow { Text("Cyclones/Severe"); Text("\(types.cyclones)") }
                                    GridRow { Text("Volcano/Ash"); Text("\(types.volcano)") }
                                    GridRow { Text("Other"); Text("\(types.other)") }
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            }
                        }

                        Divider()
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Recent Highlights")
                                .font(.subheadline)
                            ForEach(Array(items.prefix(4))) { item in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(item.title ?? item.location ?? "—")
                                        .font(.caption)
                                    if let severity = item.severity, !severity.isEmpty {
                                        Text(severity)
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Hazards", systemImage: "exclamationmark.triangle.fill")
            }
        }
    }

    private struct EarthquakesSummaryCard: View {
        let latest: QuakeDaily?
        let events: [QuakeEvent]
        let error: String?

        private func summaryText() -> String {
            let count = latest?.allQuakes
            let maxEvent = events.max { ($0.mag ?? 0) < ($1.mag ?? 0) }
            let mag = maxEvent?.mag
            let region = maxEvent?.place
            var parts: [String] = []
            if let count { parts.append(count == 1 ? "1 quake" : "\(count) quakes") }
            if let mag { parts.append(String(format: "max M%.1f", mag)) }
            if let region, !region.isEmpty { parts.append(region) }
            return parts.isEmpty ? "Live quake feed" : parts.joined(separator: " · ")
        }

        private func shortTime(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            let fmt2 = ISO8601DateFormatter()
            fmt2.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let d = fmt2.date(from: iso) ?? fmt.date(from: iso) {
                return DateFormatter.localizedString(from: d, dateStyle: .medium, timeStyle: .short)
            }
            return iso
        }

        var body: some View {
            let cleanError = ContentView.scrubError(error)
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text(summaryText())
                        .font(.subheadline)
                    if let error = cleanError, !error.isEmpty {
                        Text(error)
                            .font(.caption2)
                            .foregroundColor(.orange)
                    }
                    if !events.isEmpty {
                        Divider()
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(Array(events.prefix(4).enumerated()), id: \.offset) { _, event in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("M\(event.mag.map { String(format: "%.1f", $0) } ?? "—") • \(event.place ?? "Unknown location")")
                                        .font(.caption)
                                    if let t = shortTime(event.timeUtc) {
                                        Text(t)
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }
                    }
                    NavigationLink("View details") {
                        EarthquakesDetailView(latest: latest, events: events, error: error)
                    }
                    .font(.caption)
                    .underline()
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Earthquakes", systemImage: "waveform.path")
            }
        }
    }

    private struct EarthquakesDetailView: View {
        let latest: QuakeDaily?
        let events: [QuakeEvent]
        let error: String?

        private func summaryText() -> String {
            let count = latest?.allQuakes
            let maxEvent = events.max { ($0.mag ?? 0) < ($1.mag ?? 0) }
            let mag = maxEvent?.mag
            let region = maxEvent?.place
            var parts: [String] = []
            if let count { parts.append(count == 1 ? "1 quake" : "\(count) quakes") }
            if let mag { parts.append(String(format: "max M%.1f", mag)) }
            if let region, !region.isEmpty { parts.append(region) }
            return parts.isEmpty ? "Live quake feed" : parts.joined(separator: " · ")
        }

        private func shortTime(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            let fmt2 = ISO8601DateFormatter()
            fmt2.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let d = fmt2.date(from: iso) ?? fmt.date(from: iso) {
                return DateFormatter.localizedString(from: d, dateStyle: .medium, timeStyle: .short)
            }
            return iso
        }

        var body: some View {
            let cleanError = ContentView.scrubError(error)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(summaryText())
                        .font(.headline)
                    if let error = cleanError, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    if events.isEmpty {
                        Text("No recent quake events available.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        ForEach(Array(events.prefix(20).enumerated()), id: \.offset) { _, event in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("M\(event.mag.map { String(format: "%.1f", $0) } ?? "—") • \(event.place ?? "Unknown location")")
                                    .font(.subheadline)
                                HStack(spacing: 10) {
                                    if let t = shortTime(event.timeUtc) {
                                        Text(t)
                                    }
                                    if let depth = event.depthKm {
                                        Text(String(format: "%.0f km depth", depth))
                                    }
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    Text("Tap Earthscope on the dashboard for the full journal and quake context.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.top, 6)
                }
                .padding()
            }
            .navigationTitle("Earthquakes")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct LocalHealthCard: View {
        @Binding var zip: String
        let snapshot: LocalCheckResponse?
        let isLoading: Bool
        let error: String?
        let onRefresh: () -> Void

        private func formatNumber(_ value: Double?, decimals: Int = 1) -> String {
            guard let value else { return "—" }
            return String(format: "%.\(decimals)f", value)
        }

        private func formatTemp(_ celsius: Double?) -> String {
            guard let c = celsius else { return "—" }
            let f = (c * 9.0/5.0) + 32.0
            return "\(String(format: "%.1f", c)) °C (\(String(format: "%.1f", f)) °F)"
        }

        private func formatTempDelta(_ celsius: Double?) -> String {
            guard let c = celsius else { return "—" }
            let f = c * 9.0/5.0
            return "\(String(format: "%.1f", c)) °C (\(String(format: "%.1f", f)) °F)"
        }

        private func formatPressure(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            let inHg = hpa * 0.02953
            return "\(String(format: "%.1f", hpa)) hPa (\(String(format: "%.2f", inHg)) inHg)"
        }

        private func formatPressureDelta(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            let inHg = hpa * 0.02953
            return "\(String(format: "%.1f", hpa)) hPa (\(String(format: "%.2f", inHg)) inHg)"
        }

        private func formatPercent(_ value: Double?) -> String {
            guard let value else { return "—" }
            return "\(String(format: "%.0f", value)) %"
        }

        private func formatBaroTrend(_ trend: String?) -> String {
            guard let trend, !trend.isEmpty else { return "—" }
            switch trend.lowercased() {
            case "rising": return "↑ rising"
            case "falling": return "↓ falling"
            case "steady": return "→ steady"
            default: return trend
            }
        }

        private func asofText(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            if let d = fmt.date(from: iso) {
                return DateFormatter.localizedString(from: d, dateStyle: .medium, timeStyle: .short)
            }
            return nil
        }

        var body: some View {
            let weather = snapshot?.weather
            let air = snapshot?.air
            let moon = snapshot?.moon
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        Text("Local Health (\(zip.isEmpty ? "ZIP" : zip))")
                            .font(.headline)
                        Spacer()
                        if isLoading { ProgressView().scaleEffect(0.8) }
                        Button("Refresh") { onRefresh() }
                            .font(.caption)
                    }
                    HStack(spacing: 8) {
                        TextField("ZIP", text: $zip)
                            .keyboardType(.numbersAndPunctuation)
                            .textFieldStyle(.roundedBorder)
                            .frame(maxWidth: 120)
                            .onSubmit { onRefresh() }
                        if let asof = asofText(snapshot?.asof) {
                            Text("as of \(asof)")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    if let error, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    if snapshot == nil && !isLoading && (error == nil || error?.isEmpty == true) {
                        Text("Local health unavailable.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Weather").font(.subheadline)
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                            GridRow { Text("Temp"); Text(formatTemp(weather?.tempC)) }
                            GridRow { Text("24h Δ"); Text(formatTempDelta(weather?.tempDelta24hC)) }
                            GridRow { Text("Humidity"); Text(formatPercent(weather?.humidityPct)) }
                            GridRow { Text("Precip"); Text(formatPercent(weather?.precipProbPct)) }
                            GridRow { Text("Pressure"); Text(formatPressure(weather?.pressureHpa)) }
                            GridRow { Text("Baro 24h Δ"); Text(formatPressureDelta(weather?.baroDelta24hHpa)) }
                            GridRow { Text("Baro trend"); Text(formatBaroTrend(weather?.pressureTrend ?? weather?.baroTrend)) }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }

                    Divider()
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Air Quality").font(.subheadline)
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                            GridRow { Text("AQI"); Text(formatNumber(air?.aqi, decimals: 0)) }
                            GridRow { Text("Category"); Text(air?.category ?? "—") }
                            GridRow { Text("Pollutant"); Text(air?.pollutant ?? "—") }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }

                    Divider()
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Moon").font(.subheadline)
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                            GridRow { Text("Phase"); Text(moon?.phase ?? "—") }
                            GridRow {
                                Text("Illumination")
                                Text(moon?.illum.map { "\(String(format: "%.0f", $0 * 100)) %" } ?? "—")
                            }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Local Health", systemImage: "location.fill")
            }
        }
    }

    private struct MagnetosphereCard: View {
        let data: MagnetosphereData?
        let isLoading: Bool
        let error: String?
        let onOpenDetail: () -> Void

        private func formatValue(_ value: Double?, decimals: Int = 1, suffix: String = "") -> String {
            guard let value else { return "—" }
            let base = String(format: "%.\(decimals)f", value)
            return suffix.isEmpty ? base : "\(base) \(suffix)"
        }

        private func formatTimestamp(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            if let d = fmt.date(from: iso) {
                return DateFormatter.localizedString(from: d, dateStyle: .medium, timeStyle: .short)
            }
            return nil
        }

        var body: some View {
            let cleanError = ContentView.scrubError(error)
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Magnetosphere Status").font(.headline)
                        Spacer()
                        if isLoading { ProgressView().scaleEffect(0.8) }
                        Button("View detail") { onOpenDetail() }
                            .font(.caption)
                    }
                    if let stamp = formatTimestamp(data?.ts) {
                        Text("Updated: \(stamp)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    if let error = cleanError, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    if data == nil && !isLoading && (cleanError == nil || cleanError?.isEmpty == true) {
                        Text("Magnetosphere data unavailable.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    if let kpis = data?.kpis {
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                            GridRow { Text("R0"); Text(formatValue(kpis.r0Re, suffix: "Re")) }
                            GridRow { Text("Plasmapause"); Text(formatValue(kpis.lppRe, suffix: "Re")) }
                            GridRow { Text("GEO risk"); Text(kpis.geoRisk ?? "—") }
                            GridRow { Text("Storminess"); Text(kpis.storminess ?? "—") }
                            GridRow { Text("GIC feel"); Text(kpis.dbdt ?? "—") }
                            GridRow { Text("Kp"); Text(formatValue(kpis.kp, decimals: 1)) }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }
                    if let sw = data?.sw {
                        Divider()
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                            GridRow { Text("Density"); Text(formatValue(sw.nCm3, suffix: "cm^-3")) }
                            GridRow { Text("Speed"); Text(formatValue(sw.vKms, decimals: 0, suffix: "km/s")) }
                            GridRow { Text("Bz"); Text(formatValue(sw.bzNt, decimals: 1, suffix: "nT")) }
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Magnetosphere", systemImage: "shield.fill")
            }
        }
    }

    private struct MagnetosphereDetailView: View {
        let data: MagnetosphereData?
        @Environment(\.dismiss) private var dismiss

        private func resolveMediaURL(_ path: String) -> URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty {
                    let base = URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s)
                    let rel = path.hasPrefix("/") ? String(path.dropFirst()) : path
                    if let base {
                        return rel.split(separator: "/").reduce(base) { url, seg in
                            url.appendingPathComponent(String(seg))
                        }
                    }
                }
            }
            let base = URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
            let rel = path.hasPrefix("/") ? String(path.dropFirst()) : path
            if let base {
                return rel.split(separator: "/").reduce(base) { url, seg in
                    url.appendingPathComponent(String(seg))
                }
            }
            return nil
        }

        private func chartPoints() -> [(Date, Double)] {
            let fmt = ISO8601DateFormatter()
            return (data?.series?.r0 ?? []).compactMap { point in
                guard let t = point.t, let v = point.v, let d = fmt.date(from: t) else { return nil }
                return (d, v)
            }
        }

        var body: some View {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if data == nil {
                            Text("No magnetosphere data available yet.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        if let ts = data?.ts {
                            Text("Updated: \(ts)")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        if let kpis = data?.kpis {
                            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                                GridRow { Text("R0"); Text(kpis.r0Re.map { String(format: "%.1f Re", $0) } ?? "—") }
                                GridRow { Text("Plasmapause"); Text(kpis.lppRe.map { String(format: "%.1f Re", $0) } ?? "—") }
                                GridRow { Text("GEO risk"); Text(kpis.geoRisk ?? "—") }
                                GridRow { Text("Storminess"); Text(kpis.storminess ?? "—") }
                                GridRow { Text("GIC feel"); Text(kpis.dbdt ?? "—") }
                                GridRow { Text("Kp"); Text(kpis.kp.map { String(format: "%.1f", $0) } ?? "—") }
                            }
                            .font(.caption)
                            .foregroundColor(.secondary)
                        }

                        if !chartPoints().isEmpty {
                            Text("Shield Edge (R0) - last 24h")
                                .font(.subheadline)
                            Chart(chartPoints(), id: \.0) { point in
                                LineMark(
                                    x: .value("Time", point.0),
                                    y: .value("R0", point.1)
                                )
                                .interpolationMethod(.catmullRom)
                            }
                            .frame(height: 180)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Geospace visuals")
                                .font(.subheadline)
                            HStack(spacing: 10) {
                                ForEach(["magnetosphere/geospace/1d.png",
                                         "magnetosphere/geospace/3h.png",
                                         "magnetosphere/geospace/7d.png"], id: \.self) { path in
                                    if let url = resolveMediaURL(path) {
                                        AsyncImage(url: url) { phase in
                                            switch phase {
                                            case .empty:
                                                ZStack { RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15)); ProgressView() }
                                                    .frame(width: 110, height: 80)
                                            case .success(let img):
                                                img.resizable().scaledToFit().frame(width: 110, height: 80).clipShape(RoundedRectangle(cornerRadius: 8))
                                            case .failure:
                                                RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.12)).overlay { Image(systemName: "photo").foregroundColor(.secondary) }
                                                    .frame(width: 110, height: 80)
                                            @unknown default:
                                                EmptyView().frame(width: 110, height: 80)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .padding()
                }
                .navigationTitle("Magnetosphere")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { dismiss() }
                    }
                }
            }
        }
    }

    private struct EarthscopeCardV2: View {
        let title: String?
        let caption: String?
        let images: Any?
        let bodyMarkdown: String?
        @State private var showFull: Bool = false
        @State private var reelPlayer: AVPlayer? = nil

        private func earthscopeBaseURL() -> URL? {
            if let raw = Bundle.main.object(forInfoDictionaryKey: "MEDIA_BASE_URL") as? String {
                let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { return URL(string: s.hasSuffix("/") ? String(s.dropLast()) : s) }
            }
            return URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals")
        }

        private func resolveEarthscopeURL(_ raw: String?) -> URL? {
            guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            if let u = URL(string: raw), u.scheme != nil { return u }
            let rel = raw.hasPrefix("/") ? String(raw.dropFirst()) : raw
            guard let base = earthscopeBaseURL() else { return URL(string: raw) }
            return rel.split(separator: "/").reduce(base) { url, seg in
                url.appendingPathComponent(String(seg))
            }
        }

        private var earthscopeReelURL: URL? {
            resolveEarthscopeURL("social/earthscope/reels/latest/latest.mp4")
        }

        // Extract URLs from multiple possible shapes
        private func extractImageURLs() -> [URL] {
            var urls: [URL] = []
            // 1) Direct dictionary [String:String]
            if let dict = images as? [String:String] {
                ["caption","stats","affects","playbook"].forEach { k in
                    if let u = resolveEarthscopeURL(dict[k]) { urls.append(u) }
                }
            }
            // 2) Dictionary [String:Any]
            else if let dict = images as? [String:Any] {
                ["caption","stats","affects","playbook"].forEach { k in
                    if let s = dict[k] as? String, let u = resolveEarthscopeURL(s) { urls.append(u) }
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
                    if let s = map[k], let u = resolveEarthscopeURL(s) { urls.append(u) }
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

                    if let reelURL = earthscopeReelURL {
                        VideoPlayer(player: reelPlayer ?? AVPlayer(url: reelURL))
                            .aspectRatio(9.0 / 16.0, contentMode: .fit)
                            .frame(maxWidth: .infinity)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .onAppear {
                                if reelPlayer == nil {
                                    reelPlayer = AVPlayer(url: reelURL)
                                }
                            }
                    }

                    if let body = bodyMarkdown, !body.isEmpty {
                        Text(body)
                            .font(.footnote)
                            .foregroundColor(.secondary)
                            .lineLimit(6)
                            .padding(8)
                            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }

                    Button("Read today's Earthscope") { showFull = true }
                        .font(.caption)
                        .underline()
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
                        if let b = bodyText, !b.isEmpty { Text(b).font(.body) }
                        if !urls.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Daily visuals")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
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
