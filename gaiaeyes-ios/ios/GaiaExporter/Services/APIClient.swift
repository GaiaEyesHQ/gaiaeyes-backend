// APIClient.swift
// GaiaExporter
// Restored & upgraded: robust chunk uploading with retry/backoff

import Foundation
import Network

public struct APIConfig {
    public let baseURLString: String
    public let bearer: String
    public let timeout: TimeInterval
    public init(baseURLString: String, bearer: String, timeout: TimeInterval = 60) {
        self.baseURLString = baseURLString
        self.bearer = bearer
        self.timeout = timeout
    }
}

// Absolute-URL helper (bypasses baseURL) with the same retries/decoder behavior.
extension APIClient {
    @discardableResult
    public func getJSONAbsolute<T: Decodable>(_ url: URL,
                                              as type: T.Type,
                                              retries: Int = 2,
                                              perRequestTimeout: TimeInterval = 20) async throws -> T {
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.timeoutInterval = perRequestTimeout
        // Attach auth + developer scope for absolute requests as well
        if !bearer.isEmpty {
            req.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        if let uid = devUserId?.trimmingCharacters(in: .whitespacesAndNewlines), !uid.isEmpty {
            req.setValue(uid, forHTTPHeaderField: "X-Dev-UserId")
        }

        var attemptsLeft = max(0, retries)
        var lastError: Error?
        while true {
            do {
                logger?("GET \(url.absoluteString)")
                let (data, resp) = try await session.data(for: req)
                let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
                guard (200...299).contains(code) else {
                    let body = String(data: data, encoding: .utf8) ?? ""
                    logger?("↩︎ \(code) \(HTTPURLResponse.localizedString(forStatusCode: code)) \(body)")
                    throw APIError.server(code: code, body: body)
                }
                let dec = APIClient.tolerantJSONDecoder()
                return try dec.decode(T.self, from: data)
            } catch {
                lastError = error
                if attemptsLeft > 0, let uerr = error as? URLError {
                    let retryables: Set<URLError.Code> = [.timedOut, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed]
                    if retryables.contains(uerr.code) {
                        attemptsLeft -= 1
                        let base: UInt64 = 300_000_000 // 300ms
                        let factor = UInt64((retries - attemptsLeft) * (retries - attemptsLeft))
                        let delay = base * factor
                        let jitter = UInt64(Int.random(in: 0..<(Int(base)/2)))
                        try? await Task.sleep(nanoseconds: delay + jitter)
                        continue
                    }
                }
                throw lastError ?? error
            }
        }
    }
}

// MARK: - Wire payloads

private struct SamplesRawPayload: Encodable {
    let samples: [Sample]
}

private enum APIError: Error {
    case server(code: Int, body: String)
}

struct DecodingPreviewError: Error, LocalizedError {
    let endpoint: String
    let preview: String
    let underlying: Error

    var errorDescription: String? {
        let sanitized = preview.replacingOccurrences(of: "\n", with: " ")
        return "Decoding failed for \(endpoint): \(underlying.localizedDescription) preview=\(sanitized)"
    }
}

// Human‑readable errors for logs/UI
extension APIError: LocalizedError, CustomStringConvertible {
    public var errorDescription: String? {
        switch self {
        case .server(let code, let body):
            let preview = body.replacingOccurrences(of: "\n", with: " ").prefix(200)
            return "HTTP \(code): \(preview)"
        }
    }
    public var description: String { errorDescription ?? "APIError" }
}

enum SymptomUploadError: Error {
    case unknownSymptomCode(valid: [String])
}

extension SymptomUploadError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .unknownSymptomCode:
            return "Unknown symptom code"
        }
    }
}

/// If your project already defines `Sample` elsewhere, this file will use it.
/// `Sample` must conform to `Encodable`. Example shape:
/// struct Sample: Encodable { let user_id: String; let device_os: String; let source: String; let type: String; let start_time: String; let end_time: String; let value: Double?; let unit: String?; let value_text: String? }

private extension APIClient {
    static func makeTunedSession() -> URLSession {
        let cfg = URLSessionConfiguration.default
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        cfg.waitsForConnectivity = false
        cfg.allowsExpensiveNetworkAccess = true
        cfg.allowsConstrainedNetworkAccess = true
        cfg.timeoutIntervalForRequest = 8    // short per-request timeout
        cfg.timeoutIntervalForResource = 20  // cap whole transfer time
        cfg.httpMaximumConnectionsPerHost = 4
        var headers = cfg.httpAdditionalHeaders ?? [:]
        headers["Accept-Encoding"] = "gzip, deflate, br"
        cfg.httpAdditionalHeaders = headers
        return URLSession(configuration: cfg)
    }

    private static func tolerantJSONDecoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        dec.dateDecodingStrategy = .custom { decoder in
            let c = try decoder.singleValueContainer()
            if let n = try? c.decode(Double.self) {
                let secs = n > 10_000_000_000 ? n / 1000.0 : n
                return Date(timeIntervalSince1970: secs)
            }
            let s = try c.decode(String.self)
            let isoFrac = ISO8601DateFormatter()
            isoFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let d = isoFrac.date(from: s) { return d }
            let iso = ISO8601DateFormatter()
            if let d = iso.date(from: s) { return d }
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unsupported date \(s)")
        }
        return dec
    }
}
// MARK: - API Client

final class APIClient {
    private let baseURL: URL
    private let bearer: String
    private let session: URLSession
    private let timeout: TimeInterval

    // Network path monitoring (decide chunk sizes)
    private let pathMonitor = NWPathMonitor()
    private var pathIsConstrained = false
    private var pathIsExpensive = false
    private var pathIsSatisfied = false

    // Only run /health preflight once per client
    private var didPreflight = false

    /// Optional dev-only header for your backend (used in earlier code)
    public var devUserId: String?

    /// Optional logger to surface network activity
    public var logger: ((String) -> Void)?

    init(config: APIConfig) {
        self.bearer = config.bearer
        self.timeout = config.timeout
        // Ensure base URL is valid
        self.baseURL = URL(string: config.baseURLString) ?? URL(string: "http://127.0.0.1:8000")!

        // Tuned session: short timeouts, limited concurrency to avoid UI stalls
        self.session = APIClient.makeTunedSession()

        // Start path monitor
        let q = DispatchQueue(label: "api.path.monitor")
        pathMonitor.pathUpdateHandler = { [weak self] path in
            self?.pathIsConstrained = path.isConstrained
            self?.pathIsExpensive = path.isExpensive
            self?.pathIsSatisfied = (path.status == .satisfied)
            self?.logger?("[NET] satisfied=\(path.status == .satisfied) exp=\(path.isExpensive) constr=\(path.isConstrained)")
        }
        pathMonitor.start(queue: q)
    }

    /// Send a prepared request using the tuned session (short timeouts, limited concurrency)
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        try await self.session.data(for: request)
    }

    // MARK: - CDN fallback
    private var cdnBaseURL: URL? {
        guard let raw = ProcessInfo.processInfo.environment["MEDIA_BASE_URL"], !raw.isEmpty else { return nil }
        let trimmed = raw.hasSuffix("/") ? String(raw.dropLast()) : raw
        return URL(string: trimmed)
    }

    /// Map backend paths to CDN JSON snapshots, if available.
    private func cdnPath(for backendPath: String) -> String? {
        let clean = backendPath.hasPrefix("/") ? String(backendPath.dropFirst()) : backendPath

        // Split path and query (if any): e.g. "v1/space/series?days=30"
        let parts = clean.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        let pathOnly = String(parts[0])
        let query = parts.count > 1 ? String(parts[1]) : nil

        // Extract days=N (defaults to 30 if missing)
        func extractDays(_ q: String?) -> Int {
            guard let q = q else { return 30 }
            for kv in q.split(separator: "&") {
                if kv.hasPrefix("days="), let v = Int(kv.dropFirst(5)) {
                    return max(1, min(90, v))
                }
            }
            return 30
        }

        switch pathOnly {
        case "v1/features/today":
            return "data/earthscope_daily.json"
        case "v1/space/forecast/summary":
            return "data/space_weather.json"
        case "v1/space/forecast/outlook":
            return "data/space_outlook.json"
        case "v1/space/series", "v1/series":
            let d = extractDays(query)
            // If you publish only a generic series snapshot, change to: return "data/series.json"
            return "data/series_\(d)d.json"
        case "v1/space/visuals":
            return "data/space_live.json"
        default:
            return nil
        }
    }

    /// Fetch JSON from CDN as a resilience fallback.
    private func fetchFromCDN<T: Decodable>(_ cdnRelPath: String, as type: T.Type) async throws -> T {
        guard let base = cdnBaseURL else { throw URLError(.badURL) }
        var url = base
        url.appendPathComponent(cdnRelPath)
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.timeoutInterval = 20
        logger?("CDN GET \(url.absoluteString)")
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        guard (200...299).contains(code) else { throw APIError.server(code: code, body: String(data: data, encoding: .utf8) ?? "") }
        let dec = APIClient.tolerantJSONDecoder()
        return try dec.decode(T.self, from: data)
    }

    // MARK: - GET helpers (timeouts, retries, tolerant decoding)

    /// Generic JSON GET with retry on timeouts and tolerant decoding (ISO8601 dates, snake_case keys).
    @discardableResult
    public func getJSON<T: Decodable>(_ path: String,
                                      as type: T.Type,
                                      retries: Int = 3,
                                      perRequestTimeout: TimeInterval = 45) async throws -> T {
        let clean = path.trimmingCharacters(in: .whitespacesAndNewlines)
        // Split into path and query (e.g., "v1/space/series?days=30")
        let parts = clean.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        let pathOnly = String(parts[0].hasPrefix("/") ? parts[0].dropFirst() : parts[0])
        let query = parts.count > 1 ? String(parts[1]) : nil

        guard var comps = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        // Ensure single slash join between baseURL.path and pathOnly
        var basePath = comps.path
        if basePath.hasSuffix("/") { basePath.removeLast() }
        comps.path = basePath + "/" + pathOnly
        comps.percentEncodedQuery = query

        guard let finalURL = comps.url else { throw URLError(.badURL) }
        var req = URLRequest(url: finalURL)
        req.httpMethod = "GET"
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if !bearer.isEmpty { req.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization") }
        if let uid = devUserId, !uid.isEmpty { req.setValue(uid, forHTTPHeaderField: "X-Dev-UserId") }
        req.timeoutInterval = perRequestTimeout

        // Warm up the backend (handles cold starts) once per client
        await preflightHealth()

        var attemptsLeft = max(0, retries)
        var lastError: Error?
        while true {
            do {
                logger?("GET \(finalURL.absoluteString)")
                let (data, resp) = try await session.data(for: req)
                let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
                guard (200...299).contains(code) else {
                    let body = String(data: data, encoding: .utf8) ?? ""
                    logger?("↩︎ \(code) \(HTTPURLResponse.localizedString(forStatusCode: code)) \(body)")
                    throw APIError.server(code: code, body: body)
                }
                let dec = APIClient.tolerantJSONDecoder()
                do {
                    return try dec.decode(T.self, from: data)
                } catch {
                    let preview = String(data: data.prefix(200), encoding: .utf8) ?? "<bin>"
                    logger?("[Decode] \(clean) failed: \(error) — preview: \(preview)")
                    throw DecodingPreviewError(endpoint: clean, preview: preview, underlying: error)
                }
            } catch {
                lastError = error
                if attemptsLeft > 0 {
                    if let uerr = error as? URLError {
                        let retryables: Set<URLError.Code> = [
                            .timedOut, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed
                        ]
                        if retryables.contains(uerr.code) {
                            attemptsLeft -= 1
                            // Exponential backoff with jitter
                            let base: UInt64 = 300_000_000 // 300ms
                            let factor = UInt64((retries - attemptsLeft) * (retries - attemptsLeft))
                            let delay = base * factor  // 0.3s, 1.2s, 2.7s pattern
                            let jitter = UInt64(Int.random(in: 0..<(Int(base)/2)))
                            try? await Task.sleep(nanoseconds: delay + jitter)
                            continue
                        }
                    }
                }
                // Final chance: on timeout-family errors, try a CDN snapshot if we know one for this path
                if let uerr = error as? URLError {
                    let timeoutFamily: Set<URLError.Code> = [.timedOut, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed]
                    if timeoutFamily.contains(uerr.code), let cdnRel = cdnPath(for: clean) {
                        do {
                            let snap: T = try await fetchFromCDN(cdnRel, as: T.self)
                            logger?("[CDN] served fallback for \(clean) → \(cdnRel)")
                            return snap
                        } catch {
                            // ignore and fall through to original error
                        }
                    }
                }
                // Also try CDN on server 5xx responses if a mapping exists
                if case let APIError.server(code, _) = (lastError ?? error),
                   (500...599).contains(code),
                   let cdnRel = cdnPath(for: clean) {
                    do {
                        let snap: T = try await fetchFromCDN(cdnRel, as: T.self)
                        logger?("[CDN] served fallback for \(clean) → \(cdnRel)")
                        return snap
                    } catch {
                        // ignore and fall through
                    }
                }
                throw lastError ?? error
            }
        }
    }

    private struct SymptomPostPayload: Encodable {
        let symptomCode: String
        let tsUtc: String?
        let severity: Int?
        let freeText: String?
        let tags: [String]?

        enum CodingKeys: String, CodingKey {
            case symptomCode = "symptom_code"
            case tsUtc = "ts_utc"
            case severity
            case freeText = "free_text"
            case tags
        }
    }

    @discardableResult
    func postJSON<Body: Encodable, Resp: Decodable>(_ path: String,
                                                    body: Body,
                                                    as responseType: Resp.Type) async throws -> Resp {
        var req = makeRequest(path: path)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        req.httpBody = try encoder.encode(body)

        await preflightHealth()

        logger?("POST \(req.url?.absoluteString ?? path)")
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        let bodyString = String(data: data, encoding: .utf8) ?? ""
        guard (200...299).contains(code) else {
            logger?("↩︎ \(code) \(HTTPURLResponse.localizedString(forStatusCode: code)) \(bodyString)")
            throw APIError.server(code: code, body: bodyString)
        }
        logger?("↩︎ \(code) \(bodyString)")

        let decoder = APIClient.tolerantJSONDecoder()
        return try decoder.decode(Resp.self, from: data)
    }

    private struct SymptomPostErrorPayload: Decodable {
        let error: String
        let valid: [String]?
    }

    func postSymptomEvent(from event: SymptomQueuedEvent) async throws -> SymptomPostResponse {
        let isoFmt = ISO8601DateFormatter()
        isoFmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let ts = isoFmt.string(from: event.tsUtc)
        let payload = SymptomPostPayload(symptomCode: normalize(event.symptomCode),
                                         tsUtc: ts,
                                         severity: event.severity,
                                         freeText: event.freeText,
                                         tags: event.tags)
        do {
            let response = try await postJSON("v1/symptoms", body: payload, as: SymptomPostResponse.self)
            if response.ok == false {
                logger?("[SYM] POST ok=false — treating as success")
            }
            return response
        } catch let decodeError as DecodingError {
            logger?("[SYM] POST decode fallback: \(decodeError)")
            return SymptomPostResponse(ok: nil, id: nil, tsUtc: nil)
        } catch APIError.server(let code, let body) {
            if code == 400, let data = body.data(using: .utf8) {
                let decoder = APIClient.tolerantJSONDecoder()
                if let errorPayload = try? decoder.decode(SymptomPostErrorPayload.self, from: data),
                   errorPayload.error.lowercased() == "unknown symptom_code" {
                    throw SymptomUploadError.unknownSymptomCode(valid: errorPayload.valid ?? [])
                }
            }
            throw APIError.server(code: code, body: body)
        }
    }

    func fetchSymptomsToday() async throws -> Envelope<[SymptomEventToday]> {
        try await getJSON("v1/symptoms/today", as: Envelope<[SymptomEventToday]>.self)
    }

    func fetchSymptomsDaily(days: Int = 30) async throws -> Envelope<[SymptomDailySummary]> {
        try await getJSON("v1/symptoms/daily?days=\(days)", as: Envelope<[SymptomDailySummary]>.self)
    }

    func fetchSymptomsDiagnostics(days: Int = 30) async throws -> Envelope<[SymptomDiagSummary]> {
        try await getJSON("v1/symptoms/diag?days=\(days)", as: Envelope<[SymptomDiagSummary]>.self)
    }

    func fetchSymptomCodes() async throws -> Envelope<[SymptomCodeDefinition]> {
        try await getJSON("v1/symptoms/codes", as: Envelope<[SymptomCodeDefinition]>.self)
    }

    /// Optional convenience wrappers if your models exist in the app.
    /// Callers can still use `getJSON(_:as:)` directly to avoid type coupling here.
    /*
    public func featuresToday() async throws -> FeaturesToday { try await getJSON("v1/features/today", as: FeaturesToday.self) }
    public func series() async throws -> SeriesResponse { try await getJSON("v1/series", as: SeriesResponse.self) }
    public func forecast() async throws -> ForecastResponse { try await getJSON("v1/forecast", as: ForecastResponse.self) }
    */

    // MARK: - Public upload

    private struct SamplesBatchResponse: Decodable {
        let ok: Bool?
        let received: Int?
    }

    /// Upload in chunks with retry/backoff per chunk and bisect-on-failure (default: 200 rows, 3 tries)
    @discardableResult
    func postSamplesChunked(_ samples: [Sample], chunkSize: Int = 200, maxRetries: Int = 3) async throws -> Bool {
        guard !samples.isEmpty else { return false }

        await preflightHealth()

        var effectiveChunk = chunkSize
        if pathIsConstrained || pathIsExpensive { effectiveChunk = min(chunkSize, 150) } else { effectiveChunk = min(chunkSize, 200) }

        var offset = 0
        var didUpload = false
        if samples.count > effectiveChunk {
            let warm = min(100, samples.count)
            let first = Array(samples[0..<warm])
            let warmUploaded = try await sendChunkWithRescue(first, label: "chunk 1(warm)/?", attemptLimit: maxRetries + 2)
            didUpload = didUpload || warmUploaded
            try? await Task.sleep(nanoseconds: 150_000_000)
            offset = warm
        }

        var index = 1
        while offset < samples.count {
            let end = min(offset + effectiveChunk, samples.count)
            let chunk = Array(samples[offset..<end])
            let uploaded = try await sendChunkWithRescue(chunk, label: "chunk \(index)/?", attemptLimit: maxRetries)
            didUpload = didUpload || uploaded
            try? await Task.sleep(nanoseconds: 60_000_000)
            offset = end
            index += 1
        }
        return didUpload
    }

    private func sendChunkWithRescue(_ chunk: [Sample], label: String, attemptLimit: Int) async throws -> Bool {
        do {
            return try await sendChunk(chunk, label: label, attemptLimit: attemptLimit)
        } catch APIError.server(let code, let body) where code >= 500 {
            logger?("⚠️ \(label) 500: \(body)")
            // retry once with same payload
            do {
                return try await sendChunk(chunk, label: label + " (retry)", attemptLimit: 1)
            } catch {
                return try await bisectAndSend(chunk, label: label)
            }
        }
    }

    private func bisectAndSend(_ chunk: [Sample], label: String) async throws -> Bool {
        guard chunk.count > 1 else {
            // single poison record: log and skip
            if let s = chunk.first {
                logger?("⚠️ Skipping poison record: {type:\(s.type) start:\(s.start_time) value:\(s.value ?? -999)}")
            }
            return false
        }
        let mid = chunk.count / 2
        let left = Array(chunk[..<mid])
        let right = Array(chunk[mid...])
        let leftUploaded = (try? await sendChunkWithRescue(left, label: label + " [L]", attemptLimit: 1)) ?? false
        let rightUploaded = (try? await sendChunkWithRescue(right, label: label + " [R]", attemptLimit: 1)) ?? false
        return leftUploaded || rightUploaded
    }

    private func sendChunk(_ chunk: [Sample], label: String, attemptLimit: Int) async throws -> Bool {
        guard !chunk.isEmpty else { return false }
        // Try /v1/samples/batch first, then /samples/batch for compatibility
        let paths = ["v1/samples/batch", "samples/batch"]

        for (pi, path) in paths.enumerated() {
            var req = makeRequest(path: path)
            let payload = SamplesRawPayload(samples: chunk)
            req.httpBody = try JSONEncoder().encode(payload)

            var attempt = 0
            var lastError: Error?
            while attempt < max(1, attemptLimit) {
                do {
                    logger?("POST \(label) (\(chunk.count) rows) → \(req.url?.absoluteString ?? path)")
                    let (data, resp) = try await session.data(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
                    let body = String(data: data, encoding: .utf8) ?? ""
                    if (200...299).contains(code) {
                        logger?("↩︎ \(code) \(body)")
                        let uploaded = parseReceivedCount(from: data) ?? (chunk.isEmpty ? 0 : chunk.count)
                        return uploaded > 0
                    } else {
                        logger?("↩︎ \(code) \(HTTPURLResponse.localizedString(forStatusCode: code)) \(body)")
                        lastError = APIError.server(code: code, body: body)
                    }
                } catch {
                    lastError = error
                    logger?("POST error: \(error.localizedDescription)")
                }
                attempt += 1
                // backoff 200ms, 600ms, 1200ms with jitter
                let base: UInt64 = 200_000_000
                let delay = base * UInt64(1 << max(0, attempt - 1))
                let jitter = UInt64(Int.random(in: 0..<(Int(base)/3)))
                try? await Task.sleep(nanoseconds: delay + jitter)
            }
            // Exhausted retries on this path → try the next
            if pi == paths.count - 1 { throw lastError ?? APIError.server(code: -1, body: "Upload failed after retries") }
            logger?("⚠️ Switching upload path to '\(paths[pi+1])'")
        }
        return false
    }

    private func parseReceivedCount(from data: Data) -> Int? {
        guard !data.isEmpty else { return nil }
        let decoder = APIClient.tolerantJSONDecoder()
        if let resp = try? decoder.decode(SamplesBatchResponse.self, from: data) {
            return resp.received
        }
        return nil
    }

    private func makeRequest(path: String) -> URLRequest {
        // Ensure we append a clean path segment (strip leading / if present)
        let clean = path.hasPrefix("/") ? String(path.dropFirst()) : path
        var url = baseURL
        url.appendPathComponent(clean)

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !bearer.isEmpty { req.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization") }
        if let uid = devUserId, !uid.isEmpty { req.setValue(uid, forHTTPHeaderField: "X-Dev-UserId") }
        req.timeoutInterval = timeout
        return req
    }

    private func preflightHealth() async {
        guard !didPreflight else { return }
        didPreflight = true
        var healthURL = baseURL
        healthURL.appendPathComponent("health")
        var req = URLRequest(url: healthURL)
        req.httpMethod = "GET"
        req.timeoutInterval = 10
        do {
            let (data, resp) = try await session.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            let body = String(data: data, encoding: .utf8) ?? ""
            logger?("[PF] /health ↩︎ \(code) \(body)")
        } catch let uerr as URLError {
            // Swallow benign lifecycle events
            if uerr.code == .cancelled || uerr.code == .timedOut {
                return
            }
            logger?("[PF] /health warn: \(uerr.code.rawValue) \(uerr.localizedDescription)")
        } catch {
            logger?("[PF] /health warn: \(error.localizedDescription)")
        }
    }
}

// MARK: - Features Diagnostics (diag=1)
extension APIClient {
    func fetchFeaturesDiagnostics(tz: String = "America/Chicago") async throws -> FeaturesTodayDiagEnvelope {
        var components = URLComponents(url: baseURL.appendingPathComponent("v1/features/today"), resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "tz", value: tz),
            URLQueryItem(name: "diag", value: "1")
        ]
        guard let url = components?.url else { throw URLError(.badURL) }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !bearer.isEmpty {
            request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        if let uid = devUserId?.trimmingCharacters(in: .whitespacesAndNewlines), !uid.isEmpty {
            request.setValue(uid, forHTTPHeaderField: "X-Dev-UserId")
        }

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let decoder = APIClient.tolerantJSONDecoder()
        return try decoder.decode(FeaturesTodayDiagEnvelope.self, from: data)
    }
}
