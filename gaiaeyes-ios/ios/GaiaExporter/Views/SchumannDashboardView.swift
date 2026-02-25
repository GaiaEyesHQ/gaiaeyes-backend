import SwiftUI
import Charts
#if canImport(UIKit)
import UIKit
#endif

private enum SchumannDisplayMode: String, CaseIterable, Identifiable {
    case scientific
    case mystical

    var id: String { rawValue }

    var title: String {
        switch self {
        case .scientific: return "Scientific"
        case .mystical: return "Mystical"
        }
    }
}

private struct SchumannLatestResponse: Codable {
    let ok: Bool?
    let generatedAt: String?
    let harmonics: SchumannHarmonics?
    let amplitude: SchumannAmplitude?
    let quality: SchumannQuality?

    enum CodingKeys: String, CodingKey {
        case ok
        case generatedAt = "generated_at"
        case harmonics
        case amplitude
        case quality
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
        let c = try decoder.container(keyedBy: CodingKeys.self)
        srTotal0_20 = Self.decodeNumber(c, forKey: .srTotal0_20)
        band7_9 = Self.decodeNumber(c, forKey: .band7_9)
        band13_15 = Self.decodeNumber(c, forKey: .band13_15)
        band18_20 = Self.decodeNumber(c, forKey: .band18_20)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(srTotal0_20, forKey: .srTotal0_20)
        try c.encodeIfPresent(band7_9, forKey: .band7_9)
        try c.encodeIfPresent(band13_15, forKey: .band13_15)
        try c.encodeIfPresent(band18_20, forKey: .band18_20)
    }

    private static func decodeNumber(_ c: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Double? {
        if let v = try? c.decodeIfPresent(Double.self, forKey: key) { return v }
        if let i = try? c.decodeIfPresent(Int.self, forKey: key) { return Double(i) }
        if let s = try? c.decodeIfPresent(String.self, forKey: key) { return Double(s) }
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
    let scientific: String
    let mystical: String
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
            return SchumannGaugeLevel(scientific: "Calm", mystical: "Calm", color: Color(red: 0.44, green: 0.81, blue: 0.90))
        case calmUpper..<stableUpper:
            return SchumannGaugeLevel(scientific: "Stable", mystical: "Stable", color: Color(red: 0.49, green: 0.88, blue: 0.84))
        case stableUpper..<activeUpper:
            return SchumannGaugeLevel(scientific: "Active", mystical: "Active", color: Color(red: 0.90, green: 0.88, blue: 0.52))
        case activeUpper..<elevatedUpper:
            return SchumannGaugeLevel(scientific: "Elevated", mystical: "Elevated", color: Color(red: 0.97, green: 0.72, blue: 0.50))
        default:
            return SchumannGaugeLevel(scientific: "Intense", mystical: "Intense", color: Color(red: 0.95, green: 0.58, blue: 0.58))
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
    @Published var mode: SchumannDisplayMode = .scientific
    @Published var showDetails: Bool = true
    @Published var showHarmonics: Bool = true
    @Published var highContrast: Bool = false

    @Published var latest: SchumannLatestResponse?
    @Published var seriesRows: [SchumannSeriesRow] = []
    @Published var heatmap: SchumannHeatmapResponse?

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
        if latest == nil && seriesRows.isEmpty && heatmap == nil {
            isLoading = true
        }
        errorMessage = nil

        let api = state.apiWithAuth()

        async let latestResult: Result<SchumannLatestResponse, Error> = run {
            try await self.fetchLatest(api: api, force: force)
        }
        async let seriesResult: Result<SchumannSeriesResponse, Error> = run {
            try await self.fetchSeries(api: api, force: force)
        }
        async let heatmapResult: Result<SchumannHeatmapResponse, Error> = run {
            try await self.fetchHeatmap(api: api, force: force)
        }

        let resolvedLatest = await latestResult
        let resolvedSeries = await seriesResult
        let resolvedHeatmap = await heatmapResult

        var errorParts: [String] = []

        switch resolvedLatest {
        case .success(let response):
            latest = response
        case .failure(let err):
            errorParts.append("latest: \(err.localizedDescription)")
        }

        switch resolvedSeries {
        case .success(let response):
            seriesRows = response.rows ?? []
        case .failure(let err):
            errorParts.append("series: \(err.localizedDescription)")
        }

        switch resolvedHeatmap {
        case .success(let response):
            heatmap = response
        case .failure(let err):
            errorParts.append("heatmap: \(err.localizedDescription)")
        }

        if !errorParts.isEmpty && latest == nil && seriesRows.isEmpty && heatmap == nil {
            errorMessage = "Unable to load Schumann data (\(errorParts.joined(separator: " | ")))."
        } else if !errorParts.isEmpty {
            errorMessage = "Some sections are unavailable right now."
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

    func interpretationText(level: SchumannGaugeLevel) -> String {
        switch mode {
        case .scientific:
            return "Primary index is derived from the 0-20 Hz amplitude band and updates every 15 minutes."
        case .mystical:
            return "Current field tone is \(level.mystical.lowercased()). Open details for exact frequencies and amplitudes."
        }
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
    @StateObject private var viewModel = SchumannDashboardViewModel()

    private let timer = Timer.publish(every: 12 * 60, on: .main, in: .common).autoconnect()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                headerCard
                gaugeCard
                heatmapCard
                bandsCard
                pulseCard
                proCard
            }
            .padding()
        }
        .background(viewModel.highContrast ? Color.black : Color(.systemGroupedBackground))
        .navigationTitle("Schumann")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            await viewModel.refresh(using: state, force: true)
        }
        .task {
            await viewModel.loadIfNeeded(using: state)
        }
        .onReceive(timer) { _ in
            Task {
                await viewModel.refresh(using: state, force: false)
            }
        }
    }

    private var headerCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                Picker("Mode", selection: $viewModel.mode) {
                    ForEach(SchumannDisplayMode.allCases) { mode in
                        Text(mode.title).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

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
                }

                HStack(spacing: 10) {
                    Toggle("Show details", isOn: $viewModel.showDetails)
                        .font(.caption)
                    Toggle("Harmonics", isOn: $viewModel.showHarmonics)
                        .font(.caption)
                    Toggle("High contrast", isOn: $viewModel.highContrast)
                        .font(.caption)
                }
                .toggleStyle(.switch)

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            Label("Schumann Mode", systemImage: "dial.medium")
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

        return GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 12) {
                    SchumannGaugeDial(value: gaugeIndex / 100, color: level.color)
                        .frame(width: 170, height: 130)
                        .accessibilityLabel("Schumann gauge")
                        .accessibilityValue(viewModel.mode == .scientific
                                            ? "Index \(String(format: "%.1f", gaugeIndex))"
                                            : "State \(level.mystical)")

                    VStack(alignment: .leading, spacing: 6) {
                        if viewModel.mode == .scientific {
                            Text(String(format: "%.1f", gaugeIndex))
                                .font(.system(size: 36, weight: .bold, design: .rounded))
                            Text("Index")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            Text(level.mystical)
                                .font(.system(size: 32, weight: .bold, design: .rounded))
                            Text("State")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        Text(viewModel.interpretationText(level: level))
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
            SchumannHeatmapView(
                heatmap: viewModel.heatmap,
                samples: viewModel.samplesAscending,
                mode: viewModel.mode,
                showDetails: viewModel.showDetails,
                showHarmonics: viewModel.showHarmonics,
                highContrast: viewModel.highContrast
            )
        } label: {
            Label("48h Heatmap", systemImage: "square.grid.3x3.fill")
        }
    }

    private var bandsCard: some View {
        GroupBox {
            SchumannBandBarsView(
                samples: viewModel.samplesAscending,
                mode: viewModel.mode
            )
        } label: {
            Label("Harmonic Bands", systemImage: "chart.bar.fill")
        }
    }

    private var pulseCard: some View {
        GroupBox {
            SchumannPulseChartView(
                samples: viewModel.samplesAscending,
                mode: viewModel.mode,
                showDetails: viewModel.showDetails
            )
        } label: {
            Label("48h Pulse Line", systemImage: "waveform.path.ecg")
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
    let mode: SchumannDisplayMode

    private struct BandItem: Identifiable {
        let id = UUID()
        let key: String
        let label: String
        let latest: Double?
        let baseline: Double?
    }

    var body: some View {
        let latest = samples.last
        let previousWindow = Array(samples.dropLast().suffix(8))

        let items: [BandItem] = [
            BandItem(
                key: "band7_9",
                label: mode == .scientific ? "7-9 Hz" : "Ground",
                latest: latest?.band7_9,
                baseline: average(previousWindow.map(\.band7_9))
            ),
            BandItem(
                key: "band13_15",
                label: mode == .scientific ? "13-15 Hz" : "Flow",
                latest: latest?.band13_15,
                baseline: average(previousWindow.map(\.band13_15))
            ),
            BandItem(
                key: "band18_20",
                label: mode == .scientific ? "18-20 Hz" : "Spark",
                latest: latest?.band18_20,
                baseline: average(previousWindow.map(\.band18_20))
            )
        ]

        VStack(alignment: .leading, spacing: 10) {
            if latest == nil {
                Text("Band data unavailable.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                ForEach(items) { item in
                    HStack(spacing: 10) {
                        Text(item.label)
                            .font(.caption)
                            .frame(width: 80, alignment: .leading)

                        ProgressView(value: min(max(item.latest ?? 0, 0), 1), total: 1)
                            .tint(Color.cyan)

                        Text(trendText(latest: item.latest, baseline: item.baseline))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(trendColor(latest: item.latest, baseline: item.baseline))
                            .frame(width: 64, alignment: .trailing)
                    }
                }
                Text("Trend compares latest reading against the previous 2 hours (8 points).")
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
    let mode: SchumannDisplayMode
    let showDetails: Bool

    @State private var selectedSample: SchumannSeriesSample?

    private var showAxes: Bool {
        mode == .scientific || showDetails
    }

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
                                y: .value("Pulse", sr)
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

                    if mode == .scientific {
                        ForEach(samples) { sample in
                            if let f0 = sample.f0 {
                                LineMark(
                                    x: .value("Time", sample.date),
                                    y: .value("F0Scaled", mapF0ToPulseScale(f0))
                                )
                                .foregroundStyle(Color.yellow)
                                .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [5, 4]))
                            }
                        }
                    }

                    if let selectedSample, let sr = selectedSample.srTotal {
                        RuleMark(x: .value("Selected", selectedSample.date))
                            .foregroundStyle(.secondary.opacity(0.35))
                        PointMark(x: .value("Selected", selectedSample.date), y: .value("SelectedPulse", sr))
                            .symbolSize(46)
                            .foregroundStyle(.white)
                    }
                }
                .chartYScale(domain: 0...srUpperBound)
                .frame(height: 230)
                .chartXAxis {
                    if showAxes {
                        AxisMarks(values: .automatic(desiredCount: 4))
                    }
                }
                .chartYAxis {
                    if showAxes {
                        AxisMarks(position: .leading)
                        if mode == .scientific {
                            let ticks = trailingF0TickValues()
                            AxisMarks(position: .trailing, values: ticks) { value in
                                if let scaled = value.as(Double.self) {
                                    AxisValueLabel(String(format: "%.2f Hz", mapPulseScaleToF0(scaled)))
                                }
                            }
                        }
                    }
                }
                .chartOverlay { proxy in
                    GeometryReader { geo in
                        Rectangle()
                            .fill(Color.clear)
                            .contentShape(Rectangle())
                            .gesture(
                                DragGesture(minimumDistance: 0)
                                    .onChanged { value in
                                        guard let plotFrame = proxy.plotFrame else {
                                            return
                                        }
                                        let origin = geo[plotFrame].origin
                                        let locationX = value.location.x - origin.x
                                        guard let date: Date = proxy.value(atX: locationX) else {
                                            return
                                        }
                                        selectedSample = nearestSample(to: date)
                                    }
                                    .onEnded { _ in }
                            )
                    }
                }

                if let selected = selectedSample {
                    HStack(spacing: 10) {
                        Text(formattedTooltipDate(selected.date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text("Pulse \(selected.srTotal.map { String(format: "%.3f", $0) } ?? "-")")
                            .font(.caption)
                        if mode == .scientific {
                            Text("f0 \(selected.f0.map { String(format: "%.2f", $0) } ?? "-") Hz")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Text(selected.usable ? "OK" : "Low confidence")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background((selected.usable ? Color.green : Color.orange).opacity(0.2), in: Capsule())
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func nearestSample(to date: Date) -> SchumannSeriesSample? {
        samples.min(by: { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) })
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
    let mode: SchumannDisplayMode
    let showDetails: Bool
    let showHarmonics: Bool
    let highContrast: Bool

    @State private var bitmap: SchumannHeatmapBitmap?
    @State private var hover: SchumannHeatmapHover?

    #if canImport(UIKit)
    @State private var sharePayload: SchumannShareImagePayload?
    #endif

    private var showAxes: Bool {
        mode == .scientific || showDetails
    }

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

                    if showHarmonics, let bitmap {
                        harmonicOverlay(size: geo.size, axis: heatmap?.axis, bins: bitmap.binCount)
                    }

                    if let hover {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(hover.ts)
                                .bold()
                            Text(String(format: "Freq %.2f Hz", hover.freqHz))
                            Text(String(format: "Intensity %.3f", hover.intensity))
                        }
                        .font(.caption2)
                        .padding(8)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
                        .position(
                            x: min(max(hover.position.x + 70, 70), geo.size.width - 70),
                            y: min(max(hover.position.y - 34, 24), geo.size.height - 24)
                        )
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { gesture in
                            updateHover(location: gesture.location, size: geo.size)
                        }
                        .onEnded { _ in }
                )
            }
            .frame(height: 220)

            if showAxes {
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
            } else {
                Text("Mystical mode: details hidden")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
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

    private func updateHover(location: CGPoint, size: CGSize) {
        guard let heatmap,
              let points = heatmap.points,
              let first = points.first,
              !points.isEmpty,
              !first.bins.isEmpty
        else {
            hover = nil
            return
        }

        let x = min(max(0, location.x), size.width - 1)
        let y = min(max(0, location.y), size.height - 1)

        let pointIndex = Int((x / max(1, size.width)) * CGFloat(points.count - 1))
        let clampedPointIndex = max(0, min(points.count - 1, pointIndex))

        let binCount = first.bins.count
        let normalizedY = 1 - (y / max(1, size.height))
        let rawBinIndex = Int(normalizedY * CGFloat(binCount - 1))
        let binIndex = max(0, min(binCount - 1, rawBinIndex))

        let point = points[clampedPointIndex]
        guard point.bins.indices.contains(binIndex) else {
            hover = nil
            return
        }

        let freqStart = heatmap.axis?.freqStartHz ?? 0
        let freqStep = heatmap.axis?.freqStepHz ?? (20.0 / Double(max(1, binCount)))
        let freq = freqStart + (Double(binIndex) * freqStep)

        hover = SchumannHeatmapHover(
            ts: formattedHoverTimestamp(point.ts),
            freqHz: freq,
            intensity: point.bins[binIndex],
            position: CGPoint(x: x, y: y)
        )
    }

    private func formattedHoverTimestamp(_ iso: String?) -> String {
        guard let iso else { return "-" }
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        guard let date = frac.date(from: iso) ?? plain.date(from: iso) else {
            return iso
        }
        let out = DateFormatter()
        out.dateStyle = .medium
        out.timeStyle = .short
        return out.string(from: date)
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
