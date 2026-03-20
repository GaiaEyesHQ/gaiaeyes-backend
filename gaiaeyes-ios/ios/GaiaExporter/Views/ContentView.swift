import SwiftUI
import AVKit
#if canImport(UIKit)
import UIKit
#endif
#if canImport(CoreLocation)
import CoreLocation
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

private struct LocalCheckResponse: Decodable {
    let ok: Bool?
    let whereInfo: LocalWhere?
    let weather: LocalWeather?
    let air: LocalAir?
    let moon: LocalMoon?
    let forecastDaily: [LocalForecastDay]?
    let asof: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok, weather, air, moon, asof, error, forecastDaily
        case whereInfo = "where"
    }
}

private struct LocalWhere: Decodable {
    let zip: String?
    let lat: Double?
    let lon: Double?
}

private struct LocalWeather: Decodable {
    let tempC: Double?
    let tempDelta24hC: Double?
    let humidityPct: Double?
    let precipProbPct: Double?
    let pressureHpa: Double?
    let baroDelta24hHpa: Double?
    let pressureTrend: String?
    let baroTrend: String?

    private enum CodingKeys: String, CodingKey {
        case tempC
        case tempCSnake = "temp_c"
        case tempDelta24hC
        case tempDelta24HC = "tempDelta24HC"
        case tempDelta24hCSnake = "temp_delta_24h_c"
        case humidityPct
        case humidityPctSnake = "humidity_pct"
        case precipProbPct
        case precipProbPctSnake = "precip_prob_pct"
        case pressureHpa
        case pressureHpaSnake = "pressure_hpa"
        case baroDelta24hHpa
        case baroDelta24HHpa = "baroDelta24HHpa"
        case baroDelta24hHpaSnake = "baro_delta_24h_hpa"
        case pressureTrend
        case pressureTrendSnake = "pressure_trend"
        case baroTrend
        case baroTrendSnake = "baro_trend"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        tempC = Self.decodeDouble(from: container, keys: [.tempC, .tempCSnake])
        tempDelta24hC = Self.decodeDouble(from: container, keys: [.tempDelta24hC, .tempDelta24HC, .tempDelta24hCSnake])
        humidityPct = Self.decodeDouble(from: container, keys: [.humidityPct, .humidityPctSnake])
        precipProbPct = Self.decodeDouble(from: container, keys: [.precipProbPct, .precipProbPctSnake])
        pressureHpa = Self.decodeDouble(from: container, keys: [.pressureHpa, .pressureHpaSnake])
        baroDelta24hHpa = Self.decodeDouble(from: container, keys: [.baroDelta24hHpa, .baroDelta24HHpa, .baroDelta24hHpaSnake])
        pressureTrend = Self.decodeString(from: container, keys: [.pressureTrend, .pressureTrendSnake])
        baroTrend = Self.decodeString(from: container, keys: [.baroTrend, .baroTrendSnake])
    }

    init(
        tempC: Double?,
        tempDelta24hC: Double?,
        humidityPct: Double?,
        precipProbPct: Double?,
        pressureHpa: Double?,
        baroDelta24hHpa: Double?,
        pressureTrend: String?,
        baroTrend: String?
    ) {
        self.tempC = tempC
        self.tempDelta24hC = tempDelta24hC
        self.humidityPct = humidityPct
        self.precipProbPct = precipProbPct
        self.pressureHpa = pressureHpa
        self.baroDelta24hHpa = baroDelta24hHpa
        self.pressureTrend = pressureTrend
        self.baroTrend = baroTrend
    }

    private static func decodeDouble(
        from container: KeyedDecodingContainer<CodingKeys>,
        keys: [CodingKeys]
    ) -> Double? {
        for key in keys {
            if let value = try? container.decodeIfPresent(Double.self, forKey: key) {
                return value
            }
        }
        return nil
    }

    private static func decodeString(
        from container: KeyedDecodingContainer<CodingKeys>,
        keys: [CodingKeys]
    ) -> String? {
        for key in keys {
            if let value = try? container.decodeIfPresent(String.self, forKey: key) {
                return value
            }
        }
        return nil
    }
}

private struct LocalAir: Decodable {
    let aqi: Double?
    let category: String?
    let pollutant: String?
}

private struct LocalMoon: Decodable {
    let phase: String?
    let illum: Double?
    let cycle: Double?
}

private struct LocalForecastDay: Codable, Hashable, Identifiable {
    let locationKey: String?
    let day: String?
    let source: String?
    let issuedAt: String?
    let locationZip: String?
    let lat: Double?
    let lon: Double?
    let tempHighC: Double?
    let tempLowC: Double?
    let tempDeltaFromPriorDayC: Double?
    let pressureHpa: Double?
    let pressureDeltaFromPriorDayHpa: Double?
    let humidityAvg: Double?
    let precipProbability: Double?
    let windSpeed: Double?
    let windGust: Double?
    let conditionCode: String?
    let conditionSummary: String?
    let aqiForecast: Double?
    let updatedAt: String?

    var id: String { "\(locationKey ?? "local")|\(day ?? "day")" }
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

        let parts = [url, title, source, kind, location, severity, startedAt]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        id = parts.isEmpty ? UUID().uuidString : parts.joined(separator: "|")
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

private struct DashboardGaugeSet: Codable, Hashable {
    let pain: Double?
    let focus: Double?
    let heart: Double?
    let stamina: Double?
    let energy: Double?
    let sleep: Double?
    let mood: Double?
    let healthStatus: Double?

    private enum CodingKeys: String, CodingKey {
        case pain, focus, heart, stamina, energy, sleep, mood
        case healthStatus
    }
}

private struct DashboardGaugeMeta: Codable, Hashable {
    let zone: String?
    let label: String?
}

private struct DashboardGaugeZone: Codable, Hashable {
    let min: Double
    let max: Double
    let key: String

    static let defaultZones: [DashboardGaugeZone] = [
        DashboardGaugeZone(min: 0, max: 29, key: "low"),
        DashboardGaugeZone(min: 30, max: 59, key: "mild"),
        DashboardGaugeZone(min: 60, max: 79, key: "elevated"),
        DashboardGaugeZone(min: 80, max: 100, key: "high"),
    ]
}

private struct DashboardAlertItem: Codable, Hashable, Identifiable {
    var id: String {
        let parts = [key, title, severity].compactMap { $0 }.joined(separator: "|")
        return parts.isEmpty ? "dashboard_alert" : parts
    }
    let key: String?
    let title: String?
    let severity: String?
    let suggestedActions: [String]?

    private enum CodingKeys: String, CodingKey {
        case key, title, severity
        case suggestedActions
    }
}

private struct DashboardPatternRef: Codable, Hashable, Identifiable {
    let id: String
    let driverKey: String?
    let signalKey: String?
    let signal: String?
    let outcomeKey: String?
    let outcome: String?
    let confidence: String?
    let usedToday: Bool?
    let usedTodayLabel: String?
    let relevanceScore: Double?
    let explanation: String?
}

private struct DashboardGaugeRelevanceItem: Codable, Hashable, Identifiable {
    let gaugeKey: String
    let gaugeLabel: String?
    let summary: String?
    let activePatternRefs: [DashboardPatternRef]?

    var id: String { gaugeKey }
}

private struct DashboardPersonalTheme: Codable, Hashable, Identifiable {
    let key: String
    let label: String
    let score: Double?
    let summary: String?

    var id: String { key }
}

private struct DashboardTodayRelevanceExplanations: Codable, Hashable {
    let primaryDriver: String?
    let supportingDrivers: [String]?
    let dailyBrief: String?
}

private struct DashboardDriverItem: Codable, Hashable, Identifiable {
    let key: String
    let label: String?
    let severity: String?
    let state: String?
    let value: Double?
    let unit: String?
    let display: String?
    let role: String?
    let roleLabel: String?
    let rawSeverityScore: Double?
    let personalRelevanceScore: Double?
    let personalReason: String?
    let activePatternRefs: [DashboardPatternRef]?

    var id: String { key }
}

private struct DashboardModalCTA: Codable, Hashable {
    let label: String?
    let action: String?
    let prefill: [String]?
}

private struct DashboardQuickLogOption: Codable, Hashable, Identifiable {
    let code: String
    let label: String

    var id: String { "\(code)|\(label)" }
}

private struct DashboardQuickLog: Codable, Hashable {
    let title: String?
    let confirmLabel: String?
    let options: [DashboardQuickLogOption]?
    let defaultSeverity: Int?
    let baseTags: [String]?
}

private struct DashboardModalEntry: Codable, Hashable {
    let modalType: String?
    let title: String?
    let body: String?
    let tip: String?
    let why: [String]?
    let whatYouMayNotice: [String]?
    let suggestedActions: [String]?
    let quickLog: DashboardQuickLog?
    let cta: DashboardModalCTA?
}

private struct DashboardModalModels: Codable, Hashable {
    let gauges: [String: DashboardModalEntry]?
    let drivers: [String: DashboardModalEntry]?
}

private struct DashboardEarthscopePost: Codable, Hashable {
    let day: String?
    let title: String?
    let caption: String?
    let bodyMarkdown: String?
    let updatedAt: String?

    private enum CodingKeys: String, CodingKey {
        case day, title, caption
        case bodyMarkdown
        case updatedAt
    }
}

private struct DashboardPayload: Codable {
    let day: String?
    let gauges: DashboardGaugeSet?
    let gaugesMeta: [String: DashboardGaugeMeta]?
    let gaugeZones: [DashboardGaugeZone]?
    let gaugeLabels: [String: String]?
    let gaugesDelta: [String: Int]?
    let drivers: [DashboardDriverItem]?
    let driversCompact: [String]?
    let primaryDriver: DashboardDriverItem?
    let supportingDrivers: [DashboardDriverItem]?
    let patternRelevantGauges: [DashboardGaugeRelevanceItem]?
    let activePatternRefs: [DashboardPatternRef]?
    let todayPersonalThemes: [DashboardPersonalTheme]?
    let todayRelevanceExplanations: DashboardTodayRelevanceExplanations?
    let modalModels: DashboardModalModels?
    let earthscopeSummary: String?
    let alerts: [DashboardAlertItem]?
    let entitled: Bool?
    let memberPost: DashboardEarthscopePost?
    let publicPost: DashboardEarthscopePost?
    let personalPost: DashboardEarthscopePost?

    private enum CodingKeys: String, CodingKey {
        case day, gauges, gaugesMeta, gaugeZones, gaugeLabels, gaugesDelta, drivers, driversCompact, primaryDriver, supportingDrivers, patternRelevantGauges, activePatternRefs, todayPersonalThemes, todayRelevanceExplanations, modalModels, earthscopeSummary, alerts, entitled
        case memberPost
        case publicPost
        case personalPost
    }
}

private struct UserPatternCard: Decodable, Hashable, Identifiable {
    let signalKey: String
    let signal: String
    let outcomeKey: String
    let outcome: String
    let explanation: String
    let confidence: String?
    let sampleSize: Int?
    let lagHours: Int?
    let lagLabel: String?
    let lastSeenAt: String?
    let relativeLift: Double?
    let exposedRate: Double?
    let unexposedRate: Double?
    let rateDiff: Double?
    let exposedDays: Int?
    let unexposedDays: Int?
    let thresholdValue: Double?
    let thresholdOperator: String?
    let thresholdText: String?
    let usedToday: Bool?
    let usedTodayLabel: String?

    var id: String {
        "\(signalKey)|\(outcomeKey)|\(lagHours ?? 0)"
    }
}

private struct UserPatternsPayload: Decodable {
    let ok: Bool?
    let generatedAt: String?
    let disclaimer: String?
    let strongestPatterns: [UserPatternCard]?
    let emergingPatterns: [UserPatternCard]?
    let bodySignalsPatterns: [UserPatternCard]?
}

private struct MemberEarthscopeMetricsPayload: Decodable {
    let gauges: DashboardGaugeSet?
}

private struct MemberEarthscopePostPayload: Decodable {
    let day: String?
    let title: String?
    let caption: String?
    let bodyMarkdown: String?
    let updatedAt: String?
    let metricsJson: MemberEarthscopeMetricsPayload?
}

private struct MemberEarthscopeEnvelope: Decodable {
    let ok: Bool?
    let post: MemberEarthscopePostPayload?
}

private struct ProfileLocation: Codable {
    let zip: String?
    let lat: Double?
    let lon: Double?
    let useGps: Bool?
    let localInsightsEnabled: Bool?

    private enum CodingKeys: String, CodingKey {
        case zip, lat, lon
        case useGps
        case localInsightsEnabled
    }
}

private struct ProfileLocationEnvelope: Codable {
    let ok: Bool?
    let location: ProfileLocation?
}

private struct ProfileLocationUpsert: Codable {
    let zip: String?
    let lat: Double?
    let lon: Double?
    let useGps: Bool?
    let localInsightsEnabled: Bool?

    private enum CodingKeys: String, CodingKey {
        case zip, lat, lon
        case useGps = "use_gps"
        case localInsightsEnabled = "local_insights_enabled"
    }
}

private struct TagCatalogItem: Decodable, Hashable, Identifiable {
    var id: String { tagKey }
    let tagKey: String
    let label: String?
    let description: String?
    let section: String?

    private enum CodingKeys: String, CodingKey {
        case tagKey
        case tagKeySnake = "tag_key"
        case label, description, section
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let camelKey = try c.decodeIfPresent(String.self, forKey: .tagKey)
        let snakeKey = try c.decodeIfPresent(String.self, forKey: .tagKeySnake)
        let resolvedKey = (camelKey ?? snakeKey ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if resolvedKey.isEmpty {
            throw DecodingError.keyNotFound(
                CodingKeys.tagKey,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Missing tagKey/tag_key")
            )
        }
        tagKey = resolvedKey
        label = try c.decodeIfPresent(String.self, forKey: .label)
        description = try c.decodeIfPresent(String.self, forKey: .description)
        section = try c.decodeIfPresent(String.self, forKey: .section)
    }
}

private struct TagCatalogEnvelope: Decodable {
    let ok: Bool?
    let items: [TagCatalogItem]?
}

private struct UserTagsEnvelope: Codable {
    let ok: Bool?
    let tags: [String]?
}

private struct UserTagsUpsert: Codable {
    let tags: [String]
}

private let healthContextTagKeys: Set<String> = [
    "migraine_history",
    "chronic_pain",
    "arthritis",
    "fibromyalgia",
    "hypermobility_eds",
    "pots_dysautonomia",
    "mcas_histamine",
    "allergies_sinus",
    "asthma_breathing_sensitive",
    "heart_rhythm_sensitive",
    "autoimmune_condition",
    "nervous_system_dysregulation",
    "insomnia_sleep_disruption",
]

private func canonicalProfileTagKey(_ raw: String) -> String {
    let normalized = raw
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "-", with: "_")
        .replacingOccurrences(of: " ", with: "_")
    switch normalized {
    case "aqi_sensitive":
        return "air_quality_sensitive"
    case "temp_sensitive":
        return "temperature_sensitive"
    default:
        return normalized
    }
}

private struct DiscardValue: Decodable {}

private struct LossyArray<Element: Decodable>: Decodable {
    let values: [Element]

    init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        var items: [Element] = []
        while !container.isAtEnd {
            if let item = try? container.decode(Element.self) {
                items.append(item)
            } else {
                _ = try? container.decode(DiscardValue.self)
            }
        }
        values = items
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleDouble(forKey key: Key) -> Double? {
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return Double(value)
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return Double(value.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
    }

    func decodeFlexibleInt(forKey key: Key) -> Int? {
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return Int(value.rounded())
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return Int(value.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
    }

    func decodeFlexibleBool(forKey key: Key) -> Bool? {
        if let value = try? decodeIfPresent(Bool.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value != 0
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["true", "t", "yes", "y", "1"].contains(normalized) { return true }
            if ["false", "f", "no", "n", "0"].contains(normalized) { return false }
        }
        return nil
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

    private static func decodeDouble(_ container: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Double? {
        if let value = try? container.decodeIfPresent(Double.self, forKey: key) {
            return value
        }
        if let intValue = try? container.decodeIfPresent(Int.self, forKey: key) {
            return Double(intValue)
        }
        if let stringValue = try? container.decodeIfPresent(String.self, forKey: key) {
            return Double(stringValue.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.title = try container.decodeIfPresent(String.self, forKey: .title)
        self.summary = try container.decodeIfPresent(String.self, forKey: .summary)
        self.probability = Self.decodeDouble(container, forKey: .probability)
        self.confidence = try container.decodeIfPresent(String.self, forKey: .confidence)
        self.severity = try container.decodeIfPresent(String.self, forKey: .severity)
        self.region = try container.decodeIfPresent(String.self, forKey: .region)
        self.windowStart = try container.decodeIfPresent(String.self, forKey: .windowStart)
        self.windowEnd = try container.decodeIfPresent(String.self, forKey: .windowEnd)
        self.issuedAt = try container.decodeIfPresent(String.self, forKey: .issuedAt)
        self.driver = try container.decodeIfPresent(String.self, forKey: .driver)
        self.metric = try container.decodeIfPresent(String.self, forKey: .metric)
        self.value = Self.decodeDouble(container, forKey: .value)
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
    var id: String {
        let parts = [ts, src, message].compactMap { $0 }.joined(separator: "|")
        return parts.isEmpty ? "swpc_text_alert" : parts
    }
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
        case auroraOutlook
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
    let forecastDaily: [SpaceForecastDay]?
    let data: OutlookData?

    private struct DynamicKey: CodingKey {
        var stringValue: String
        init?(stringValue: String) { self.stringValue = stringValue }
        var intValue: Int?
        init?(intValue: Int) { return nil }
    }

    private static func decodeDouble(_ container: KeyedDecodingContainer<DynamicKey>, forKey key: DynamicKey) -> Double? {
        if let value = try? container.decodeIfPresent(Double.self, forKey: key) {
            return value
        }
        if let intValue = try? container.decodeIfPresent(Int.self, forKey: key) {
            return Double(intValue)
        }
        if let stringValue = try? container.decodeIfPresent(String.self, forKey: key) {
            return Double(stringValue.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
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
        var forecastDaily: [SpaceForecastDay]? = nil
        var data: OutlookData? = nil

        for key in container.allKeys {
            switch key.stringValue {
            case "issuedAt", "issued_at":
                issued = try container.decodeIfPresent(String.self, forKey: key)
            case "notes":
                notes = try container.decodeIfPresent([String].self, forKey: key)
            case "kp":
                kp = try? container.decode(OutlookKp.self, forKey: key)
            case "bzNow", "bz_now":
                bzNow = Self.decodeDouble(container, forKey: key)
            case "swSpeedNowKms", "sw_speed_now_kms":
                swSpeedNowKms = Self.decodeDouble(container, forKey: key)
            case "swDensityNowCm3", "sw_density_now_cm3":
                swDensityNowCm3 = Self.decodeDouble(container, forKey: key)
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
            case "swpcTextAlerts", "swpc_text_alerts":
                swpcTextAlerts = try? container.decode([SwpcTextAlert].self, forKey: key)
            case "forecastDaily", "forecast_daily":
                forecastDaily = (try? container.decode(LossyArray<SpaceForecastDay>.self, forKey: key))?.values
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
        self.forecastDaily = forecastDaily
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
        if let forecastDaily, let key = DynamicKey(stringValue: "forecast_daily") {
            try container.encode(forecastDaily, forKey: key)
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

private struct SpaceForecastDay: Codable, Hashable, Identifiable {
    let forecastDay: String?
    let issuedAt: String?
    let sourceProductTs: String?
    let sourceSrc: String?
    let kpMaxForecast: Double?
    let gScaleMax: String?
    let s1OrGreaterPct: Double?
    let r1R2Pct: Double?
    let r3OrGreaterPct: Double?
    let geomagneticRationale: String?
    let radiationRationale: String?
    let radioRationale: String?
    let flareWatch: Bool?
    let cmeWatch: Bool?
    let solarWindWatch: Bool?
    let geomagneticSeverityBucket: String?
    let radiationSeverityBucket: String?
    let radioSeverityBucket: String?
    let updatedAt: String?

    var id: String { forecastDay ?? "forecast-day" }

    private enum CodingKeys: String, CodingKey {
        case forecastDay, issuedAt, sourceProductTs, sourceSrc, kpMaxForecast, gScaleMax
        case s1OrGreaterPct, r1R2Pct, r3OrGreaterPct
        case geomagneticRationale, radiationRationale, radioRationale
        case flareWatch, cmeWatch, solarWindWatch
        case geomagneticSeverityBucket, radiationSeverityBucket, radioSeverityBucket
        case updatedAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        forecastDay = try container.decodeIfPresent(String.self, forKey: .forecastDay)
        issuedAt = try container.decodeIfPresent(String.self, forKey: .issuedAt)
        sourceProductTs = try container.decodeIfPresent(String.self, forKey: .sourceProductTs)
        sourceSrc = try container.decodeIfPresent(String.self, forKey: .sourceSrc)
        kpMaxForecast = container.decodeFlexibleDouble(forKey: .kpMaxForecast)
        gScaleMax = try container.decodeIfPresent(String.self, forKey: .gScaleMax)
        s1OrGreaterPct = container.decodeFlexibleDouble(forKey: .s1OrGreaterPct)
        r1R2Pct = container.decodeFlexibleDouble(forKey: .r1R2Pct)
        r3OrGreaterPct = container.decodeFlexibleDouble(forKey: .r3OrGreaterPct)
        geomagneticRationale = try container.decodeIfPresent(String.self, forKey: .geomagneticRationale)
        radiationRationale = try container.decodeIfPresent(String.self, forKey: .radiationRationale)
        radioRationale = try container.decodeIfPresent(String.self, forKey: .radioRationale)
        flareWatch = container.decodeFlexibleBool(forKey: .flareWatch)
        cmeWatch = container.decodeFlexibleBool(forKey: .cmeWatch)
        solarWindWatch = container.decodeFlexibleBool(forKey: .solarWindWatch)
        geomagneticSeverityBucket = try container.decodeIfPresent(String.self, forKey: .geomagneticSeverityBucket)
        radiationSeverityBucket = try container.decodeIfPresent(String.self, forKey: .radiationSeverityBucket)
        radioSeverityBucket = try container.decodeIfPresent(String.self, forKey: .radioSeverityBucket)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

private struct UserOutlookDomain: Codable, Hashable, Identifiable {
    let key: String
    let label: String?
    let likelihood: String?
    let currentGauge: Double?
    let explanation: String?
    let topDriverKey: String?
    let topDriverLabel: String?

    var id: String { key }

    private enum CodingKeys: String, CodingKey {
        case key, label, likelihood, currentGauge, explanation, topDriverKey, topDriverLabel
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = (try container.decodeIfPresent(String.self, forKey: .key)) ?? "domain"
        label = try container.decodeIfPresent(String.self, forKey: .label)
        likelihood = try container.decodeIfPresent(String.self, forKey: .likelihood)
        currentGauge = container.decodeFlexibleDouble(forKey: .currentGauge)
        explanation = try container.decodeIfPresent(String.self, forKey: .explanation)
        topDriverKey = try container.decodeIfPresent(String.self, forKey: .topDriverKey)
        topDriverLabel = try container.decodeIfPresent(String.self, forKey: .topDriverLabel)
    }
}

private struct UserOutlookDriver: Codable, Hashable, Identifiable {
    let key: String
    let label: String?
    let severity: String?
    let value: Double?
    let unit: String?
    let day: String?
    let detail: String?
    let signalKey: String?

    var id: String { key }

    private enum CodingKeys: String, CodingKey {
        case key, label, severity, value, unit, day, detail, signalKey
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = (try container.decodeIfPresent(String.self, forKey: .key)) ?? "driver"
        label = try container.decodeIfPresent(String.self, forKey: .label)
        severity = try container.decodeIfPresent(String.self, forKey: .severity)
        value = container.decodeFlexibleDouble(forKey: .value)
        unit = try container.decodeIfPresent(String.self, forKey: .unit)
        day = try container.decodeIfPresent(String.self, forKey: .day)
        detail = try container.decodeIfPresent(String.self, forKey: .detail)
        signalKey = try container.decodeIfPresent(String.self, forKey: .signalKey)
    }
}

private struct UserOutlookWindow: Codable, Hashable {
    let windowHours: Int?
    let likelyElevatedDomains: [UserOutlookDomain]?
    let topDrivers: [UserOutlookDriver]?
    let summary: String?
    let supportLine: String?

    private enum CodingKeys: String, CodingKey {
        case windowHours, likelyElevatedDomains, topDrivers, summary, supportLine
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        windowHours = container.decodeFlexibleInt(forKey: .windowHours)
        likelyElevatedDomains = (try? container.decode(LossyArray<UserOutlookDomain>.self, forKey: .likelyElevatedDomains))?.values
        topDrivers = (try? container.decode(LossyArray<UserOutlookDriver>.self, forKey: .topDrivers))?.values
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
        supportLine = try container.decodeIfPresent(String.self, forKey: .supportLine)
    }
}

private struct UserOutlookDataReady: Codable, Hashable {
    let locationFound: Bool?
    let localForecastDaily: Bool?
    let localForecastDays: Int?
    let spaceForecastDaily: Bool?
    let spaceForecastDays: Int?
    let next24h: Bool?
    let next72h: Bool?
    let next7d: Bool?

    private struct DynamicKey: CodingKey {
        var stringValue: String
        init?(stringValue: String) { self.stringValue = stringValue }
        var intValue: Int?
        init?(intValue: Int) { return nil }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)
        var locationFound: Bool? = nil
        var localForecastDaily: Bool? = nil
        var localForecastDays: Int? = nil
        var spaceForecastDaily: Bool? = nil
        var spaceForecastDays: Int? = nil
        var next24h: Bool? = nil
        var next72h: Bool? = nil
        var next7d: Bool? = nil

        for key in container.allKeys {
            switch key.stringValue {
            case "locationFound", "location_found":
                locationFound = container.decodeFlexibleBool(forKey: key)
            case "localForecastDaily", "local_forecast_daily":
                localForecastDaily = container.decodeFlexibleBool(forKey: key)
            case "localForecastDays", "local_forecast_days":
                localForecastDays = container.decodeFlexibleInt(forKey: key)
            case "spaceForecastDaily", "space_forecast_daily":
                spaceForecastDaily = container.decodeFlexibleBool(forKey: key)
            case "spaceForecastDays", "space_forecast_days":
                spaceForecastDays = container.decodeFlexibleInt(forKey: key)
            case "next24H", "next24h", "next_24h":
                next24h = container.decodeFlexibleBool(forKey: key)
            case "next72H", "next72h", "next_72h":
                next72h = container.decodeFlexibleBool(forKey: key)
            case "next7D", "next7d", "next_7d":
                next7d = container.decodeFlexibleBool(forKey: key)
            default:
                break
            }
        }

        self.locationFound = locationFound
        self.localForecastDaily = localForecastDaily
        self.localForecastDays = localForecastDays
        self.spaceForecastDaily = spaceForecastDaily
        self.spaceForecastDays = spaceForecastDays
        self.next24h = next24h
        self.next72h = next72h
        self.next7d = next7d
    }
}

private struct UserForecastOutlook: Codable {
    let ok: Bool?
    let generatedAt: String?
    let availableWindows: [String]?
    let forecastDataReady: UserOutlookDataReady?
    let next24h: UserOutlookWindow?
    let next72h: UserOutlookWindow?
    let next7d: UserOutlookWindow?
    let error: String?

    private struct DynamicKey: CodingKey {
        var stringValue: String
        init?(stringValue: String) { self.stringValue = stringValue }
        var intValue: Int?
        init?(intValue: Int) { return nil }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)
        var ok: Bool? = nil
        var generatedAt: String? = nil
        var availableWindows: [String]? = nil
        var forecastDataReady: UserOutlookDataReady? = nil
        var next24h: UserOutlookWindow? = nil
        var next72h: UserOutlookWindow? = nil
        var next7d: UserOutlookWindow? = nil
        var error: String? = nil

        for key in container.allKeys {
            switch key.stringValue {
            case "ok":
                ok = container.decodeFlexibleBool(forKey: key)
            case "generatedAt", "generated_at":
                generatedAt = try? container.decode(String.self, forKey: key)
            case "availableWindows", "available_windows":
                availableWindows = try? container.decode([String].self, forKey: key)
            case "forecastDataReady", "forecast_data_ready":
                forecastDataReady = try? container.decode(UserOutlookDataReady.self, forKey: key)
            case "next24H", "next24h", "next_24h":
                next24h = try? container.decode(UserOutlookWindow.self, forKey: key)
            case "next72H", "next72h", "next_72h":
                next72h = try? container.decode(UserOutlookWindow.self, forKey: key)
            case "next7D", "next7d", "next_7d":
                next7d = try? container.decode(UserOutlookWindow.self, forKey: key)
            case "error":
                error = try? container.decode(String.self, forKey: key)
            default:
                break
            }
        }

        self.ok = ok
        self.generatedAt = generatedAt
        self.availableWindows = availableWindows
        self.forecastDataReady = forecastDataReady
        self.next24h = next24h
        self.next72h = next72h
        self.next7d = next7d
        self.error = error
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

#if canImport(CoreLocation)
private final class OneShotLocationProvider: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocation?, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    func requestLocation() async -> CLLocation? {
        let status = manager.authorizationStatus
        if status == .denied || status == .restricted {
            return nil
        }
        return await withCheckedContinuation { continuation in
            self.continuation = continuation
            if status == .notDetermined {
                manager.requestWhenInUseAuthorization()
            }
            manager.requestLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(returning: locations.last)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(returning: nil)
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        if status == .denied || status == .restricted {
            guard let continuation else { return }
            self.continuation = nil
            continuation.resume(returning: nil)
        }
    }
}
#endif

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
    @AppStorage("user_outlook_cache_json") private var userOutlookCacheJSON: String = ""
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
    @State private var userOutlook: UserForecastOutlook? = nil
    @State private var lastKnownUserOutlook: UserForecastOutlook? = nil
    @State private var userOutlookLoading: Bool = false
    @State private var userOutlookError: String? = nil

    @AppStorage("local_health_zip") private var localHealthZip: String = "78209"
    @AppStorage("did_location_onboarding") private var didLocationOnboarding: Bool = false
    @State private var localHealth: LocalCheckResponse? = nil
    @State private var localHealthLoading: Bool = false
    @State private var localHealthError: String?
    @State private var localZipRefreshTask: Task<Void, Never>? = nil
    @State private var showLocationOnboarding: Bool = false
    @State private var profileUseGPS: Bool = false
    @State private var profileLocalInsightsEnabled: Bool = true
    @State private var profileLocationMessage: String?
    @State private var profileLocationSaving: Bool = false
#if canImport(CoreLocation)
    @State private var locationProvider = OneShotLocationProvider()
#endif
    @State private var tagCatalog: [TagCatalogItem] = []
    @State private var selectedTagKeys: Set<String> = []
    @State private var tagSaveMessage: String?
    @State private var tagsSaving: Bool = false
    @State private var notificationPreferences: AppNotificationPreferences = PushNotificationService.currentPreferencesDefault()
    @State private var notificationSettingsSaving: Bool = false
    @State private var notificationSettingsMessage: String?
    @State private var pushPermissionGranted: Bool = PushNotificationService.storedPermissionGranted()
    @State private var pushDeviceToken: String? = PushNotificationService.storedDeviceToken()
    @State private var pendingPushRoute: GaiaPushRoute? = nil
    @AppStorage("dashboard_payload_cache_json") private var dashboardPayloadCacheJSON: String = ""
    @State private var dashboardPayload: DashboardPayload? = nil
    @State private var lastNonNilDashboardGauges: DashboardGaugeSet? = nil
    @State private var dashboardLoading: Bool = false
    @State private var dashboardError: String?
    @State private var dashboardFetchInFlight: Bool = false
    @State private var dashboardLastFetchAt: Date = .distantPast
    @State private var dashboardLastUpdatedText: String? = nil
    @State private var showMissionSettingsSheet: Bool = false
    @State private var showMissionInsightsSheet: Bool = false
    @State private var showLocalConditionsSheet: Bool = false
    @State private var showSchumannDashboardSheet: Bool = false
    @State private var showCameraHealthCheckSheet: Bool = false
    @State private var latestCameraCheck: CameraHealthDailySummary? = nil
    @State private var latestCameraCheckLoading: Bool = false
    @State private var latestCameraCheckError: String? = nil
    @AppStorage("camera_health_debug_export_enabled") private var cameraHealthDebugExportEnabled: Bool = false

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
    @State private var symptomToast: SymptomToastState? = nil
    @State private var symptomSheetPrefill: SymptomQueuedEvent? = nil
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
    @State private var showHazards: Bool = false
    @State private var showQuakes: Bool = false
    @State private var showAuroraForecast: Bool = false
    @State private var showMagnetosphere: Bool = false

    private struct SymptomToastState: Identifiable {
        let id = UUID()
        let message: String
        let actionTitle: String?
        let prefill: SymptomQueuedEvent?
    }

    private struct MissionControlQuickLogRequest {
        let label: String
        let event: SymptomQueuedEvent
    }

    private enum InsightsRoute: String, Hashable, Identifiable {
        case yourOutlook
        case spaceWeather
        case localConditions
        case yourPatterns
        case magnetosphere
        case schumann
        case healthSymptoms
        case earthquakes
        case hazards

        var id: String { rawValue }
    }

    private enum InsightsTrendRange: String, CaseIterable, Identifiable {
        case days7 = "7D"
        case days14 = "14D"
        case days30 = "30D"

        var id: String { rawValue }

        var days: Int {
            switch self {
            case .days7:
                return 7
            case .days14:
                return 14
            case .days30:
                return 30
            }
        }

        var title: String {
            switch self {
            case .days7:
                return "7 days"
            case .days14:
                return "14 days"
            case .days30:
                return "30 days"
            }
        }
    }
    
    private func chicagoDayString(offsetDays: Int = 0) -> String {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/Chicago") ?? .current
        let base = cal.date(byAdding: .day, value: offsetDays, to: Date()) ?? Date()
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.timeZone = TimeZone(identifier: "America/Chicago")
        return df.string(from: base)
    }

    private func chicagoTodayString() -> String {
        chicagoDayString(offsetDays: 0)
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
    
    private func showSymptomToast(
        _ message: String,
        actionTitle: String? = nil,
        prefill: SymptomQueuedEvent? = nil
    ) {
        let toast = SymptomToastState(message: message, actionTitle: actionTitle, prefill: prefill)
        withAnimation {
            symptomToast = toast
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [self] in
            withAnimation {
                if self.symptomToast?.id == toast.id {
                    self.symptomToast = nil
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

    private func decodeUserOutlook(from json: String) -> UserForecastOutlook? {
        guard !json.isEmpty, let data = json.data(using: .utf8) else { return nil }
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try? dec.decode(UserForecastOutlook.self, from: data)
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

    @MainActor
    private func applyUserOutlook(_ payload: UserForecastOutlook) {
        userOutlook = payload
        lastKnownUserOutlook = payload
        if let encoded = try? JSONEncoder().encode(payload), let json = String(data: encoded, encoding: .utf8) {
            userOutlookCacheJSON = json
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

    private func fetchUserOutlook() async {
        let backendAvailable = await MainActor.run { state.backendDBAvailable }
        if !backendAvailable, let cached = decodeUserOutlook(from: userOutlookCacheJSON) {
            await MainActor.run { lastKnownUserOutlook = cached }
        }
        await MainActor.run {
            userOutlookLoading = true
            userOutlookError = nil
        }
        let api = state.apiWithAuth()
        do {
            let payload: UserForecastOutlook = try await api.getJSON("v1/users/me/outlook", as: UserForecastOutlook.self, perRequestTimeout: 30)
            await MainActor.run {
                if payload.ok == false {
                    userOutlookError = payload.error ?? "Outlook unavailable"
                } else {
                    applyUserOutlook(payload)
                }
                userOutlookLoading = false
            }
        } catch is CancellationError {
            await MainActor.run { userOutlookLoading = false }
        } catch let uerr as URLError where uerr.code == .cancelled {
            await MainActor.run { userOutlookLoading = false }
        } catch {
            if let cached = decodeUserOutlook(from: userOutlookCacheJSON) {
                await MainActor.run { lastKnownUserOutlook = cached }
            }
            await MainActor.run {
                userOutlookError = error.localizedDescription
                userOutlookLoading = false
            }
        }
    }

    private func putJSON<Body: Encodable, Resp: Decodable>(_ path: String, body: Body, as responseType: Resp.Type) async throws -> Resp {
        let clean = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard var url = URL(string: state.baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            throw URLError(.badURL)
        }
        url.appendPathComponent(clean)
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if !state.bearer.isEmpty {
            req.setValue("Bearer \(state.bearer)", forHTTPHeaderField: "Authorization")
        }
        let devUser = state.userId.trimmingCharacters(in: .whitespacesAndNewlines)
        if !devUser.isEmpty {
            req.setValue(devUser, forHTTPHeaderField: "X-Dev-UserId")
        }
        let encoder = JSONEncoder()
        req.httpBody = try encoder.encode(body)
        let (data, response) = try await URLSession.shared.data(for: req)
        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
        guard (200...299).contains(code) else {
            throw DecodingPreviewError(endpoint: path, preview: String(data: data, encoding: .utf8) ?? "", underlying: URLError(.badServerResponse))
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Resp.self, from: data)
    }

    private func decodeDashboardPayload(from json: String) -> DashboardPayload? {
        guard !json.isEmpty, let data = json.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(DashboardPayload.self, from: data)
    }

    private func currentEarthscopePost(_ post: DashboardEarthscopePost?, requestedDay: String) -> DashboardEarthscopePost? {
        guard let post else { return nil }
        let day = (post.day ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !day.isEmpty, day == requestedDay else { return nil }
        return post
    }

    private func fetchDashboardPayload(force: Bool = false) async {
        let shouldStart = await MainActor.run { () -> Bool in
            if dashboardFetchInFlight { return false }
            if !force, dashboardPayload != nil, Date().timeIntervalSince(dashboardLastFetchAt) < 60 {
                return false
            }
            dashboardFetchInFlight = true
            dashboardLoading = true
            dashboardError = nil
            return true
        }
        guard shouldStart else { return }

        defer {
            Task { @MainActor in
                dashboardFetchInFlight = false
                dashboardLoading = false
            }
        }

        let api = state.apiWithAuth()
        let dashboardDay = chicagoTodayString()
        let endpoint = "v1/dashboard?day=\(dashboardDay)"
        let startedAt = Date()
        let backoffs: [UInt64] = [500_000_000, 1_500_000_000]
        var lastError: Error?

        for attempt in 0..<3 {
            do {
                let payload: DashboardPayload = try await api.getJSON(endpoint, as: DashboardPayload.self, perRequestTimeout: 15)
                var resolvedPayload = payload
                var fallbackUsed = false
                var fallbackSourceDay: String? = nil

                if payload.gauges == nil || (payload.memberPost == nil && payload.personalPost == nil) {
                    for offset in [-1, -2, -3, -4, -5, -6, -7] {
                        let fallbackDay = chicagoDayString(offsetDays: offset)
                        let fallbackEndpoint = "v1/dashboard?day=\(fallbackDay)"
                        guard let older: DashboardPayload = try? await api.getJSON(fallbackEndpoint, as: DashboardPayload.self, perRequestTimeout: 15) else {
                            continue
                        }
                        let hasUsefulFallback =
                            older.gauges != nil ||
                            older.memberPost != nil ||
                            older.personalPost != nil ||
                            older.publicPost != nil
                        guard hasUsefulFallback else { continue }

                        resolvedPayload = DashboardPayload(
                            day: payload.day ?? older.day,
                            gauges: payload.gauges ?? older.gauges,
                            gaugesMeta: payload.gaugesMeta ?? older.gaugesMeta,
                            gaugeZones: payload.gaugeZones ?? older.gaugeZones,
                            gaugeLabels: payload.gaugeLabels ?? older.gaugeLabels,
                            gaugesDelta: payload.gaugesDelta ?? older.gaugesDelta,
                            drivers: payload.drivers ?? older.drivers,
                            driversCompact: payload.driversCompact ?? older.driversCompact,
                            primaryDriver: payload.primaryDriver ?? older.primaryDriver,
                            supportingDrivers: payload.supportingDrivers ?? older.supportingDrivers,
                            patternRelevantGauges: payload.patternRelevantGauges ?? older.patternRelevantGauges,
                            activePatternRefs: payload.activePatternRefs ?? older.activePatternRefs,
                            todayPersonalThemes: payload.todayPersonalThemes ?? older.todayPersonalThemes,
                            todayRelevanceExplanations: payload.todayRelevanceExplanations ?? older.todayRelevanceExplanations,
                            modalModels: payload.modalModels ?? older.modalModels,
                            earthscopeSummary: payload.earthscopeSummary,
                            alerts: (payload.alerts?.isEmpty == false) ? payload.alerts : older.alerts,
                            entitled: payload.entitled ?? older.entitled,
                            memberPost: payload.memberPost ?? payload.personalPost,
                            publicPost: payload.publicPost,
                            personalPost: payload.personalPost
                        )
                        fallbackUsed = true
                        fallbackSourceDay = fallbackDay
                        break
                    }
                }

                let currentMemberPost = currentEarthscopePost(resolvedPayload.memberPost, requestedDay: dashboardDay)
                let currentPersonalPost = currentEarthscopePost(resolvedPayload.personalPost, requestedDay: dashboardDay)
                let currentPublicPost = currentEarthscopePost(resolvedPayload.publicPost, requestedDay: dashboardDay)
                let hasCurrentMemberEarthscope = (currentMemberPost != nil || currentPersonalPost != nil)

                if resolvedPayload.gauges == nil || !hasCurrentMemberEarthscope {
                    if let memberEnv: MemberEarthscopeEnvelope = try? await api.getJSON(
                        "v1/earthscope/member?day=\(dashboardDay)",
                        as: MemberEarthscopeEnvelope.self,
                        perRequestTimeout: 15
                    ),
                    memberEnv.ok == true,
                    let memberPost = memberEnv.post {
                        let normalizedMember = DashboardEarthscopePost(
                            day: memberPost.day,
                            title: memberPost.title,
                            caption: memberPost.caption,
                            bodyMarkdown: memberPost.bodyMarkdown,
                            updatedAt: memberPost.updatedAt
                        )
                        resolvedPayload = DashboardPayload(
                            day: resolvedPayload.day,
                            gauges: resolvedPayload.gauges ?? memberPost.metricsJson?.gauges,
                            gaugesMeta: resolvedPayload.gaugesMeta,
                            gaugeZones: resolvedPayload.gaugeZones,
                            gaugeLabels: resolvedPayload.gaugeLabels,
                            gaugesDelta: resolvedPayload.gaugesDelta,
                            drivers: resolvedPayload.drivers,
                            driversCompact: resolvedPayload.driversCompact,
                            primaryDriver: resolvedPayload.primaryDriver,
                            supportingDrivers: resolvedPayload.supportingDrivers,
                            patternRelevantGauges: resolvedPayload.patternRelevantGauges,
                            activePatternRefs: resolvedPayload.activePatternRefs,
                            todayPersonalThemes: resolvedPayload.todayPersonalThemes,
                            todayRelevanceExplanations: resolvedPayload.todayRelevanceExplanations,
                            modalModels: resolvedPayload.modalModels,
                            earthscopeSummary: resolvedPayload.earthscopeSummary,
                            alerts: resolvedPayload.alerts,
                            entitled: resolvedPayload.entitled,
                            memberPost: currentMemberPost ?? currentPersonalPost ?? normalizedMember,
                            publicPost: currentPublicPost,
                            personalPost: currentPersonalPost
                        )
                    }
                }

                let resolvedCurrentMemberPost = currentEarthscopePost(resolvedPayload.memberPost, requestedDay: dashboardDay)
                let resolvedCurrentPersonalPost = currentEarthscopePost(resolvedPayload.personalPost, requestedDay: dashboardDay)
                let resolvedCurrentPublicPost = currentEarthscopePost(resolvedPayload.publicPost, requestedDay: dashboardDay)

                if resolvedCurrentMemberPost == nil && resolvedCurrentPersonalPost == nil && resolvedCurrentPublicPost == nil {
                    if let features: FeaturesToday = try? await api.getJSON("v1/features/today", as: FeaturesToday.self, perRequestTimeout: 15),
                       (features.postTitle != nil || features.postCaption != nil || features.postBody != nil) {
                        let fallbackPublic = DashboardEarthscopePost(
                            day: features.day,
                            title: features.postTitle,
                            caption: features.postCaption,
                            bodyMarkdown: features.postBody,
                            updatedAt: features.updatedAt
                        )
                        resolvedPayload = DashboardPayload(
                            day: resolvedPayload.day,
                            gauges: resolvedPayload.gauges,
                            gaugesMeta: resolvedPayload.gaugesMeta,
                            gaugeZones: resolvedPayload.gaugeZones,
                            gaugeLabels: resolvedPayload.gaugeLabels,
                            gaugesDelta: resolvedPayload.gaugesDelta,
                            drivers: resolvedPayload.drivers,
                            driversCompact: resolvedPayload.driversCompact,
                            primaryDriver: resolvedPayload.primaryDriver,
                            supportingDrivers: resolvedPayload.supportingDrivers,
                            patternRelevantGauges: resolvedPayload.patternRelevantGauges,
                            activePatternRefs: resolvedPayload.activePatternRefs,
                            todayPersonalThemes: resolvedPayload.todayPersonalThemes,
                            todayRelevanceExplanations: resolvedPayload.todayRelevanceExplanations,
                            modalModels: resolvedPayload.modalModels,
                            earthscopeSummary: resolvedPayload.earthscopeSummary,
                            alerts: resolvedPayload.alerts,
                            entitled: resolvedPayload.entitled,
                            memberPost: resolvedCurrentMemberPost,
                            publicPost: currentEarthscopePost(fallbackPublic, requestedDay: dashboardDay),
                            personalPost: resolvedCurrentPersonalPost
                        )
                    }
                }

                let encoded = try? JSONEncoder().encode(resolvedPayload)
                let json = encoded.flatMap { String(data: $0, encoding: .utf8) }
                let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000.0)
                await MainActor.run {
                    if let g = resolvedPayload.gauges {
                        lastNonNilDashboardGauges = g
                    }
                    let gaugesForRender = resolvedPayload.gauges ?? lastNonNilDashboardGauges
                    let effectivePayload = DashboardPayload(
                        day: resolvedPayload.day,
                        gauges: gaugesForRender,
                        gaugesMeta: resolvedPayload.gaugesMeta,
                        gaugeZones: resolvedPayload.gaugeZones,
                        gaugeLabels: resolvedPayload.gaugeLabels,
                        gaugesDelta: resolvedPayload.gaugesDelta,
                        drivers: resolvedPayload.drivers,
                        driversCompact: resolvedPayload.driversCompact,
                        primaryDriver: resolvedPayload.primaryDriver,
                        supportingDrivers: resolvedPayload.supportingDrivers,
                        patternRelevantGauges: resolvedPayload.patternRelevantGauges,
                        activePatternRefs: resolvedPayload.activePatternRefs,
                        todayPersonalThemes: resolvedPayload.todayPersonalThemes,
                        todayRelevanceExplanations: resolvedPayload.todayRelevanceExplanations,
                        modalModels: resolvedPayload.modalModels,
                        earthscopeSummary: resolvedPayload.earthscopeSummary,
                        alerts: resolvedPayload.alerts,
                        entitled: resolvedPayload.entitled,
                        memberPost: currentEarthscopePost(resolvedPayload.memberPost, requestedDay: dashboardDay),
                        publicPost: currentEarthscopePost(resolvedPayload.publicPost, requestedDay: dashboardDay),
                        personalPost: currentEarthscopePost(resolvedPayload.personalPost, requestedDay: dashboardDay)
                    )
                    dashboardPayload = effectivePayload
                    if let json {
                        dashboardPayloadCacheJSON = json
                    }
                    dashboardError = nil
                    dashboardLastFetchAt = Date()
                    let out = DateFormatter()
                    out.dateStyle = .none
                    out.timeStyle = .short
                    dashboardLastUpdatedText = out.string(from: dashboardLastFetchAt)
                }
                appLog(
                    "[UI] dashboard ok: day=\(dashboardDay) ms=\(durationMs) gauges=\(resolvedPayload.gauges != nil) alerts=\(resolvedPayload.alerts?.count ?? 0) member=\(resolvedPayload.memberPost != nil || resolvedPayload.personalPost != nil) public=\(resolvedPayload.publicPost != nil) entitled=\(String(describing: resolvedPayload.entitled)) fallback=\(fallbackUsed) fallback_day=\(fallbackSourceDay ?? "-")"
                )
                return
            } catch {
                if isCancellationError(error) { return }
                lastError = error
                if attempt < backoffs.count {
                    try? await Task.sleep(nanoseconds: backoffs[attempt])
                }
            }
        }

        await MainActor.run {
            dashboardError = lastError?.localizedDescription ?? "dashboard fetch failed"
            if dashboardPayload == nil, let cached = decodeDashboardPayload(from: dashboardPayloadCacheJSON) {
                dashboardPayload = cached
                dashboardLastUpdatedText = "cached"
            }
        }
        appLog("[UI] dashboard payload error: \(lastError?.localizedDescription ?? "unknown")")
    }

    private func fetchLatestCameraCheck() async {
        let shouldStart = await MainActor.run { () -> Bool in
            if latestCameraCheckLoading {
                return false
            }
            latestCameraCheckLoading = true
            latestCameraCheckError = nil
            return true
        }
        guard shouldStart else { return }

        defer {
            Task { @MainActor in
                latestCameraCheckLoading = false
            }
        }

        do {
            let remoteSummary = try await CameraHealthSupabaseClient.shared.fetchLatestDailySummary()
            let localSummary = await CameraHealthLocalStore.shared.latestSummary()
            let summary = newestCameraCheckSummary(remote: remoteSummary, local: localSummary)
            await MainActor.run {
                latestCameraCheck = summary
                latestCameraCheckError = nil
            }
        } catch CameraHealthSupabaseError.notAuthenticated {
            let localSummary = await CameraHealthLocalStore.shared.latestSummary()
            await MainActor.run {
                latestCameraCheck = localSummary
                latestCameraCheckError = nil
            }
        } catch CameraHealthSupabaseError.missingUserId {
            let localSummary = await CameraHealthLocalStore.shared.latestSummary()
            await MainActor.run {
                latestCameraCheck = localSummary
                latestCameraCheckError = nil
            }
        } catch {
            let localSummary = await CameraHealthLocalStore.shared.latestSummary()
            await MainActor.run {
                latestCameraCheck = localSummary
                latestCameraCheckError = localSummary == nil ? "Latest check unavailable" : nil
            }
            appLog("[UI] camera check fetch error: \(error.localizedDescription)")
        }
    }

    private func newestCameraCheckSummary(remote: CameraHealthDailySummary?, local: CameraHealthDailySummary?) -> CameraHealthDailySummary? {
        switch (remote, local) {
        case let (remote?, local?):
            return (remote.captureDate ?? .distantPast) >= (local.captureDate ?? .distantPast) ? remote : local
        case let (remote?, nil):
            return remote
        case let (nil, local?):
            return local
        case (nil, nil):
            return nil
        }
    }

    private func fetchProfileLocation() async {
        let api = state.apiWithAuth()
        do {
            let payload: ProfileLocationEnvelope = try await api.getJSON("v1/profile/location", as: ProfileLocationEnvelope.self, perRequestTimeout: 20)
            await MainActor.run {
                if let loc = payload.location {
                    if let zip = loc.zip, !zip.isEmpty {
                        localHealthZip = zip
                    }
                    profileUseGPS = loc.useGps ?? profileUseGPS
                    profileLocalInsightsEnabled = loc.localInsightsEnabled ?? profileLocalInsightsEnabled
                    didLocationOnboarding = true
                }
            }
        } catch {
            appLog("[UI] profile location fetch error: \(error.localizedDescription)")
        }
    }

    private func saveProfileLocation(markOnboardingComplete: Bool = false) async {
        await MainActor.run {
            profileLocationSaving = true
            profileLocationMessage = nil
        }
        let resolved = await resolveLocationInput(zip: localHealthZip, useGPS: profileUseGPS)
        let payload = ProfileLocationUpsert(
            zip: resolved.zip,
            lat: resolved.lat,
            lon: resolved.lon,
            useGps: profileUseGPS,
            localInsightsEnabled: profileLocalInsightsEnabled
        )
        if profileLocalInsightsEnabled && profileUseGPS && resolved.usedGPS == false && (resolved.zip == nil || resolved.zip?.isEmpty == true) {
            await MainActor.run {
                profileLocationMessage = "GPS did not return a ZIP. Enter ZIP to continue."
                profileLocationSaving = false
            }
            return
        }
        do {
            let _: ProfileLocationEnvelope = try await putJSON("v1/profile/location", body: payload, as: ProfileLocationEnvelope.self)
            await MainActor.run {
                profileLocationMessage = "Location saved"
                profileLocationSaving = false
                if markOnboardingComplete {
                    didLocationOnboarding = true
                    showLocationOnboarding = false
                }
            }
            await fetchLocalHealth()
        } catch {
            await MainActor.run {
                profileLocationMessage = "Could not save location"
                profileLocationSaving = false
            }
            appLog("[UI] save profile location error: \(error.localizedDescription)")
        }
    }

    private func fetchTagCatalog() async {
        let api = state.apiWithAuth()
        do {
            let payload: TagCatalogEnvelope = try await api.getJSON("v1/profile/tags/catalog", as: TagCatalogEnvelope.self, perRequestTimeout: 20)
            await MainActor.run {
                tagCatalog = payload.items ?? []
            }
        } catch {
            appLog("[UI] tag catalog fetch error: \(error.localizedDescription)")
        }
    }

    private func fetchSelectedTags() async {
        let api = state.apiWithAuth()
        do {
            let payload: UserTagsEnvelope = try await api.getJSON("v1/profile/tags", as: UserTagsEnvelope.self, perRequestTimeout: 20)
            await MainActor.run {
                selectedTagKeys = Set((payload.tags ?? []).map(canonicalProfileTagKey))
            }
        } catch {
            appLog("[UI] selected tags fetch error: \(error.localizedDescription)")
        }
    }

    private func saveSelectedTags() async {
        await MainActor.run {
            tagsSaving = true
            tagSaveMessage = nil
        }
        let payload = UserTagsUpsert(tags: Array(selectedTagKeys).sorted())
        do {
            let _: UserTagsEnvelope = try await putJSON("v1/profile/tags", body: payload, as: UserTagsEnvelope.self)
            await MainActor.run {
                tagsSaving = false
                tagSaveMessage = "Personalization saved"
            }
        } catch {
            await MainActor.run {
                tagsSaving = false
                tagSaveMessage = "Could not save personalization"
            }
            appLog("[UI] save personalization error: \(error.localizedDescription)")
        }
    }

    private func fetchProfileSettings(includeNotifications: Bool = false) async {
        await fetchProfileLocation()
        await fetchTagCatalog()
        await fetchSelectedTags()
        if includeNotifications {
            await fetchNotificationPreferences()
        }
    }

    private func applyStoredPushState() async {
        await MainActor.run {
            pushPermissionGranted = PushNotificationService.storedPermissionGranted()
            pushDeviceToken = PushNotificationService.storedDeviceToken()
        }
    }

    private func refreshPushState() async {
        await PushNotificationService.refreshAuthorizationState()
        await applyStoredPushState()
    }

    private func fetchNotificationPreferences() async {
        do {
            let prefs = try await PushNotificationService.fetchPreferences()
            await MainActor.run {
                notificationPreferences = prefs
                pushPermissionGranted = PushNotificationService.storedPermissionGranted()
                pushDeviceToken = PushNotificationService.storedDeviceToken()
                notificationSettingsMessage = nil
            }
        } catch {
            await MainActor.run {
                notificationPreferences.timeZone = TimeZone.current.identifier
                pushPermissionGranted = PushNotificationService.storedPermissionGranted()
                pushDeviceToken = PushNotificationService.storedDeviceToken()
            }
            appLog("[UI] notification preferences fetch error: \(error.localizedDescription)")
        }
    }

    private func saveNotificationPreferences(requestAuthorizationIfNeeded: Bool = false) async {
        await MainActor.run {
            notificationSettingsSaving = true
            notificationSettingsMessage = nil
            notificationPreferences.timeZone = TimeZone.current.identifier
        }

        var payload = await MainActor.run { notificationPreferences }
        let permissionGranted = await MainActor.run { pushPermissionGranted }
        if requestAuthorizationIfNeeded && payload.enabled && !permissionGranted {
            let granted = await PushNotificationService.requestAuthorization()
            await MainActor.run {
                pushPermissionGranted = granted
            }
            if !granted {
                await MainActor.run {
                    notificationSettingsSaving = false
                    notificationSettingsMessage = "Allow notifications in iOS Settings to finish enabling pushes."
                    notificationPreferences.enabled = false
                }
                return
            }
            await refreshPushState()
            payload = await MainActor.run { notificationPreferences }
        }

        do {
            let saved = try await PushNotificationService.savePreferences(payload)
            let synced = await PushNotificationService.syncTokenRegistration(preferences: saved)
            await MainActor.run {
                notificationPreferences = saved
                notificationSettingsSaving = false
                pushPermissionGranted = PushNotificationService.storedPermissionGranted()
                pushDeviceToken = PushNotificationService.storedDeviceToken()
                if saved.enabled && pushDeviceToken == nil {
                    notificationSettingsMessage = "Settings saved. APNs token will sync after iOS registration completes."
                } else if saved.enabled && !synced {
                    notificationSettingsMessage = "Settings saved. Push token sync is waiting on auth or APNs registration."
                } else {
                    notificationSettingsMessage = "Notification settings saved"
                }
            }
        } catch {
            await MainActor.run {
                notificationSettingsSaving = false
                let message = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
                notificationSettingsMessage = message.isEmpty ? "Could not save notification settings" : message
            }
            appLog("[UI] save notification settings error: \(error.localizedDescription)")
        }
    }

    private func handleIncomingPushRoute(_ route: GaiaPushRoute) {
        pendingPushRoute = route
        showMissionInsightsSheet = false
        showLocalConditionsSheet = false
        showSchumannDashboardSheet = false
        showMissionSettingsSheet = false
    }

    private func resolveLocationInput(zip: String, useGPS: Bool) async -> (zip: String?, lat: Double?, lon: Double?, usedGPS: Bool) {
        let cleaned = sanitizedZip(zip)
        if !useGPS {
            return (cleaned.isEmpty ? nil : cleaned, nil, nil, false)
        }
#if canImport(CoreLocation)
        let provider = await MainActor.run { locationProvider }
        if let location = await provider.requestLocation() {
            let lat = location.coordinate.latitude
            let lon = location.coordinate.longitude
            if let gpsZip = await reverseGeocodeZip(from: location), !gpsZip.isEmpty {
                return (gpsZip, lat, lon, true)
            }
            if !cleaned.isEmpty {
                return (cleaned, lat, lon, true)
            }
            return (nil, lat, lon, true)
        }
#endif
        return (cleaned.isEmpty ? nil : cleaned, nil, nil, false)
    }

#if canImport(CoreLocation)
    private func reverseGeocodeZip(from location: CLLocation) async -> String? {
        await withCheckedContinuation { continuation in
            CLGeocoder().reverseGeocodeLocation(location) { placemarks, _ in
                let zip = placemarks?.first?.postalCode?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                continuation.resume(returning: zip.isEmpty ? nil : zip)
            }
        }
    }
#endif

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
        if !profileLocalInsightsEnabled {
            await MainActor.run {
                localHealth = nil
                localHealthError = nil
                localHealthLoading = false
            }
            return
        }
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

    private func fetchInsightsHubData() async {
        let api = state.apiWithAuth()
        async let featuresTask: Void = fetchFeaturesToday(trigger: .initial)
        async let forecastTask: Void = fetchForecastSummary()
        async let outlookTask: Void = fetchSpaceOutlook()
        async let userOutlookTask: Void = fetchUserOutlook()
        async let symptomsTask: Void = fetchSymptoms(api: api)
        async let localTask: Void = fetchLocalHealth()
        async let magnetosphereTask: Void = fetchMagnetosphere()
        _ = await (featuresTask, forecastTask, outlookTask, userOutlookTask, symptomsTask, localTask, magnetosphereTask)

        if hazardsBrief == nil {
            await fetchHazardsBrief()
        }
        if quakeLatest == nil && quakeEvents.isEmpty {
            await fetchQuakes()
        }
    }
    
    private func logSymptomEvent(
        _ event: SymptomQueuedEvent,
        successMessage: String = "Symptom logged",
        successPrefill: SymptomQueuedEvent? = nil
    ) async -> Bool {
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
                showSymptomToast(
                    successMessage,
                    actionTitle: successPrefill == nil ? nil : "Edit",
                    prefill: successPrefill
                )
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

    private func quickLogMissionControl(_ request: MissionControlQuickLogRequest) async {
        _ = await logSymptomEvent(
            request.event,
            successMessage: "Logged: \(request.label)",
            successPrefill: request.event
        )
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

    private func dashboardFeaturesView(_ fallbackFeatures: FeaturesToday?) -> some View {
        let dashboardGauges = dashboardPayload?.gauges ?? lastNonNilDashboardGauges
        let dashboardGaugesMeta = dashboardPayload?.gaugesMeta ?? [:]
        let dashboardGaugeZones = dashboardPayload?.gaugeZones ?? DashboardGaugeZone.defaultZones
        let dashboardGaugeLabels = dashboardPayload?.gaugeLabels ?? [:]
        let dashboardGaugesDelta = dashboardPayload?.gaugesDelta ?? [:]
        let dashboardDrivers = dashboardPayload?.drivers ?? []
        let dashboardDriversCompact = dashboardPayload?.driversCompact ?? []
        let dashboardModalModels = dashboardPayload?.modalModels
        let dashboardEarthscopeSummary = dashboardPayload?.earthscopeSummary
        let dashboardAlerts = dashboardPayload?.alerts ?? []
        let requestedEarthscopeDay = chicagoTodayString()
        let resolvedEarthscope: DashboardEarthscopePost? = {
            return currentEarthscopePost(dashboardPayload?.memberPost, requestedDay: requestedEarthscopeDay)
                ?? currentEarthscopePost(dashboardPayload?.personalPost, requestedDay: requestedEarthscopeDay)
                ?? currentEarthscopePost(dashboardPayload?.publicPost, requestedDay: requestedEarthscopeDay)
        }()

        return VStack(spacing: 16) {
            MissionControlSectionView(
                gauges: dashboardGauges,
                gaugesMeta: dashboardGaugesMeta,
                gaugeZones: dashboardGaugeZones,
                gaugeLabels: dashboardGaugeLabels,
                gaugesDelta: dashboardGaugesDelta,
                drivers: dashboardDrivers,
                driversCompact: dashboardDriversCompact,
                modalModels: dashboardModalModels,
                earthscopeSummary: dashboardEarthscopeSummary,
                alerts: dashboardAlerts,
                earthscope: resolvedEarthscope,
                latestCameraCheck: latestCameraCheck,
                cameraCheckLoading: latestCameraCheckLoading,
                cameraCheckError: latestCameraCheckError,
                pushRoute: $pendingPushRoute,
                fallbackTitle: fallbackFeatures?.postTitle,
                fallbackBody: fallbackFeatures?.postBody,
                isLoading: dashboardLoading,
                errorMessage: ContentView.scrubError(dashboardError),
                lastUpdatedText: dashboardLastUpdatedText,
                onQuickLog: { request in
                    Task {
                        await quickLogMissionControl(request)
                    }
                },
                onOpenCustomLog: { event in
                    symptomSheetPrefill = event
                    showSymptomSheet = true
                }
            )
            .padding(.horizontal)

            MissionMenuSectionView(
                onSymptoms: { showSymptomSheet = true },
                onInsights: { showMissionInsightsSheet = true },
                onLocalConditions: { showLocalConditionsSheet = true },
                onSettings: { showMissionSettingsSheet = true },
                onQuickCheck: { showCameraHealthCheckSheet = true },
                onSchumann: { showSchumannDashboardSheet = true },
                onResearch: {
#if canImport(UIKit)
                    if let url = URL(string: "https://gaiaeyes.com/research/") {
                        UIApplication.shared.open(url)
                    }
#endif
                }
            )
            .padding(.horizontal)
        }
    }

    private struct MissionMenuSectionView: View {
        let onSymptoms: () -> Void
        let onInsights: () -> Void
        let onLocalConditions: () -> Void
        let onSettings: () -> Void
        let onQuickCheck: () -> Void
        let onSchumann: () -> Void
        let onResearch: () -> Void

        var body: some View {
            VStack(alignment: .leading, spacing: 6) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        Button(action: onQuickCheck) { Label("Quick Check", systemImage: "camera.fill") }
                        Button(action: onSymptoms) { Label("Symptoms", systemImage: "plus.circle") }
                        Button(action: onInsights) { Label("Insights", systemImage: "chart.xyaxis.line") }
                        Button(action: onLocalConditions) { Label("Local", systemImage: "location.fill") }
                        Button(action: onSettings) { Label("Settings", systemImage: "gearshape") }
                        Button(action: onSchumann) { Label("Schumann", systemImage: "waveform.path.ecg") }
                        Button(action: onResearch) { Label("Research", systemImage: "book.closed") }
                    }
                }
                Text("Quick links open dedicated views for insights, local conditions, and Schumann.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }

    private struct MissionControlSectionView: View {
        let gauges: DashboardGaugeSet?
        let gaugesMeta: [String: DashboardGaugeMeta]
        let gaugeZones: [DashboardGaugeZone]
        let gaugeLabels: [String: String]
        let gaugesDelta: [String: Int]
        let drivers: [DashboardDriverItem]
        let driversCompact: [String]
        let modalModels: DashboardModalModels?
        let earthscopeSummary: String?
        let alerts: [DashboardAlertItem]
        let earthscope: DashboardEarthscopePost?
        let latestCameraCheck: CameraHealthDailySummary?
        let cameraCheckLoading: Bool
        let cameraCheckError: String?
        @Binding var pushRoute: GaiaPushRoute?
        let fallbackTitle: String?
        let fallbackBody: String?
        let isLoading: Bool
        let errorMessage: String?
        let lastUpdatedText: String?
        let onQuickLog: (MissionControlQuickLogRequest) -> Void
        let onOpenCustomLog: (SymptomQueuedEvent) -> Void
        @State private var selectedModal: ModalPresentation? = nil

        private struct ModalPresentation: Identifiable {
            let id: String
            let entry: DashboardModalEntry
        }

        private struct GaugeRow: Identifiable {
            let key: String
            let label: String
            let value: Double?
            let delta: Int
            let zoneKey: String?
            let zoneLabel: String?
            let tappable: Bool
            let showAffordance: Bool

            var id: String { key }
        }

        private struct ArcGaugeCard: View {
            let row: GaugeRow
            let onTap: (() -> Void)?
            private let ringLineWidth: CGFloat = 9
            private let meterSize: CGFloat = 108

            private var valueText: String {
                guard let value = row.value else { return "—" }
                return String(Int(round(value)))
            }

            private var deltaText: String {
                let value = row.delta
                return value > 0 ? "(+\(value))" : "(\(value))"
            }

            private var deltaColor: Color {
                abs(row.delta) >= 5 ? GaugePalette.zoneColor(row.zoneKey) : .secondary
            }

            private var statusText: String {
                if row.value == nil {
                    return "Calibrating"
                }
                if let label = row.zoneLabel, !label.isEmpty {
                    return label
                }
                if let zone = row.zoneKey, !zone.isEmpty {
                    return zone.replacingOccurrences(of: "_", with: " ").capitalized
                }
                return "Calibrating"
            }

            private var zoneKeyText: String {
                guard
                    let zone = row.zoneKey,
                    !zone.isEmpty,
                    zone.lowercased() != "calibrating"
                else { return "" }
                return zone.replacingOccurrences(of: "_", with: " ").capitalized
            }

            private var progress: CGFloat? {
                guard let value = row.value else { return nil }
                return CGFloat(min(1.0, max(0.0, value / 100.0)))
            }

            private func markerPosition(in size: CGSize, progress: CGFloat) -> CGPoint {
                let diameter = min(size.width, size.height)
                let radius = max(0, (diameter * 0.5) - (ringLineWidth * 0.5))
                let center = CGPoint(x: size.width * 0.5, y: size.height * 0.5)
                let angle = ((Double(progress) * 360.0) - 90.0) * Double.pi / 180.0
                return CGPoint(
                    x: center.x + CGFloat(cos(angle)) * radius,
                    y: center.y + CGFloat(sin(angle)) * radius
                )
            }

            private var content: some View {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(row.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(Color.white.opacity(0.92))
                        Spacer(minLength: 4)
                        if row.showAffordance {
                            Image(systemName: "sparkles")
                                .font(.caption2)
                                .foregroundColor(GaugePalette.zoneColor(row.zoneKey))
                        }
                    }

                    ZStack {
                        Circle()
                            .stroke(GaugePalette.ringBackground, lineWidth: ringLineWidth)

                        if let progress {
                            Circle()
                                .trim(from: 0.0, to: max(0.002, progress))
                                .stroke(
                                    GaugePalette.arcGradient,
                                    style: StrokeStyle(lineWidth: ringLineWidth, lineCap: .round)
                                )
                                .rotationEffect(.degrees(-90))
                                .shadow(
                                    color: row.showAffordance
                                    ? GaugePalette
                                        .zoneColor(row.zoneKey)
                                        .opacity(GaugePalette.glowOpacity(row.zoneKey))
                                    : .clear,
                                    radius: row.showAffordance ? GaugePalette.glowRadius(row.zoneKey) : 0,
                                    x: 0,
                                    y: 0
                                )
                        }

                        GeometryReader { geo in
                            if let progress {
                                let point = markerPosition(in: geo.size, progress: progress)
                                Circle()
                                    .fill(GaugePalette.marker)
                                    .overlay(Circle().stroke(GaugePalette.zoneColor(row.zoneKey), lineWidth: 1.75))
                                    .frame(width: 10, height: 10)
                                    .position(point)
                            }
                        }

                        VStack(spacing: 2) {
                            HStack(spacing: 4) {
                                Text(valueText)
                                    .font(.system(size: 24, weight: .heavy, design: .rounded))
                                if row.value != nil {
                                    Text(deltaText)
                                        .font(.caption2)
                                        .foregroundColor(deltaColor)
                                }
                            }
                            Text(statusText)
                                .font(.caption)
                                .foregroundColor(
                                    row.value == nil
                                    ? .secondary
                                    : GaugePalette.zoneColor(row.zoneKey)
                                )
                        }
                    }
                    .frame(width: meterSize, height: meterSize)
                    .frame(maxWidth: .infinity)

                    if !zoneKeyText.isEmpty {
                        Text(zoneKeyText)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(10)
                .background(Color.black.opacity(0.25))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(
                            row.showAffordance
                            ? GaugePalette.zoneColor(row.zoneKey).opacity(0.45)
                            : Color.white.opacity(0.05),
                            lineWidth: row.showAffordance ? 1.2 : 1
                        )
                )
                .shadow(
                    color: row.showAffordance
                    ? GaugePalette.zoneColor(row.zoneKey).opacity(0.20)
                    : .clear,
                    radius: row.showAffordance ? 8 : 0,
                    x: 0,
                    y: 0
                )
            }

            var body: some View {
                if let onTap {
                    Button(action: onTap) {
                        content
                    }
                    .buttonStyle(.plain)
                } else {
                    content
                }
            }
        }

        private struct DriverStatusRow: View {
            let driver: DashboardDriverItem
            let tappable: Bool
            let showAffordance: Bool
            let zoneKey: String
            let progress: Double
            let onTap: (() -> Void)?

            private func formattedValue() -> String {
                guard let value = driver.value else { return "" }
                let unit = (driver.unit ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let key = driver.key.lowercased()
                let text: String
                if key == "sw" || key == "aqi" {
                    text = String(Int(round(value)))
                } else if key == "schumann" {
                    text = String(format: "%.2f", value)
                } else if abs(value - round(value)) < 0.01 {
                    text = String(Int(round(value)))
                } else {
                    text = String(format: "%.1f", value)
                }
                if unit.isEmpty { return text }
                if key == "temp" {
                    return "\(text)\u{00B0}C"
                }
                return "\(text) \(unit)"
            }

            private var content: some View {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(driver.label ?? driver.key.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.subheadline.weight(.semibold))
                            if let roleLabel = driver.roleLabel, !roleLabel.isEmpty {
                                Text(roleLabel)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundColor(GaugePalette.zoneColor(zoneKey))
                            }
                        }
                        Spacer(minLength: 6)
                        Text(driver.state ?? "Low")
                            .font(.caption)
                            .foregroundColor(GaugePalette.zoneColor(zoneKey))
                        let value = formattedValue()
                        if !value.isEmpty {
                            Text(value)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        if showAffordance {
                            Image(systemName: "sparkles")
                                .font(.caption2)
                                .foregroundColor(GaugePalette.zoneColor(zoneKey))
                        }
                    }
                    GeometryReader { geo in
                        let width = max(18, geo.size.width * progress)
                        ZStack(alignment: .leading) {
                            Capsule()
                                .fill(GaugePalette.zoneColor(zoneKey).opacity(0.18))
                                .frame(height: 10)
                            Capsule()
                                .fill(GaugePalette.zoneColor(zoneKey).opacity(0.50))
                                .frame(width: width, height: 10)
                        }
                    }
                    .frame(height: 10)
                    if let personalReason = driver.personalReason, !personalReason.isEmpty {
                        Text(personalReason)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(10)
                .background(Color.black.opacity(0.20))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(
                            showAffordance
                            ? GaugePalette.zoneColor(zoneKey).opacity(0.38)
                            : Color.white.opacity(0.06),
                            lineWidth: showAffordance ? 1.1 : 1
                        )
                )
                .shadow(
                    color: showAffordance ? GaugePalette.zoneColor(zoneKey).opacity(0.16) : .clear,
                    radius: showAffordance ? 7 : 0,
                    x: 0,
                    y: 0
                )
            }

            var body: some View {
                if let onTap {
                    Button(action: onTap) {
                        content
                    }
                    .buttonStyle(.plain)
                } else {
                    content
                }
            }
        }

        private struct ContextModalSheetView: View {
            let entry: DashboardModalEntry
            let onQuickLog: (MissionControlQuickLogRequest) -> Void
            let onOpenCustomLog: (SymptomQueuedEvent) -> Void
            @Environment(\.dismiss) private var dismiss
            @State private var selectedQuickLog: DashboardQuickLogOption? = nil

            private var modalType: String {
                (entry.modalType ?? "full").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            }

            private var quickLog: DashboardQuickLog? {
                if let quickLog = entry.quickLog {
                    return quickLog
                }
                let options = (entry.cta?.prefill ?? ["OTHER"]).map { code in
                    DashboardQuickLogOption(
                        code: normalize(code),
                        label: normalize(code).replacingOccurrences(of: "_", with: " ").capitalized
                    )
                }
                return DashboardQuickLog(
                    title: "Log what you're feeling:",
                    confirmLabel: entry.cta?.label,
                    options: options,
                    defaultSeverity: nil,
                    baseTags: nil
                )
            }

            private func quickLogSection(_ quickLog: DashboardQuickLog) -> some View {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Quick Log")
                        .font(.headline)
                    if let title = quickLog.title, !title.isEmpty {
                        Text(title)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    let options = quickLog.options ?? []
                    let columns = [GridItem(.adaptive(minimum: 120), spacing: 10)]
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(options) { option in
                            Button {
                                if selectedQuickLog == option {
                                    selectedQuickLog = nil
                                } else {
                                    selectedQuickLog = option
                                }
                            } label: {
                                Text(option.label)
                                    .font(.subheadline.weight(.semibold))
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 10)
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.plain)
                            .background(
                                Capsule()
                                    .fill(
                                        selectedQuickLog == option
                                        ? Color.accentColor.opacity(0.22)
                                        : Color.white.opacity(0.08)
                                    )
                            )
                            .overlay(
                                Capsule()
                                    .stroke(
                                        selectedQuickLog == option
                                        ? Color.accentColor.opacity(0.9)
                                        : Color.white.opacity(0.10),
                                        lineWidth: 1
                                    )
                            )
                        }
                        Button {
                            var event = SymptomQueuedEvent(symptomCode: SymptomCodeHelper.fallbackCode, tsUtc: Date())
                            event.severity = quickLog.defaultSeverity
                            event.tags = quickLog.baseTags
                            onOpenCustomLog(event)
                        } label: {
                            Text("Custom / Other")
                                .font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 10)
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.plain)
                        .background(
                            Capsule()
                                .fill(Color.white.opacity(0.06))
                        )
                        .overlay(
                            Capsule()
                                .stroke(Color.white.opacity(0.16), lineWidth: 1)
                        )
                    }
                    let confirmLabel = quickLog.confirmLabel?.isEmpty == false ? quickLog.confirmLabel! : "Log Symptoms"
                    Button(confirmLabel) {
                        guard let selectedQuickLog else { return }
                        var event = SymptomQueuedEvent(symptomCode: selectedQuickLog.code, tsUtc: Date())
                        event.severity = quickLog.defaultSeverity
                        event.tags = quickLog.baseTags
                        onQuickLog(MissionControlQuickLogRequest(label: selectedQuickLog.label, event: event))
                        dismiss()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedQuickLog == nil)
                }
            }

            var body: some View {
                NavigationStack {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            if let title = entry.title, !title.isEmpty {
                                Text(title)
                                    .font(.title3.weight(.bold))
                            }
                            if modalType == "short" {
                                if let body = entry.body, !body.isEmpty {
                                    Text(body)
                                        .font(.body)
                                }
                                if let tip = entry.tip, !tip.isEmpty {
                                    VStack(alignment: .leading, spacing: 8) {
                                        Text("Tip")
                                            .font(.headline)
                                        Text(tip)
                                            .font(.subheadline)
                                    }
                                }
                            } else if let why = entry.why, !why.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Why")
                                        .font(.headline)
                                    ForEach(Array(why.enumerated()), id: \.offset) { _, line in
                                        Text("\u{2022} \(line)")
                                            .font(.subheadline)
                                    }
                                }
                            }
                            if let notice = entry.whatYouMayNotice, !notice.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("What Might Stand Out")
                                        .font(.headline)
                                    ForEach(Array(notice.enumerated()), id: \.offset) { _, line in
                                        Text("\u{2022} \(line)")
                                            .font(.subheadline)
                                    }
                                }
                            }
                            if let actions = entry.suggestedActions, !actions.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("What May Help Right Now")
                                        .font(.headline)
                                    ForEach(Array(actions.enumerated()), id: \.offset) { _, line in
                                        Text("\u{2022} \(line)")
                                            .font(.subheadline)
                                    }
                                }
                            }
                            if let quickLog {
                                quickLogSection(quickLog)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                    }
                    .navigationTitle("Why This Matters Now")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Close") { dismiss() }
                        }
                    }
                }
            }
        }

        private struct CameraCheckCard: View {
            let summary: CameraHealthDailySummary?
            let isLoading: Bool
            let errorText: String?

            private func statusColor(_ summary: CameraHealthDailySummary?) -> Color {
                switch summary?.summaryStatus ?? .pending {
                case .good:
                    return .green
                case .partial:
                    return .yellow
                case .poor:
                    return .orange
                case .pending:
                    return .secondary
                }
            }

            private func statusLabel(_ summary: CameraHealthDailySummary?) -> String {
                (summary?.summaryStatus ?? .pending).rawValue.capitalized
            }

            private func qualityLabel(_ quality: String?) -> String {
                let token = (quality ?? "unknown").trimmingCharacters(in: .whitespacesAndNewlines)
                if token.isEmpty { return "Unknown" }
                return token.capitalized
            }

            private func saveScopeText(_ summary: CameraHealthDailySummary) -> String {
                switch summary.persistedSaveScope {
                case .account:
                    return "Saved to your account"
                case .localOnly:
                    return "Saved locally only"
                case .notSaved:
                    return "Not saved"
                }
            }

            private func summaryText(_ summary: CameraHealthDailySummary) -> String {
                switch summary.summaryStatus {
                case .good:
                    return "Heart rate and HRV were captured."
                case .partial:
                    if summary.hrvMetricStatus == .notRequested {
                        return "Heart rate captured. HRV was not requested in Quick HR mode."
                    }
                    return "Heart rate captured. HRV was withheld because quality was too low."
                case .poor:
                    return "No reliable reading captured."
                case .pending:
                    return "Latest check pending."
                }
            }

            private func poorSuggestion(_ summary: CameraHealthDailySummary) -> String {
                if summary.qualityScore ?? 0 < 0.45 {
                    return "Try lighter pressure, full lens coverage, and keep still."
                }
                return "Try another run after adjusting finger placement."
            }

            private func timeText(_ raw: String?) -> String? {
                guard let raw, let date = ISO8601DateFormatter().date(from: raw) else { return nil }
                let out = DateFormatter()
                out.dateStyle = .none
                out.timeStyle = .short
                return out.string(from: date)
            }

            var body: some View {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Label("Latest Check", systemImage: "camera.metering.center.weighted")
                            .font(.headline)
                        Spacer()
                        if summary != nil {
                            Text(statusLabel(summary))
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(statusColor(summary).opacity(0.18))
                                .foregroundColor(statusColor(summary))
                                .clipShape(Capsule())
                        }
                    }
                    if isLoading {
                        ProgressView("Loading latest check...")
                            .font(.caption)
                    } else if let errorText, !errorText.isEmpty, summary == nil {
                        Text(errorText)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    } else if let summary {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 12) {
                                if summary.hasUsableHR {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("BPM")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                        Text(summary.bpm.map { String(Int($0.rounded())) } ?? "--")
                                            .font(.title3.weight(.bold))
                                    }
                                }
                                if summary.hasUsableHRV {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("RMSSD")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                        Text(summary.rmssdMs.map { "\(Int($0.rounded())) ms" } ?? "--")
                                            .font(.subheadline.weight(.semibold))
                                    }
                                }
                                if let timestamp = timeText(summary.latestTsUtc) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("Time")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                        Text(timestamp)
                                            .font(.caption.weight(.semibold))
                                    }
                                }
                            }
                            Text(summaryText(summary))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            if summary.summaryStatus == .poor {
                                Text(poorSuggestion(summary))
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                            Text("\(saveScopeText(summary)) | Quality \(qualityLabel(summary.qualityLabel))")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        Text("Wellness estimate only. Not medical advice.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    } else {
                        Text("No camera check yet today.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(10)
                .background(Color.black.opacity(0.20))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                )
            }
        }

        private func gaugeRows(_ g: DashboardGaugeSet?) -> [GaugeRow] {
            guard let g else { return [] }
            let values: [(String, Double?)] = [
                ("pain", g.pain),
                ("focus", g.focus),
                ("heart", g.heart),
                ("stamina", g.stamina),
                ("energy", g.energy),
                ("sleep", g.sleep),
                ("mood", g.mood),
                ("health_status", g.healthStatus),
            ]
            let fallbackLabels: [String: String] = [
                "pain": "Pain",
                "focus": "Focus",
                "heart": "Heart",
                "stamina": "Recovery Load",
                "energy": "Energy",
                "sleep": "Sleep",
                "mood": "Mood",
                "health_status": "Health Status",
            ]
            return values.map { key, value in
                let meta = gaugesMeta[key]
                let zoneKey = meta?.zone ?? inferredZoneKey(for: value)
                let delta = gaugesDelta[key] ?? 0
                let tappable = modalModels?.gauges?[key] != nil
                return GaugeRow(
                    key: key,
                    label: gaugeLabels[key] ?? fallbackLabels[key] ?? key,
                    value: value,
                    delta: delta,
                    zoneKey: zoneKey,
                    zoneLabel: meta?.label,
                    tappable: tappable,
                    showAffordance: gaugeShowsAffordance(zoneKey: zoneKey, zoneLabel: meta?.label)
                )
            }
        }

        private func gaugeHasAffordance(zoneKey: String?) -> Bool {
            let zone = (zoneKey ?? "").lowercased()
            return zone == "elevated" || zone == "high"
        }

        private func gaugeShowsAffordance(zoneKey: String?, zoneLabel: String?) -> Bool {
            if gaugeHasAffordance(zoneKey: zoneKey) {
                return true
            }
            let label = (zoneLabel ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return label.contains("elevated") || label.contains("high") || label.contains("watch")
        }

        private func driverSeverityKey(_ raw: String?) -> String {
            let token = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if token == "high" { return "high" }
            if token == "watch" { return "elevated" }
            if token == "elevated" { return "elevated" }
            if token == "mild" { return "mild" }
            return "low"
        }

        private func driverProgress(_ raw: String?) -> Double {
            let token = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if token == "high" { return 1.0 }
            if token == "watch" || token == "elevated" { return 0.76 }
            if token == "mild" { return 0.5 }
            return 0.28
        }

        private func driverHasAffordance(_ raw: String?) -> Bool {
            let token = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return token == "watch" || token == "elevated" || token == "high"
        }

        private func presentGaugeModal(_ key: String) {
            guard let entry = modalModels?.gauges?[key] else { return }
            selectedModal = ModalPresentation(id: "gauge:\(key)", entry: entry)
        }

        private func presentDriverModal(_ key: String) {
            guard let entry = modalModels?.drivers?[key] else { return }
            selectedModal = ModalPresentation(id: "driver:\(key)", entry: entry)
        }

        private func presentPushRouteIfPossible(_ route: GaiaPushRoute?) {
            guard let route else { return }
            let targetKey = route.targetKey.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !targetKey.isEmpty else {
                pushRoute = nil
                return
            }
            let targetType = route.targetType.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if targetType == "gauge", let entry = modalModels?.gauges?[targetKey] {
                selectedModal = ModalPresentation(id: "gauge:\(targetKey)", entry: entry)
            } else if targetType == "driver", let entry = modalModels?.drivers?[targetKey] {
                selectedModal = ModalPresentation(id: "driver:\(targetKey)", entry: entry)
            }
            pushRoute = nil
        }

        private func inferredZoneKey(for value: Double?) -> String? {
            guard let value else { return nil }
            let zones = resolvedZones()
            for zone in zones {
                if value >= zone.min && value <= zone.max {
                    return zone.key
                }
            }
            guard let first = zones.first, let last = zones.last else { return nil }
            if value < first.min { return first.key }
            return last.key
        }

        private func resolvedZones() -> [DashboardGaugeZone] {
            let sorted = gaugeZones.sorted { $0.min < $1.min }
            return sorted.isEmpty ? DashboardGaugeZone.defaultZones : sorted
        }

        private func pillSeverity(_ raw: String?) -> StatusPill.Severity {
            let s = (raw ?? "").lowercased()
            if s == "high" || s == "alert" || s == "red" { return .alert }
            if s == "watch" || s == "warn" || s == "orange" || s == "yellow" { return .warn }
            return .ok
        }

        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    if isLoading {
                        ProgressView("Loading dashboard…")
                            .font(.caption)
                    } else if let errorMessage, !errorMessage.isEmpty {
                        Text("Dashboard refresh issue: \(errorMessage)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    let rows = gaugeRows(gauges)
                    if rows.isEmpty {
                        Text("Gauges are calibrating.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        let cols = [GridItem(.flexible()), GridItem(.flexible())]
                        LazyVGrid(columns: cols, spacing: 10) {
                            ForEach(rows) { row in
                                ArcGaugeCard(
                                    row: row,
                                    onTap: row.tappable ? { presentGaugeModal(row.key) } : nil
                                )
                            }
                        }
                        HStack(spacing: 10) {
                            ForEach(["low", "mild", "elevated", "high"], id: \.self) { key in
                                HStack(spacing: 4) {
                                    Circle()
                                        .fill(GaugePalette.zoneColor(key))
                                        .frame(width: 7, height: 7)
                                    Text(key.capitalized)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }
                    }

                    if !alerts.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(alerts) { alert in
                                    StatusPill(alert.title ?? (alert.key ?? "Alert"), severity: pillSeverity(alert.severity))
                                }
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("What Matters Now")
                            .font(.headline)
                        if drivers.isEmpty {
                            Text("No major environmental drivers are elevated right now.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            ForEach(Array(drivers.prefix(3))) { driver in
                                let zoneKey = driverSeverityKey(driver.severity)
                                let tappable = modalModels?.drivers?[driver.key] != nil
                                DriverStatusRow(
                                    driver: driver,
                                    tappable: tappable,
                                    showAffordance: driverHasAffordance(driver.severity),
                                    zoneKey: zoneKey,
                                    progress: driverProgress(driver.severity),
                                    onTap: tappable ? { presentDriverModal(driver.key) } : nil
                                )
                            }
                        }
                    }

                    EarthscopeCardV2(
                        title: earthscope?.title ?? fallbackTitle,
                        updatedAt: earthscope?.updatedAt,
                        bodyMarkdown: earthscope?.bodyMarkdown ?? fallbackBody,
                        summaryText: earthscopeSummary,
                        driversCompact: driversCompact
                    )

                    CameraCheckCard(
                        summary: latestCameraCheck,
                        isLoading: cameraCheckLoading,
                        errorText: cameraCheckError
                    )

                    if let lastUpdatedText, !lastUpdatedText.isEmpty {
                        Text("Last updated: \(lastUpdatedText)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            } label: {
                Label("Mission Control", systemImage: "dial.medium")
            }
            .sheet(item: $selectedModal) { modal in
                ContextModalSheetView(
                    entry: modal.entry,
                    onQuickLog: onQuickLog,
                    onOpenCustomLog: { event in
                        selectedModal = nil
                        DispatchQueue.main.async {
                            onOpenCustomLog(event)
                        }
                    }
                )
            }
            .onAppear {
                presentPushRouteIfPossible(pushRoute)
            }
            .onChange(of: pushRoute, initial: false) { _, newValue in
                presentPushRouteIfPossible(newValue)
            }
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
        let updatedText: String?
        let usingYesterdayFallback: Bool
        let forecast: ForecastSummary?
        let outlook: SpaceForecastOutlook?
        let seriesDetail: SpaceSeries?
        let showVisualsPreview: Bool
        let onSelectVisual: (SpaceVisualItem) -> Void
        @Binding var showSpaceWeatherDetail: Bool
        @Binding var spaceDetailFocus: SpaceDetailSection?

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
                    forecast: forecast
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
        let swDensityNow: Double?
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
            swDensityNow = outlook?.swDensityNowCm3
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

        var body: some View {
            VStack(spacing: 16) {
                if (current.kpAlert ?? false) || (current.flareAlert ?? false) {
                    SpaceAlertsCard(kpAlert: current.kpAlert ?? false, flareAlert: current.flareAlert ?? false)
                        .padding(.horizontal)
                }

                if let fc = forecast {
                    ForecastCard(summary: fc).padding(.horizontal)
                }
            }
        }
    }

    private struct InsightsHubView: View {
        let current: FeaturesToday?
        let outlook: SpaceForecastOutlook?
        let userOutlook: UserForecastOutlook?
        let updatedText: String?
        let usingYesterdayFallback: Bool
        let localHealthZip: String
        let localHealth: LocalCheckResponse?
        let localHealthLoading: Bool
        let localHealthError: String?
        let userOutlookLoading: Bool
        let userOutlookError: String?
        let useGPS: Bool
        let localInsightsEnabled: Bool
        let dashboardDrivers: [DashboardDriverItem]
        let magnetosphere: MagnetosphereData?
        let magnetosphereLoading: Bool
        let magnetosphereError: String?
        let symptomsTodayCount: Int
        let queuedSymptomsCount: Int
        let topSymptomSummary: String?
        let latestCameraCheck: CameraHealthDailySummary?
        let latestCameraCheckLoading: Bool
        let latestCameraCheckError: String?
        let quakeLatest: QuakeDaily?
        let quakeEvents: [QuakeEvent]
        let quakeLoading: Bool
        let quakeError: String?
        let hazardsBrief: HazardsBriefResponse?
        let hazardsLoading: Bool
        let hazardsError: String?
        let onRefresh: () async -> Void

        private struct HubMetric: Identifiable {
            let id = UUID()
            let label: String
            let value: String
            let tint: Color
        }

        private struct HubCard: View {
            private static let metricColumns = [
                GridItem(.adaptive(minimum: 96, maximum: 220), spacing: 10, alignment: .topLeading)
            ]

            let title: String
            let icon: String
            let status: String
            let pillText: String
            let severity: StatusPill.Severity
            let metrics: [HubMetric]
            let isExplore: Bool

            var body: some View {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 12) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(Color.white.opacity(isExplore ? 0.05 : 0.10))
                            Image(systemName: icon)
                                .font(.headline)
                                .foregroundColor(.white.opacity(isExplore ? 0.72 : 0.90))
                        }
                        .frame(width: isExplore ? 42 : 48, height: isExplore ? 42 : 48)

                        VStack(alignment: .leading, spacing: 4) {
                            Text(title)
                                .font(isExplore ? .headline : .title3.weight(.semibold))
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(status)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        VStack(alignment: .trailing, spacing: 10) {
                            StatusPill(pillText, severity: severity)
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.white.opacity(0.44))
                        }
                    }

                    if !metrics.isEmpty {
                        LazyVGrid(columns: Self.metricColumns, alignment: .leading, spacing: 10) {
                            ForEach(metrics.prefix(3)) { metric in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(metric.label.uppercased())
                                        .font(.caption2.weight(.semibold))
                                        .foregroundColor(.secondary)
                                    Text(metric.value)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.78)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(metric.tint.opacity(isExplore ? 0.10 : 0.15))
                                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                                        .stroke(metric.tint.opacity(isExplore ? 0.14 : 0.22), lineWidth: 1)
                                )
                            }
                        }
                    }
                }
                .padding(isExplore ? 14 : 16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(isExplore ? 0.035 : 0.06))
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(Color.white.opacity(isExplore ? 0.05 : 0.08), lineWidth: 1)
                )
            }
        }

        private func statusSeverity(for kp: Double?) -> StatusPill.Severity {
            guard let kp else { return .ok }
            if kp >= 6 { return .alert }
            if kp >= 4 { return .warn }
            return .ok
        }

        private func severity(for raw: String?) -> StatusPill.Severity {
            LocalConditionsStyle.pillSeverity(raw)
        }

        private func dashboardDriver(for key: String) -> DashboardDriverItem? {
            dashboardDrivers.first {
                $0.key.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == key.lowercased()
            }
        }

        private func normalizedPillText(_ raw: String?, fallback: String) -> String {
            let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return trimmed.isEmpty ? fallback : trimmed
        }

        private func localConditionsPill(weather: LocalWeather?, air: LocalAir?) -> (text: String, severity: StatusPill.Severity) {
            let tempSwing = abs(weather?.tempDelta24hC ?? 0)
            let pressureSwing = abs(weather?.baroDelta24hHpa ?? 0)
            let aqi = air?.aqi ?? 0

            if tempSwing >= 12 || pressureSwing >= 12 || aqi >= 151 {
                return ("High", .alert)
            }
            if tempSwing >= 6 || pressureSwing >= 6 || aqi >= 51 {
                return ("Watch", .warn)
            }
            return ("Stable", .ok)
        }

        private func countHazardSeverities(_ items: [HazardItem]) -> (red: Int, orange: Int) {
            items.reduce(into: (red: 0, orange: 0)) { counts, item in
                let severity = (item.severity ?? "").lowercased()
                if severity.contains("red") {
                    counts.red += 1
                } else if severity.contains("orange") {
                    counts.orange += 1
                }
            }
        }

        private var localLocationSummary: String {
            let resolvedZip = (localHealth?.whereInfo?.zip ?? localHealthZip).trimmingCharacters(in: .whitespacesAndNewlines)
            if useGPS {
                return resolvedZip.isEmpty ? "GPS preferred" : "GPS preferred • ZIP \(resolvedZip)"
            }
            return resolvedZip.isEmpty ? "ZIP not set" : "ZIP \(resolvedZip)"
        }

        private var spaceWeatherCard: some View {
            let kpNow = current?.kpCurrent?.value
            let swSpeed = current?.swSpeedAvg?.value
            let flares = Int((current?.flaresCount?.value ?? 0).rounded())
            let geomagneticState = normalizedPillText(
                outlook?.kp?.gScaleNow?.capitalized,
                fallback: (kpNow.map { $0 >= 5 ? "Active" : "Quiet" } ?? "Quiet")
            )
            let kpText = kpNow.map { String(format: "%.1f", $0) } ?? "—"
            let swText = swSpeed.map { String(format: "%.0f km/s", $0) } ?? "—"
            let flareText = flares == 0 ? "0" : "\(flares)"
            let status: String
            if let kpNow, kpNow >= 5 {
                status = "Geomagnetic activity is elevated right now."
            } else if let updatedText, !updatedText.isEmpty {
                status = "\(geomagneticState) geomagnetic conditions. Updated \(updatedText)."
            } else {
                status = "\(geomagneticState) geomagnetic conditions with fresh summary metrics."
            }

            return NavigationLink(value: InsightsRoute.spaceWeather) {
                HubCard(
                    title: "Space Weather",
                    icon: "sun.max.fill",
                    status: status,
                    pillText: geomagneticState,
                    severity: statusSeverity(for: kpNow),
                    metrics: [
                        HubMetric(label: "Kp", value: kpText, tint: GaugePalette.zoneColor(kpNow.map { $0 >= 4 ? "elevated" : "low" })),
                        HubMetric(label: "Wind", value: swText, tint: GaugePalette.mild),
                        HubMetric(label: "Flares", value: flareText, tint: GaugePalette.elevated)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var localConditionsCard: some View {
            let weather = localHealth?.weather
            let air = localHealth?.air
            let pill = localConditionsPill(weather: weather, air: air)
            let tempText = LocalConditionsFormatting.formatTempMetric(weather?.tempC)
            let pressureText = LocalConditionsFormatting.formatPressureShort(weather?.pressureHpa)
            let aqiText = LocalConditionsFormatting.formatNumber(air?.aqi, decimals: 0)
            let status: String
            if let error = ContentView.scrubError(localHealthError) {
                status = error
            } else if !localInsightsEnabled {
                status = "Local insights are off until location sharing is enabled."
            } else if localHealthLoading {
                status = "Refreshing local conditions for \(localLocationSummary)."
            } else {
                status = "Weather, air quality, and moon signals for \(localLocationSummary)."
            }

            return NavigationLink(value: InsightsRoute.localConditions) {
                HubCard(
                    title: "Local Conditions",
                    icon: "location.fill",
                    status: status,
                    pillText: !localInsightsEnabled ? "Off" : pill.text,
                    severity: !localInsightsEnabled ? .warn : (ContentView.scrubError(localHealthError) == nil ? pill.severity : .warn),
                    metrics: [
                        HubMetric(label: "Temp", value: tempText, tint: GaugePalette.low),
                        HubMetric(label: "AQI", value: aqiText, tint: GaugePalette.mild),
                        HubMetric(label: "Pressure", value: pressureText, tint: GaugePalette.elevated)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var yourOutlookCard: some View {
            let next24 = userOutlook?.next24h
            let next72 = userOutlook?.next72h
            let available = userOutlook?.availableWindows ?? []
            let primaryWindow = next24 ?? next72
            let topDomain24 = next24?.likelyElevatedDomains?.first
            let topDomain72 = next72?.likelyElevatedDomains?.first
            let primaryDriver = primaryWindow?.topDrivers?.first
            let pillText: String
            let pillSeverity: StatusPill.Severity
            if userOutlookLoading {
                pillText = "Loading"
                pillSeverity = .warn
            } else if let likelihood = topDomain24?.likelihood ?? topDomain72?.likelihood {
                pillText = likelihood.capitalized
                pillSeverity = severity(for: likelihood)
            } else if !available.isEmpty {
                pillText = "Ready"
                pillSeverity = .ok
            } else {
                pillText = "Pending"
                pillSeverity = .warn
            }
            let status: String
            if let error = ContentView.scrubError(userOutlookError) {
                status = error
            } else if userOutlookLoading {
                status = "Building your next 24 to 72 hour outlook from your patterns and live forecast inputs."
            } else if userOutlook?.forecastDataReady?.locationFound == false {
                status = "Set your location to unlock a personal short-range outlook."
            } else if let summary = primaryWindow?.summary, !summary.isEmpty {
                status = summary
            } else {
                status = "Forecast inputs are syncing before the personal outlook appears."
            }

            return NavigationLink(value: InsightsRoute.yourOutlook) {
                HubCard(
                    title: "Your Outlook",
                    icon: "calendar.badge.clock",
                    status: status,
                    pillText: pillText,
                    severity: pillSeverity,
                    metrics: [
                        HubMetric(label: "24h", value: topDomain24?.label ?? "—", tint: GaugePalette.low),
                        HubMetric(label: "72h", value: topDomain72?.label ?? "—", tint: GaugePalette.mild),
                        HubMetric(label: "Driver", value: primaryDriver?.label ?? "—", tint: GaugePalette.elevated),
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var yourPatternsCard: some View {
            NavigationLink(value: InsightsRoute.yourPatterns) {
                HubCard(
                    title: "Your Patterns",
                    icon: "chart.line.text.clipboard",
                    status: "Patterns drawn from your own logs and repeating signal overlap.",
                    pillText: "Deterministic",
                    severity: .ok,
                    metrics: [
                        HubMetric(label: "Source", value: "Your logs", tint: GaugePalette.low),
                        HubMetric(label: "Window", value: "0-48h", tint: GaugePalette.mild),
                        HubMetric(label: "Method", value: "No ML", tint: GaugePalette.elevated)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var magnetosphereCard: some View {
            let kpis = magnetosphere?.kpis
            let sw = magnetosphere?.sw
            let storminess = (kpis?.storminess ?? "Quiet").capitalized
            let geoRisk = (kpis?.geoRisk ?? "Low").capitalized
            let bzText = sw?.bzNt.map { String(format: "%.1f nT", $0) } ?? "—"
            let r0Text = kpis?.r0Re.map { String(format: "%.1f Re", $0) } ?? "—"
            let kpText = kpis?.kp.map { String(format: "%.1f", $0) } ?? "—"
            let severity: StatusPill.Severity = {
                if storminess.lowercased().contains("storm") || geoRisk.lowercased().contains("high") {
                    return .alert
                }
                if storminess.lowercased().contains("active") || geoRisk.lowercased().contains("elev") {
                    return .warn
                }
                if ContentView.scrubError(magnetosphereError) != nil {
                    return .warn
                }
                return .ok
            }()
            let status: String
            if let error = ContentView.scrubError(magnetosphereError) {
                status = error
            } else if magnetosphereLoading {
                status = "Refreshing coupling and shield-edge conditions."
            } else {
                status = "\(storminess) storminess with \(geoRisk.lowercased()) GEO risk."
            }

            return NavigationLink(value: InsightsRoute.magnetosphere) {
                HubCard(
                    title: "Magnetosphere",
                    icon: "shield.lefthalf.filled",
                    status: status,
                    pillText: storminess,
                    severity: severity,
                    metrics: [
                        HubMetric(label: "R0", value: r0Text, tint: GaugePalette.low),
                        HubMetric(label: "Bz", value: bzText, tint: GaugePalette.elevated),
                        HubMetric(label: "Kp", value: kpText, tint: GaugePalette.mild)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var schumannCard: some View {
            let schumannDriver = dashboardDriver(for: "schumann")
            let station = current?.schStation?.capitalized ?? "Station"
            let f0Text = current?.schF0Hz?.value.map { String(format: "%.2f Hz", $0) } ?? "—"
            let f1Text = current?.schF1Hz?.value.map { String(format: "%.2f Hz", $0) } ?? "—"
            let updated = updatedText ?? "recent"
            let pillText = normalizedPillText(
                schumannDriver?.state?.capitalized,
                fallback: current?.schF0Hz?.value == nil ? "Pending" : "Active"
            )
            let status = "Dedicated resonance dashboard with live harmonics and quality detail."

            return NavigationLink(value: InsightsRoute.schumann) {
                HubCard(
                    title: "Schumann Resonance",
                    icon: "waveform.path.ecg",
                    status: "\(status) Last app summary \(updated).",
                    pillText: pillText,
                    severity: schumannDriver == nil ? .warn : severity(for: schumannDriver?.severity),
                    metrics: [
                        HubMetric(label: "Source", value: station, tint: GaugePalette.low),
                        HubMetric(label: "f0", value: f0Text, tint: GaugePalette.mild),
                        HubMetric(label: "f1", value: f1Text, tint: GaugePalette.elevated)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var healthCard: some View {
            let sleepText: String = {
                guard let current else { return "—" }
                let total = Int((current.sleepTotalMinutes?.value ?? 0).rounded())
                return "\(total / 60)h \(total % 60)m"
            }()
            let stepsText = current.map { "\(Int(($0.stepsTotal?.value ?? 0).rounded()))" } ?? "—"
            let cameraText = latestCameraCheck?.bpm.map { "\(Int($0.rounded())) bpm" } ?? "—"
            let status: String
            if symptomsTodayCount > 0 {
                status = "\(symptomsTodayCount) symptoms logged today. Open for sleep, vitals, and comparisons."
            } else if let topSymptomSummary, !topSymptomSummary.isEmpty {
                status = topSymptomSummary
            } else if queuedSymptomsCount > 0 {
                status = "\(queuedSymptomsCount) symptom entries are queued to sync."
            } else {
                status = "Symptoms are quiet right now. Open for deeper health context."
            }
            let severity: StatusPill.Severity = symptomsTodayCount >= 4 ? .alert : queuedSymptomsCount > 0 ? .warn : .ok
            let pillText = symptomsTodayCount > 0 ? "Active" : (queuedSymptomsCount > 0 ? "Syncing" : "Quiet")

            return NavigationLink(value: InsightsRoute.healthSymptoms) {
                HubCard(
                    title: "Health & Symptoms",
                    icon: "heart.text.square.fill",
                    status: status,
                    pillText: pillText,
                    severity: severity,
                    metrics: [
                        HubMetric(label: "Sleep", value: sleepText, tint: GaugePalette.low),
                        HubMetric(label: "Steps", value: stepsText, tint: GaugePalette.mild),
                        HubMetric(label: "Quick Check", value: cameraText, tint: GaugePalette.elevated)
                    ],
                    isExplore: false
                )
            }
            .buttonStyle(.plain)
        }

        private var earthquakesCard: some View {
            let total = quakeLatest?.allQuakes ?? quakeEvents.count
            let maxMag = quakeEvents.max(by: { ($0.mag ?? 0) < ($1.mag ?? 0) })?.mag
            let status: String
            if let error = ContentView.scrubError(quakeError) {
                status = error
            } else if quakeLoading {
                status = "Refreshing the global quake snapshot."
            } else if maxMag != nil {
                status = "Interesting global quake context, outside the core daily loop."
            } else {
                status = "Open for recent quake context when you want to explore."
            }

            return NavigationLink(value: InsightsRoute.earthquakes) {
                HubCard(
                    title: "Earthquakes",
                    icon: "waveform.path",
                    status: status,
                    pillText: (maxMag ?? 0) >= 6.5 ? "Watch" : "Ready",
                    severity: (maxMag ?? 0) >= 6.5 ? .warn : .ok,
                    metrics: [
                        HubMetric(label: "Total", value: total > 0 ? "\(total)" : "—", tint: GaugePalette.low),
                        HubMetric(label: "Max", value: maxMag.map { String(format: "M%.1f", $0) } ?? "—", tint: GaugePalette.elevated),
                        HubMetric(label: "M6+", value: quakeLatest?.m6p.map(String.init) ?? "—", tint: GaugePalette.mild)
                    ],
                    isExplore: true
                )
            }
            .buttonStyle(.plain)
        }

        private var hazardsCard: some View {
            let items = hazardsBrief?.items ?? []
            let severityCounts = countHazardSeverities(items)
            let total = items.count
            let status: String
            if let error = ContentView.scrubError(hazardsError) {
                status = error
            } else if hazardsLoading {
                status = "Refreshing the GDACS hazard brief."
            } else if total > 0 {
                status = "Global hazards stay available as optional exploration."
            } else {
                status = "Open for the latest hazard brief if you want broader context."
            }

            return NavigationLink(value: InsightsRoute.hazards) {
                HubCard(
                    title: "Hazards",
                    icon: "exclamationmark.triangle.fill",
                    status: status,
                    pillText: severityCounts.red > 0 ? "Alert" : severityCounts.orange > 0 ? "Watch" : "Ready",
                    severity: severityCounts.red > 0 ? .alert : severityCounts.orange > 0 ? .warn : .ok,
                    metrics: [
                        HubMetric(label: "Active", value: total > 0 ? "\(total)" : "—", tint: GaugePalette.low),
                        HubMetric(label: "Red", value: "\(severityCounts.red)", tint: GaugePalette.high),
                        HubMetric(label: "Orange", value: "\(severityCounts.orange)", tint: GaugePalette.elevated)
                    ],
                    isExplore: true
                )
            }
            .buttonStyle(.plain)
        }

        var body: some View {
            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Start with what matters now.")
                                .font(.system(size: 32, weight: .bold, design: .rounded))
                            Text("Open a card for plain-language context on what may matter for you right now.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            if usingYesterdayFallback {
                                Label("Showing yesterday’s features while today finishes updating.", systemImage: "clock.arrow.circlepath")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        spaceWeatherCard
                        localConditionsCard
                        yourOutlookCard
                        yourPatternsCard
                        magnetosphereCard
                        schumannCard
                        healthCard

                        VStack(alignment: .leading, spacing: 10) {
                            Text("Explore")
                                .font(.headline.weight(.semibold))
                            Text("Interesting context, but kept secondary so Insights stays fast and personal.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            earthquakesCard
                            hazardsCard
                        }
                        .padding(.top, 4)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .refreshable {
                    await onRefresh()
                }
            }
            .navigationTitle("Insights")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct YourOutlookView: View {
        let payload: UserForecastOutlook?
        let isLoading: Bool
        let error: String?
        let onRefresh: () -> Void

        private let columns = [
            GridItem(.adaptive(minimum: 150, maximum: 260), spacing: 10, alignment: .topLeading)
        ]

        private func severity(_ raw: String?) -> StatusPill.Severity {
            LocalConditionsStyle.pillSeverity(raw)
        }

        private func formatUpdate(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let fmt = ISO8601DateFormatter()
            guard let date = fmt.date(from: iso) else { return nil }
            let out = DateFormatter()
            out.dateStyle = .medium
            out.timeStyle = .short
            return out.string(from: date)
        }

        private func driverValue(_ driver: UserOutlookDriver) -> String {
            if let value = driver.value {
                if let unit = driver.unit, !unit.isEmpty {
                    return "\(String(format: "%.1f", value)) \(unit)"
                }
                return String(format: "%.1f", value)
            }
            if let day = driver.day, !day.isEmpty {
                return day
            }
            return (driver.severity ?? "watch").capitalized
        }

        private func availabilityText(_ raw: String) -> String {
            switch raw {
            case "next_24h":
                return "24h"
            case "next_72h":
                return "72h"
            case "next_7d":
                return "7d"
            default:
                return raw
            }
        }

        private func windowTitle(_ hours: Int?) -> String {
            switch hours {
            case 24:
                return "Next 24 Hours"
            case 72:
                return "Next 72 Hours"
            default:
                return "Outlook"
            }
        }

        @ViewBuilder
        private func domainCard(_ domain: UserOutlookDomain) -> some View {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 8) {
                    Text(domain.label ?? domain.key.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    StatusPill((domain.likelihood ?? "watch").capitalized, severity: severity(domain.likelihood))
                }
                if let gauge = domain.currentGauge {
                    Text("Current gauge \(Int(gauge.rounded()))")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if let explanation = domain.explanation, !explanation.isEmpty {
                    Text(explanation)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
            )
        }

        @ViewBuilder
        private func windowSection(_ window: UserOutlookWindow?) -> some View {
            if let window {
                let drivers = window.topDrivers ?? []
                let domains = window.likelyElevatedDomains ?? []

                LocalConditionsSurfaceCard(title: windowTitle(window.windowHours), icon: "sparkles.rectangle.stack.fill") {
                    VStack(alignment: .leading, spacing: 12) {
                        if let summary = window.summary, !summary.isEmpty {
                            Text(summary)
                                .font(.subheadline)
                        }

                        if let primary = drivers.first {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .top, spacing: 8) {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("Primary driver")
                                            .font(.caption2.weight(.semibold))
                                            .foregroundColor(.secondary)
                                        Text(primary.label ?? primary.key.replacingOccurrences(of: "_", with: " ").capitalized)
                                            .font(.headline)
                                    }
                                    Spacer()
                                    StatusPill((primary.severity ?? "watch").capitalized, severity: severity(primary.severity))
                                }
                                if let detail = primary.detail, !detail.isEmpty {
                                    Text(detail)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }

                        if drivers.count > 1 {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Supporting drivers")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundColor(.secondary)
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 10) {
                                        ForEach(Array(drivers.dropFirst())) { driver in
                                            LocalConditionsValueChip(
                                                label: driver.label ?? driver.key.capitalized,
                                                value: driverValue(driver),
                                                tint: GaugePalette.zoneColor(driver.severity)
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        if !domains.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Likely elevated domains")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundColor(.secondary)
                                LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                                    ForEach(domains) { domain in
                                        domainCard(domain)
                                    }
                                }
                            }
                        }

                        if let supportLine = window.supportLine, !supportLine.isEmpty {
                            Text(supportLine)
                                .font(.footnote)
                                .foregroundColor(.secondary)
                                .padding(.top, 2)
                        }
                    }
                }
            }
        }

        var body: some View {
            let cleanError = ContentView.scrubError(error)

            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        LocalConditionsSurfaceCard(title: "Near-Future Outlook", icon: "calendar.badge.clock") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("Next 24-72 hours")
                                        .font(.system(size: 30, weight: .bold, design: .rounded))
                                    Text("Deterministic guidance from your recent patterns, current gauges, and real local plus SWPC forecast inputs.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    if let updated = formatUpdate(payload?.generatedAt) {
                                        Text("Updated \(updated)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Spacer()
                                if isLoading { ProgressView().scaleEffect(0.85) }
                                Button("Refresh") { onRefresh() }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }

                            if let cleanError, !cleanError.isEmpty {
                                Text(cleanError)
                                    .font(.caption)
                                    .foregroundColor(.orange)
                            }

                            if let windows = payload?.availableWindows, !windows.isEmpty {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 10) {
                                        ForEach(windows, id: \.self) { item in
                                            LocalConditionsValueChip(
                                                label: "Window",
                                                value: availabilityText(item),
                                                tint: GaugePalette.low
                                            )
                                        }
                                    }
                                }
                            } else if !isLoading && cleanError == nil {
                                Text("Forecast inputs are still syncing for a personal short-range outlook.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        windowSection(payload?.next24h)
                        windowSection(payload?.next72h)

                        if payload?.forecastDataReady?.next7d != true {
                            LocalConditionsSurfaceCard(title: "7-Day Outlook", icon: "calendar") {
                                Text("7-day outlook coming soon. It stays hidden until the input layer is stable enough to support it cleanly.")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Your Outlook")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct YourPatternsView: View {
        @EnvironmentObject private var state: AppState
        @State private var payload: UserPatternsPayload? = nil
        @State private var isLoading: Bool = false
        @State private var errorMessage: String? = nil

        private func confidenceSeverity(_ confidence: String?) -> StatusPill.Severity {
            switch (confidence ?? "").lowercased() {
            case "strong":
                return .ok
            case "moderate":
                return .warn
            case "emerging":
                return .warn
            default:
                return .ok
            }
        }

        private func displayDate(_ value: String?) -> String {
            guard let value, let parsed = ISO8601DateFormatter().date(from: value) else { return "—" }
            let formatter = DateFormatter()
            formatter.dateStyle = .medium
            formatter.timeStyle = .none
            return formatter.string(from: parsed)
        }

        private func liftLine(_ card: UserPatternCard) -> String {
            let lift = String(format: "%.1fx", card.relativeLift ?? 0)
            let lag = card.lagLabel ?? "same day"
            let sample = card.sampleSize ?? card.exposedDays ?? 0
            return "\(lift) more often • \(sample) exposed days • Lag: \(lag)"
        }

        private func rateLine(_ card: UserPatternCard) -> String {
            let exposedRate = Int(round((card.exposedRate ?? 0) * 100))
            let baselineRate = Int(round((card.unexposedRate ?? 0) * 100))
            let lastSeen = displayDate(card.lastSeenAt)
            return "Exposed days: \(exposedRate)% • Other days: \(baselineRate)% • Last seen: \(lastSeen)"
        }

        private func iconName(for signalKey: String) -> String {
            switch signalKey {
            case "pressure_swing_exposed":
                return "gauge.with.dots.needle.bottom.50percent"
            case "aqi_moderate_plus_exposed":
                return "aqi.low"
            case "temp_swing_exposed":
                return "thermometer.medium"
            case "kp_g1_plus_exposed":
                return "sun.max.fill"
            case "bz_south_exposed":
                return "arrow.down.circle"
            case "solar_wind_exposed":
                return "wind"
            case "schumann_exposed":
                return "waveform.path.ecg"
            default:
                return "chart.line.uptrend.xyaxis"
            }
        }

        private func loadPatterns(force: Bool = false) async {
            if isLoading && !force {
                return
            }
            isLoading = true
            defer { isLoading = false }

            do {
                let api = state.apiWithAuth()
                let decoded: UserPatternsPayload = try await api.getJSON("v1/patterns", as: UserPatternsPayload.self, perRequestTimeout: 20)
                payload = decoded
                errorMessage = nil
            } catch {
                if payload == nil {
                    errorMessage = ContentView.scrubError(error.localizedDescription)
                }
            }
        }

        private struct PatternCardView: View {
            let card: UserPatternCard
            let iconName: String
            let confidenceSeverity: StatusPill.Severity
            let liftLine: String
            let rateLine: String

            var body: some View {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top, spacing: 12) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(Color.white.opacity(0.06))
                            Image(systemName: iconName)
                                .font(.headline)
                                .foregroundColor(.white.opacity(0.88))
                        }
                        .frame(width: 44, height: 44)

                        VStack(alignment: .leading, spacing: 4) {
                            Text(card.outcome)
                                .font(.headline.weight(.semibold))
                                .foregroundColor(.white.opacity(0.95))
                            Text(card.signal)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }

                        Spacer(minLength: 8)

                        VStack(alignment: .trailing, spacing: 6) {
                            if card.usedToday == true {
                                Text(card.usedTodayLabel ?? "Active now")
                                    .font(.caption2.weight(.semibold))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(Color.green.opacity(0.16))
                                    .foregroundColor(Color.green.opacity(0.95))
                                    .clipShape(Capsule())
                            }
                            StatusPill(card.confidence ?? "Observed", severity: confidenceSeverity)
                        }
                    }

                    Text(card.explanation)
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.88))

                    Text(liftLine)
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Text(rateLine)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
            }
        }

        @ViewBuilder
        private func sectionView(title: String, subtitle: String, cards: [UserPatternCard], emptyMessage: String) -> some View {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.title3.weight(.semibold))
                    Text(subtitle)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                if cards.isEmpty {
                    Text(emptyMessage)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.white.opacity(0.04))
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                } else {
                    ForEach(cards) { card in
                        PatternCardView(
                            card: card,
                            iconName: iconName(for: card.signalKey),
                            confidenceSeverity: confidenceSeverity(card.confidence),
                            liftLine: liftLine(card),
                            rateLine: rateLine(card)
                        )
                    }
                }
            }
        }

        var body: some View {
            let strongest = payload?.strongestPatterns ?? []
            let emerging = payload?.emergingPatterns ?? []
            let bodySignals = payload?.bodySignalsPatterns ?? []

            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("What keeps showing up for you.")
                                .font(.system(size: 30, weight: .bold, design: .rounded))
                            Text(payload?.disclaimer ?? "Patterns compare your own logged outcomes against recurring signals in your recent history.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }

                        if let errorMessage, payload == nil {
                            Text(errorMessage)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .padding(16)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.white.opacity(0.04))
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }

                        if isLoading && payload == nil {
                            HStack(spacing: 10) {
                                ProgressView()
                                Text("Refreshing your latest pattern cards.")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.white.opacity(0.04))
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }

                        sectionView(
                            title: "Clearest Patterns",
                            subtitle: "The most reliable repeats in your history so far.",
                            cards: strongest,
                            emptyMessage: "No higher-confidence patterns are ready yet. Keep logging symptoms and daily history will sharpen this section."
                        )

                        sectionView(
                            title: "Still Taking Shape",
                            subtitle: "Signals that may be repeating, but still need more overlap.",
                            cards: emerging,
                            emptyMessage: "Nothing is emerging yet. This section fills in after repeated signal and symptom overlap."
                        )

                        sectionView(
                            title: "Body Signals",
                            subtitle: "Wearable-based patterns only show when the overlap is strong enough to meet the current evidence rules.",
                            cards: bodySignals,
                            emptyMessage: "No clear body-signal patterns are standing out yet."
                        )
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .refreshable {
                    await loadPatterns(force: true)
                }
            }
            .navigationTitle("Your Patterns")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await loadPatterns(force: true) }
                    } label: {
                        if isLoading {
                            ProgressView()
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                }
            }
            .task {
                if payload == nil {
                    await loadPatterns()
                }
            }
        }
    }

    private struct InsightsSpaceWeatherView: View {
        let current: FeaturesToday?
        let updatedText: String?
        let usingYesterdayFallback: Bool
        let forecast: ForecastSummary?
        let outlook: SpaceForecastOutlook?
        let series: SpaceSeries?

        private func geomagneticSeverity(kp: Double?) -> StatusPill.Severity {
            guard let kp else { return .ok }
            if kp >= 6 { return .alert }
            if kp >= 4 { return .warn }
            return .ok
        }

        private func progress(_ value: Double?, max: Double) -> Double {
            guard let value, max > 0 else { return 0.12 }
            return LocalConditionsFormatting.clamped(abs(value) / max)
        }

        private func bzSeverity(_ bz: Double?) -> String {
            guard let bz else { return "low" }
            if bz <= -10 { return "high" }
            if bz <= -5 { return "elevated" }
            if bz < 0 { return "mild" }
            return "low"
        }

        private func windSeverity(_ speed: Double?) -> String {
            guard let speed else { return "low" }
            if speed >= 650 { return "high" }
            if speed >= 550 { return "elevated" }
            if speed >= 450 { return "mild" }
            return "low"
        }

        private func severity(_ raw: String?) -> StatusPill.Severity {
            LocalConditionsStyle.pillSeverity(raw)
        }

        private var metrics: SpaceWeatherCardMetrics? {
            current.map { SpaceWeatherCardMetrics(current: $0, outlook: outlook, series: series) }
        }

        private func cleanedOutlookLine(_ raw: String?) -> String? {
            guard let raw else { return nil }
            let trimmed = raw
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: "•", with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            let lower = trimmed.lowercased()
            if lower == "space weather outlook" || lower == "outlook" || lower == "forecast" {
                return nil
            }
            return trimmed
        }

        private var forecastBodyLines: [String] {
            guard let body = forecast?.body, !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return []
            }
            return body
                .components(separatedBy: .newlines)
                .compactMap(cleanedOutlookLine)
        }

        private var sectionSummaryLines: [String] {
            (outlook?.sections ?? [])
                .flatMap { section in
                    section.entries.compactMap { entry in
                        cleanedOutlookLine(entry.summary ?? entry.title)
                    }
                }
        }

        private func outlookMetricValue(matching keywords: [String]) -> Double? {
            let lowered = keywords.map { $0.lowercased() }
            for section in outlook?.sections ?? [] {
                for entry in section.entries {
                    let haystack = [
                        entry.title?.lowercased(),
                        entry.summary?.lowercased(),
                        entry.driver?.lowercased(),
                        entry.metric?.lowercased()
                    ]
                    .compactMap { $0 }
                    .joined(separator: " ")
                    if lowered.contains(where: { haystack.contains($0) }), let value = entry.value {
                        return value
                    }
                }
            }
            return nil
        }

        private var outlookSummaryLines: [String] {
            var lines: [String] = []
            if let headline = cleanedOutlookLine(outlook?.headline), !lines.contains(headline) {
                lines.append(headline)
            }
            if let summary = cleanedOutlookLine(outlook?.summary), !lines.contains(summary) {
                lines.append(summary)
            }
            if let forecastHeadline = cleanedOutlookLine(forecast?.headline), !lines.contains(forecastHeadline) {
                lines.append(forecastHeadline)
            }
            for bucket in [forecast?.lines ?? [], forecastBodyLines, outlook?.alerts ?? [], sectionSummaryLines, outlook?.notes ?? []] {
                for rawLine in bucket {
                    if let line = cleanedOutlookLine(rawLine), !lines.contains(line) {
                        lines.append(line)
                    }
                    if lines.count >= 4 {
                        return Array(lines.prefix(4))
                    }
                }
            }
            return Array(lines.prefix(4))
        }

        private func forecastDayLabel(_ iso: String?) -> String {
            guard let iso else { return "Day" }
            let fmt = ISO8601DateFormatter()
            if let date = fmt.date(from: iso) {
                let out = DateFormatter()
                out.dateFormat = "EEE, MMM d"
                return out.string(from: date)
            }
            let simple = DateFormatter()
            simple.dateFormat = "yyyy-MM-dd"
            if let date = simple.date(from: iso) {
                let out = DateFormatter()
                out.dateFormat = "EEE, MMM d"
                return out.string(from: date)
            }
            return iso
        }

        private func watchFlags(for day: SpaceForecastDay) -> [String] {
            var flags: [String] = []
            if day.cmeWatch == true { flags.append("CME watch") }
            if day.flareWatch == true { flags.append("Flare watch") }
            if day.solarWindWatch == true { flags.append("Solar wind watch") }
            return flags
        }

        var body: some View {
            let metrics = metrics
            let kpNow = metrics?.kpNow
            let kpMax = metrics?.kpMax
            let bzNow = metrics?.bzNow
            let swSpeed = metrics?.swSpeedNow
            let density = metrics?.swDensityNow
                ?? outlookMetricValue(matching: ["density", "cm^-3", "cm-3", "cm3"])
            let protonFlux = metrics?.protonFlux
            let flaresCount = outlook?.flares?.total24h ?? Int((current?.flaresCount?.value ?? 0).rounded())
            let cmeCount = outlook?.cmes?.stats?.total72h ?? Int((current?.cmesCount?.value ?? 0).rounded())
            let geomagneticState = outlook?.kp?.gScaleNow ?? (kpNow.map { $0 >= 5 ? "Active" : "Quiet" } ?? "Quiet")

            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        LocalConditionsSurfaceCard(title: "Geomagnetic State", icon: "sun.max.fill") {
                            VStack(alignment: .leading, spacing: 12) {
                                HStack(alignment: .top, spacing: 12) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(geomagneticState)
                                            .font(.system(size: 32, weight: .bold, design: .rounded))
                                        if let updatedText {
                                            Text("Updated \(updatedText)")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                    Spacer()
                                    StatusPill(geomagneticState, severity: geomagneticSeverity(kp: kpNow))
                                }

                                HStack(spacing: 12) {
                                    LocalConditionsMetricTile(
                                        title: "Kp Now",
                                        value: kpNow.map { String(format: "%.1f", $0) } ?? "—",
                                        progress: progress(kpNow, max: 9),
                                        tint: GaugePalette.zoneColor(kpNow.map { $0 >= 4 ? "elevated" : "low" })
                                    )
                                    LocalConditionsMetricTile(
                                        title: "Kp 24h Max",
                                        value: kpMax.map { String(format: "%.1f", $0) } ?? "—",
                                        progress: progress(kpMax, max: 9),
                                        tint: GaugePalette.zoneColor(kpMax.map { $0 >= 5 ? "high" : $0 >= 4 ? "elevated" : "low" })
                                    )
                                }

                                if usingYesterdayFallback {
                                    Text("Showing yesterday’s feature summary while today updates.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Solar Wind", icon: "dot.radiowaves.left.and.right") {
                            HStack(spacing: 12) {
                                LocalConditionsMetricTile(
                                    title: "Bz",
                                    value: bzNow.map { String(format: "%.1f nT", $0) } ?? "—",
                                    progress: progress(bzNow, max: 20),
                                    tint: GaugePalette.zoneColor(bzSeverity(bzNow))
                                )
                                LocalConditionsMetricTile(
                                    title: "Speed",
                                    value: swSpeed.map { String(format: "%.0f km/s", $0) } ?? "—",
                                    progress: progress(swSpeed, max: 800),
                                    tint: GaugePalette.zoneColor(windSeverity(swSpeed))
                                )
                            }
                            HStack(spacing: 10) {
                                LocalConditionsValueChip(
                                    label: "Density",
                                    value: density.map { String(format: "%.1f cm^-3", $0) } ?? "—",
                                    tint: GaugePalette.mild
                                )
                                LocalConditionsValueChip(
                                    label: "Proton Flux",
                                    value: protonFlux.map { String(format: "%.1f pfu", $0) } ?? "—",
                                    tint: GaugePalette.elevated
                                )
                                LocalConditionsValueChip(
                                    label: "S-Scale",
                                    value: metrics?.sScale ?? "S0",
                                    tint: GaugePalette.zoneColor((metrics?.sScale ?? "S0") == "S0" ? "low" : "elevated")
                                )
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Events", icon: "bolt.horizontal.fill") {
                            HStack(spacing: 10) {
                                LocalConditionsValueChip(
                                    label: "Flares",
                                    value: "\(flaresCount)",
                                    tint: GaugePalette.mild
                                )
                                LocalConditionsValueChip(
                                    label: "CMEs",
                                    value: "\(cmeCount)",
                                    tint: GaugePalette.elevated
                                )
                                LocalConditionsValueChip(
                                    label: "Confidence",
                                    value: outlook?.confidence ?? "—",
                                    tint: GaugePalette.low
                                )
                            }
                            if let headline = outlook?.cmes?.headline, !headline.isEmpty {
                                Text(headline)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        if !outlookSummaryLines.isEmpty {
                            LocalConditionsSurfaceCard(title: "Outlook", icon: "text.justify.left") {
                                VStack(alignment: .leading, spacing: 8) {
                                    ForEach(Array(outlookSummaryLines.enumerated()), id: \.offset) { _, line in
                                        Text("• \(line)")
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                    }
                                }
                            }
                        }

                        if let forecastDays = outlook?.forecastDaily, !forecastDays.isEmpty {
                            LocalConditionsSurfaceCard(title: "3-Day Space Forecast", icon: "calendar") {
                                VStack(alignment: .leading, spacing: 12) {
                                    ForEach(forecastDays) { day in
                                        VStack(alignment: .leading, spacing: 8) {
                                            HStack(alignment: .top, spacing: 12) {
                                                VStack(alignment: .leading, spacing: 3) {
                                                    Text(forecastDayLabel(day.forecastDay))
                                                        .font(.headline)
                                                    Text(day.gScaleMax ?? "Geomagnetic outlook")
                                                        .font(.caption)
                                                        .foregroundColor(.secondary)
                                                }
                                                Spacer()
                                                StatusPill(
                                                    (day.geomagneticSeverityBucket ?? "mild").capitalized,
                                                    severity: severity(day.geomagneticSeverityBucket)
                                                )
                                            }

                                            ScrollView(.horizontal, showsIndicators: false) {
                                                HStack(spacing: 10) {
                                                    LocalConditionsValueChip(
                                                        label: "Kp Max",
                                                        value: day.kpMaxForecast.map { String(format: "%.1f", $0) } ?? "—",
                                                        tint: GaugePalette.low
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "G-Scale",
                                                        value: day.gScaleMax ?? "—",
                                                        tint: GaugePalette.elevated
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "S1+",
                                                        value: day.s1OrGreaterPct.map { String(format: "%.0f%%", $0) } ?? "—",
                                                        tint: GaugePalette.mild
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "R1-R2",
                                                        value: day.r1R2Pct.map { String(format: "%.0f%%", $0) } ?? "—",
                                                        tint: GaugePalette.elevated
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "R3+",
                                                        value: day.r3OrGreaterPct.map { String(format: "%.0f%%", $0) } ?? "—",
                                                        tint: GaugePalette.high
                                                    )
                                                }
                                            }

                                            let flags = watchFlags(for: day)
                                            if !flags.isEmpty {
                                                Text(flags.joined(separator: " · "))
                                                    .font(.caption2.weight(.semibold))
                                                    .foregroundColor(.secondary)
                                            }

                                            if let rationale = cleanedOutlookLine(day.geomagneticRationale), !rationale.isEmpty {
                                                Text(rationale)
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                        }
                                        .padding(.bottom, day.id == forecastDays.last?.id ? 0 : 8)

                                        if day.id != forecastDays.last?.id {
                                            Divider().overlay(Color.white.opacity(0.08))
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Space Weather")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct InsightsMagnetosphereView: View {
        let data: MagnetosphereData?
        let isLoading: Bool
        let error: String?

        private func formatValue(_ value: Double?, decimals: Int = 1, suffix: String = "") -> String {
            guard let value else { return "—" }
            let base = String(format: "%.\(decimals)f", value)
            return suffix.isEmpty ? base : "\(base) \(suffix)"
        }

        private func progress(_ value: Double?, max: Double) -> Double {
            guard let value, max > 0 else { return 0.12 }
            return LocalConditionsFormatting.clamped(abs(value) / max)
        }

        private func chartPoints() -> [(Date, Double)] {
            let fmt = ISO8601DateFormatter()
            return (data?.series?.r0 ?? []).compactMap { point in
                guard let t = point.t, let v = point.v, let d = fmt.date(from: t) else { return nil }
                return (d, v)
            }
        }

        var body: some View {
            let kpis = data?.kpis
            let sw = data?.sw

            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        LocalConditionsSurfaceCard(title: "Magnetosphere Summary", icon: "shield.lefthalf.filled") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text((kpis?.storminess ?? "Quiet").capitalized)
                                        .font(.system(size: 32, weight: .bold, design: .rounded))
                                    Text("GEO risk \((kpis?.geoRisk ?? "Low").capitalized) • GIC feel \((kpis?.dbdt ?? "Low").capitalized)")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                    if let ts = data?.ts {
                                        Text("Updated \(ts)")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Spacer()
                                if isLoading {
                                    ProgressView()
                                } else {
                                    StatusPill(
                                        (kpis?.storminess ?? "Quiet"),
                                        severity: (kpis?.storminess ?? "").lowercased().contains("storm")
                                            ? .alert
                                            : (kpis?.storminess ?? "").lowercased().contains("active")
                                            ? .warn
                                            : .ok
                                    )
                                }
                            }
                            if let cleanError = ContentView.scrubError(error) {
                                Text(cleanError)
                                    .font(.caption)
                                    .foregroundColor(.orange)
                            }
                        }

                        LocalConditionsSurfaceCard(title: "KPIs", icon: "gauge.with.dots.needle.bottom.50percent") {
                            HStack(spacing: 12) {
                                LocalConditionsMetricTile(
                                    title: "R0",
                                    value: formatValue(kpis?.r0Re, suffix: "Re"),
                                    progress: progress(kpis?.r0Re, max: 16),
                                    tint: GaugePalette.low
                                )
                                LocalConditionsMetricTile(
                                    title: "Plasmapause",
                                    value: formatValue(kpis?.lppRe, suffix: "Re"),
                                    progress: progress(kpis?.lppRe, max: 8),
                                    tint: GaugePalette.mild
                                )
                                LocalConditionsMetricTile(
                                    title: "Kp",
                                    value: formatValue(kpis?.kp),
                                    progress: progress(kpis?.kp, max: 9),
                                    tint: GaugePalette.elevated
                                )
                            }
                            HStack(spacing: 10) {
                                LocalConditionsValueChip(label: "Storminess", value: (kpis?.storminess ?? "—").capitalized, tint: GaugePalette.mild)
                                LocalConditionsValueChip(label: "GEO Risk", value: (kpis?.geoRisk ?? "—").capitalized, tint: GaugePalette.elevated)
                                LocalConditionsValueChip(label: "Trend", value: (data?.trend?.r0 ?? "—").capitalized, tint: GaugePalette.low)
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Solar Wind Coupling", icon: "arrow.triangle.2.circlepath") {
                            HStack(spacing: 12) {
                                LocalConditionsMetricTile(
                                    title: "Density",
                                    value: formatValue(sw?.nCm3, suffix: "cm^-3"),
                                    progress: progress(sw?.nCm3, max: 20),
                                    tint: GaugePalette.mild
                                )
                                LocalConditionsMetricTile(
                                    title: "Speed",
                                    value: formatValue(sw?.vKms, decimals: 0, suffix: "km/s"),
                                    progress: progress(sw?.vKms, max: 800),
                                    tint: GaugePalette.elevated
                                )
                                LocalConditionsMetricTile(
                                    title: "Bz",
                                    value: formatValue(sw?.bzNt, suffix: "nT"),
                                    progress: progress(sw?.bzNt, max: 20),
                                    tint: GaugePalette.zoneColor((sw?.bzNt ?? 0) <= -5 ? "elevated" : "low")
                                )
                            }
                        }

                        if !chartPoints().isEmpty {
                            LocalConditionsSurfaceCard(title: "Shield Edge Trend", icon: "chart.xyaxis.line") {
                                Chart(chartPoints(), id: \.0) { point in
                                    LineMark(
                                        x: .value("Time", point.0),
                                        y: .value("R0", point.1)
                                    )
                                    .interpolationMethod(.catmullRom)
                                    .foregroundStyle(GaugePalette.low)
                                }
                                .frame(height: 200)
                            }
                        }

                        LocalConditionsSurfaceCard(title: "How to Read This", icon: "text.book.closed.fill") {
                            Text("R0 tracks the magnetopause boundary, while the coupling metrics summarize how solar wind pressure and Bz may be loading the system. Higher Kp, stronger southward Bz, and tighter shield-edge values usually mean more active geospace conditions.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Magnetosphere")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct InsightsHealthStatsCard: View {
        let current: FeaturesToday?
        let updatedText: String?

        private func metric(_ label: String, value: String, tint: Color) -> some View {
            LocalConditionsValueChip(label: label, value: value, tint: tint)
        }

        var body: some View {
            LocalConditionsSurfaceCard(title: "Health Stats", icon: "heart.fill") {
                VStack(alignment: .leading, spacing: 12) {
                    if let updatedText {
                        Text("Updated \(updatedText)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    HStack(spacing: 10) {
                        metric("Steps", value: current.map { "\(Int(($0.stepsTotal?.value ?? 0).rounded()))" } ?? "—", tint: GaugePalette.low)
                        metric("HRV", value: current?.hrvAvg?.value.map { "\(Int($0.rounded()))" } ?? "—", tint: GaugePalette.mild)
                        metric("SpO₂", value: current?.spo2AvgDisplay.map { String(format: "%.0f%%", $0) } ?? "—", tint: GaugePalette.elevated)
                    }
                    HStack(spacing: 10) {
                        metric(
                            "Heart Rate",
                            value: {
                                let minText = current?.hrMin?.value.map { "\(Int($0.rounded()))" } ?? "—"
                                let maxText = current?.hrMax?.value.map { "\(Int($0.rounded()))" } ?? "—"
                                return "\(minText)-\(maxText)"
                            }(),
                            tint: GaugePalette.low
                        )
                        metric(
                            "Blood Pressure",
                            value: {
                                let sys = current?.bpSysAvg?.value.map { "\(Int($0.rounded()))" } ?? "—"
                                let dia = current?.bpDiaAvg?.value.map { "\(Int($0.rounded()))" } ?? "—"
                                return "\(sys)/\(dia)"
                            }(),
                            tint: GaugePalette.mild
                        )
                    }
                }
            }
        }
    }

    private struct InsightsCameraCheckCard: View {
        let summary: CameraHealthDailySummary?
        let isLoading: Bool
        let errorText: String?
        let onOpenQuickCheck: () -> Void

        private func statusColor(_ summary: CameraHealthDailySummary?) -> Color {
            switch summary?.summaryStatus ?? .pending {
            case .good:
                return GaugePalette.low
            case .partial:
                return GaugePalette.mild
            case .poor:
                return GaugePalette.elevated
            case .pending:
                return .secondary
            }
        }

        private func statusLabel(_ summary: CameraHealthDailySummary?) -> String {
            (summary?.summaryStatus ?? .pending).rawValue.capitalized
        }

        private func statusSeverity(_ summary: CameraHealthDailySummary?) -> StatusPill.Severity {
            switch summary?.summaryStatus ?? .pending {
            case .good:
                return .ok
            case .partial:
                return .warn
            case .poor:
                return .alert
            case .pending:
                return .warn
            }
        }

        private func qualityLabel(_ quality: String?) -> String {
            let token = (quality ?? "unknown").trimmingCharacters(in: .whitespacesAndNewlines)
            if token.isEmpty { return "Unknown" }
            return token.capitalized
        }

        private func saveScopeText(_ summary: CameraHealthDailySummary) -> String {
            switch summary.persistedSaveScope {
            case .account:
                return "Saved to your account"
            case .localOnly:
                return "Saved locally only"
            case .notSaved:
                return "Not saved"
            }
        }

        private func summaryText(_ summary: CameraHealthDailySummary) -> String {
            switch summary.summaryStatus {
            case .good:
                return "Heart rate and HRV were captured."
            case .partial:
                if summary.hrvMetricStatus == .notRequested {
                    return "Heart rate captured. HRV was not requested in Quick HR mode."
                }
                return "Heart rate captured. HRV was withheld because quality was too low."
            case .poor:
                return "No reliable reading captured. Try lighter pressure and keep still."
            case .pending:
                return "No quick check recorded yet today."
            }
        }

        private func metricChips(_ summary: CameraHealthDailySummary) -> some View {
            HStack(spacing: 10) {
                if summary.hasUsableHR {
                    LocalConditionsValueChip(
                        label: "BPM",
                        value: summary.bpm.map { "\(Int($0.rounded()))" } ?? "--",
                        tint: statusColor(summary)
                    )
                }
                if summary.hasUsableHRV {
                    LocalConditionsValueChip(
                        label: "RMSSD",
                        value: summary.rmssdMs.map { "\(Int($0.rounded())) ms" } ?? "--",
                        tint: GaugePalette.low
                    )
                }
                LocalConditionsValueChip(
                    label: "Time",
                    value: timeText(summary.latestTsUtc),
                    tint: GaugePalette.mild
                )
            }
        }

        private func timeText(_ raw: String?) -> String {
            guard let raw, let date = ISO8601DateFormatter().date(from: raw) else { return "—" }
            let out = DateFormatter()
            out.dateStyle = .none
            out.timeStyle = .short
            return out.string(from: date)
        }

        var body: some View {
            LocalConditionsSurfaceCard(title: "Quick Health Check", icon: "camera.metering.center.weighted") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(statusLabel(summary))
                                .font(.title3.weight(.semibold))
                            Text("Camera-based wellness estimate only. Not medical advice.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        StatusPill(statusLabel(summary), severity: statusSeverity(summary))
                    }

                    if isLoading {
                        ProgressView("Loading latest check...")
                            .font(.caption)
                    } else if let errorText, !errorText.isEmpty, summary == nil {
                        Text(errorText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if let summary {
                        VStack(alignment: .leading, spacing: 10) {
                            metricChips(summary)
                            Text(summaryText(summary))
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("\(saveScopeText(summary)) | Quality \(qualityLabel(summary.qualityLabel))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    } else {
                        Text("No quick check recorded yet today.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Button(action: onOpenQuickCheck) {
                        Label("Open Quick Health Check", systemImage: "camera.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
    }

    private struct InsightsHealthSymptomsView: View {
        let current: FeaturesToday?
        let todayString: String
        let updatedText: String?
        let bannerText: String?
        let usingYesterdayFallback: Bool
        let todayCount: Int
        let queuedCount: Int
        let sparklinePoints: [SymptomSparkPoint]
        let topSummary: String?
        let diagnostics: [SymptomDiagSummary]
        let series: SpaceSeries?
        let highlights: [SymptomHighlight]
        let latestCameraCheck: CameraHealthDailySummary?
        let latestCameraCheckLoading: Bool
        let latestCameraCheckError: String?
        @Binding var showSymptomSheet: Bool
        let onOpenQuickCheck: () -> Void
        let onLoadComparison: () async -> Void
        @State private var selectedRange: InsightsTrendRange = .days7
        @State private var isComparisonExpanded: Bool = false
        @State private var hasStartedComparisonLoad: Bool = false

        private var topDiagnostics: [SymptomDiagSummary] {
            diagnostics.sorted { $0.events > $1.events }
        }

        private func ensureComparisonLoad(immediate: Bool = false) {
            guard series == nil, !hasStartedComparisonLoad else { return }
            hasStartedComparisonLoad = true
            Task {
                if !immediate {
                    try? await Task.sleep(nanoseconds: 600_000_000)
                }
                if Task.isCancelled { return }
                await onLoadComparison()
            }
        }

        var body: some View {
            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        SymptomsTileView(
                            todayCount: todayCount,
                            queuedCount: queuedCount,
                            sparklinePoints: sparklinePoints,
                            topSummary: topSummary,
                            onLogTap: { showSymptomSheet = true }
                        )

                        if let current {
                            SleepCard(
                                title: current.day == todayString ? "Sleep (Today)" : "Sleep (\(current.day))",
                                totalMin: Int((current.sleepTotalMinutes?.value ?? 0).rounded()),
                                remMin: Int((current.remM?.value ?? 0).rounded()),
                                coreMin: Int((current.coreM?.value ?? 0).rounded()),
                                deepMin: Int((current.deepM?.value ?? 0).rounded()),
                                awakeMin: Int((current.awakeM?.value ?? 0).rounded()),
                                inbedMin: Int((current.inbedM?.value ?? 0).rounded()),
                                efficiency: current.sleepEfficiency?.value
                            )
                        }

                        if let bannerText, !bannerText.isEmpty {
                            LocalConditionsSurfaceCard(title: "Sleep Sync", icon: "clock.arrow.circlepath") {
                                Text(bannerText)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }

                        if usingYesterdayFallback {
                            LocalConditionsSurfaceCard(title: "Feature Lag", icon: "calendar.badge.clock") {
                                Text("Today’s health features are still filling in, so this page is currently showing yesterday’s summary where needed.")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }

                        InsightsHealthStatsCard(
                            current: current,
                            updatedText: updatedText
                        )

                        if !topDiagnostics.isEmpty {
                            LocalConditionsSurfaceCard(title: "Top Symptoms", icon: "waveform.path.ecg") {
                                VStack(spacing: 10) {
                                    ForEach(Array(topDiagnostics.prefix(3).enumerated()), id: \.offset) { _, item in
                                        HStack(spacing: 10) {
                                            Text(item.symptomCode.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.subheadline.weight(.semibold))
                                            Spacer()
                                            LocalConditionsValueChip(
                                                label: "Events",
                                                value: "\(item.events)",
                                                tint: GaugePalette.mild
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Comparison Chart", icon: "chart.xyaxis.line") {
                            VStack(alignment: .leading, spacing: 12) {
                                Button {
                                    withAnimation(.easeInOut(duration: 0.18)) {
                                        isComparisonExpanded.toggle()
                                    }
                                    if isComparisonExpanded {
                                        ensureComparisonLoad(immediate: true)
                                    }
                                } label: {
                                    HStack(alignment: .center, spacing: 12) {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("Signals vs Symptoms")
                                                .font(.subheadline.weight(.semibold))
                                            Text(
                                                series == nil
                                                    ? "Loads after the page opens and stays hidden until you want the deeper comparison."
                                                    : "7, 14, or 30 day signal comparison is ready on demand."
                                            )
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                            .fixedSize(horizontal: false, vertical: true)
                                        }
                                        Spacer()
                                        if hasStartedComparisonLoad && series == nil {
                                            ProgressView()
                                                .scaleEffect(0.82)
                                        }
                                        Image(systemName: isComparisonExpanded ? "chevron.up.circle.fill" : "chevron.down.circle.fill")
                                            .foregroundColor(.white.opacity(0.72))
                                    }
                                }
                                .buttonStyle(.plain)

                                if isComparisonExpanded {
                                    Picker("Range", selection: $selectedRange) {
                                        ForEach(InsightsTrendRange.allCases) { range in
                                            Text(range.rawValue).tag(range)
                                        }
                                    }
                                    .pickerStyle(.segmented)

                                    Text("Signals vs symptoms over \(selectedRange.title.lowercased()). Default is 7 days for a faster read, with 14 and 30 day context on demand.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)

                                    if let series {
                                        SpaceChartsCard(
                                            title: "Signals vs Symptoms",
                                            series: series,
                                            highlights: highlights,
                                            window: selectedRange,
                                            showsSchumann: true
                                        )
                                    } else if hasStartedComparisonLoad {
                                        ProgressView("Loading comparison…")
                                            .font(.caption)
                                    } else {
                                        Text("Open the chart to load the full signal comparison.")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }

                        InsightsCameraCheckCard(
                            summary: latestCameraCheck,
                            isLoading: latestCameraCheckLoading,
                            errorText: latestCameraCheckError,
                            onOpenQuickCheck: onOpenQuickCheck
                        )
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Health & Symptoms")
            .navigationBarTitleDisplayMode(.inline)
            .task {
                ensureComparisonLoad()
            }
        }
    }

    private struct InsightsHazardsView: View {
        let payload: HazardsBriefResponse?
        let isLoading: Bool
        let error: String?

        private var items: [HazardItem] {
            payload?.items ?? []
        }

        private func severityTint(_ value: String?) -> Color {
            let token = (value ?? "").lowercased()
            if token.contains("red") { return GaugePalette.high }
            if token.contains("orange") { return GaugePalette.elevated }
            if token.contains("yellow") { return GaugePalette.mild }
            return GaugePalette.low
        }

        var body: some View {
            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        HazardsBriefCard(payload: payload, isLoading: isLoading, error: error)

                        if items.isEmpty, !isLoading {
                            LocalConditionsSurfaceCard(title: "Hazard Feed", icon: "globe.americas.fill") {
                                Text("No active hazard items are available right now.")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        } else if !items.isEmpty {
                            LocalConditionsSurfaceCard(title: "Latest Items", icon: "list.bullet.rectangle") {
                                VStack(spacing: 10) {
                                    ForEach(Array(items.prefix(12).enumerated()), id: \.offset) { _, item in
                                        VStack(alignment: .leading, spacing: 6) {
                                            HStack(spacing: 10) {
                                                Text(item.title ?? item.kind ?? "Hazard")
                                                    .font(.subheadline.weight(.semibold))
                                                Spacer()
                                                LocalConditionsValueChip(
                                                    label: "Severity",
                                                    value: item.severity?.capitalized ?? "Info",
                                                    tint: severityTint(item.severity)
                                                )
                                            }
                                            Text([item.location, item.source, item.startedAt].compactMap { $0 }.joined(separator: " • "))
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                    }
                                }
                            }
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Hazards")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private struct DashboardToolsSectionView: View {
        @ObservedObject var state: AppState
        let seriesForCharts: SpaceSeries
        let symptomHighlights: [SymptomHighlight]
        @Binding var showTrends: Bool
        let hazardsBrief: HazardsBriefResponse?
        let hazardsLoading: Bool
        let hazardsError: String?
        @Binding var showHazards: Bool
        let quakeLatest: QuakeDaily?
        let quakeEvents: [QuakeEvent]
        let quakeError: String?
        @Binding var showQuakes: Bool
        let auroraPowerValue: Double?
        let auroraWingKp: Double?
        let auroraProbabilityText: String?
        @Binding var showAuroraForecast: Bool
        let magnetosphere: MagnetosphereData?
        let magnetosphereLoading: Bool
        let magnetosphereError: String?
        @Binding var showMagnetosphereDetail: Bool
        @Binding var localHealthZip: String
        let localHealth: LocalCheckResponse?
        let localHealthLoading: Bool
        let localHealthError: String?
        let onRefreshLocalHealth: () -> Void
        @Binding var profileUseGPS: Bool
        @Binding var profileLocalInsightsEnabled: Bool
        let profileLocationMessage: String?
        let profileLocationSaving: Bool
        let onSaveProfileLocation: () -> Void
        let tagCatalog: [TagCatalogItem]
        @Binding var selectedTagKeys: Set<String>
        let tagSaveMessage: String?
        let tagsSaving: Bool
        let onSaveTags: () -> Void
        @Binding var showTools: Bool
        @Binding var showConnections: Bool
        @Binding var showActions: Bool
        @Binding var showBle: Bool
        @Binding var showPolar: Bool
        let onFetchVisuals: () -> Void
        @Binding var showMagnetosphere: Bool

        private enum SensitivitySection: String {
            case environmental = "Sensitivities"
            case health = "Health Context"
        }

        private func sectionForTag(_ item: TagCatalogItem) -> SensitivitySection {
            let key = canonicalProfileTagKey(item.tagKey)
            if healthContextTagKeys.contains(key) {
                return .health
            }
            let section = (item.section ?? "").lowercased()
            if section.contains("health") || section.contains("context") {
                return .health
            }
            return .environmental
        }

        private func tags(in section: SensitivitySection) -> [TagCatalogItem] {
            tagCatalog
                .filter { sectionForTag($0) == section }
                .sorted { (lhs, rhs) in
                    (lhs.label ?? lhs.tagKey).localizedCaseInsensitiveCompare(rhs.label ?? rhs.tagKey) == .orderedAscending
                }
        }

        private func toggleBinding(for key: String) -> Binding<Bool> {
            let canonicalKey = canonicalProfileTagKey(key)
            return Binding(
                get: { selectedTagKeys.contains(canonicalKey) },
                set: { isOn in
                    if isOn { selectedTagKeys.insert(canonicalKey) } else { selectedTagKeys.remove(canonicalKey) }
                }
            )
        }

        @ViewBuilder
        private func tagToggle(_ item: TagCatalogItem) -> some View {
            let key = canonicalProfileTagKey(item.tagKey)
            Toggle(isOn: toggleBinding(for: key)) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.label ?? key)
                    if let desc = item.description, !desc.isEmpty {
                        Text(desc).font(.caption2).foregroundColor(.secondary)
                    }
                }
            }
        }

        var body: some View {
            VStack(spacing: 16) {
                LocalHealthCard(
                    zip: $localHealthZip,
                    snapshot: localHealth,
                    isLoading: localHealthLoading,
                    error: localHealthError,
                    onRefresh: onRefreshLocalHealth
                )
                .padding(.horizontal)

                GroupBox {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Enable local insights")
                            .font(.subheadline)
                        TextField("ZIP code", text: $localHealthZip)
                            .textFieldStyle(.roundedBorder)
                            .keyboardType(.numberPad)
                        Toggle("Use GPS (optional)", isOn: $profileUseGPS)
                        Toggle("Enable local insights", isOn: $profileLocalInsightsEnabled)
                        Button(action: onSaveProfileLocation) {
                            HStack {
                                if profileLocationSaving {
                                    ProgressView().scaleEffect(0.8)
                                }
                                Text(profileLocationSaving ? "Saving..." : "Save Location")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(profileLocationSaving)
                        if let msg = profileLocationMessage {
                            Text(msg)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                } label: {
                    Label("Location Settings", systemImage: "location.fill")
                }
                .padding(.horizontal)

                GroupBox {
                    VStack(alignment: .leading, spacing: 10) {
                        if tagCatalog.isEmpty {
                            Text("No personalization tags available yet.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            let environmentalTags = tags(in: .environmental)
                            if !environmentalTags.isEmpty {
                                Text(SensitivitySection.environmental.rawValue)
                                    .font(.subheadline.weight(.semibold))
                                ForEach(environmentalTags) { item in
                                    tagToggle(item)
                                }
                            }

                            let healthTags = tags(in: .health)
                            if !healthTags.isEmpty {
                                Divider()
                                Text(SensitivitySection.health.rawValue + " (Optional)")
                                    .font(.subheadline.weight(.semibold))
                                ForEach(healthTags) { item in
                                    tagToggle(item)
                                }
                                Text("Self-reported health context only. Not for diagnosis.")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                        Button(action: onSaveTags) {
                            HStack {
                                if tagsSaving {
                                    ProgressView().scaleEffect(0.8)
                                }
                                Text(tagsSaving ? "Saving..." : "Save Personalization")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(tagsSaving)
                        if let msg = tagSaveMessage {
                            Text(msg)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                } label: {
                    Label("Personalization", systemImage: "slider.horizontal.3")
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showTrends) {
                    SpaceChartsCard(series: seriesForCharts, highlights: symptomHighlights)
                        .padding(.top, 6)
                } label: {
                    HStack {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                        Text("Weekly Trends (Kp, Bz, f0, HR)")
                        Spacer()
                    }
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showHazards) {
                    HazardsBriefCard(payload: hazardsBrief, isLoading: hazardsLoading, error: hazardsError)
                        .padding(.top, 6)
                } label: {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                        Text("Global Hazards Brief")
                        Spacer()
                    }
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showQuakes) {
                    EarthquakesSummaryCard(
                        latest: quakeLatest,
                        events: quakeEvents,
                        error: quakeError
                    )
                    .padding(.top, 6)
                } label: {
                    HStack {
                        Image(systemName: "waveform.path")
                        Text("Earthquakes")
                        Spacer()
                    }
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showAuroraForecast) {
                    AuroraThumbsSectionView(
                        auroraPowerValue: auroraPowerValue,
                        auroraWingKp: auroraWingKp,
                        auroraProbabilityText: auroraProbabilityText
                    )
                    .padding(.top, 6)
                } label: {
                    HStack {
                        Image(systemName: "sparkles")
                        Text("Aurora Forecast")
                        Spacer()
                    }
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showMagnetosphere) {
                    MagnetosphereCard(
                        data: magnetosphere,
                        isLoading: magnetosphereLoading,
                        error: magnetosphereError,
                        onOpenDetail: { showMagnetosphereDetail = true }
                    )
                    .padding(.top, 6)
                    .sheet(isPresented: $showMagnetosphereDetail) {
                        MagnetosphereDetailView(data: magnetosphere)
                    }
                } label: {
                    HStack {
                        Image(systemName: "shield.fill")
                        Text("Magnetosphere")
                        Spacer()
                    }
                }
                .padding(.horizontal)

                DisclosureGroup(isExpanded: $showTools) {
                    VStack(spacing: 12) {
                        ConnectionSettingsSection(state: state, isExpanded: $showConnections)
                        NavigationLink(destination: SubscribeView()) {
                            Label("Subscribe", systemImage: "creditcard")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
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
                NavigationLink(destination: SubscribeView()) {
                    Label("Subscribe", systemImage: "creditcard")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
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
                    dashboardFeaturesView(features ?? lastKnownFeatures)

                    if showDebug {
                        let debugFeaturesState = self.featureFetchState
                        DebugPanel(state: state, expandLog: $expandLog, featuresState: debugFeaturesState)

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
                    }

                    Spacer(minLength: 10)
                }
                .padding(.bottom, 12)
            }
            .transaction { $0.disablesAnimations = true }
            .overlay(alignment: .top) {
                if let toast = symptomToast {
                    SymptomToastView(
                        toast: toast,
                        onAction: {
                            guard let prefill = toast.prefill else { return }
                            symptomToast = nil
                            symptomSheetPrefill = prefill
                            showSymptomSheet = true
                        }
                    )
                    .padding(.top, 12)
                    .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .task {
                guard !didRunInitialTasks else { return }
                didRunInitialTasks = true
                await state.updateBackendDBFlag()
                let api = state.apiWithAuth()
                async let a: Void = fetchDashboardPayload(force: true)
                async let b: Void = fetchProfileSettings()
                async let e: Void = fetchLatestCameraCheck()
                _ = await (a, b, e)
                async let c: Void = state.flushQueuedSymptoms(api: api)
                async let d: Void = refreshSymptomPresets(api: api)
                _ = await (c, d)
            }
            .refreshable {
                await state.updateBackendDBFlag()
                let api = state.apiWithAuth()
                async let a: Void = fetchDashboardPayload(force: true)
                async let b: Void = fetchProfileSettings()
                async let e: Void = fetchLatestCameraCheck()
                _ = await (a, b, e)
                async let c: Void = state.flushQueuedSymptoms(api: api)
                async let d: Void = refreshSymptomPresets(api: api)
                _ = await (c, d)
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
                if userOutlook == nil, let cached = decodeUserOutlook(from: userOutlookCacheJSON) {
                    userOutlook = cached
                    lastKnownUserOutlook = cached
                    appLog("[UI] preloaded user outlook from persisted snapshot")
                }
                if dashboardPayload == nil, let cached = decodeDashboardPayload(from: dashboardPayloadCacheJSON) {
                    dashboardPayload = cached
                    if let g = cached.gauges {
                        lastNonNilDashboardGauges = g
                    }
                    dashboardLastUpdatedText = "cached"
                    appLog("[UI] preloaded dashboard payload from persisted snapshot")
                }
                if !didLocationOnboarding {
                    showLocationOnboarding = true
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
            .onChange(of: userOutlookCacheJSON, initial: false) { oldValue, newValue in
                guard newValue != oldValue, !newValue.isEmpty, let decoded = decodeUserOutlook(from: newValue) else { return }
                lastKnownUserOutlook = decoded
                if userOutlook == nil {
                    userOutlook = decoded
                    appLog("[UI] user outlook updated from cache change")
                }
            }
            .onChange(of: dashboardPayloadCacheJSON, initial: false) { oldValue, newValue in
                guard newValue != oldValue, !newValue.isEmpty, let decoded = decodeDashboardPayload(from: newValue) else { return }
                if let g = decoded.gauges {
                    lastNonNilDashboardGauges = g
                }
                if dashboardPayload == nil {
                    dashboardPayload = decoded
                    dashboardLastUpdatedText = "cached"
                    appLog("[UI] dashboard payload updated from cache change")
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
            .onChange(of: showHazards, initial: false) { _, newValue in
                guard newValue, !hazardsLoading else { return }
                if hazardsBrief == nil || hazardsBrief?.ok != true {
                    Task { await fetchHazardsBrief() }
                }
            }
            .onChange(of: showQuakes, initial: false) { _, newValue in
                guard newValue, !quakeLoading else { return }
                if quakeEvents.isEmpty {
                    Task { await fetchQuakes() }
                }
            }
            .onChange(of: showMagnetosphere, initial: false) { _, newValue in
                guard newValue, !magnetosphereLoading else { return }
                if magnetosphere == nil {
                    Task { await fetchMagnetosphere() }
                }
            }
            .onChange(of: showMissionInsightsSheet, initial: false) { _, newValue in
                guard newValue else { return }
                Task {
                    await fetchInsightsHubData()
                }
            }
            .onChange(of: showMissionSettingsSheet, initial: false) { _, newValue in
                guard newValue else { return }
                Task {
                    await refreshPushState()
                    await fetchProfileSettings(includeNotifications: true)
                    await fetchLocalHealth()
                }
            }
            .onChange(of: showLocalConditionsSheet, initial: false) { _, newValue in
                guard newValue else { return }
                Task {
                    await fetchLocalHealth()
                    await fetchDashboardPayload()
                }
            }
            .onChange(of: showCameraHealthCheckSheet, initial: false) { _, newValue in
                if !newValue {
                    Task { await fetchLatestCameraCheck() }
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
            .onReceive(NotificationCenter.default.publisher(for: .gaiaPushTokenDidChange).receive(on: RunLoop.main)) { _ in
                Task {
                    await applyStoredPushState()
                    let prefs = await MainActor.run { notificationPreferences }
                    _ = await PushNotificationService.syncTokenRegistration(preferences: prefs)
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .gaiaPushAuthorizationDidChange).receive(on: RunLoop.main)) { _ in
                Task {
                    await applyStoredPushState()
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .gaiaPushDeepLinkReceived).receive(on: RunLoop.main)) { note in
                guard let userInfo = note.userInfo, let route = GaiaPushRoute(userInfo: userInfo) else { return }
                handleIncomingPushRoute(route)
            }
            .task {
                await refreshPushState()
                if let pendingRoute = PushNotificationService.consumePendingRoute() {
                    handleIncomingPushRoute(pendingRoute)
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
        .sheet(isPresented: $showMissionInsightsSheet) {
            let baseFeatures = features ?? lastKnownFeatures
            let selected: (FeaturesToday, Bool)? = baseFeatures.map { selectDisplayFeatures(for: $0) }
            let current = selected?.0
            let usingYesterdayFallback = selected?.1 ?? false
            let updatedText = current?.updatedAt.flatMap { formatUpdated($0) }
            let seriesDetail = series ?? lastKnownSeries
            let resolvedOutlook = spaceOutlook ?? lastKnownSpaceOutlook
            let resolvedUserOutlook = userOutlook ?? lastKnownUserOutlook
            let symptomPoints = symptomSparkPoints()
            let symptomSummary = topSymptomSummary()
            let symptomHighlightList = symptomHighlights()

            NavigationStack {
                InsightsHubView(
                    current: current,
                    outlook: resolvedOutlook,
                    userOutlook: resolvedUserOutlook,
                    updatedText: updatedText,
                    usingYesterdayFallback: usingYesterdayFallback,
                    localHealthZip: localHealthZip,
                    localHealth: localHealth,
                    localHealthLoading: localHealthLoading,
                    localHealthError: localHealthError,
                    userOutlookLoading: userOutlookLoading,
                    userOutlookError: userOutlookError,
                    useGPS: profileUseGPS,
                    localInsightsEnabled: profileLocalInsightsEnabled,
                    dashboardDrivers: dashboardPayload?.drivers ?? [],
                    magnetosphere: magnetosphere,
                    magnetosphereLoading: magnetosphereLoading,
                    magnetosphereError: magnetosphereError,
                    symptomsTodayCount: symptomsToday.count,
                    queuedSymptomsCount: state.symptomQueueCount,
                    topSymptomSummary: symptomSummary,
                    latestCameraCheck: latestCameraCheck,
                    latestCameraCheckLoading: latestCameraCheckLoading,
                    latestCameraCheckError: latestCameraCheckError,
                    quakeLatest: quakeLatest,
                    quakeEvents: quakeEvents,
                    quakeLoading: quakeLoading,
                    quakeError: quakeError,
                    hazardsBrief: hazardsBrief,
                    hazardsLoading: hazardsLoading,
                    hazardsError: hazardsError,
                    onRefresh: { await fetchInsightsHubData() }
                )
                .navigationDestination(for: InsightsRoute.self) { route in
                    switch route {
                    case .yourOutlook:
                        YourOutlookView(
                            payload: resolvedUserOutlook,
                            isLoading: userOutlookLoading,
                            error: userOutlookError,
                            onRefresh: { Task { await fetchUserOutlook() } }
                        )
                        .task {
                            if userOutlook == nil && !userOutlookLoading {
                                await fetchUserOutlook()
                            }
                        }
                    case .spaceWeather:
                        InsightsSpaceWeatherView(
                            current: current,
                            updatedText: updatedText,
                            usingYesterdayFallback: usingYesterdayFallback,
                            forecast: forecast,
                            outlook: resolvedOutlook,
                            series: seriesDetail
                        )
                        .task {
                            if series == nil {
                                await fetchSpaceSeries(days: 30)
                            }
                        }
                    case .localConditions:
                        LocalConditionsView(
                            zip: localHealthZip,
                            snapshot: localHealth,
                            drivers: dashboardPayload?.drivers ?? [],
                            isLoading: localHealthLoading,
                            error: localHealthError,
                            useGPS: profileUseGPS,
                            onRefresh: { Task { await fetchLocalHealth() } }
                        )
                        .task {
                            if localHealth == nil && !localHealthLoading {
                                await fetchLocalHealth()
                            }
                            if dashboardPayload == nil {
                                await fetchDashboardPayload()
                            }
                        }
                    case .yourPatterns:
                        YourPatternsView()
                    case .magnetosphere:
                        InsightsMagnetosphereView(
                            data: magnetosphere,
                            isLoading: magnetosphereLoading,
                            error: magnetosphereError
                        )
                        .task {
                            if magnetosphere == nil && !magnetosphereLoading {
                                await fetchMagnetosphere()
                            }
                        }
                    case .schumann:
                        SchumannDashboardView(state: state)
                    case .healthSymptoms:
                        InsightsHealthSymptomsView(
                            current: current,
                            todayString: chicagoTodayString(),
                            updatedText: updatedText,
                            bannerText: featuresCachedBannerText,
                            usingYesterdayFallback: usingYesterdayFallback,
                            todayCount: symptomsToday.count,
                            queuedCount: state.symptomQueueCount,
                            sparklinePoints: symptomPoints,
                            topSummary: symptomSummary,
                            diagnostics: symptomDiagnostics,
                            series: seriesDetail,
                            highlights: symptomHighlightList,
                            latestCameraCheck: latestCameraCheck,
                            latestCameraCheckLoading: latestCameraCheckLoading,
                            latestCameraCheckError: latestCameraCheckError,
                            showSymptomSheet: $showSymptomSheet,
                            onOpenQuickCheck: { showCameraHealthCheckSheet = true },
                            onLoadComparison: { await fetchSpaceSeries(days: 30) }
                        )
                        .task {
                            if symptomDaily.isEmpty && symptomsToday.isEmpty {
                                await fetchSymptoms(api: state.apiWithAuth())
                            }
                        }
                    case .earthquakes:
                        EarthquakesDetailView(
                            latest: quakeLatest,
                            events: quakeEvents,
                            error: quakeError
                        )
                        .task {
                            if quakeLatest == nil && quakeEvents.isEmpty && !quakeLoading {
                                await fetchQuakes()
                            }
                        }
                    case .hazards:
                        InsightsHazardsView(
                            payload: hazardsBrief,
                            isLoading: hazardsLoading,
                            error: hazardsError
                        )
                        .task {
                            if hazardsBrief == nil && !hazardsLoading {
                                await fetchHazardsBrief()
                            }
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showMissionSettingsSheet) {
            let sectionForTag: (TagCatalogItem) -> Bool = { item in
                let canonicalKey = canonicalProfileTagKey(item.tagKey)
                if healthContextTagKeys.contains(canonicalKey) {
                    return true
                }
                let section = (item.section ?? "").lowercased()
                return section.contains("health") || section.contains("context")
            }
            let environmentalTags = tagCatalog.filter { !sectionForTag($0) }.sorted {
                ($0.label ?? $0.tagKey).localizedCaseInsensitiveCompare($1.label ?? $1.tagKey) == .orderedAscending
            }
            let healthTags = tagCatalog.filter(sectionForTag).sorted {
                ($0.label ?? $0.tagKey).localizedCaseInsensitiveCompare($1.label ?? $1.tagKey) == .orderedAscending
            }
            NavigationStack {
                ScrollView {
                    VStack(spacing: 16) {
                        LocalConditionsSummaryCard(
                            zip: $localHealthZip,
                            snapshot: localHealth,
                            isLoading: localHealthLoading,
                            error: localHealthError,
                            useGPS: profileUseGPS,
                            localInsightsEnabled: profileLocalInsightsEnabled
                        ) {
                            LocalConditionsView(
                                zip: localHealthZip,
                                snapshot: localHealth,
                                drivers: dashboardPayload?.drivers ?? [],
                                isLoading: localHealthLoading,
                                error: localHealthError,
                                useGPS: profileUseGPS,
                                onRefresh: { Task { await fetchLocalHealth() } }
                            )
                        }
                        .padding(.horizontal)

                        GroupBox {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("Enable local insights")
                                    .font(.subheadline)
                                TextField("ZIP code", text: $localHealthZip)
                                    .textFieldStyle(.roundedBorder)
                                    .keyboardType(.numberPad)
                                Toggle("Use GPS (optional)", isOn: $profileUseGPS)
                                Toggle("Enable local insights", isOn: $profileLocalInsightsEnabled)
                                Button(action: { Task { await saveProfileLocation() } }) {
                                    HStack {
                                        if profileLocationSaving {
                                            ProgressView().scaleEffect(0.8)
                                        }
                                        Text(profileLocationSaving ? "Saving..." : "Save Location")
                                    }
                                    .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(profileLocationSaving)
                                if let msg = profileLocationMessage {
                                    Text(msg)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        } label: {
                            Label("Location Settings", systemImage: "location.fill")
                        }
                        .padding(.horizontal)

                        GroupBox {
                            VStack(alignment: .leading, spacing: 10) {
                                if environmentalTags.isEmpty && healthTags.isEmpty {
                                    Text("Catalog not loaded.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Button("Refresh catalog") {
                                        Task {
                                            await fetchTagCatalog()
                                            await fetchSelectedTags()
                                        }
                                    }
                                    .buttonStyle(.bordered)
                                } else {
                                    if !environmentalTags.isEmpty {
                                        Text("Sensitivities")
                                            .font(.subheadline.weight(.semibold))
                                        ForEach(environmentalTags) { item in
                                            let canonicalKey = canonicalProfileTagKey(item.tagKey)
                                            Toggle(isOn: Binding(
                                                get: { selectedTagKeys.contains(canonicalKey) },
                                                set: { isOn in
                                                    if isOn {
                                                        selectedTagKeys.insert(canonicalKey)
                                                    } else {
                                                        selectedTagKeys.remove(canonicalKey)
                                                    }
                                                }
                                            )) {
                                                VStack(alignment: .leading, spacing: 2) {
                                                    Text(item.label ?? canonicalKey)
                                                    if let desc = item.description, !desc.isEmpty {
                                                        Text(desc)
                                                            .font(.caption2)
                                                            .foregroundColor(.secondary)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    if !healthTags.isEmpty {
                                        Divider()
                                        Text("Health Context (Optional)")
                                            .font(.subheadline.weight(.semibold))
                                        ForEach(healthTags) { item in
                                            let canonicalKey = canonicalProfileTagKey(item.tagKey)
                                            Toggle(isOn: Binding(
                                                get: { selectedTagKeys.contains(canonicalKey) },
                                                set: { isOn in
                                                    if isOn {
                                                        selectedTagKeys.insert(canonicalKey)
                                                    } else {
                                                        selectedTagKeys.remove(canonicalKey)
                                                    }
                                                }
                                            )) {
                                                VStack(alignment: .leading, spacing: 2) {
                                                    Text(item.label ?? canonicalKey)
                                                    if let desc = item.description, !desc.isEmpty {
                                                        Text(desc)
                                                            .font(.caption2)
                                                            .foregroundColor(.secondary)
                                                    }
                                                }
                                            }
                                        }
                                        Text("Self-reported health context only. Not for diagnosis.")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Button(action: { Task { await saveSelectedTags() } }) {
                                    HStack {
                                        if tagsSaving {
                                            ProgressView().scaleEffect(0.8)
                                        }
                                        Text(tagsSaving ? "Saving..." : "Save Personalization")
                                    }
                                    .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(tagsSaving)
                                if let msg = tagSaveMessage {
                                    Text(msg)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        } label: {
                            Label("Personalization", systemImage: "slider.horizontal.3")
                        }
                        .padding(.horizontal)

                        GroupBox {
                            VStack(alignment: .leading, spacing: 12) {
                                Toggle("Enable push notifications", isOn: $notificationPreferences.enabled)

                                HStack(alignment: .center, spacing: 8) {
                                    Text(pushPermissionGranted ? "iOS permission granted" : "iOS permission not granted yet")
                                        .font(.caption)
                                        .foregroundColor(pushPermissionGranted ? .secondary : .orange)
                                    Spacer()
                                    Text(pushDeviceToken == nil ? "APNs pending" : "APNs ready")
                                        .font(.caption.weight(.semibold))
                                        .foregroundColor(pushDeviceToken == nil ? .secondary : .green)
                                }

                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Signal alerts")
                                        .font(.subheadline.weight(.semibold))
                                    Toggle("Signal alerts", isOn: $notificationPreferences.signalAlertsEnabled)
                                    if notificationPreferences.signalAlertsEnabled {
                                        Toggle("Geomagnetic / Kp", isOn: $notificationPreferences.families.geomagnetic)
                                        Toggle("Solar wind / Bz coupling", isOn: $notificationPreferences.families.solarWind)
                                        Toggle("Flares / CME / SEP / DRAP", isOn: $notificationPreferences.families.flareCmeSep)
                                        Toggle("Schumann spike / elevated", isOn: $notificationPreferences.families.schumann)
                                    }
                                }
                                .disabled(!notificationPreferences.enabled)

                                Divider()

                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Local condition alerts")
                                        .font(.subheadline.weight(.semibold))
                                    Toggle("Local condition alerts", isOn: $notificationPreferences.localConditionAlertsEnabled)
                                    if notificationPreferences.localConditionAlertsEnabled {
                                        Toggle("Pressure swing", isOn: $notificationPreferences.families.pressure)
                                        Toggle("AQI", isOn: $notificationPreferences.families.aqi)
                                        Toggle("Temperature swing", isOn: $notificationPreferences.families.temp)
                                    }
                                }
                                .disabled(!notificationPreferences.enabled)

                                Divider()

                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Personalized gauge alerts")
                                        .font(.subheadline.weight(.semibold))
                                    Toggle("Personalized gauge alerts", isOn: $notificationPreferences.personalizedGaugeAlertsEnabled)
                                    if notificationPreferences.personalizedGaugeAlertsEnabled {
                                        Toggle("Gauge spikes (Pain / Energy / Sleep / Heart / Health Status)", isOn: $notificationPreferences.families.gaugeSpikes)
                                    }
                                }
                                .disabled(!notificationPreferences.enabled)

                                Divider()

                                VStack(alignment: .leading, spacing: 8) {
                                    Toggle("Enable quiet hours", isOn: $notificationPreferences.quietHoursEnabled)
                                    if notificationPreferences.quietHoursEnabled {
                                        HStack(spacing: 10) {
                                            TextField("Start (22:00)", text: $notificationPreferences.quietStart)
                                                .textFieldStyle(.roundedBorder)
                                                .textInputAutocapitalization(.never)
                                                .autocorrectionDisabled()
                                            TextField("End (08:00)", text: $notificationPreferences.quietEnd)
                                                .textFieldStyle(.roundedBorder)
                                                .textInputAutocapitalization(.never)
                                                .autocorrectionDisabled()
                                        }
                                        Text("Quiet hours use your current time zone: \(TimeZone.current.identifier)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .disabled(!notificationPreferences.enabled)

                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Alert sensitivity")
                                        .font(.subheadline.weight(.semibold))
                                    Picker("Alert sensitivity", selection: $notificationPreferences.sensitivity) {
                                        Text("Minimal").tag("minimal")
                                        Text("Normal").tag("normal")
                                        Text("Detailed").tag("detailed")
                                    }
                                    .pickerStyle(.segmented)
                                    .disabled(!notificationPreferences.enabled)
                                }

                                Button(action: {
                                    Task {
                                        await saveNotificationPreferences(requestAuthorizationIfNeeded: notificationPreferences.enabled)
                                    }
                                }) {
                                    HStack {
                                        if notificationSettingsSaving {
                                            ProgressView().scaleEffect(0.8)
                                        }
                                        Text(notificationSettingsSaving ? "Saving..." : "Save Notifications")
                                    }
                                    .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(notificationSettingsSaving)

                                if let msg = notificationSettingsMessage {
                                    Text(msg)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        } label: {
                            Label("Notifications", systemImage: "bell.badge.fill")
                        }
                        .padding(.horizontal)

                        ConnectionSettingsSection(state: state, isExpanded: $showConnections)

                        NavigationLink(destination: SubscribeView()) {
                            Label("Subscribe", systemImage: "creditcard")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .padding(.horizontal)

                        DisclosureGroup(isExpanded: $showActions) {
                            ActionsSection(state: state, onFetchVisuals: { Task { await fetchSpaceVisuals() } })
                                .padding(.top, 6)
                        } label: {
                            HStack {
                                Image(systemName: "arrow.triangle.2.circlepath")
                                Text("HealthKit Sync & Actions")
                                Spacer()
                            }
                        }
                        .padding(.horizontal)

                        DisclosureGroup(isExpanded: $showBle) {
                            BleStatusSection(state: state)
                                .padding(.top, 6)
                        } label: {
                            HStack {
                                Image(systemName: "antenna.radiowaves.left.and.right")
                                Text("Bluetooth / BLE")
                                Spacer()
                            }
                        }
                        .padding(.horizontal)

                        DisclosureGroup(isExpanded: $showPolar) {
                            PolarStatusSection(state: state)
                                .padding(.top, 6)
                        } label: {
                            HStack {
                                Image(systemName: "waveform.path.ecg")
                                Text("Polar ECG")
                                Spacer()
                            }
                        }
                        .padding(.horizontal)

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

                        GroupBox {
                            Toggle("Enable camera check JSON export", isOn: $cameraHealthDebugExportEnabled)
                                .font(.subheadline)
                            Text("Developer-only: adds a Copy Debug JSON button after Quick Check.")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        } label: {
                            Label("Camera Check", systemImage: "ladybug")
                        }
                        .padding(.horizontal)
                    }
                    .padding(.vertical, 16)
                }
                .navigationTitle("Settings")
                .navigationBarTitleDisplayMode(.inline)
            }
        }
        .sheet(isPresented: $showLocalConditionsSheet) {
            NavigationStack {
                LocalConditionsView(
                    zip: localHealthZip,
                    snapshot: localHealth,
                    drivers: dashboardPayload?.drivers ?? [],
                    isLoading: localHealthLoading,
                    error: localHealthError,
                    useGPS: profileUseGPS,
                    onRefresh: { Task { await fetchLocalHealth() } }
                )
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { showLocalConditionsSheet = false }
                    }
                }
            }
        }
        .sheet(isPresented: $showSchumannDashboardSheet) {
            NavigationStack {
                SchumannDashboardView(state: state)
            }
        }
        .sheet(isPresented: $showCameraHealthCheckSheet) {
            CameraHealthCheckView(onSaved: {
                Task { await fetchLatestCameraCheck() }
            })
        }
        .sheet(isPresented: $showSymptomSheet, onDismiss: {
            symptomSheetPrefill = nil
        }) {
            NavigationStack {
                SymptomsLogPage(
                    presets: symptomPresets,
                    queuedCount: state.symptomQueueCount,
                    isOffline: isSymptomServiceOffline,
                    isSubmitting: $isSubmittingSymptom,
                    prefill: symptomSheetPrefill,
                    showsCloseButton: true,
                    onSubmit: { event in
                        isSubmittingSymptom = true
                        Task {
                            let shouldDismiss = await logSymptomEvent(event)
                            await MainActor.run {
                                isSubmittingSymptom = false
                                if shouldDismiss {
                                    showSymptomSheet = false
                                    symptomSheetPrefill = nil
                                }
                            }
                        }
                    }
                )
            }
        }
        .sheet(isPresented: $showLocationOnboarding) {
            LocationOnboardingSheet(
                zip: $localHealthZip,
                useGPS: $profileUseGPS,
                localInsightsEnabled: $profileLocalInsightsEnabled,
                isSaving: profileLocationSaving,
                message: profileLocationMessage,
                onSave: {
                    Task { await saveProfileLocation(markOnboardingComplete: true) }
                },
                onSkip: {
                    didLocationOnboarding = true
                    showLocationOnboarding = false
                }
            )
        }
        .sheet(isPresented: $showMagnetosphereDetail) {
            MagnetosphereDetailView(data: magnetosphere)
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
        let toast: SymptomToastState
        let onAction: () -> Void
        
        var body: some View {
            HStack(spacing: 10) {
                Text(toast.message)
                    .font(.footnote)
                if let actionTitle = toast.actionTitle, !actionTitle.isEmpty {
                    Button(actionTitle, action: onAction)
                        .font(.footnote.weight(.semibold))
                }
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 18)
            .background(.ultraThinMaterial, in: Capsule())
            .shadow(radius: 3)
        }
    }

    private struct LocationOnboardingSheet: View {
        @Binding var zip: String
        @Binding var useGPS: Bool
        @Binding var localInsightsEnabled: Bool
        let isSaving: Bool
        let message: String?
        let onSave: () -> Void
        let onSkip: () -> Void

        var body: some View {
            NavigationStack {
                Form {
                    Section("Enable local insights") {
                        TextField("ZIP code", text: $zip)
                            .keyboardType(.numberPad)
                        Toggle("Use GPS (optional)", isOn: $useGPS)
                        Toggle("Enable local insights", isOn: $localInsightsEnabled)
                    }
                    Section {
                        if let message {
                            Text(message)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .navigationTitle("Local Insights")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Skip") { onSkip() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(action: onSave) {
                            if isSaving {
                                ProgressView()
                            } else {
                                Text("Continue")
                            }
                        }
                        .disabled(isSaving)
                    }
                }
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

        private func typeCounts(_ items: [HazardItem]) -> (quakes: Int, cyclones: Int, volcano: Int, fire: Int, flood: Int, other: Int) {
            var counts = (quakes: 0, cyclones: 0, volcano: 0, fire: 0, flood: 0, other: 0)
            for item in items {
                let kind = item.kind?.lowercased() ?? ""
                let title = item.title?.lowercased() ?? ""
                let haystack = "\(kind) \(title)"
                if haystack.contains("quake") || haystack.contains("earth") {
                    counts.quakes += 1
                } else if haystack.contains("cyclone") || haystack.contains("storm") || haystack.contains("severe") {
                    counts.cyclones += 1
                } else if haystack.contains("volcano") || haystack.contains("ash") {
                    counts.volcano += 1
                } else if haystack.contains("wildfire") || haystack.contains("forest fire") || haystack.contains("fire") {
                    counts.fire += 1
                } else if haystack.contains("flash flood") || haystack.contains("flood") {
                    counts.flood += 1
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
                                    GridRow { Text("Fire"); Text("\(types.fire)") }
                                    GridRow { Text("Flood"); Text("\(types.flood)") }
                                    GridRow { Text("Other"); Text("\(types.other)") }
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary)
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

        private let fullDetailsURL = URL(string: "https://gaiaeyes.com/earthquakes/")

        private func summaryText() -> String {
            let count = latest?.m5p ?? events.count
            let maxEvent = events.max { ($0.mag ?? 0) < ($1.mag ?? 0) }
            let mag = maxEvent?.mag
            let region = maxEvent?.place
            var parts: [String] = []
            parts.append(count == 1 ? "1 M5+ quake" : "\(count) M5+ quakes")
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
                    Text("This page focuses on M5+ earthquakes from the last 24 hours. For full details and more charts, visit the website.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    if let fullDetailsURL {
                        Link("Open the full earthquakes page", destination: fullDetailsURL)
                            .font(.caption.weight(.semibold))
                    }
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
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .navigationTitle("Earthquakes")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private enum LocalConditionsFormatting {
        static func formatNumber(_ value: Double?, decimals: Int = 1) -> String {
            guard let value else { return "—" }
            return String(format: "%.\(decimals)f", value)
        }

        static func formatTempMetric(_ celsius: Double?) -> String {
            guard let celsius else { return "—" }
            return "\(String(format: "%.1f", celsius)) °C"
        }

        static func formatTempImperial(_ celsius: Double?) -> String {
            guard let celsius else { return "—" }
            let fahrenheit = (celsius * 9.0 / 5.0) + 32.0
            return "\(String(format: "%.1f", fahrenheit)) °F"
        }

        static func formatTempDelta(_ celsius: Double?) -> String {
            guard let celsius else { return "—" }
            return "\(String(format: "%+.1f", celsius)) °C"
        }

        static func formatPressure(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            let inHg = hpa * 0.02953
            return "\(String(format: "%.1f", hpa)) hPa (\(String(format: "%.2f", inHg)) inHg)"
        }

        static func formatPressureShort(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            return "\(String(format: "%.1f", hpa)) hPa"
        }

        static func formatPressureImperial(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            return "\(String(format: "%.2f", hpa * 0.02953)) inHg"
        }

        static func formatPressureDelta(_ hpa: Double?) -> String {
            guard let hpa else { return "—" }
            return "\(String(format: "%+.1f", hpa)) hPa"
        }

        static func formatPercent(_ value: Double?) -> String {
            guard let value else { return "—" }
            return "\(String(format: "%.0f", value)) %"
        }

        static func normalizedTrend(_ raw: String?) -> String? {
            guard let raw, !raw.isEmpty else { return nil }
            switch raw.lowercased() {
            case "rising": return "rising"
            case "falling": return "falling"
            case "steady": return "steady"
            default: return raw.lowercased()
            }
        }

        static func derivedPressureTrend(raw: String?, deltaHpa: Double?) -> String? {
            let normalized = normalizedTrend(raw)
            guard let deltaHpa else { return normalized }
            if abs(deltaHpa) < 1 {
                return normalized ?? "steady"
            }
            if normalized == nil || normalized == "steady" {
                return deltaHpa > 0 ? "rising" : "falling"
            }
            if normalized == "rising", deltaHpa < 0 {
                return "falling"
            }
            if normalized == "falling", deltaHpa > 0 {
                return "rising"
            }
            return normalized
        }

        static func formatTrend(_ raw: String?) -> String {
            normalizedTrend(raw)?.capitalized ?? "—"
        }

        static func asofText(_ iso: String?) -> String? {
            guard let iso else { return nil }
            let formatter = ISO8601DateFormatter()
            if let date = formatter.date(from: iso) {
                return DateFormatter.localizedString(from: date, dateStyle: .medium, timeStyle: .short)
            }
            return nil
        }

        static func illuminationFraction(_ value: Double?) -> Double {
            guard let value else { return 0 }
            if value > 1 { return clamped(value / 100.0) }
            return clamped(value)
        }

        static func illuminationText(_ value: Double?) -> String {
            guard let value else { return "—" }
            let percent = value > 1 ? value : value * 100.0
            return "\(String(format: "%.0f", percent)) %"
        }

        static func clamped(_ value: Double) -> Double {
            min(max(value, 0), 1)
        }
    }

    private enum LocalConditionsStyle {
        static func severityKey(_ raw: String?) -> String {
            switch (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "high", "alert":
                return "high"
            case "watch", "elevated":
                return "elevated"
            case "mild", "moderate":
                return "mild"
            default:
                return "low"
            }
        }

        static func progress(_ raw: String?) -> Double {
            switch severityKey(raw) {
            case "high":
                return 0.95
            case "elevated":
                return 0.72
            case "mild":
                return 0.45
            default:
                return 0.20
            }
        }

        static func pillSeverity(_ raw: String?) -> StatusPill.Severity {
            switch severityKey(raw) {
            case "high":
                return .alert
            case "elevated", "mild":
                return .warn
            default:
                return .ok
            }
        }
    }

    private struct LocalConditionsDriverStatus {
        let label: String
        let state: String
        let severityKey: String
        let progress: Double
        let detail: String?
    }

    private struct LocalConditionsSurfaceCard<Content: View>: View {
        let title: String
        let icon: String
        let content: Content

        init(title: String, icon: String, @ViewBuilder content: () -> Content) {
            self.title = title
            self.icon = icon
            self.content = content()
        }

        var body: some View {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) {
                    Image(systemName: icon)
                        .font(.headline)
                        .foregroundColor(.white.opacity(0.88))
                    Text(title)
                        .font(.headline.weight(.semibold))
                    Spacer()
                }
                content
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
        }
    }

    private struct LocalConditionsBar: View {
        let progress: Double
        let tint: Color

        var body: some View {
            GeometryReader { geo in
                let safeProgress = LocalConditionsFormatting.clamped(progress)
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(tint.opacity(0.72))
                        .frame(width: max(12, geo.size.width * safeProgress))
                }
            }
            .frame(height: 9)
        }
    }

    private struct LocalConditionsMetricTile: View {
        let title: String
        let value: String
        let progress: Double
        let tint: Color

        var body: some View {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.secondary)
                Text(value)
                    .font(.title3.weight(.semibold))
                    .lineLimit(2)
                    .minimumScaleFactor(0.78)
                LocalConditionsBar(progress: progress, tint: tint)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color.black.opacity(0.20))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    private struct LocalConditionsValueChip: View {
        let label: String
        let value: String
        let tint: Color

        var body: some View {
            VStack(alignment: .leading, spacing: 2) {
                Text(label.uppercased())
                    .font(.caption2.weight(.semibold))
                    .foregroundColor(.secondary)
                Text(value)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(tint.opacity(0.14))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(tint.opacity(0.26), lineWidth: 1)
            )
        }
    }

    private struct LocalConditionsStatusStrip: View {
        let status: LocalConditionsDriverStatus

        var body: some View {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 10) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(status.label)
                            .font(.subheadline.weight(.semibold))
                        if let detail = status.detail, !detail.isEmpty, detail != "—" {
                            Text(detail)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    Spacer()
                    StatusPill(status.state, severity: LocalConditionsStyle.pillSeverity(status.severityKey))
                }
                LocalConditionsBar(
                    progress: status.progress,
                    tint: GaugePalette.zoneColor(status.severityKey)
                )
            }
            .padding(12)
            .background(Color.black.opacity(0.20))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(GaugePalette.zoneColor(status.severityKey).opacity(0.22), lineWidth: 1)
            )
        }
    }

    private struct LocalConditionsSummaryCard<Destination: View>: View {
        @Binding var zip: String
        let snapshot: LocalCheckResponse?
        let isLoading: Bool
        let error: String?
        let useGPS: Bool
        let localInsightsEnabled: Bool
        let destination: () -> Destination

        private var locationStatus: String {
            let resolvedZip = (snapshot?.whereInfo?.zip ?? zip).trimmingCharacters(in: .whitespacesAndNewlines)
            if useGPS {
                return resolvedZip.isEmpty ? "GPS preferred" : "GPS preferred • ZIP \(resolvedZip)"
            }
            return resolvedZip.isEmpty ? "ZIP not set" : "ZIP \(resolvedZip)"
        }

        private var lastUpdated: String {
            LocalConditionsFormatting.asofText(snapshot?.asof) ?? "—"
        }

        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        Text("Local Conditions")
                            .font(.headline)
                        Spacer()
                        if isLoading { ProgressView().scaleEffect(0.8) }
                    }
                    HStack(spacing: 8) {
                        StatusPill(localInsightsEnabled ? "Ready" : "Off", severity: localInsightsEnabled ? .ok : .warn)
                        Text(locationStatus)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Text("Last updated \(lastUpdated)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    if let error, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    NavigationLink {
                        destination()
                    } label: {
                        HStack {
                            Text("Open Local Conditions")
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Local Conditions", systemImage: "location.fill")
            }
        }
    }

    private struct LocalHealthCard: View {
        @Binding var zip: String
        let snapshot: LocalCheckResponse?
        let isLoading: Bool
        let error: String?
        let onRefresh: () -> Void

        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        Text("Local Conditions")
                            .font(.headline)
                        Spacer()
                        if isLoading { ProgressView().scaleEffect(0.8) }
                        Button("Refresh") { onRefresh() }
                            .font(.caption)
                    }
                    Text((snapshot?.whereInfo?.zip ?? zip).isEmpty ? "ZIP not set" : "ZIP \(snapshot?.whereInfo?.zip ?? zip)")
                        .font(.subheadline.weight(.semibold))
                    Text("Last updated \(LocalConditionsFormatting.asofText(snapshot?.asof) ?? "—")")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    if let error, !error.isEmpty {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label("Local Conditions", systemImage: "location.fill")
            }
        }
    }

    private struct LocalConditionsView: View {
        let zip: String
        let snapshot: LocalCheckResponse?
        let drivers: [DashboardDriverItem]
        let isLoading: Bool
        let error: String?
        let useGPS: Bool
        let onRefresh: () -> Void

        private func driver(for key: String) -> DashboardDriverItem? {
            drivers.first { $0.key.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == key.lowercased() }
        }

        private func formattedDriverValue(_ driver: DashboardDriverItem) -> String? {
            guard let value = driver.value else { return nil }
            let unit = (driver.unit ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            switch driver.key.lowercased() {
            case "aqi", "sw":
                return unit.isEmpty ? String(Int(round(value))) : "\(String(Int(round(value)))) \(unit)"
            case "temp":
                return "\(String(format: "%+.1f", value))°C"
            case "pressure", "bz":
                return unit.isEmpty ? String(format: "%+.1f", value) : "\(String(format: "%+.1f", value)) \(unit)"
            case "schumann":
                return unit.isEmpty ? String(format: "%.2f", value) : "\(String(format: "%.2f", value)) \(unit)"
            default:
                return unit.isEmpty ? String(format: "%.1f", value) : "\(String(format: "%.1f", value)) \(unit)"
            }
        }

        private func driverStatus(
            for key: String,
            fallbackLabel: String,
            fallbackState: String,
            fallbackSeverity: String,
            fallbackDetail: String?
        ) -> LocalConditionsDriverStatus {
            if let driver = driver(for: key) {
                let severityKey = LocalConditionsStyle.severityKey(driver.severity)
                return LocalConditionsDriverStatus(
                    label: driver.label ?? fallbackLabel,
                    state: driver.state ?? fallbackState,
                    severityKey: severityKey,
                    progress: LocalConditionsStyle.progress(severityKey),
                    detail: formattedDriverValue(driver) ?? fallbackDetail
                )
            }
            let severityKey = LocalConditionsStyle.severityKey(fallbackSeverity)
            return LocalConditionsDriverStatus(
                label: fallbackLabel,
                state: fallbackState,
                severityKey: severityKey,
                progress: LocalConditionsStyle.progress(severityKey),
                detail: fallbackDetail
            )
        }

        private func pressureStatus(weather: LocalWeather?) -> LocalConditionsDriverStatus {
            let delta = abs(weather?.baroDelta24hHpa ?? 0)
            let trend = LocalConditionsFormatting.derivedPressureTrend(
                raw: weather?.pressureTrend ?? weather?.baroTrend,
                deltaHpa: weather?.baroDelta24hHpa
            )
            let pressure = weather?.pressureHpa
            let state: String
            let severity: String
            if delta >= 12 {
                state = "Swing"
                severity = "high"
            } else if delta >= 8 {
                state = "Swing"
                severity = "elevated"
            } else if delta >= 6 {
                state = "Swing"
                severity = "mild"
            } else if trend == "rising" {
                state = "Rising"
                severity = "low"
            } else if trend == "falling" {
                state = "Falling"
                severity = "low"
            } else if let pressure, pressure <= 1008 {
                state = "Low"
                severity = "mild"
            } else if let pressure, pressure >= 1025 {
                state = "Elevated"
                severity = "mild"
            } else {
                state = "Steady"
                severity = "low"
            }
            return driverStatus(
                for: "pressure",
                fallbackLabel: "Pressure Swing",
                fallbackState: state,
                fallbackSeverity: severity,
                fallbackDetail: LocalConditionsFormatting.formatPressureDelta(weather?.baroDelta24hHpa)
            )
        }

        private func temperatureStatus(weather: LocalWeather?) -> LocalConditionsDriverStatus {
            let delta = abs(weather?.tempDelta24hC ?? 0)
            let severity: String
            if delta >= 12 {
                severity = "high"
            } else if delta >= 8 {
                severity = "elevated"
            } else if delta >= 6 {
                severity = "mild"
            } else {
                severity = "low"
            }
            let state = delta >= 6 ? "Swing" : "Steady"
            return driverStatus(
                for: "temp",
                fallbackLabel: "Temperature Swing",
                fallbackState: state,
                fallbackSeverity: severity,
                fallbackDetail: LocalConditionsFormatting.formatTempDelta(weather?.tempDelta24hC)
            )
        }

        private func airQualityStatus(air: LocalAir?) -> LocalConditionsDriverStatus {
            let aqi = air?.aqi
            let severity: String
            if let aqi, aqi >= 151 {
                severity = "high"
            } else if let aqi, aqi >= 101 {
                severity = "elevated"
            } else if let aqi, aqi >= 51 {
                severity = "mild"
            } else {
                severity = "low"
            }
            let trimmedCategory = air?.category?.trimmingCharacters(in: .whitespacesAndNewlines)
            let state: String
            if let trimmedCategory, !trimmedCategory.isEmpty {
                state = trimmedCategory
            } else {
                state = severity == "high" ? "Unhealthy" : severity == "elevated" ? "USG" : severity == "mild" ? "Moderate" : "Good"
            }
            return driverStatus(
                for: "aqi",
                fallbackLabel: "Air Quality",
                fallbackState: state,
                fallbackSeverity: severity,
                fallbackDetail: LocalConditionsFormatting.formatNumber(aqi, decimals: 0)
            )
        }

        private var locationSummary: String {
            let resolvedZip = (snapshot?.whereInfo?.zip ?? zip).trimmingCharacters(in: .whitespacesAndNewlines)
            if useGPS {
                return resolvedZip.isEmpty ? "GPS preferred" : "GPS preferred • ZIP \(resolvedZip)"
            }
            return resolvedZip.isEmpty ? "ZIP not set" : "ZIP \(resolvedZip)"
        }

        private func forecastDayLabel(_ iso: String?) -> String {
            guard let iso else { return "Day" }
            let fmt = ISO8601DateFormatter()
            if let date = fmt.date(from: iso) {
                let out = DateFormatter()
                out.dateFormat = "EEE, MMM d"
                return out.string(from: date)
            }
            let simple = DateFormatter()
            simple.dateFormat = "yyyy-MM-dd"
            if let date = simple.date(from: iso) {
                let out = DateFormatter()
                out.dateFormat = "EEE, MMM d"
                return out.string(from: date)
            }
            return iso
        }

        private func forecastTempRange(_ day: LocalForecastDay) -> String {
            let high = LocalConditionsFormatting.formatTempMetric(day.tempHighC)
            let low = LocalConditionsFormatting.formatTempMetric(day.tempLowC)
            return "\(high) / \(low)"
        }

        var body: some View {
            let weather = snapshot?.weather
            let air = snapshot?.air
            let moon = snapshot?.moon
            let tempStatus = temperatureStatus(weather: weather)
            let baroStatus = pressureStatus(weather: weather)
            let airStatus = airQualityStatus(air: air)
            let updatedText = LocalConditionsFormatting.asofText(snapshot?.asof) ?? "—"

            ZStack {
                Color.black.opacity(0.96).ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: 16) {
                        LocalConditionsSurfaceCard(title: "Local Conditions", icon: "location.fill") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(snapshot?.whereInfo?.zip ?? (zip.isEmpty ? "ZIP" : zip))
                                        .font(.system(size: 30, weight: .bold, design: .rounded))
                                    Text(locationSummary)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text("Updated \(updatedText)")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                if isLoading { ProgressView().scaleEffect(0.85) }
                                Button("Refresh") { onRefresh() }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }
                            if let error, !error.isEmpty {
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.orange)
                            } else if snapshot == nil && !isLoading {
                                Text("Local conditions are not available yet.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Weather", icon: "thermometer.medium") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(LocalConditionsFormatting.formatTempMetric(weather?.tempC))
                                        .font(.system(size: 34, weight: .bold, design: .rounded))
                                    Text(LocalConditionsFormatting.formatTempImperial(weather?.tempC))
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                LocalConditionsValueChip(
                                    label: "Temp 24h Δ",
                                    value: LocalConditionsFormatting.formatTempDelta(weather?.tempDelta24hC),
                                    tint: GaugePalette.zoneColor(tempStatus.severityKey)
                                )
                            }
                            LocalConditionsStatusStrip(status: tempStatus)
                            HStack(spacing: 12) {
                                LocalConditionsMetricTile(
                                    title: "Humidity",
                                    value: LocalConditionsFormatting.formatPercent(weather?.humidityPct),
                                    progress: LocalConditionsFormatting.clamped((weather?.humidityPct ?? 0) / 100.0),
                                    tint: GaugePalette.low
                                )
                                LocalConditionsMetricTile(
                                    title: "Precip",
                                    value: LocalConditionsFormatting.formatPercent(weather?.precipProbPct),
                                    progress: LocalConditionsFormatting.clamped((weather?.precipProbPct ?? 0) / 100.0),
                                    tint: GaugePalette.mild
                                )
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Barometric", icon: "gauge.with.dots.needle.bottom.50percent") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(LocalConditionsFormatting.formatPressureShort(weather?.pressureHpa))
                                        .font(.system(size: 30, weight: .bold, design: .rounded))
                                    Text(LocalConditionsFormatting.formatPressureImperial(weather?.pressureHpa))
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                VStack(alignment: .trailing, spacing: 8) {
                                    LocalConditionsValueChip(
                                        label: "Pressure 24h Δ",
                                        value: LocalConditionsFormatting.formatPressureDelta(weather?.baroDelta24hHpa),
                                        tint: GaugePalette.zoneColor(baroStatus.severityKey)
                                    )
                                    LocalConditionsValueChip(
                                        label: "Trend",
                                        value: LocalConditionsFormatting.formatTrend(
                                            LocalConditionsFormatting.derivedPressureTrend(
                                                raw: weather?.pressureTrend ?? weather?.baroTrend,
                                                deltaHpa: weather?.baroDelta24hHpa
                                            )
                                        ),
                                        tint: GaugePalette.zoneColor(baroStatus.severityKey)
                                    )
                                }
                            }
                            LocalConditionsStatusStrip(status: baroStatus)
                        }

                        LocalConditionsSurfaceCard(title: "Air Quality", icon: "wind") {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(LocalConditionsFormatting.formatNumber(air?.aqi, decimals: 0))
                                        .font(.system(size: 34, weight: .bold, design: .rounded))
                                    Text(air?.category ?? airStatus.state)
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                LocalConditionsValueChip(
                                    label: "Pollutant",
                                    value: air?.pollutant ?? "—",
                                    tint: GaugePalette.zoneColor(airStatus.severityKey)
                                )
                            }
                            LocalConditionsStatusStrip(status: airStatus)
                        }

                        if let forecastDays = snapshot?.forecastDaily, !forecastDays.isEmpty {
                            LocalConditionsSurfaceCard(title: "3-Day Forecast", icon: "calendar") {
                                VStack(alignment: .leading, spacing: 12) {
                                    ForEach(forecastDays) { day in
                                        VStack(alignment: .leading, spacing: 8) {
                                            HStack(alignment: .top, spacing: 12) {
                                                VStack(alignment: .leading, spacing: 3) {
                                                    Text(forecastDayLabel(day.day))
                                                        .font(.headline)
                                                    Text(day.conditionSummary ?? "Forecast")
                                                        .font(.caption)
                                                        .foregroundColor(.secondary)
                                                }
                                                Spacer()
                                                VStack(alignment: .trailing, spacing: 6) {
                                                    Text(forecastTempRange(day))
                                                        .font(.subheadline.weight(.semibold))
                                                    if let tempDelta = day.tempDeltaFromPriorDayC {
                                                        Text("\(String(format: "%+.1f", tempDelta))°C vs prior day")
                                                            .font(.caption2)
                                                            .foregroundColor(.secondary)
                                                    }
                                                }
                                            }

                                            ScrollView(.horizontal, showsIndicators: false) {
                                                HStack(spacing: 10) {
                                                    LocalConditionsValueChip(
                                                        label: "Humidity",
                                                        value: LocalConditionsFormatting.formatPercent(day.humidityAvg),
                                                        tint: GaugePalette.low
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "Precip",
                                                        value: LocalConditionsFormatting.formatPercent(day.precipProbability),
                                                        tint: GaugePalette.mild
                                                    )
                                                    LocalConditionsValueChip(
                                                        label: "Wind",
                                                        value: day.windSpeed.map { String(format: "%.1f m/s", $0) } ?? "—",
                                                        tint: GaugePalette.elevated
                                                    )
                                                    if let gust = day.windGust {
                                                        LocalConditionsValueChip(
                                                            label: "Gust",
                                                            value: String(format: "%.1f m/s", gust),
                                                            tint: GaugePalette.elevated
                                                        )
                                                    }
                                                    LocalConditionsValueChip(
                                                        label: "Pressure",
                                                        value: day.pressureHpa.map { String(format: "%.1f hPa", $0) } ?? "Unavailable",
                                                        tint: GaugePalette.zoneColor(day.pressureHpa == nil ? "mild" : "low")
                                                    )
                                                    if let pressureDelta = day.pressureDeltaFromPriorDayHpa {
                                                        LocalConditionsValueChip(
                                                            label: "Pressure Δ",
                                                            value: String(format: "%+.1f hPa", pressureDelta),
                                                            tint: GaugePalette.zoneColor(abs(pressureDelta) >= 6 ? "elevated" : "low")
                                                        )
                                                    }
                                                    if let aqiForecast = day.aqiForecast {
                                                        LocalConditionsValueChip(
                                                            label: "AQI",
                                                            value: String(format: "%.0f", aqiForecast),
                                                            tint: GaugePalette.mild
                                                        )
                                                    }
                                                }
                                            }
                                        }
                                        .padding(.bottom, day.id == forecastDays.last?.id ? 0 : 8)

                                        if day.id != forecastDays.last?.id {
                                            Divider().overlay(Color.white.opacity(0.08))
                                        }
                                    }
                                }
                            }
                        }

                        LocalConditionsSurfaceCard(title: "Moon", icon: "moon.stars.fill") {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(moon?.phase ?? "—")
                                    .font(.title2.weight(.semibold))
                                LocalConditionsMetricTile(
                                    title: "Illumination",
                                    value: LocalConditionsFormatting.illuminationText(moon?.illum),
                                    progress: LocalConditionsFormatting.illuminationFraction(moon?.illum),
                                    tint: GaugePalette.mild
                                )
                            }
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Local Conditions")
            .navigationBarTitleDisplayMode(.inline)
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

    private struct EarthscopeBriefingSection: Identifiable {
        let id: String
        let key: String
        let title: String
        let body: String
    }

    private enum EarthscopeBriefingKey: String, CaseIterable {
        case checkin
        case drivers
        case summary
        case actions
    }

    private struct EarthscopeBriefingParser {
        private static let listMarkerRegex = try? NSRegularExpression(pattern: #"^\d+\.\s+"#)
        private static let legacyEarthscopePrefixRegex = try? NSRegularExpression(
            pattern: #"^\s*Gaia Eyes\s+[—-]\s+Daily EarthScope\s*"#,
            options: [.caseInsensitive]
        )
        private static let legacyActionSplitRegex = try? NSRegularExpression(
            pattern: #"(?=(?:5-10 minutes paced breathing|Work in 25-50 minute blocks|Hydrate, add gentle movement|Wind down earlier|If pain flares))"#,
            options: [.caseInsensitive]
        )
        private static let legacyActionMarkers = [
            "5-10 minutes paced breathing",
            "Work in 25-50 minute blocks",
            "Hydrate, add gentle movement",
            "Wind down earlier",
            "If pain flares",
        ]

        private static func sectionKey(for heading: String) -> EarthscopeBriefingKey? {
            let h = heading.lowercased()
            if h == "now" || h.contains("check") || h.contains("today") { return .checkin }
            if h.contains("current driver") || h.contains("driver") { return .drivers }
            if h.contains("supportive action") || h == "actions" || h.contains("action") { return .actions }
            if h.contains("what you may feel") || h.contains("may feel") || h.contains("summary") || h.contains("note") || h.contains("feel") {
                return .summary
            }
            return nil
        }

        private static func cleanLine(_ line: String) -> String {
            var out = line.trimmingCharacters(in: .whitespacesAndNewlines)
            out = out.replacingOccurrences(of: "**", with: "")
            out = out.replacingOccurrences(of: "__", with: "")
            if out.hasPrefix("- ") || out.hasPrefix("* ") {
                out = String(out.dropFirst(2))
            }
            if let regex = listMarkerRegex {
                let range = NSRange(location: 0, length: out.utf16.count)
                out = regex.stringByReplacingMatches(in: out, options: [], range: range, withTemplate: "")
            }
            if let regex = legacyEarthscopePrefixRegex {
                let range = NSRange(location: 0, length: out.utf16.count)
                out = regex.stringByReplacingMatches(in: out, options: [], range: range, withTemplate: "")
            }
            out = out.replacingOccurrences(of: "–", with: "-")
            return out.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        private static func dedupePreservingOrder(_ lines: [String]) -> [String] {
            var seen: Set<String> = []
            var output: [String] = []
            for raw in lines {
                let cleaned = cleanLine(raw)
                guard !cleaned.isEmpty else { continue }
                let key = cleaned.lowercased()
                guard !seen.contains(key) else { continue }
                seen.insert(key)
                output.append(cleaned)
            }
            return output
        }

        private static func extractLegacyActions(fromSummary lines: [String]) -> (summary: [String], actions: [String]) {
            var summary: [String] = []
            var actions: [String] = []

            for raw in lines {
                let cleaned = cleanLine(raw)
                guard !cleaned.isEmpty else { continue }

                let firstMarkerIndex = legacyActionMarkers
                    .compactMap { marker in cleaned.range(of: marker, options: [.caseInsensitive])?.lowerBound }
                    .min()

                guard let markerIndex = firstMarkerIndex else {
                    summary.append(cleaned)
                    continue
                }

                let summaryPrefix = String(cleaned[..<markerIndex]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !summaryPrefix.isEmpty {
                    summary.append(summaryPrefix)
                }

                let tail = String(cleaned[markerIndex...]).trimmingCharacters(in: .whitespacesAndNewlines)
                guard !tail.isEmpty else { continue }

                if let regex = legacyActionSplitRegex {
                    let nsRange = NSRange(location: 0, length: tail.utf16.count)
                    let matches = regex.matches(in: tail, options: [], range: nsRange)
                    let starts = matches.map(\.range.location).sorted()
                    if !starts.isEmpty {
                        let nsTail = tail as NSString
                        for (index, start) in starts.enumerated() {
                            let end = (index + 1 < starts.count) ? starts[index + 1] : nsTail.length
                            let chunk = nsTail.substring(with: NSRange(location: start, length: end - start))
                            let action = cleanLine(chunk)
                            if !action.isEmpty {
                                actions.append(action)
                            }
                        }
                        continue
                    }
                }

                actions.append(tail)
            }

            return (
                summary: dedupePreservingOrder(summary),
                actions: dedupePreservingOrder(actions)
            )
        }

        private static func sectionTitle(_ key: EarthscopeBriefingKey) -> String {
            switch key {
            case .checkin: return "Now"
            case .drivers: return "What's Shaping Things Now"
            case .summary: return "What Might Stand Out"
            case .actions: return "What May Help Right Now"
            }
        }

        private static func defaultBody(_ key: EarthscopeBriefingKey) -> String {
            switch key {
            case .checkin:
                return "The current EarthScope update is still being prepared."
            case .drivers:
                return "No primary driver is highlighted right now."
            case .summary:
                return "Most gauges look fairly steady right now. Check highlighted gauges for fresher context."
            case .actions:
                return "• Hydrate\n• Keep your sleep window steady\n• Use gentle movement"
            }
        }

        private static func defaultSections() -> [EarthscopeBriefingSection] {
            EarthscopeBriefingKey.allCases.map { key in
                EarthscopeBriefingSection(
                    id: key.rawValue,
                    key: key.rawValue,
                    title: sectionTitle(key),
                    body: defaultBody(key)
                )
            }
        }

        static func parse(_ markdown: String?, driversCompact: [String] = []) -> [EarthscopeBriefingSection] {
            guard let markdown, !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                if driversCompact.isEmpty {
                    return defaultSections()
                }
                var fallback = defaultSections()
                if let idx = fallback.firstIndex(where: { $0.key == EarthscopeBriefingKey.drivers.rawValue }) {
                    let compact = driversCompact.map { cleanLine($0) }.filter { !$0.isEmpty }
                    if !compact.isEmpty {
                        fallback[idx] = EarthscopeBriefingSection(
                            id: EarthscopeBriefingKey.drivers.rawValue,
                            key: EarthscopeBriefingKey.drivers.rawValue,
                            title: sectionTitle(.drivers),
                            body: compact.joined(separator: "\n")
                        )
                    }
                }
                return fallback
            }

            let normalized = markdown.replacingOccurrences(of: "\r\n", with: "\n")
            let lines = normalized.components(separatedBy: "\n")
            var buckets: [EarthscopeBriefingKey: [String]] = [:]
            for key in EarthscopeBriefingKey.allCases { buckets[key] = [] }

            var current: EarthscopeBriefingKey? = nil
            var unknown: [String] = []
            var hasActionItems = false

            for raw in lines {
                let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty { continue }

                if trimmed.hasPrefix("#") {
                    let heading = trimmed.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)
                    current = sectionKey(for: heading)
                    continue
                }

                let cleaned = cleanLine(trimmed)
                if cleaned.isEmpty { continue }

                let isListItem = trimmed.hasPrefix("- ")
                    || trimmed.hasPrefix("* ")
                    || trimmed.range(of: #"^\d+\.\s+"#, options: .regularExpression) != nil

                if current == .actions, !isListItem, hasActionItems {
                    buckets[.summary, default: []].append(cleaned)
                    continue
                }

                if let key = current {
                    buckets[key, default: []].append(cleaned)
                    if key == .actions, isListItem { hasActionItems = true }
                } else {
                    unknown.append(cleaned)
                }
            }

            if (buckets[.summary] ?? []).isEmpty, !unknown.isEmpty {
                buckets[.summary] = unknown
            }
            if (buckets[.checkin] ?? []).isEmpty, !(buckets[.summary] ?? []).isEmpty {
                let summary = buckets[.summary] ?? []
                buckets[.checkin] = Array(summary.prefix(2))
                buckets[.summary] = Array(summary.dropFirst(min(2, summary.count)))
            }
            let compactDrivers = driversCompact.map { cleanLine($0) }.filter { !$0.isEmpty }
            if !compactDrivers.isEmpty {
                buckets[.drivers] = compactDrivers
            }

            let extracted = extractLegacyActions(fromSummary: buckets[.summary] ?? [])
            if !extracted.actions.isEmpty || !extracted.summary.isEmpty {
                buckets[.summary] = extracted.summary
            }
            let existingActions = buckets[.actions] ?? []
            if !extracted.actions.isEmpty {
                buckets[.actions] = dedupePreservingOrder(existingActions + extracted.actions)
            }

            var sections: [EarthscopeBriefingSection] = []
            for key in EarthscopeBriefingKey.allCases {
                let linesForKey = buckets[key] ?? []
                let body: String
                if !linesForKey.isEmpty, key == .actions {
                    body = linesForKey.map { "• \($0)" }.joined(separator: "\n")
                } else if !linesForKey.isEmpty, key == .drivers {
                    body = linesForKey.joined(separator: "\n")
                } else if !linesForKey.isEmpty {
                    body = linesForKey.joined(separator: " ")
                } else {
                    body = defaultBody(key)
                }
                sections.append(
                    EarthscopeBriefingSection(
                        id: key.rawValue,
                        key: key.rawValue,
                        title: sectionTitle(key),
                        body: body
                    )
                )
            }
            return sections.isEmpty ? defaultSections() : sections
        }
    }

    private struct EarthscopeBackgroundLayer: View {
        let candidates: [URL]
        @State private var index: Int = 0

        var body: some View {
            ZStack {
                if index < candidates.count {
                    AsyncImage(url: candidates[index]) { phase in
                        switch phase {
                        case .empty:
                            Color.black.opacity(0.25)
                        case .success(let image):
                            image.resizable().scaledToFill()
                        case .failure:
                            Color.black.opacity(0.25)
                                .onAppear {
                                    if index < candidates.count - 1 {
                                        index += 1
                                    }
                                }
                        @unknown default:
                            Color.black.opacity(0.25)
                        }
                    }
                } else {
                    LinearGradient(
                        colors: [Color(red: 0.08, green: 0.11, blue: 0.18), Color(red: 0.11, green: 0.16, blue: 0.25)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                }
                LinearGradient(
                    colors: [Color.black.opacity(0.26), Color.black.opacity(0.68)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            }
        }
    }

    private struct EarthscopeBriefingBlock: View {
        let section: EarthscopeBriefingSection
        let compact: Bool

        private func backgroundCandidates() -> [URL] {
            let names: [String]
            switch section.key {
            case "checkin":
                names = ["now", "checkin", "today_checkin", "todays_checkin"]
            case "drivers":
                names = ["current_drivers", "drivers"]
            case "summary":
                names = ["what_you_may_feel", "feel", "summary", "note"]
            case "actions":
                names = ["actions", "supportive_actions"]
            default:
                names = [section.key]
            }

            var urls: [URL] = []
            for n in names {
                for ext in ["png", "jpg", "PNG", "JPG"] {
                    if let u = ContentView.resolvedMediaURL("social/earthscope/backgrounds/\(n).\(ext)") {
                        urls.append(u)
                    }
                }
            }
            var seen: Set<URL> = []
            return urls.filter { seen.insert($0).inserted }
        }

        private func lineLimitForCompact() -> Int {
            switch section.key {
            case "actions": return 6
            case "summary": return 4
            default: return 5
            }
        }

        var body: some View {
            ZStack(alignment: .topLeading) {
                EarthscopeBackgroundLayer(candidates: backgroundCandidates())
                VStack(alignment: .leading, spacing: 8) {
                    Text(section.title)
                        .font(.headline)
                        .foregroundColor(.white)
                    Text(section.body)
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.95))
                        .lineSpacing(2)
                        .lineLimit(compact ? lineLimitForCompact() : nil)
                        .multilineTextAlignment(.leading)
                }
                .padding(12)
            }
            .frame(minHeight: compact ? 140 : 170)
            .frame(maxWidth: .infinity, alignment: .leading)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.white.opacity(0.10), lineWidth: 1)
            )
        }
    }

    private struct EarthscopeCardV2: View {
        let title: String?
        let updatedAt: String?
        let bodyMarkdown: String?
        let summaryText: String?
        let driversCompact: [String]
        @State private var showFull: Bool = false

        private func displayTitle() -> String {
            let raw = (title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let cleaned = raw.replacingOccurrences(
                of: #"\s+—\s+\d{4}-\d{2}-\d{2}$"#,
                with: "",
                options: .regularExpression
            )
            return cleaned.isEmpty ? "Your EarthScope" : cleaned
        }

        private func displayUpdatedText() -> String? {
            LocalConditionsFormatting.asofText(updatedAt).map { "Updated \($0)" }
        }

        private func resolvedSummary() -> String {
            if let summaryText, !summaryText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return summaryText.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            let sections = EarthscopeBriefingParser.parse(bodyMarkdown, driversCompact: driversCompact)
            if let summary = sections.first(where: { $0.key == EarthscopeBriefingKey.summary.rawValue })?.body,
               !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return summary
            }
            return "Keep an eye on highlighted gauges and drivers for context."
        }

        var body: some View {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text(displayTitle())
                        .font(.headline)
                    if let updated = displayUpdatedText() {
                        Text(updated)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }

                    Text(resolvedSummary())
                        .font(.subheadline)
                        .foregroundColor(.primary)
                        .padding(10)
                        .background(Color.black.opacity(0.18), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                    Button("Read full EarthScope") { showFull = true }
                        .font(.caption)
                        .underline()
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: { Label("EarthScope", systemImage: "globe.americas.fill") }
            .sheet(isPresented: $showFull) {
                EarthscopeFullSheetV2(
                    title: title,
                    updatedAt: updatedAt,
                    bodyText: bodyMarkdown,
                    driversCompact: driversCompact
                )
            }
        }
    }

    private struct EarthscopeFullSheetV2: View {
        let title: String?
        let updatedAt: String?
        let bodyText: String?
        let driversCompact: [String]
        @Environment(\.dismiss) private var dismiss

        private func displayTitle() -> String {
            let raw = (title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let cleaned = raw.replacingOccurrences(
                of: #"\s+—\s+\d{4}-\d{2}-\d{2}$"#,
                with: "",
                options: .regularExpression
            )
            return cleaned.isEmpty ? "Your EarthScope" : cleaned
        }

        var body: some View {
            let sections = EarthscopeBriefingParser.parse(bodyText, driversCompact: driversCompact)
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(displayTitle())
                            .font(.title3)
                            .bold()
                        if let updated = LocalConditionsFormatting.asofText(updatedAt) {
                            Text("Updated \(updated)")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }

                        ForEach(sections) { section in
                            EarthscopeBriefingBlock(section: section, compact: false)
                        }

                    }
                    .padding()
                }
                .navigationTitle("EarthScope")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { dismiss() }
                    }
                }
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
        let title: String
        let series: SpaceSeries
        let highlights: [SymptomHighlight]
        let window: InsightsTrendRange
        let showsSchumann: Bool

        init(
            title: String = "Signals vs Symptoms",
            series: SpaceSeries,
            highlights: [SymptomHighlight],
            window: InsightsTrendRange = .days7,
            showsSchumann: Bool = false
        ) {
            self.title = title
            self.series = series
            self.highlights = highlights
            self.window = window
            self.showsSchumann = showsSchumann
        }

        private struct SWPoint: Identifiable {
            let id: Date
            let date: Date
            let kp: Double?
            let bz: Double?
            init(date: Date, kp: Double?, bz: Double?) {
                self.id = date
                self.date = date
                self.kp = kp
                self.bz = bz
            }
        }

        private struct SchPoint: Identifiable {
            let id: Date
            let date: Date
            let f0: Double?
            let f1: Double?

            var schumannValue: Double? {
                f1 ?? f0
            }
        }

        private struct HRTSPoint: Identifiable {
            let id: Date
            let date: Date
            let hr: Double
        }

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

        private static func parseISODate(_ s: String) -> Date? {
            SpaceChartsCard.isoFmt.date(from: s) ?? SpaceChartsCard.isoFmtSimple.date(from: s)
        }

        private var cutoffDate: Date {
            Calendar.current.date(byAdding: .day, value: -(window.days - 1), to: Date()) ?? .distantPast
        }

        private var filteredHighlights: [SymptomHighlight] {
            highlights.filter { $0.date >= cutoffDate }
        }

        private var swPoints: [SWPoint] {
            (series.spaceWeather ?? []).compactMap { point in
                guard let ts = point.ts, let date = Self.parseISODate(ts), date >= cutoffDate else { return nil }
                return SWPoint(date: date, kp: point.kp, bz: point.bz)
            }
        }

        private var schPoints: [SchPoint] {
            (series.schumannDaily ?? []).compactMap { day in
                guard let rawDay = day.day, let date = ContentView.symptomDayFormatter.date(from: rawDay), date >= cutoffDate else { return nil }
                return SchPoint(id: date, date: date, f0: day.f0, f1: day.f1)
            }
        }

        private var hrPoints: [HRTSPoint] {
            (series.hrTimeseries ?? []).compactMap { point in
                guard let ts = point.ts, let date = Self.parseISODate(ts), date >= cutoffDate, let hr = point.hr else { return nil }
                return HRTSPoint(id: date, date: date, hr: hr)
            }
        }

        private func emptyText(_ label: String) -> String {
            "No \(label) samples in the last \(window.days) days"
        }

        var body: some View {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.headline)

                if #available(iOS 16.0, *) {
                    HStack(spacing: 12) {
                        Label("Kp", systemImage: "circle.fill").foregroundColor(.green).font(.caption)
                        Label("Bz", systemImage: "circle.fill").foregroundColor(.blue).font(.caption)
                        if showsSchumann {
                            Label("F1", systemImage: "circle.fill").foregroundColor(.purple).font(.caption)
                        }
                        Label("HR", systemImage: "circle.fill").foregroundColor(.gray).font(.caption)
                    }

                    if swPoints.compactMap(\.kp).isEmpty {
                        Text(emptyText("Kp"))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Chart {
                            ForEach(filteredHighlights) { highlight in
                                RuleMark(x: .value("Symptom", highlight.date))
                                    .foregroundStyle(.pink.opacity(0.20))
                                    .lineStyle(StrokeStyle(lineWidth: 14, lineCap: .round))
                                    .annotation(position: .top) {
                                        Text("▲ \(highlight.events)")
                                            .font(.caption2)
                                            .foregroundColor(.pink)
                                    }
                            }
                            ForEach(swPoints) { point in
                                if let kp = point.kp {
                                    LineMark(x: .value("Date", point.date), y: .value("Kp", kp))
                                        .interpolationMethod(.catmullRom)
                                        .foregroundStyle(.green)
                                }
                            }
                        }
                        .chartYScale(domain: 0...9)
                        .frame(height: 120)
                    }

                    if swPoints.compactMap(\.bz).isEmpty {
                        Text(emptyText("Bz"))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Chart {
                            ForEach(filteredHighlights) { highlight in
                                RuleMark(x: .value("Symptom", highlight.date))
                                    .foregroundStyle(.pink.opacity(0.18))
                                    .lineStyle(StrokeStyle(lineWidth: 12, lineCap: .round))
                            }
                            ForEach(swPoints) { point in
                                if let bz = point.bz {
                                    LineMark(x: .value("Date", point.date), y: .value("Bz nT", bz))
                                        .interpolationMethod(.catmullRom)
                                        .foregroundStyle(.blue)
                                }
                            }
                        }
                        .frame(height: 120)
                    }

                    if showsSchumann {
                        if schPoints.compactMap(\.schumannValue).isEmpty {
                            Text(emptyText("Schumann"))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            Chart(schPoints) { point in
                                if let schumannValue = point.schumannValue {
                                    LineMark(x: .value("Day", point.date), y: .value("Schumann Hz", schumannValue))
                                        .interpolationMethod(.catmullRom)
                                        .foregroundStyle(.purple)
                                    PointMark(x: .value("Day", point.date), y: .value("Schumann Hz", schumannValue))
                                        .foregroundStyle(.purple)
                                }
                            }
                            .frame(height: 100)
                        }
                    }

                    if hrPoints.isEmpty {
                        Text(emptyText("HR"))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Chart(hrPoints) { point in
                            LineMark(x: .value("Time", point.date), y: .value("HR", point.hr))
                                .interpolationMethod(.catmullRom)
                                .foregroundStyle(.gray)
                        }
                        .frame(height: 100)
                    }
                } else {
                    Text("Charts require iOS 16 or later.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .transaction { $0.disablesAnimations = true }
        }
    }
#endif
}
