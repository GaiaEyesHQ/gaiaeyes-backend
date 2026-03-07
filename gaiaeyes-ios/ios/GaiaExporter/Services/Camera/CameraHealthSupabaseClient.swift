import Foundation

struct CameraHealthDailySummary: Decodable {
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
        let ibiMs: [Double]
        let ibiTsMs: [Double]
        let ppgDs: [Double]
        let ppgDsHz: Double?

        private enum CodingKeys: String, CodingKey {
            case userId = "user_id"
            case tsUtc = "ts_utc"
            case source
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
    func saveCheck(_ result: CameraPPGComputedResult, auth: AuthManager? = nil) async throws {
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
            tsUtc: iso.string(from: Date()),
            source: "ios_camera",
            durationSec: result.durationSec,
            fps: result.fps,
            bpm: result.metrics.bpm,
            avnnMs: result.metrics.avnnMs,
            sdnnMs: result.metrics.sdnnMs,
            rmssdMs: result.metrics.rmssdMs,
            pnn50: result.metrics.pnn50,
            lnRmssd: result.metrics.lnRmssd,
            stressIndex: result.metrics.stressIndex,
            respRateBpm: result.metrics.respRateBpm,
            qualityScore: result.quality.score,
            qualityLabel: result.quality.label.rawValue,
            artifacts: [
                "dropped_frames": Double(result.artifacts.droppedFrames),
                "dropped_frame_ratio": result.artifacts.droppedFrameRatio,
                "saturation_hits": result.artifacts.saturationHitRatio,
                "motion_score": result.artifacts.motionScore,
                "valid_ibi_count": Double(result.artifacts.validIbiCount),
                "total_ibi_count": Double(result.artifacts.totalIbiCount),
            ],
            ibiMs: result.ibiMs,
            ibiTsMs: result.ibiTimestampsMs,
            ppgDs: Array(result.ppgDownsampled.prefix(1500)),
            ppgDsHz: result.ppgDownsampledHz
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
            URLQueryItem(name: "select", value: "day,latest_ts_utc,bpm,rmssd_ms,sdnn_ms,pnn50,ln_rmssd,stress_index,resp_rate_bpm,quality_score,quality_label"),
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
