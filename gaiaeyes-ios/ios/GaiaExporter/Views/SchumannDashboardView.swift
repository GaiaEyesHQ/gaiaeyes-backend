import SwiftUI
import Charts
#if canImport(UIKit)
import UIKit
#endif

private struct SchumannLatestResponse: Codable {
    let ok: Bool?
    let generatedAt: String?
    let harmonics: SchumannHarmonics?
    let amplitude: SchumannAmplitude?
    let quality: SchumannQuality?
    let fusion: SchumannFusionResponse?

    enum CodingKeys: String, CodingKey {
        case ok
        case generatedAt = "generated_at"
        case harmonics
        case amplitude
        case quality
        case fusion
    }
}

private struct SchumannSeriesResponse: Codable {
    let ok: Bool?
    let count: Int?
    let rows: [SchumannSeriesRow]?
}

private struct SchumannHeatmapResponse: Codable {
    let ok: Bool?
    let axis: SchumannAxis?
    let count: Int?
    let points: [SchumannHeatmapPoint]?
}

private struct SchumannSeriesRow: Codable {
    let ts: String?
    let harmonics: SchumannHarmonics?
    let amplitude: SchumannAmplitude?
    let quality: SchumannQuality?
    let axis: SchumannAxis?
}

private struct SchumannHeatmapPoint: Codable {
    let ts: String?
    let bins: [Double]

    enum CodingKeys: String, CodingKey {
        case ts
        case bins
    }

    init(ts: String?, bins: [Double]) {
        self.ts = ts
        self.bins = bins
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ts = try container.decodeIfPresent(String.self, forKey: .ts)

        if let doubles = try? container.decode([Double].self, forKey: .bins) {
            bins = doubles
            return
        }
        if let ints = try? container.decode([Int].self, forKey: .bins) {
            bins = ints.map(Double.init)
            return
        }
        if let strings = try? container.decode([String].self, forKey: .bins) {
            bins = strings.compactMap(Double.init)
            return
        }

        bins = []
    }
}

private struct SchumannHarmonics: Codable {
    let f0: Double?
    let f1: Double?
    let f2: Double?
    let f3: Double?
    let f4: Double?
    let f5: Double?
}

private struct SchumannAmplitude: Codable {
    let srTotal0_20: Double?
    let band7_9: Double?
    let band13_15: Double?
    let band18_20: Double?

    enum CodingKeys: String, CodingKey {
        case srTotal0_20 = "sr_total_0_20"
        case band7_9 = "band_7_9"
        case band13_15 = "band_13_15"
        case band18_20 = "band_18_20"
    }

    init(srTotal0_20: Double?, band7_9: Double?, band13_15: Double?, band18_20: Double?) {
        self.srTotal0_20 = srTotal0_20
        self.band7_9 = band7_9
        self.band13_15 = band13_15
        self.band18_20 = band18_20
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: SchumannDynamicCodingKey.self)
        srTotal0_20 = Self.decodeNumber(c, keys: ["sr_total_0_20", "srTotal020", "srTotal0_20"])
        band7_9 = Self.decodeNumber(c, keys: ["band_7_9", "band79", "band7_9"])
        band13_15 = Self.decodeNumber(c, keys: ["band_13_15", "band1315", "band13_15"])
        band18_20 = Self.decodeNumber(c, keys: ["band_18_20", "band1820", "band18_20"])
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(srTotal0_20, forKey: .srTotal0_20)
        try c.encodeIfPresent(band7_9, forKey: .band7_9)
        try c.encodeIfPresent(band13_15, forKey: .band13_15)
        try c.encodeIfPresent(band18_20, forKey: .band18_20)
    }

    private static func decodeNumber(_ c: KeyedDecodingContainer<SchumannDynamicCodingKey>, keys: [String]) -> Double? {
        for raw in keys {
            guard let key = SchumannDynamicCodingKey(stringValue: raw) else { continue }
            if let v = try? c.decodeIfPresent(Double.self, forKey: key) { return v }
            if let i = try? c.decodeIfPresent(Int.self, forKey: key) { return Double(i) }
            if let s = try? c.decodeIfPresent(String.self, forKey: key), let d = Double(s) { return d }
        }
        return nil
    }
}

private struct SchumannDynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        return nil
    }
}

private struct SchumannQuality: Codable {
    let primarySource: String?
    let usable: Bool?
    let qualityScore: Double?

    enum CodingKeys: String, CodingKey {
        case primarySource = "primary_source"
        case usable
        case qualityScore = "quality_score"
    }

    init(primarySource: String?, usable: Bool?, qualityScore: Double?) {
        self.primarySource = primarySource
        self.usable = usable
        self.qualityScore = qualityScore
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        primarySource = try? c.decodeIfPresent(String.self, forKey: .primarySource)
        usable = try? c.decodeIfPresent(Bool.self, forKey: .usable)
        // quality_score may arrive as number or string
        if let v = try? c.decodeIfPresent(Double.self, forKey: .qualityScore) {
            qualityScore = v
        } else if let i = try? c.decodeIfPresent(Int.self, forKey: .qualityScore) {
            qualityScore = Double(i)
        } else if let s = try? c.decodeIfPresent(String.self, forKey: .qualityScore) {
            qualityScore = Double(s)
        } else {
            qualityScore = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(primarySource, forKey: .primarySource)
        try c.encodeIfPresent(usable, forKey: .usable)
        try c.encodeIfPresent(qualityScore, forKey: .qualityScore)
    }
}

private struct SchumannAxis: Codable {
    let freqStartHz: Double?
    let freqStepHz: Double?
    let bins: Int?

    enum CodingKeys: String, CodingKey {
        case freqStartHz = "freq_start_hz"
        case freqStepHz = "freq_step_hz"
        case bins
    }
}

private struct TomskCoherence: Codable {
    let label: String?
    let percentile: Double?
    let q1Value: Double?

    enum CodingKeys: String, CodingKey {
        case label
        case percentile
        case q1Value = "q1_value"
    }
}

private struct SchumannFusionResponse: Codable {
    let enabled: Bool?
    let tomskUsable: Bool?
    let displayF0Hz: Double?
    let displayF0Source: String?
    let secondaryF0Hz: Double?
    let secondaryF0Source: String?
    let coherence: TomskCoherence?

    enum CodingKeys: String, CodingKey {
        case enabled
        case tomskUsable = "tomsk_usable"
        case displayF0Hz = "display_f0_hz"
        case displayF0Source = "display_f0_source"
        case secondaryF0Hz = "secondary_f0_hz"
        case secondaryF0Source = "secondary_f0_source"
        case coherence
    }
}

private struct TomskTrendDelta: Codable {
    let delta: Double?
    let dir: String?
}

private struct TomskParamsLatestResponse: Codable {
    let ok: Bool?
    let generatedAt: String?
    let stationId: String?
    let usable: Bool?
    let usableForFusion: Bool?
    let qualityScore: Double?
    let frequencyHz: [String: Double]?
    let amplitude: [String: Double]?
    let qFactor: [String: Double]?
    let trend2h: [String: TomskTrendDelta]?
    let coherence: TomskCoherence?

    enum CodingKeys: String, CodingKey {
        case ok
        case generatedAt = "generated_at"
        case stationId = "station_id"
        case usable
        case usableForFusion = "usable_for_fusion"
        case qualityScore = "quality_score"
        case frequencyHz = "frequency_hz"
        case amplitude
        case qFactor = "q_factor"
        case trend2h = "trend_2h"
        case coherence
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = try? c.decodeIfPresent(Bool.self, forKey: .ok)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        stationId = try? c.decodeIfPresent(String.self, forKey: .stationId)
        usable = Self.decodeBool(c, forKey: .usable)
        usableForFusion = Self.decodeBool(c, forKey: .usableForFusion)
        qualityScore = Self.decodeDouble(c, forKey: .qualityScore)
        frequencyHz = Self.decodeNumericMap(c, forKey: .frequencyHz)
        amplitude = Self.decodeNumericMap(c, forKey: .amplitude)
        qFactor = Self.decodeNumericMap(c, forKey: .qFactor)
        trend2h = try? c.decodeIfPresent([String: TomskTrendDelta].self, forKey: .trend2h)
        coherence = try? c.decodeIfPresent(TomskCoherence.self, forKey: .coherence)
    }

    private static func decodeBool(_ c: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Bool? {
        if let value = try? c.decode(Bool.self, forKey: key) {
            return value
        }
        if let stringValue = try? c.decode(String.self, forKey: key) {
            switch stringValue.lowercased() {
            case "true", "1", "yes":
                return true
            case "false", "0", "no":
                return false
            default:
                return nil
            }
        }
        return nil
    }

    private static func decodeDouble(_ c: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Double? {
        if let value = try? c.decode(Double.self, forKey: key) {
            return value
        }
        if let intValue = try? c.decode(Int.self, forKey: key) {
            return Double(intValue)
        }
        if let stringValue = try? c.decode(String.self, forKey: key) {
            return Double(stringValue)
        }
        return nil
    }

    private static func decodeNumericMap(
        _ c: KeyedDecodingContainer<CodingKeys>,
        forKey key: CodingKeys
    ) -> [String: Double]? {
        guard c.contains(key),
              let nested = try? c.nestedContainer(keyedBy: SchumannDynamicCodingKey.self, forKey: key)
        else {
            return nil
        }

        var mapped: [String: Double] = [:]
        for nestedKey in nested.allKeys {
            if let value = try? nested.decode(Double.self, forKey: nestedKey) {
                mapped[nestedKey.stringValue] = value
                continue
            }
            if let intValue = try? nested.decode(Int.self, forKey: nestedKey) {
                mapped[nestedKey.stringValue] = Double(intValue)
                continue
            }
            if let stringValue = try? nested.decode(String.self, forKey: nestedKey),
               let value = Double(stringValue) {
                mapped[nestedKey.stringValue] = value
            }
        }

        return mapped.isEmpty ? nil : mapped
    }
}

private struct TomskParamsSeriesResponse: Codable {
    let ok: Bool?
    let stationId: String?
    let count: Int?
    let points: [TomskParamsSeriesPoint]?

    enum CodingKeys: String, CodingKey {
        case ok
        case stationId = "station_id"
        case count
        case points
    }
}

private struct TomskParamsSeriesPoint: Codable, Identifiable {
    let ts: String?
    let usable: Bool?
    let qualityScore: Double?
    let qualityFlags: [String]?
    let values: [String: Double]

    var id: String { ts ?? UUID().uuidString }

    enum ReservedCodingKeys: String, CodingKey {
        case ts
        case usable
        case qualityScore = "quality_score"
        case qualityFlags = "quality_flags"
    }

    init(from decoder: Decoder) throws {
        let reserved = try decoder.container(keyedBy: ReservedCodingKeys.self)
        let dynamic = try decoder.container(keyedBy: SchumannDynamicCodingKey.self)

        ts = try reserved.decodeIfPresent(String.self, forKey: .ts)
        usable = try reserved.decodeIfPresent(Bool.self, forKey: .usable)
        qualityScore = try? reserved.decodeIfPresent(Double.self, forKey: .qualityScore)
        qualityFlags = try reserved.decodeIfPresent([String].self, forKey: .qualityFlags)

        var mapped: [String: Double] = [:]
        for key in dynamic.allKeys {
            if ["ts", "usable", "quality_score", "quality_flags"].contains(key.stringValue) {
                continue
            }
            if let value = try? dynamic.decodeIfPresent(Double.self, forKey: key) {
                mapped[key.stringValue] = value
            } else if let intValue = try? dynamic.decodeIfPresent(Int.self, forKey: key) {
                mapped[key.stringValue] = Double(intValue)
            } else if let stringValue = try? dynamic.decodeIfPresent(String.self, forKey: key),
                      let number = Double(stringValue) {
                mapped[key.stringValue] = number
            }
        }
        values = mapped
    }

    func encode(to encoder: Encoder) throws {
        var reserved = encoder.container(keyedBy: ReservedCodingKeys.self)
        try reserved.encodeIfPresent(ts, forKey: .ts)
        try reserved.encodeIfPresent(usable, forKey: .usable)
        try reserved.encodeIfPresent(qualityScore, forKey: .qualityScore)
        try reserved.encodeIfPresent(qualityFlags, forKey: .qualityFlags)

        var dynamic = encoder.container(keyedBy: SchumannDynamicCodingKey.self)
        for (key, value) in values {
            guard let codingKey = SchumannDynamicCodingKey(stringValue: key) else { continue }
            try dynamic.encode(value, forKey: codingKey)
        }
    }

    func value(_ key: String) -> Double? {
        values[key]
    }
}

private struct TomskSparkPoint: Identifiable {
    let id: String
    let ts: String
    let date: Date
    let values: [String: Double]
    let usable: Bool

    func value(_ key: String) -> Double? {
        values[key]
    }
}

private struct SchumannSeriesSample: Identifiable {
    let id: String
    let ts: String
    let date: Date
    let srTotal: Double?
    let band7_9: Double?
    let band13_15: Double?
    let band18_20: Double?
    let f0: Double?
    let usable: Bool
    let qualityScore: Double?
}

private struct SchumannGaugeLevel {
    let state: String
    let color: Color
}

private enum SchumannTuning {
    static let calmUpper = 0.03
    static let stableUpper = 0.06
    static let activeUpper = 0.10
    static let elevatedUpper = 0.16

    static func level(for amplitude: Double?) -> SchumannGaugeLevel {
        let value = amplitude ?? 0
        switch value {
        case ..<calmUpper:
            return SchumannGaugeLevel(state: "Calm", color: Color(red: 0.44, green: 0.81, blue: 0.90))
        case calmUpper..<stableUpper:
            return SchumannGaugeLevel(state: "Stable", color: Color(red: 0.49, green: 0.88, blue: 0.84))
        case stableUpper..<activeUpper:
            return SchumannGaugeLevel(state: "Active", color: Color(red: 0.90, green: 0.88, blue: 0.52))
        case activeUpper..<elevatedUpper:
            return SchumannGaugeLevel(state: "Elevated", color: Color(red: 0.97, green: 0.72, blue: 0.50))
        default:
            return SchumannGaugeLevel(state: "Intense", color: Color(red: 0.95, green: 0.58, blue: 0.58))
        }
    }

    static func gaugeIndex(for amplitude: Double?) -> Double {
        guard let amplitude else { return 0 }
        return min(100, max(0, amplitude * 1000))
    }

    static func qualityText(for quality: SchumannQuality?) -> String {
        let usable = quality?.usable ?? true
        let score = quality?.qualityScore ?? 1
        return (!usable || score < 0.5) ? "Low confidence" : "OK"
    }

    static func qualityColor(for quality: SchumannQuality?) -> Color {
        let usable = quality?.usable ?? true
        let score = quality?.qualityScore ?? 1
        return (!usable || score < 0.5) ? Color.orange : Color.green
    }
}

private actor SchumannEndpointCache {
    static let shared = SchumannEndpointCache()

    private struct Entry {
        let expiresAt: Date
        let data: Data
    }

    private var storage: [String: Entry] = [:]

    func readValid<T: Decodable>(_ key: String, as type: T.Type) -> T? {
        guard let entry = storage[key], entry.expiresAt > Date() else {
            return nil
        }
        return try? JSONDecoder().decode(type, from: entry.data)
    }

    func readAny<T: Decodable>(_ key: String, as type: T.Type) -> T? {
        guard let entry = storage[key] else {
            return nil
        }
        return try? JSONDecoder().decode(type, from: entry.data)
    }

    func write<T: Encodable>(_ value: T, key: String, ttl: TimeInterval) {
        guard let data = try? JSONEncoder().encode(value) else {
            return
        }
        storage[key] = Entry(expiresAt: Date().addingTimeInterval(ttl), data: data)
    }
}

@MainActor
private final class SchumannDashboardViewModel: ObservableObject {
    @Published var highContrast: Bool = false

    @Published var latest: SchumannLatestResponse?
    @Published var seriesRows: [SchumannSeriesRow] = []
    @Published var heatmap: SchumannHeatmapResponse?
    @Published var tomskLatest: TomskParamsLatestResponse?
    @Published var tomskSeries: [TomskParamsSeriesPoint] = []
    @Published var isTomskLatestLoading: Bool = false
    @Published var isTomskSeriesLoading: Bool = false
    @Published var isSeriesLoading: Bool = false
    @Published var isHeatmapLoading: Bool = false
    @Published var tomskErrorMessage: String?

    @Published var isLoading: Bool = false
    @Published var errorMessage: String?

    private var didInitialLoad = false
    private let cache = SchumannEndpointCache.shared

    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    func loadIfNeeded(using state: AppState) async {
        guard !didInitialLoad else { return }
        didInitialLoad = true
        await refresh(using: state, force: false)
    }

    func refresh(using state: AppState, force: Bool) async {
        if latest == nil {
            isLoading = true
        }
        errorMessage = nil

        let api = state.apiWithAuth()

        async let latestResult: Result<SchumannLatestResponse, Error> = run {
            try await self.fetchLatest(api: api, force: force)
        }
        let resolvedLatest = await latestResult

        var errorParts: [String] = []

        switch resolvedLatest {
        case .success(let response):
            latest = response
        case .failure(let err):
            errorParts.append("latest: \(err.localizedDescription)")
        }

        if !errorParts.isEmpty && latest == nil {
            errorMessage = "Unable to load Schumann data (\(errorParts.joined(separator: " | ")))."
        }

        isLoading = false
    }

    var samplesAscending: [SchumannSeriesSample] {
        let mapped = seriesRows.compactMap { row -> SchumannSeriesSample? in
            guard let ts = row.ts, let date = parseDate(ts) else {
                return nil
            }
            let quality = row.quality
            return SchumannSeriesSample(
                id: ts,
                ts: ts,
                date: date,
                srTotal: row.amplitude?.srTotal0_20,
                band7_9: row.amplitude?.band7_9,
                band13_15: row.amplitude?.band13_15,
                band18_20: row.amplitude?.band18_20,
                f0: row.harmonics?.f0,
                usable: quality?.usable != false,
                qualityScore: quality?.qualityScore
            )
        }
        return mapped.sorted { $0.date < $1.date }
    }

    var latestAmplitude: Double? {
        if let value = latest?.amplitude?.srTotal0_20 {
            return value
        }
        return samplesAscending.last?.srTotal
    }

    var latestQuality: SchumannQuality? {
        if let quality = latest?.quality {
            return quality
        }
        guard let tail = samplesAscending.last else {
            return nil
        }
        return SchumannQuality(primarySource: "cumiana", usable: tail.usable, qualityScore: tail.qualityScore)
    }

    var latestTimestamp: String? {
        if let generated = latest?.generatedAt {
            return generated
        }
        return samplesAscending.last?.ts
    }

    var tomskSamplesAscending: [TomskSparkPoint] {
        let mapped = tomskSeries.compactMap { point -> TomskSparkPoint? in
            guard let ts = point.ts, let date = parseDate(ts) else {
                return nil
            }
            let isUsable = (point.usable != false) && !(point.qualityFlags?.contains("low_quality") ?? false)
            return TomskSparkPoint(
                id: ts,
                ts: ts,
                date: date,
                values: point.values,
                usable: isUsable
            )
        }
        return mapped.sorted { $0.date < $1.date }
    }

    private func normalizeTomskMap(_ raw: [String: Double]?) -> [String: Double] {
        var normalized: [String: Double] = [:]
        for (key, value) in raw ?? [:] {
            normalized[key.uppercased()] = value
        }
        return normalized
    }

    private func normalizeTomskTrendMap(_ raw: [String: TomskTrendDelta]?) -> [String: TomskTrendDelta] {
        var normalized: [String: TomskTrendDelta] = [:]
        for (key, value) in raw ?? [:] {
            normalized[key.uppercased()] = value
        }
        return normalized
    }

    private var latestTomskSeriesPoint: TomskParamsSeriesPoint? {
        tomskSeries
            .compactMap { point -> (TomskParamsSeriesPoint, Date)? in
                guard let ts = point.ts, let date = parseDate(ts) else { return nil }
                return (point, date)
            }
            .sorted { $0.1 < $1.1 }
            .last?
            .0
    }

    private func latestSeriesValues(prefix: String) -> [String: Double] {
        guard let point = latestTomskSeriesPoint else { return [:] }
        var filtered: [String: Double] = [:]
        for (key, value) in point.values {
            let normalizedKey = key.uppercased()
            if normalizedKey.hasPrefix(prefix) {
                filtered[normalizedKey] = value
            }
        }
        return filtered
    }

    private func derivedTomskTrend2hFromSeries() -> [String: TomskTrendDelta] {
        let sortedPoints = tomskSeries
            .compactMap { point -> (TomskParamsSeriesPoint, Date)? in
                guard let ts = point.ts, let date = parseDate(ts) else { return nil }
                return (point, date)
            }
            .sorted { $0.1 < $1.1 }
            .map(\.0)

        let window = Array(sortedPoints.suffix(8))
        guard window.count >= 2 else { return [:] }

        var trendMap: [String: TomskTrendDelta] = [:]
        let keys = ["F1", "F2", "F3", "F4", "A1", "A2", "A3", "A4", "Q1", "Q2", "Q3", "Q4"]

        for key in keys {
            let values = window.compactMap { point -> Double? in
                point.values[key] ?? point.values[key.lowercased()] ?? point.values[key.uppercased()]
            }
            guard values.count >= 2 else { continue }
            let delta = values[values.count - 1] - values[0]
            let dir: String
            if abs(delta) < 0.000_000_1 {
                dir = "flat"
            } else {
                dir = delta > 0 ? "up" : "down"
            }
            trendMap[key] = TomskTrendDelta(delta: delta, dir: dir)
        }

        return trendMap
    }

    var fusionEnabled: Bool {
        latest?.fusion?.enabled ?? true
    }

    var displayedFundamentalHz: Double? {
        if let fused = latest?.fusion?.displayF0Hz {
            return fused
        }
        return latest?.harmonics?.f0
    }

    var displayedFundamentalSource: String {
        if let source = latest?.fusion?.displayF0Source, !source.isEmpty {
            return source
        }
        return "cumiana"
    }

    var secondaryFundamentalHz: Double? {
        if let secondary = latest?.fusion?.secondaryF0Hz {
            return secondary
        }
        return nil
    }

    var coherence: TomskCoherence? {
        latest?.fusion?.coherence ?? tomskLatest?.coherence
    }

    var tomskDisplayFrequencyHz: [String: Double] {
        let latestValues = normalizeTomskMap(tomskLatest?.frequencyHz)
        return latestValues.isEmpty ? latestSeriesValues(prefix: "F") : latestValues
    }

    var tomskDisplayAmplitude: [String: Double] {
        let latestValues = normalizeTomskMap(tomskLatest?.amplitude)
        return latestValues.isEmpty ? latestSeriesValues(prefix: "A") : latestValues
    }

    var tomskDisplayQFactor: [String: Double] {
        let latestValues = normalizeTomskMap(tomskLatest?.qFactor)
        return latestValues.isEmpty ? latestSeriesValues(prefix: "Q") : latestValues
    }

    var tomskDisplayTrend2h: [String: TomskTrendDelta] {
        let latestTrends = normalizeTomskTrendMap(tomskLatest?.trend2h)
        return latestTrends.isEmpty ? derivedTomskTrend2hFromSeries() : latestTrends
    }

    var tomskDisplayQualityScore: Double? {
        tomskLatest?.qualityScore ?? latestTomskSeriesPoint?.qualityScore
    }

    var tomskDisplayUpdatedTimestamp: String? {
        tomskLatest?.generatedAt ?? latestTomskSeriesPoint?.ts
    }

    var tomskDisplayUsable: Bool {
        if latest?.fusion?.tomskUsable == true {
            return true
        }
        if tomskLatest?.usableForFusion == true || tomskLatest?.usable == true {
            return true
        }
        if let point = latestTomskSeriesPoint,
           point.usable == true,
           !(point.qualityFlags?.contains("low_quality") ?? false) {
            if let score = point.qualityScore {
                return score >= 0.55
            }
            return true
        }
        return false
    }

    var hasTomskDisplayData: Bool {
        !tomskDisplayFrequencyHz.isEmpty || !tomskDisplayAmplitude.isEmpty || !tomskDisplayQFactor.isEmpty
    }

    var tomskStatusText: String {
        if tomskDisplayUsable {
            return "Tomsk: OK"
        }
        return "Tomsk: unavailable"
    }

    var tomskUpdatedTimestamp: String? {
        tomskDisplayUpdatedTimestamp
    }

    private func isIncompleteTomskLatest(_ response: TomskParamsLatestResponse) -> Bool {
        let hasAmplitude = !(response.amplitude ?? [:]).isEmpty
        let hasFrequency = !(response.frequencyHz ?? [:]).isEmpty
        let hasQFactor = !(response.qFactor ?? [:]).isEmpty
        let hasStatus = response.usable != nil || response.usableForFusion != nil || response.qualityScore != nil
        let hasTimestamp = !(response.generatedAt ?? "").isEmpty

        if hasAmplitude && (!hasFrequency || !hasQFactor || !hasStatus || !hasTimestamp) {
            return true
        }

        return false
    }

    private func parseDate(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        return Self.isoFractional.date(from: iso) ?? Self.isoPlain.date(from: iso)
    }

    private func run<T>(_ block: @escaping () async throws -> T) async -> Result<T, Error> {
        do {
            return .success(try await block())
        } catch {
            return .failure(error)
        }
    }

    private func fetchLatest(api: APIClient, force: Bool) async throws -> SchumannLatestResponse {
        try await fetchCached(
            key: "sch_latest",
            ttl: 60,
            force: force,
            type: SchumannLatestResponse.self
        ) {
            try await api.getJSON(
                "v1/earth/schumann/latest",
                as: SchumannLatestResponse.self,
                retries: 2,
                perRequestTimeout: 20
            )
        }
    }

    private func fetchSeries(api: APIClient, force: Bool) async throws -> SchumannSeriesResponse {
        try await fetchCached(
            key: "sch_series_48h",
            ttl: 300,
            force: force,
            type: SchumannSeriesResponse.self
        ) {
            try await api.getJSON(
                "v1/earth/schumann/series_primary?limit=192",
                as: SchumannSeriesResponse.self,
                retries: 2,
                perRequestTimeout: 20
            )
        }
    }

    private func fetchHeatmap(api: APIClient, force: Bool) async throws -> SchumannHeatmapResponse {
        try await fetchCached(
            key: "sch_heatmap_48h",
            ttl: 300,
            force: force,
            type: SchumannHeatmapResponse.self
        ) {
            try await api.getJSON(
                "v1/earth/schumann/heatmap_48h",
                as: SchumannHeatmapResponse.self,
                retries: 2,
                perRequestTimeout: 20
            )
        }
    }

    private func fetchTomskLatest(api: APIClient, force: Bool) async throws -> TomskParamsLatestResponse {
        try await fetchCached(
            key: "sch_tomsk_latest",
            ttl: 60,
            force: force,
            type: TomskParamsLatestResponse.self
        ) {
            try await api.getJSON(
                "v1/earth/schumann/tomsk_params/latest?station_id=tomsk",
                as: TomskParamsLatestResponse.self,
                retries: 2,
                perRequestTimeout: 20
            )
        }
    }

    private func fetchTomskLatestFresh(api: APIClient) async throws -> TomskParamsLatestResponse {
        let response = try await api.getJSON(
            "v1/earth/schumann/tomsk_params/latest?station_id=tomsk",
            as: TomskParamsLatestResponse.self,
            retries: 2,
            perRequestTimeout: 20
        )
        await cache.write(response, key: "sch_tomsk_latest", ttl: 60)
        return response
    }

    func loadTomskLatestIfNeeded(using state: AppState, force: Bool = false) async {
        if !force, tomskLatest != nil {
            return
        }
        isTomskLatestLoading = true
        tomskErrorMessage = nil

        defer {
            isTomskLatestLoading = false
        }

        do {
            let api = state.apiWithAuth()
            var response = try await fetchTomskLatest(api: api, force: force)
            if !force, isIncompleteTomskLatest(response) {
                response = try await fetchTomskLatestFresh(api: api)
            }
            tomskLatest = response
        } catch {
            tomskErrorMessage = "Tomsk detail is temporarily unavailable."
        }
    }

    func loadTomskSeriesIfNeeded(using state: AppState, force: Bool = false) async {
        if !force, !tomskSeries.isEmpty {
            return
        }
        isTomskSeriesLoading = true
        tomskErrorMessage = nil

        defer {
            isTomskSeriesLoading = false
        }

        do {
            let api = state.apiWithAuth()
            let response: TomskParamsSeriesResponse = try await fetchCached(
                key: "sch_tomsk_series_48h",
                ttl: 300,
                force: force,
                type: TomskParamsSeriesResponse.self
            ) {
                try await api.getJSON(
                    "v1/earth/schumann/tomsk_params/series?hours=48&station_id=tomsk",
                    as: TomskParamsSeriesResponse.self,
                    retries: 2,
                    perRequestTimeout: 20
                )
            }
            tomskSeries = response.points ?? []
        } catch {
            tomskErrorMessage = "Tomsk 48h detail could not be loaded."
        }
    }

    func refreshVisibleContent(
        using state: AppState,
        includeTomsk: Bool,
        includeTomskSeries: Bool,
        includeBands: Bool,
        includeHeatmap: Bool,
        includePulse: Bool
    ) async {
        await refresh(using: state, force: true)
        if includeTomsk {
            await loadTomskLatestIfNeeded(using: state, force: true)
        }
        if includeTomskSeries {
            await loadTomskSeriesIfNeeded(using: state, force: true)
        }
        if includeBands || includePulse {
            await loadSeriesIfNeeded(using: state, force: true)
        }
        if includeHeatmap {
            await loadHeatmapIfNeeded(using: state, force: true)
        }
    }

    func loadSeriesIfNeeded(using state: AppState, force: Bool = false) async {
        if !force, !seriesRows.isEmpty {
            return
        }
        isSeriesLoading = true
        defer { isSeriesLoading = false }

        do {
            let api = state.apiWithAuth()
            let response = try await fetchSeries(api: api, force: force)
            seriesRows = response.rows ?? []
        } catch {
            errorMessage = "Trend series is temporarily unavailable."
        }
    }

    func loadHeatmapIfNeeded(using state: AppState, force: Bool = false) async {
        if !force, heatmap != nil {
            return
        }
        isHeatmapLoading = true
        defer { isHeatmapLoading = false }

        do {
            let api = state.apiWithAuth()
            let response = try await fetchHeatmap(api: api, force: force)
            heatmap = response
        } catch {
            errorMessage = "Heatmap is temporarily unavailable."
        }
    }

    private func fetchCached<T: Codable>(
        key: String,
        ttl: TimeInterval,
        force: Bool,
        type: T.Type,
        loader: @escaping () async throws -> T
    ) async throws -> T {
        if !force, let cached: T = await cache.readValid(key, as: type) {
            return cached
        }

        do {
            let fresh = try await loader()
            await cache.write(fresh, key: key, ttl: ttl)
            return fresh
        } catch {
            if let stale: T = await cache.readAny(key, as: type) {
                return stale
            }
            throw error
        }
    }
}

struct SchumannDashboardView: View {
    @ObservedObject var state: AppState
    var mode: ExperienceMode = .scientific
    var tone: ToneStyle = .balanced
    @StateObject private var viewModel = SchumannDashboardViewModel()
    @State private var showHowToRead: Bool = false
    @State private var showBandsDetails: Bool = false
    @State private var showHeatmapDetails: Bool = false
    @State private var showPulseDetails: Bool = false
    @State private var showTomskDetails: Bool = false
    @State private var shareDraft: ShareDraft?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                headerCard
                gaugeCard
                heatmapCard
                bandsCard
                tomskCard
                pulseCard
                proCard
            }
            .padding()
        }
        .background(viewModel.highContrast ? Color.black : Color(.systemGroupedBackground))
        .navigationTitle("Schumann")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task {
                        await viewModel.refreshVisibleContent(
                            using: state,
                            includeTomsk: showTomskDetails || viewModel.tomskLatest != nil,
                            includeTomskSeries: showTomskDetails || !viewModel.tomskSeries.isEmpty,
                            includeBands: showBandsDetails || !viewModel.seriesRows.isEmpty,
                            includeHeatmap: showHeatmapDetails || viewModel.heatmap != nil,
                            includePulse: showPulseDetails
                        )
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("Refresh Schumann")
            }
        }
        .sheet(item: $shareDraft) { draft in
            SharePreviewView(draft: draft)
        }
        .task {
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            await viewModel.loadIfNeeded(using: state)
        }
        .onChange(of: showTomskDetails) { _, expanded in
            guard expanded else { return }
            Task {
                await viewModel.loadTomskLatestIfNeeded(using: state, force: false)
                await viewModel.loadTomskSeriesIfNeeded(using: state, force: false)
            }
        }
        .onChange(of: showBandsDetails) { _, expanded in
            guard expanded else { return }
            Task {
                await viewModel.loadSeriesIfNeeded(using: state, force: false)
            }
        }
        .onChange(of: showHeatmapDetails) { _, expanded in
            guard expanded else { return }
            Task {
                await viewModel.loadHeatmapIfNeeded(using: state, force: false)
            }
        }
        .onChange(of: showPulseDetails) { _, expanded in
            guard expanded else { return }
            Task {
                await viewModel.loadSeriesIfNeeded(using: state, force: false)
            }
        }
    }

    private var headerCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    qualityBadge
                    Text("Last updated: \(formattedTimestamp(viewModel.latestTimestamp))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                    Spacer()
                    Text((viewModel.latestQuality?.primarySource ?? "cumiana").capitalized)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.15), in: Capsule())

                    if let draft = schumannShareDraft() {
                        Button {
                            shareDraft = draft
                        } label: {
                            Label(sharePromptLabel(for: draft.card.accentLevel), systemImage: "square.and.arrow.up")
                                .font(.caption.weight(.semibold))
                        }
                        .buttonStyle(.bordered)
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Text("F0: \(formattedFundamental(viewModel.displayedFundamentalHz))")
                            .font(.subheadline.weight(.semibold))
                        Text(viewModel.displayedFundamentalSource.capitalized)
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background((viewModel.displayedFundamentalSource == "tomsk" ? Color.cyan : Color.secondary).opacity(0.18), in: Capsule())
                    }

                    if let secondary = viewModel.secondaryFundamentalHz {
                        Text("Cumiana F0: \(String(format: "%.2f Hz", secondary))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if let coherence = viewModel.coherence,
                       let label = coherence.label,
                       viewModel.fusionEnabled,
                       viewModel.tomskLatest?.usableForFusion == true || viewModel.latest?.fusion?.tomskUsable == true {
                        Text("Coherence: Q1 \(label.capitalized)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(coherenceColor(label).opacity(0.2), in: Capsule())
                            .foregroundStyle(coherenceColor(label))
                    }
                }

                Toggle("High contrast", isOn: $viewModel.highContrast)
                    .font(.caption)
                .toggleStyle(.switch)

                DisclosureGroup("How to read this", isExpanded: $showHowToRead) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("\u{2022} Gauge: overall intensity level (0-20 Hz).")
                        Text("\u{2022} Heatmap: time x frequency; brighter = stronger.")
                        Text("\u{2022} Bands: relative strength in key ranges.")
                        Text("\u{2022} Pulse: intensity trend; dashed line = frequency.")
                    }
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.top, 4)
                }
                .font(.caption.weight(.semibold))

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            Label("Schumann Overview", systemImage: "dial.medium")
        }
    }

    private var qualityBadge: some View {
        let quality = viewModel.latestQuality
        return Text(SchumannTuning.qualityText(for: quality))
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(SchumannTuning.qualityColor(for: quality).opacity(0.2), in: Capsule())
            .foregroundStyle(SchumannTuning.qualityColor(for: quality))
    }

    private var gaugeCard: some View {
        let level = SchumannTuning.level(for: viewModel.latestAmplitude)
        let gaugeIndex = SchumannTuning.gaugeIndex(for: viewModel.latestAmplitude)
        let gaugeSummary = String(format: "%.1f \u{2014} %@", gaugeIndex, level.state)

        return GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 12) {
                    SchumannGaugeDial(value: gaugeIndex / 100, color: level.color)
                        .frame(width: 170, height: 130)
                        .accessibilityLabel("Schumann gauge")
                        .accessibilityValue("Index \(String(format: "%.1f", gaugeIndex)) State \(level.state)")

                    VStack(alignment: .leading, spacing: 6) {
                        Text(gaugeSummary)
                            .font(.system(size: 34, weight: .bold, design: .rounded))
                        Text("Activity across the 0-20 Hz range. Updates every 15 minutes.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            Label("Earth Resonance Gauge", systemImage: "gauge.with.dots.needle.67percent")
        }
    }

    private var heatmapCard: some View {
        GroupBox {
            DisclosureGroup(isExpanded: $showHeatmapDetails) {
                if showHeatmapDetails {
                    if viewModel.isHeatmapLoading && viewModel.heatmap == nil {
                        ProgressView("Loading heatmap…")
                            .font(.caption)
                            .padding(.top, 8)
                    } else {
                        SchumannHeatmapView(
                            heatmap: viewModel.heatmap,
                            samples: viewModel.samplesAscending,
                            highContrast: viewModel.highContrast
                        )
                        .padding(.top, 8)
                    }
                } else {
                    Text("Open to load the 48-hour heatmap.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
            } label: {
                Text("Load heatmap")
                    .font(.subheadline.weight(.semibold))
            }
        } label: {
            Label("48h Heatmap", systemImage: "square.grid.3x3.fill")
        }
    }

    private var bandsCard: some View {
        GroupBox {
            DisclosureGroup(isExpanded: $showBandsDetails) {
                if showBandsDetails {
                    if viewModel.isSeriesLoading && viewModel.seriesRows.isEmpty {
                        ProgressView("Loading band trends…")
                            .font(.caption)
                            .padding(.top, 8)
                    } else {
                        SchumannBandBarsView(
                            samples: viewModel.samplesAscending
                        )
                        .padding(.top, 8)
                    }
                } else {
                    Text("Tap to load harmonic band trends.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
            } label: {
                Text("Load band trends")
                    .font(.subheadline.weight(.semibold))
            }
        } label: {
            Label("Harmonic Bands", systemImage: "chart.bar.fill")
        }
    }

    private var pulseCard: some View {
        GroupBox {
            DisclosureGroup(isExpanded: $showPulseDetails) {
                if showPulseDetails {
                    if viewModel.isSeriesLoading && viewModel.seriesRows.isEmpty {
                        ProgressView("Loading pulse line…")
                            .font(.caption)
                            .padding(.top, 8)
                    } else {
                        SchumannPulseChartView(
                            samples: viewModel.samplesAscending
                        )
                        .padding(.top, 8)
                    }
                } else {
                    Text("Tap to load the 48h pulse line.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
            } label: {
                Text("Load pulse line")
                    .font(.subheadline.weight(.semibold))
            }
        } label: {
            Label("48h Pulse Line", systemImage: "waveform.path.ecg")
        }
    }

    private var tomskCard: some View {
        GroupBox {
            DisclosureGroup(isExpanded: $showTomskDetails) {
                if showTomskDetails {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 10) {
                            Text("Usable: \(viewModel.tomskDisplayUsable ? "Yes" : "No")")
                                .font(.caption)
                            Text("Quality: \(viewModel.tomskDisplayQualityScore.map { String(format: "%.2f", $0) } ?? "-")")
                                .font(.caption)
                            Spacer()
                            Text("Updated: \(formattedTimestamp(viewModel.tomskDisplayUpdatedTimestamp))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        if viewModel.isTomskLatestLoading || viewModel.isTomskSeriesLoading {
                            ProgressView(viewModel.tomskLatest == nil ? "Loading Tomsk detail…" : "Loading Tomsk 48h series…")
                                .font(.caption)
                        }

                        if viewModel.hasTomskDisplayData {
                            TomskMetricSectionView(
                                title: "Frequencies",
                                legend: "F = frequency tracking",
                                keys: ["F1", "F2", "F3", "F4"],
                                unit: "Hz",
                                values: viewModel.tomskDisplayFrequencyHz,
                                trends: viewModel.tomskDisplayTrend2h
                            )
                            TomskMetricSectionView(
                                title: "Amplitudes",
                                legend: "A = amplitude tracking",
                                keys: ["A1", "A2", "A3", "A4"],
                                unit: nil,
                                values: viewModel.tomskDisplayAmplitude,
                                trends: viewModel.tomskDisplayTrend2h
                            )
                            TomskMetricSectionView(
                                title: "Q Factors",
                                legend: "Q = resonance quality proxy",
                                keys: ["Q1", "Q2", "Q3", "Q4"],
                                unit: nil,
                                values: viewModel.tomskDisplayQFactor,
                                trends: viewModel.tomskDisplayTrend2h
                            )
                        } else if !viewModel.isTomskLatestLoading {
                            Text("Tomsk detail is currently unavailable.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        if !viewModel.tomskSamplesAscending.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("48h Mini Sparklines")
                                    .font(.caption.weight(.semibold))
                                TomskSparklineView(title: "F1", unit: "Hz", key: "F1", color: .cyan, points: viewModel.tomskSamplesAscending)
                                TomskSparklineView(title: "A1", unit: nil, key: "A1", color: .yellow, points: viewModel.tomskSamplesAscending)
                                TomskSparklineView(title: "Q1", unit: nil, key: "Q1", color: .green, points: viewModel.tomskSamplesAscending)
                            }
                        }

                        if let tomskError = viewModel.tomskErrorMessage {
                            Text(tomskError)
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    }
                    .padding(.top, 8)
                }
            } label: {
                HStack {
                    Text("Tomsk Details (F/A/Q)")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(viewModel.tomskStatusText)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background((viewModel.tomskDisplayUsable ? Color.green : Color.secondary).opacity(0.18), in: Capsule())
                    Text(formattedTimestamp(viewModel.tomskUpdatedTimestamp))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        } label: {
            Label("Tomsk Detail", systemImage: "point.3.connected.trianglepath.dotted")
        }
    }

    private var proCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Text("Free window: 48h (15-minute cadence)")
                    .font(.subheadline)
                Text("Pro: 30d history")
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.secondary.opacity(0.15), in: Capsule())
                Text("Feature flag hook is in place; premium history is intentionally not enabled yet.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            Label("History Access", systemImage: "lock.fill")
        }
    }

    private func formattedTimestamp(_ iso: String?) -> String {
        guard let iso else { return "-" }
        let fmtFrac = ISO8601DateFormatter()
        fmtFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fmtPlain = ISO8601DateFormatter()
        fmtPlain.formatOptions = [.withInternetDateTime]

        guard let date = fmtFrac.date(from: iso) ?? fmtPlain.date(from: iso) else {
            return iso
        }
        let out = DateFormatter()
        out.dateStyle = .medium
        out.timeStyle = .short
        return out.string(from: date)
    }

    private func formattedFundamental(_ value: Double?) -> String {
        guard let value else { return "-" }
        return String(format: "%.2f Hz", value)
    }

    private func coherenceColor(_ label: String) -> Color {
        switch label.lowercased() {
        case "high":
            return .green
        case "medium":
            return .yellow
        default:
            return .orange
        }
    }

    private func sharePromptLabel(for accent: ShareAccentLevel) -> String {
        _ = accent
        return "Share"
    }

    private func schumannShareDraft() -> ShareDraft? {
        let vocabulary = mode.copyVocabulary
        let amplitude = viewModel.latestAmplitude
        let level = SchumannTuning.level(for: amplitude)
        let accent: ShareAccentLevel
        switch level.state.lowercased() {
        case "strong", "storm":
            accent = .storm
        case "elevated":
            accent = .elevated
        case "watch", "active":
            accent = .watch
        default:
            accent = .calm
        }

        let title = vocabulary.schumannLabel
        let interpretation = tone.resolveCopy(
            straight: "Earth resonance activity is \(level.state.lowercased()) right now.",
            balanced: "Earth resonance activity may feel a little different right now.",
            humorous: "The background hum is doing a bit more than whispering."
        )
        var bullets: [String] = []
        let qualityText = SchumannTuning.qualityText(for: viewModel.latestQuality)
        if !qualityText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            bullets.append("Quality: \(qualityText)")
        }
        if let coherence = viewModel.coherence?.label, !coherence.isEmpty {
            bullets.append("Coherence: \(coherence.capitalized)")
        }
        if let secondary = viewModel.secondaryFundamentalHz {
            bullets.append("Cumiana F0: \(String(format: "%.2f Hz", secondary))")
        }
        if bullets.isEmpty {
            bullets = [
                "15-minute cadence",
                "48-hour heatmap available",
            ]
        }

        let background = ShareCardBackground(
            style: .schumann,
            candidateURLs: [
                MediaPaths.sanitize("social/earthscope/latest/tomsk_latest.png"),
                MediaPaths.sanitize("social/earthscope/latest/cumiana_latest.png"),
            ].compactMap { $0 }
        )

        return ShareDraftFactory.signalSnapshot(
            surface: "schumann_dashboard",
            analyticsKey: "schumann",
            mode: mode,
            tone: tone,
            title: title,
            value: formattedFundamental(viewModel.displayedFundamentalHz),
            state: level.state,
            interpretation: interpretation,
            bullets: bullets,
            accent: accent,
            background: background,
            sourceLine: "Source: \((viewModel.latestQuality?.primarySource ?? "cumiana").capitalized)",
            updatedAt: formattedTimestamp(viewModel.latestTimestamp),
            promptText: sharePromptLabel(for: accent)
        )
    }
}

private struct SchumannGaugeDial: View {
    let value: Double
    let color: Color

    var body: some View {
        Canvas { context, size in
            let clamped = min(1, max(0, value))
            let center = CGPoint(x: size.width / 2, y: size.height * 0.9)
            let radius = min(size.width * 0.38, size.height * 0.7)
            let start = Angle.degrees(200)
            let end = Angle.degrees(-20)

            var track = Path()
            track.addArc(center: center, radius: radius, startAngle: start, endAngle: end, clockwise: false)
            context.stroke(track, with: .color(Color.white.opacity(0.2)), style: StrokeStyle(lineWidth: 13, lineCap: .round))

            let fillEnd = Angle.degrees(200 + (140 * clamped))
            var fill = Path()
            fill.addArc(center: center, radius: radius, startAngle: start, endAngle: fillEnd, clockwise: false)
            context.stroke(fill, with: .color(color), style: StrokeStyle(lineWidth: 13, lineCap: .round))
        }
    }
}

private struct SchumannBandBarsView: View {
    let samples: [SchumannSeriesSample]

    private struct BandItem: Identifiable {
        let id = UUID()
        let label: String
        let latest: Double?
        let baseline: Double?
        let min48h: Double?
        let max48h: Double?
    }

    var body: some View {
        let latest = samples.last
        let previousWindow = Array(samples.dropLast().suffix(8))
        let minMax7_9 = robustRange(usableValues(\.band7_9), fallback: allValues(\.band7_9))
        let minMax13_15 = robustRange(usableValues(\.band13_15), fallback: allValues(\.band13_15))
        let minMax18_20 = robustRange(usableValues(\.band18_20), fallback: allValues(\.band18_20))

        let items: [BandItem] = [
            BandItem(
                label: "7-9 Hz \u{2022} Ground",
                latest: latest?.band7_9,
                baseline: average(previousWindow.map(\.band7_9)),
                min48h: minMax7_9?.min,
                max48h: minMax7_9?.max
            ),
            BandItem(
                label: "13-15 Hz \u{2022} Flow",
                latest: latest?.band13_15,
                baseline: average(previousWindow.map(\.band13_15)),
                min48h: minMax13_15?.min,
                max48h: minMax13_15?.max
            ),
            BandItem(
                label: "18-20 Hz \u{2022} Spark",
                latest: latest?.band18_20,
                baseline: average(previousWindow.map(\.band18_20)),
                min48h: minMax18_20?.min,
                max48h: minMax18_20?.max
            )
        ]

        VStack(alignment: .leading, spacing: 10) {
            if latest == nil {
                Text("No band data yet.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                ForEach(items) { item in
                    HStack(spacing: 10) {
                        Text(item.label)
                            .font(.caption)
                            .frame(width: 126, alignment: .leading)

                        ProgressView(value: normalized(latest: item.latest, min: item.min48h, max: item.max48h), total: 1)
                            .tint(Color.cyan)

                        Text(trendText(latest: item.latest, baseline: item.baseline))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(trendColor(latest: item.latest, baseline: item.baseline))
                            .frame(width: 64, alignment: .trailing)
                    }
                }
                Text("Relative strength vs the last 48 hours. Trend compares with the previous 2 hours.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func average(_ values: [Double?]) -> Double? {
        let numeric = values.compactMap { $0 }
        guard !numeric.isEmpty else { return nil }
        return numeric.reduce(0, +) / Double(numeric.count)
    }

    private func usableValues(_ keyPath: KeyPath<SchumannSeriesSample, Double?>) -> [Double] {
        samples.filter(\.usable).compactMap { $0[keyPath: keyPath] }
    }

    private func allValues(_ keyPath: KeyPath<SchumannSeriesSample, Double?>) -> [Double] {
        samples.compactMap { $0[keyPath: keyPath] }
    }

    private func robustRange(_ preferred: [Double], fallback: [Double]) -> (min: Double, max: Double)? {
        let base = preferred.count >= 8 ? preferred : fallback
        guard !base.isEmpty else { return nil }

        let sorted = base.sorted()
        if sorted.count < 8 {
            return (sorted[0], sorted[sorted.count - 1])
        }

        let low = percentile(sorted, p: 0.05)
        let high = percentile(sorted, p: 0.95)
        if high > low {
            return (low, high)
        }

        return (sorted[0], sorted[sorted.count - 1])
    }

    private func percentile(_ sorted: [Double], p: Double) -> Double {
        guard !sorted.isEmpty else { return 0 }
        let idx = Int((Double(sorted.count - 1) * p).rounded())
        return sorted[max(0, min(sorted.count - 1, idx))]
    }

    private func normalized(latest: Double?, min: Double?, max: Double?) -> Double {
        guard let latest else {
            return 0
        }

        let minimumVisible = latest > 0 ? 0.04 : 0
        guard let min, let max, max > min else {
            return minimumVisible
        }

        let raw = Swift.min(1, Swift.max(0, (latest - min) / (max - min)))
        return Swift.max(raw, minimumVisible)
    }

    private func trendText(latest: Double?, baseline: Double?) -> String {
        guard let latest, let baseline else {
            return "-"
        }
        let delta = latest - baseline
        let symbol: String
        if delta > 0.008 {
            symbol = "\u{2191}"
        } else if delta < -0.008 {
            symbol = "\u{2193}"
        } else {
            symbol = "\u{2192}"
        }
        return "\(symbol) \(String(format: "%.1f%%", latest * 100))"
    }

    private func trendColor(latest: Double?, baseline: Double?) -> Color {
        guard let latest, let baseline else { return .secondary }
        let delta = latest - baseline
        if delta > 0.008 { return .green }
        if delta < -0.008 { return .orange }
        return .secondary
    }
}

private struct SchumannPulseChartView: View {
    let samples: [SchumannSeriesSample]

    private var srUpperBound: Double {
        let maxValue = samples.compactMap(\.srTotal).max() ?? 0.12
        return max(0.16, maxValue * 1.2)
    }

    private var f0Range: ClosedRange<Double> {
        let values = samples.compactMap(\.f0)
        let minVal = values.min() ?? 7.4
        let maxVal = values.max() ?? 8.2
        let adjustedMax = maxVal <= minVal ? (minVal + 0.2) : maxVal
        return minVal...adjustedMax
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if samples.isEmpty {
                Text("Pulse series unavailable.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                Chart {
                    ForEach(samples) { sample in
                        if let sr = sample.srTotal {
                            LineMark(
                                x: .value("Time", sample.date),
                                y: .value("Pulse", sr),
                                series: .value("Series", "Pulse")
                            )
                            .foregroundStyle(Color.cyan)
                            .lineStyle(StrokeStyle(lineWidth: 2))
                            .opacity(sample.usable ? 1 : 0.3)
                        }
                    }

                    ForEach(samples.filter { !$0.usable }) { sample in
                        if let sr = sample.srTotal {
                            PointMark(
                                x: .value("Time", sample.date),
                                y: .value("Pulse", sr)
                            )
                            .symbolSize(24)
                            .foregroundStyle(.orange)
                        }
                    }

                    ForEach(samples) { sample in
                        if let f0 = sample.f0 {
                            LineMark(
                                x: .value("Time", sample.date),
                                y: .value("F0Scaled", mapF0ToPulseScale(f0)),
                                series: .value("Series", "f0")
                            )
                            .foregroundStyle(Color.yellow)
                            .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [5, 4]))
                        }
                    }

                }
                .chartYScale(domain: 0...srUpperBound)
                .frame(height: 230)
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 4))
                }
                .chartYAxis {
                    AxisMarks(position: .leading)
                    let ticks = trailingF0TickValues()
                    AxisMarks(position: .trailing, values: ticks) { value in
                        if let scaled = value.as(Double.self) {
                            AxisValueLabel(String(format: "%.2f Hz", mapPulseScaleToF0(scaled)))
                        }
                    }
                }
                HStack(spacing: 12) {
                    Text("Cyan: Intensity (0-20 Hz)")
                        .font(.caption2)
                        .foregroundColor(.cyan)
                    Text("Yellow dashed: Fundamental (Hz)")
                        .font(.caption2)
                        .foregroundColor(.yellow)
                }

                if let latest = samples.last {
                    HStack(spacing: 10) {
                        Text(formattedTooltipDate(latest.date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text("Pulse \(latest.srTotal.map { String(format: "%.3f", $0) } ?? "-")")
                            .font(.caption)
                        Text("f0 \(latest.f0.map { String(format: "%.2f", $0) } ?? "-") Hz")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(latest.usable ? "OK" : "Low confidence")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background((latest.usable ? Color.green : Color.orange).opacity(0.2), in: Capsule())
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func mapF0ToPulseScale(_ f0: Double) -> Double {
        let range = f0Range
        let normalized = (f0 - range.lowerBound) / max(0.0001, range.upperBound - range.lowerBound)
        return normalized * srUpperBound
    }

    private func mapPulseScaleToF0(_ pulse: Double) -> Double {
        let normalized = pulse / max(0.0001, srUpperBound)
        let range = f0Range
        return range.lowerBound + normalized * (range.upperBound - range.lowerBound)
    }

    private func trailingF0TickValues() -> [Double] {
        let range = f0Range
        let step = max(0.1, (range.upperBound - range.lowerBound) / 3)
        var ticks: [Double] = []
        var value = range.lowerBound
        while value <= range.upperBound + 0.0001 {
            ticks.append(mapF0ToPulseScale(value))
            value += step
        }
        return ticks
    }

    private func formattedTooltipDate(_ date: Date) -> String {
        let df = DateFormatter()
        df.dateStyle = .medium
        df.timeStyle = .short
        return df.string(from: date)
    }
}

private struct TomskMetricSectionView: View {
    let title: String
    let legend: String
    let keys: [String]
    let unit: String?
    let values: [String: Double]
    let trends: [String: TomskTrendDelta]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.caption.weight(.semibold))

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 8) {
                ForEach(keys, id: \.self) { key in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(key)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text(metricValue(for: key))
                            .font(.subheadline.weight(.semibold))
                        Text(trendText(for: key))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(trendColor(for: key))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                }
            }

            Text(legend)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }

    private func metricValue(for key: String) -> String {
        guard let value = values[key] ?? values[key.lowercased()] ?? values[key.uppercased()] else {
            return "-"
        }
        if let unit {
            return String(format: "%.2f %@", value, unit)
        }
        return String(format: "%.2f", value)
    }

    private func trendText(for key: String) -> String {
        let trend = trends[key] ?? trends[key.lowercased()] ?? trends[key.uppercased()]
        guard let trend, let delta = trend.delta else {
            return "→ -"
        }
        let arrow: String
        switch trend.dir?.lowercased() {
        case "up":
            arrow = "↑"
        case "down":
            arrow = "↓"
        default:
            arrow = "→"
        }
        if let unit {
            return "\(arrow) \(String(format: "%.2f %@", delta, unit))"
        }
        return "\(arrow) \(String(format: "%.2f", delta))"
    }

    private func trendColor(for key: String) -> Color {
        let trend = trends[key] ?? trends[key.lowercased()] ?? trends[key.uppercased()]
        switch trend?.dir?.lowercased() {
        case "up":
            return .green
        case "down":
            return .orange
        default:
            return .secondary
        }
    }
}

private struct TomskSparklineView: View {
    let title: String
    let unit: String?
    let key: String
    let color: Color
    let points: [TomskSparkPoint]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                    .font(.caption.weight(.semibold))
                Spacer()
                if let latestValue = plottedValues.last?.value {
                    Text(formattedValue(latestValue))
                        .font(.caption2.weight(.semibold))
                        .foregroundColor(.secondary)
                }
            }

            if plottedValues.isEmpty {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.secondary.opacity(0.08))
                    .frame(height: 72)
                    .overlay {
                        Text("No data yet")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
            } else {
                Canvas { context, size in
                    let lastIndex = max(plottedValues.count - 1, 1)
                    let range = valueRange

                    var path = Path()
                    for (index, entry) in plottedValues.enumerated() {
                        let point = CGPoint(
                            x: xPosition(for: index, width: size.width, lastIndex: lastIndex),
                            y: yPosition(for: entry.value, height: size.height, range: range)
                        )
                        if index == 0 {
                            path.move(to: point)
                        } else {
                            path.addLine(to: point)
                        }
                    }

                    context.stroke(
                        path,
                        with: .color(color),
                        style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round)
                    )

                    for entry in plottedValues where !entry.point.usable {
                        let center = CGPoint(
                            x: xPosition(for: entry.index, width: size.width, lastIndex: lastIndex),
                            y: yPosition(for: entry.value, height: size.height, range: range)
                        )
                        let dotRect = CGRect(x: center.x - 3, y: center.y - 3, width: 6, height: 6)
                        context.fill(Path(ellipseIn: dotRect), with: .color(.orange))
                    }

                    if let latest = plottedValues.last {
                        let center = CGPoint(
                            x: xPosition(for: latest.index, width: size.width, lastIndex: lastIndex),
                            y: yPosition(for: latest.value, height: size.height, range: range)
                        )
                        let dotRect = CGRect(x: center.x - 3.5, y: center.y - 3.5, width: 7, height: 7)
                        context.fill(Path(ellipseIn: dotRect), with: .color(.white))
                    }
                }
                .frame(height: 72)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.secondary.opacity(0.08))
                )
            }

            if let latest = plottedValues.last {
                Text("\(formattedDate(latest.point.date)) • \(formattedValue(latest.value)) • \(latest.point.usable ? "OK" : "Low confidence")")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            } else {
                Text("Low-confidence points are dimmed.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }

    private var plottedValues: [(index: Int, point: TomskSparkPoint, value: Double)] {
        points.enumerated().compactMap { index, point in
            guard let value = point.value(key) else {
                return nil
            }
            return (index, point, value)
        }
    }

    private var valueRange: ClosedRange<Double> {
        let values = plottedValues.map(\.value)
        guard let minValue = values.min(), let maxValue = values.max() else {
            return 0...1
        }
        if abs(maxValue - minValue) < 0.0001 {
            let padding = max(abs(maxValue) * 0.05, 0.1)
            return (minValue - padding)...(maxValue + padding)
        }
        let padding = (maxValue - minValue) * 0.08
        return (minValue - padding)...(maxValue + padding)
    }

    private func xPosition(for index: Int, width: CGFloat, lastIndex: Int) -> CGFloat {
        guard lastIndex > 0 else { return width / 2 }
        return CGFloat(index) / CGFloat(lastIndex) * width
    }

    private func yPosition(for value: Double, height: CGFloat, range: ClosedRange<Double>) -> CGFloat {
        let span = max(range.upperBound - range.lowerBound, 0.0001)
        let normalized = (value - range.lowerBound) / span
        return height - (CGFloat(normalized) * height)
    }

    private func formattedValue(_ value: Double) -> String {
        if let unit {
            return String(format: "%.2f %@", value, unit)
        }
        return String(format: "%.2f", value)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}

private struct SchumannHeatmapBitmap {
    let image: CGImage
    let minValue: Double
    let maxValue: Double
    let pointCount: Int
    let binCount: Int
}

private struct SchumannHeatmapHover {
    let ts: String
    let freqHz: Double
    let intensity: Double
    let position: CGPoint
}

private enum SchumannHeatmapRenderer {
    static func build(
        heatmap: SchumannHeatmapResponse?,
        qualityByTs: [String: Bool],
        highContrast: Bool
    ) -> SchumannHeatmapBitmap? {
        guard let heatmap,
              let points = heatmap.points,
              !points.isEmpty
        else {
            return nil
        }

        let pointCount = points.count
        let binCount = points.first?.bins.count ?? 0
        guard pointCount > 0, binCount > 0 else {
            return nil
        }

        let values = points.flatMap { $0.bins }.filter { $0.isFinite }
        guard !values.isEmpty else {
            return nil
        }

        let sorted = values.sorted()
        let minValue = percentile(sorted, p: 0.03)
        var maxValue = percentile(sorted, p: 0.97)
        if maxValue <= minValue {
            maxValue = minValue + 0.001
        }

        let palette = buildPalette(highContrast: highContrast)

        var pixels = [UInt8](repeating: 0, count: pointCount * binCount * 4)
        for x in 0..<pointCount {
            let point = points[x]
            let usable = qualityByTs[point.ts ?? ""] != false
            let alpha: UInt8 = usable ? 255 : 95
            for y in 0..<binCount {
                let sourceValue = y < point.bins.count ? point.bins[y] : minValue
                let normalized = min(1, max(0, (sourceValue - minValue) / (maxValue - minValue)))
                let paletteIndex = max(0, min(255, Int((normalized * 255).rounded())))
                let color = palette[paletteIndex]

                let drawY = (binCount - 1) - y
                let idx = (drawY * pointCount + x) * 4
                pixels[idx] = color.0
                pixels[idx + 1] = color.1
                pixels[idx + 2] = color.2
                pixels[idx + 3] = alpha
            }
        }

        let data = Data(pixels)
        guard let provider = CGDataProvider(data: data as CFData) else {
            return nil
        }

        guard let image = CGImage(
            width: pointCount,
            height: binCount,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: pointCount * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        ) else {
            return nil
        }

        return SchumannHeatmapBitmap(
            image: image,
            minValue: minValue,
            maxValue: maxValue,
            pointCount: pointCount,
            binCount: binCount
        )
    }

    private static func percentile(_ sorted: [Double], p: Double) -> Double {
        guard !sorted.isEmpty else { return 0 }
        let idx = Int((Double(sorted.count - 1) * p).rounded())
        return sorted[max(0, min(sorted.count - 1, idx))]
    }

    private static func buildPalette(highContrast: Bool) -> [(UInt8, UInt8, UInt8)] {
        let stops: [(Double, (Double, Double, Double))]
        if highContrast {
            stops = [
                (0.0, (0, 0, 0)),
                (0.25, (10, 95, 140)),
                (0.55, (90, 210, 220)),
                (0.8, (255, 220, 125)),
                (1.0, (255, 120, 95)),
            ]
        } else {
            stops = [
                (0.0, (6, 18, 28)),
                (0.3, (14, 98, 129)),
                (0.6, (116, 208, 188)),
                (1.0, (248, 188, 101)),
            ]
        }

        func interpolate(_ t: Double) -> (UInt8, UInt8, UInt8) {
            var lower = stops.first!
            var upper = stops.last!

            if stops.count > 1 {
                for i in 0..<(stops.count - 1) {
                    let left = stops[i]
                    let right = stops[i + 1]
                    if t >= left.0 && t <= right.0 {
                        lower = left
                        upper = right
                        break
                    }
                }
            }

            let span = max(0.0001, upper.0 - lower.0)
            let localT = (t - lower.0) / span
            let r = lower.1.0 + (upper.1.0 - lower.1.0) * localT
            let g = lower.1.1 + (upper.1.1 - lower.1.1) * localT
            let b = lower.1.2 + (upper.1.2 - lower.1.2) * localT
            return (UInt8(max(0, min(255, Int(r.rounded())))),
                    UInt8(max(0, min(255, Int(g.rounded())))),
                    UInt8(max(0, min(255, Int(b.rounded())))))
        }

        return (0...255).map { idx in
            interpolate(Double(idx) / 255)
        }
    }
}

private struct SchumannHeatmapView: View {
    let heatmap: SchumannHeatmapResponse?
    let samples: [SchumannSeriesSample]
    let highContrast: Bool

    @State private var bitmap: SchumannHeatmapBitmap?

    #if canImport(UIKit)
    @State private var sharePayload: SchumannShareImagePayload?
    #endif

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let bitmap {
                    Text("Intensity range: \(String(format: "%.3f", bitmap.minValue)) - \(String(format: "%.3f", bitmap.maxValue))")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                } else {
                    Text("Heatmap unavailable")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }

                Spacer()

                #if canImport(UIKit)
                Button {
                    guard let bitmap else { return }
                    sharePayload = SchumannShareImagePayload(image: UIImage(cgImage: bitmap.image))
                } label: {
                    Label("Export PNG", systemImage: "square.and.arrow.up")
                        .font(.caption)
                }
                .buttonStyle(.bordered)
                .disabled(bitmap == nil)
                #endif
            }

            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    if let bitmap {
                        Image(decorative: bitmap.image, scale: 1)
                            .resizable()
                            .interpolation(.none)
                            .frame(width: geo.size.width, height: geo.size.height)
                            .clipped()
                    } else {
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.secondary.opacity(0.12))
                            .overlay {
                                Text("No heatmap points")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                    }

                    if let bitmap {
                        harmonicOverlay(size: geo.size, axis: heatmap?.axis, bins: bitmap.binCount)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .frame(height: 220)

            let axisText = axisSummary()
            HStack {
                Text(axisText.start)
                Spacer()
                Text(axisText.middle)
                Spacer()
                Text(axisText.end)
            }
            .font(.caption2)
            .foregroundColor(.secondary)

            Text("Heatmap = time x frequency. Brighter colors = stronger signal.")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            rebuildBitmap()
        }
        .onChange(of: rebuildToken()) { _, _ in
            rebuildBitmap()
        }
        #if canImport(UIKit)
        .sheet(item: $sharePayload) { payload in
            SchumannActivityViewController(items: [payload.image])
        }
        #endif
    }

    private func rebuildToken() -> String {
        let points = heatmap?.points?.count ?? 0
        let bins = heatmap?.points?.first?.bins.count ?? 0
        let qualityCount = samples.count
        return "\(points)-\(bins)-\(qualityCount)-\(highContrast)"
    }

    private func rebuildBitmap() {
        var qualityByTs: [String: Bool] = [:]
        for sample in samples {
            qualityByTs[sample.ts] = sample.usable
        }
        bitmap = SchumannHeatmapRenderer.build(
            heatmap: heatmap,
            qualityByTs: qualityByTs,
            highContrast: highContrast
        )
    }

    @ViewBuilder
    private func harmonicOverlay(size: CGSize, axis: SchumannAxis?, bins: Int) -> some View {
        let freqStart = axis?.freqStartHz ?? 0
        let freqStep = axis?.freqStepHz ?? (20.0 / Double(max(1, bins)))
        let guides: [Double] = [7.8, 14.1, 20.0]

        Path { path in
            for freq in guides {
                let binPos = (freq - freqStart) / max(0.0001, freqStep)
                let y = size.height - CGFloat(binPos / Double(max(1, bins - 1))) * size.height
                guard y >= 0, y <= size.height else { continue }
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            }
        }
        .stroke(Color.white.opacity(0.4), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
    }

    private func axisSummary() -> (start: String, middle: String, end: String) {
        guard let points = heatmap?.points, !points.isEmpty else {
            return ("-", "0-20 Hz", "-")
        }
        let start = formattedAxisTime(points.first?.ts)
        let end = formattedAxisTime(points.last?.ts)
        return (start, "0-20 Hz", end)
    }

    private func formattedAxisTime(_ iso: String?) -> String {
        guard let iso else { return "-" }
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        guard let date = frac.date(from: iso) ?? plain.date(from: iso) else {
            return "-"
        }
        let out = DateFormatter()
        out.timeStyle = .short
        out.dateStyle = .none
        return out.string(from: date)
    }
}

#if canImport(UIKit)
private struct SchumannShareImagePayload: Identifiable {
    let id = UUID()
    let image: UIImage
}

private struct SchumannActivityViewController: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
#endif
