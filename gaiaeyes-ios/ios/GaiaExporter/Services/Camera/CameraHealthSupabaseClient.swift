import Foundation

enum CameraMetricStatus: String, Codable {
    case usable
    case withheldLowQuality = "withheld_low_quality"
    case notCaptured = "not_captured"
    case notRequested = "not_requested"
}

enum CameraSaveScope: String, Codable {
    case account
    case localOnly = "local_only"
    case notSaved = "not_saved"
}

enum CameraCheckSummaryStatus: String, Codable {
    case good
    case partial
    case poor
    case pending
}

struct CameraHealthQualityBreakdown: Codable {
    let validIBIRatio: Double
    let snrProxy: Double
    let stabilityScore: Double
    let saturationPenalty: Double
    let motionPenalty: Double
    let droppedFramePenalty: Double
}

struct CameraHealthDebugMeta: Codable {
    let hrReasons: [String]
    let hrvReasons: [String]
    let guidanceHints: [String]
    let failureReason: String?
    let nextStepSuggestion: String?
    let quality: CameraHealthQualityBreakdown
}

struct CameraHealthCheckRecord: Codable {
    let capturedAt: Date
    let measurementMode: String
    let hrStatus: CameraMetricStatus
    let hrvStatus: CameraMetricStatus
    let overallStatus: CameraCheckSummaryStatus
    var saveScope: CameraSaveScope
    let result: CameraPPGComputedResult
    let debugMeta: CameraHealthDebugMeta
}

struct CameraHealthDailySummary: Codable {
    let day: String?
    let latestTsUtc: String?
    let bpm: Double?
    let rmssdMs: Double?
    let sdnnMs: Double?
    let pnn50: Double?
    let lnRmssd: Double?
    let stressIndex: Double?
    let respRateBpm: Double?
    let qualityScore: Double?
    let qualityLabel: String?
    let measurementMode: String?
    let hrStatus: String?
    let hrvStatus: String?
    let saveScope: String?

    private enum CodingKeys: String, CodingKey {
        case day
        case latestTsUtc = "latest_ts_utc"
        case bpm
        case rmssdMs = "rmssd_ms"
        case sdnnMs = "sdnn_ms"
        case pnn50
        case lnRmssd = "ln_rmssd"
        case stressIndex = "stress_index"
        case respRateBpm = "resp_rate_bpm"
        case qualityScore = "quality_score"
        case qualityLabel = "quality_label"
        case measurementMode = "measurement_mode"
        case hrStatus = "hr_status"
        case hrvStatus = "hrv_status"
        case saveScope = "save_scope"
    }
}

extension CameraHealthDailySummary {
    var hrMetricStatus: CameraMetricStatus {
        CameraMetricStatus(rawValue: hrStatus ?? "") ?? (bpm != nil ? .usable : .notCaptured)
    }

    var hrvMetricStatus: CameraMetricStatus {
        CameraMetricStatus(rawValue: hrvStatus ?? "") ?? (rmssdMs != nil ? .usable : .notCaptured)
    }

    var persistedSaveScope: CameraSaveScope {
        CameraSaveScope(rawValue: saveScope ?? "") ?? .notSaved
    }

    var summaryStatus: CameraCheckSummaryStatus {
        switch (hrMetricStatus, hrvMetricStatus) {
        case (.usable, .usable):
            return .good
        case (.usable, _), (_, .usable):
            return .partial
        case (.notRequested, .notRequested):
            return .pending
        default:
            return .poor
        }
    }

    var hasUsableHR: Bool {
        hrMetricStatus == .usable && bpm != nil
    }

    var hasUsableHRV: Bool {
        hrvMetricStatus == .usable && rmssdMs != nil
    }

    var captureDate: Date? {
        guard let latestTsUtc else { return nil }
        return CameraHealthLocalStore.parseDate(latestTsUtc)
    }
}

enum CameraHealthSupabaseError: LocalizedError {
    case missingConfig
    case notAuthenticated
    case missingUserId
    case server(Int, String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .missingConfig:
            return "Supabase config missing from app settings."
        case .notAuthenticated:
            return "Sign in required to save camera checks."
        case .missingUserId:
            return "Could not resolve session user."
        case .server(let code, let body):
            return "Supabase error \(code): \(body)"
        case .invalidResponse:
            return "Unexpected Supabase response."
        }
    }
}

final class CameraHealthSupabaseClient {
    static let shared = CameraHealthSupabaseClient()

    private struct Config {
        let baseURL: URL
        let anonKey: String
    }

    private struct InsertRow: Encodable {
        let userId: String
        let tsUtc: String
        let source: String
        let measurementMode: String
        let hrStatus: String
        let hrvStatus: String
        let saveScope: String
        let durationSec: Int
        let fps: Int?
        let bpm: Double?
        let avnnMs: Double?
        let sdnnMs: Double?
        let rmssdMs: Double?
        let pnn50: Double?
        let lnRmssd: Double?
        let stressIndex: Double?
        let respRateBpm: Double?
        let qualityScore: Double
        let qualityLabel: String
        let artifacts: [String: Double]
        let debugMeta: CameraHealthDebugMeta
        let ibiMs: [Double]
        let ibiTsMs: [Double]
        let ppgDs: [Double]
        let ppgDsHz: Double?

        private enum CodingKeys: String, CodingKey {
            case userId = "user_id"
            case tsUtc = "ts_utc"
            case source
            case measurementMode = "measurement_mode"
            case hrStatus = "hr_status"
            case hrvStatus = "hrv_status"
            case saveScope = "save_scope"
            case durationSec = "duration_sec"
            case fps
            case bpm
            case avnnMs = "avnn_ms"
            case sdnnMs = "sdnn_ms"
            case rmssdMs = "rmssd_ms"
            case pnn50
            case lnRmssd = "ln_rmssd"
            case stressIndex = "stress_index"
            case respRateBpm = "resp_rate_bpm"
            case qualityScore = "quality_score"
            case qualityLabel = "quality_label"
            case artifacts
            case debugMeta = "debug_meta"
            case ibiMs = "ibi_ms"
            case ibiTsMs = "ibi_ts_ms"
            case ppgDs = "ppg_ds"
            case ppgDsHz = "ppg_ds_hz"
        }
    }

    private let session: URLSession
    private let decoder: JSONDecoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)
        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    @MainActor
    func saveCheck(_ record: CameraHealthCheckRecord, auth: AuthManager? = nil) async throws {
        let auth = auth ?? AuthManager.shared
        auth.loadFromKeychain()
        guard let config = loadConfig() else {
            throw CameraHealthSupabaseError.missingConfig
        }
        guard let token = await auth.validAccessToken(), !token.isEmpty else {
            throw CameraHealthSupabaseError.notAuthenticated
        }
        guard let userId = await auth.resolveSupabaseUserId(), !userId.isEmpty else {
            throw CameraHealthSupabaseError.missingUserId
        }

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        let row = InsertRow(
            userId: userId,
            tsUtc: iso.string(from: record.capturedAt),
            source: "ios_camera",
            measurementMode: record.measurementMode,
            hrStatus: record.hrStatus.rawValue,
            hrvStatus: record.hrvStatus.rawValue,
            saveScope: CameraSaveScope.account.rawValue,
            durationSec: record.result.durationSec,
            fps: record.result.fps,
            bpm: record.result.metrics.bpm,
            avnnMs: record.result.metrics.avnnMs,
            sdnnMs: record.result.metrics.sdnnMs,
            rmssdMs: record.result.metrics.rmssdMs,
            pnn50: record.result.metrics.pnn50,
            lnRmssd: record.result.metrics.lnRmssd,
            stressIndex: record.result.metrics.stressIndex,
            respRateBpm: record.result.metrics.respRateBpm,
            qualityScore: record.result.quality.score,
            qualityLabel: record.result.quality.label.rawValue,
            artifacts: [
                "dropped_frames": Double(record.result.artifacts.droppedFrames),
                "dropped_frame_ratio": record.result.artifacts.droppedFrameRatio,
                "saturation_hits": record.result.artifacts.saturationHitRatio,
                "motion_score": record.result.artifacts.motionScore,
                "valid_ibi_count": Double(record.result.artifacts.validIbiCount),
                "total_ibi_count": Double(record.result.artifacts.totalIbiCount),
            ],
            debugMeta: record.debugMeta,
            ibiMs: record.result.ibiMs,
            ibiTsMs: record.result.ibiTimestampsMs,
            ppgDs: Array(record.result.ppgDownsampled.prefix(1500)),
            ppgDsHz: record.result.ppgDownsampledHz
        )

        var url = config.baseURL
        url.appendPathComponent("rest/v1/camera_health_checks")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("raw", forHTTPHeaderField: "Content-Profile")
        request.setValue("return=minimal", forHTTPHeaderField: "Prefer")
        request.httpBody = try JSONEncoder().encode([row])

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw CameraHealthSupabaseError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw CameraHealthSupabaseError.server(http.statusCode, body)
        }
    }

    @MainActor
    func fetchLatestDailySummary(auth: AuthManager? = nil) async throws -> CameraHealthDailySummary? {
        let auth = auth ?? AuthManager.shared
        auth.loadFromKeychain()
        guard let config = loadConfig() else {
            throw CameraHealthSupabaseError.missingConfig
        }
        guard let token = await auth.validAccessToken(), !token.isEmpty else {
            throw CameraHealthSupabaseError.notAuthenticated
        }
        guard let userId = await auth.resolveSupabaseUserId(), !userId.isEmpty else {
            throw CameraHealthSupabaseError.missingUserId
        }

        guard var components = URLComponents(url: config.baseURL.appendingPathComponent("rest/v1/camera_health_daily"), resolvingAgainstBaseURL: false) else {
            throw CameraHealthSupabaseError.invalidResponse
        }
        components.queryItems = [
            URLQueryItem(name: "select", value: "day,latest_ts_utc,bpm,rmssd_ms,sdnn_ms,pnn50,ln_rmssd,stress_index,resp_rate_bpm,quality_score,quality_label,measurement_mode,hr_status,hrv_status,save_scope"),
            URLQueryItem(name: "user_id", value: "eq.\(userId)"),
            URLQueryItem(name: "order", value: "day.desc,latest_ts_utc.desc"),
            URLQueryItem(name: "limit", value: "1"),
        ]
        guard let url = components.url else {
            throw CameraHealthSupabaseError.invalidResponse
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("marts", forHTTPHeaderField: "Accept-Profile")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw CameraHealthSupabaseError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw CameraHealthSupabaseError.server(http.statusCode, body)
        }

        let rows = try decoder.decode([CameraHealthDailySummary].self, from: data)
        return rows.first
    }

    private func loadConfig() -> Config? {
        guard let urlString = Bundle.main.object(forInfoDictionaryKey: "SUPABASE_URL") as? String,
              let baseURL = URL(string: urlString),
              let anonKey = Bundle.main.object(forInfoDictionaryKey: "SUPABASE_ANON_KEY") as? String,
              !anonKey.isEmpty else {
            return nil
        }
        return Config(baseURL: baseURL, anonKey: anonKey)
    }
}

actor CameraHealthLocalStore {
    static let shared = CameraHealthLocalStore()
    static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    static let iso8601Basic: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private struct LocalEntry: Codable {
        let summary: CameraHealthDailySummary
        let debugMeta: CameraHealthDebugMeta
    }

    private let storageKey = "gaia.camera.health.local_entries"
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private var cached: [LocalEntry] = []

    private init() {
        encoder = JSONEncoder()
        decoder = JSONDecoder()
        if let data = UserDefaults.standard.data(forKey: storageKey),
           let decoded = try? decoder.decode([LocalEntry].self, from: data) {
            cached = decoded
        }
    }

    func save(record: CameraHealthCheckRecord, saveScope: CameraSaveScope) {
        let summary = CameraHealthDailySummary(
            day: Self.dayString(from: record.capturedAt),
            latestTsUtc: Self.iso8601.string(from: record.capturedAt),
            bpm: record.result.metrics.bpm,
            rmssdMs: record.result.metrics.rmssdMs,
            sdnnMs: record.result.metrics.sdnnMs,
            pnn50: record.result.metrics.pnn50,
            lnRmssd: record.result.metrics.lnRmssd,
            stressIndex: record.result.metrics.stressIndex,
            respRateBpm: record.result.metrics.respRateBpm,
            qualityScore: record.result.quality.score,
            qualityLabel: record.result.quality.label.rawValue,
            measurementMode: record.measurementMode,
            hrStatus: record.hrStatus.rawValue,
            hrvStatus: record.hrvStatus.rawValue,
            saveScope: saveScope.rawValue
        )
        cached.removeAll { $0.summary.latestTsUtc == summary.latestTsUtc }
        cached.insert(LocalEntry(summary: summary, debugMeta: record.debugMeta), at: 0)
        cached = Array(cached.prefix(20))
        persist()
    }

    func latestSummary() -> CameraHealthDailySummary? {
        cached
            .sorted { ($0.summary.captureDate ?? .distantPast) > ($1.summary.captureDate ?? .distantPast) }
            .first?
            .summary
    }

    private func persist() {
        guard let data = try? encoder.encode(cached) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }

    private static func dayString(from date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    static func parseDate(_ raw: String) -> Date? {
        iso8601.date(from: raw) ?? iso8601Basic.date(from: raw)
    }
}
