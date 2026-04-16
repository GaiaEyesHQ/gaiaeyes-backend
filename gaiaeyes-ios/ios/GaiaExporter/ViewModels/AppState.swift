
import Foundation

extension Notification.Name {
    static let gaiaBackendDBRecovered = Notification.Name("gaia.backend.db.recovered")
    static let dashboardShouldRefresh = Notification.Name("DashboardShouldRefresh")
}

enum DeveloperAuthDefaults {
    static let baseURL = "https://gaiaeyes-backend.onrender.com"
    static let bearer = "devtoken123"
    static let userId = "e20a3e9e-1fc2-41ad-b6f7-656668310d13"
}

// Helper to decode arbitrary JSON values for ping
private struct AnyDecodable: Decodable, CustomStringConvertible {
    let value: Any
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self.value = "null" }
        else if let b = try? c.decode(Bool.self) { self.value = b }
        else if let i = try? c.decode(Int.self) { self.value = i }
        else if let d = try? c.decode(Double.self) { self.value = d }
        else if let s = try? c.decode(String.self) { self.value = s }
        else { self.value = "<obj>" }
    }
    var description: String { String(describing: value) }
}
import SwiftUI
// MARK: - Symptom POST helpers
private struct SymptomPOSTResponse: Decodable {
    let id: UUID?
    let tsUtc: String?
    enum CodingKeys: String, CodingKey { case id; case tsUtc = "ts_utc" }
}
private struct SymptomEnvelope: Decodable {
    let ok: Bool?
    let data: SymptomPOSTResponse?
    let error: String?
}
private enum LocalSymptomUploadError: Error { case unknownSymptomCode; case server(String) }
import CoreBluetooth
import HealthKit

// MARK: - App State

@MainActor
final class AppState: ObservableObject, BleManagerDelegate, HrSessionDelegate, PolarManagerDelegate {
    // MARK: - Connection / API
    @Published var baseURLString: String = DeveloperAuthDefaults.baseURL {
        didSet {
            let trimmed = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
            UserDefaults.standard.set(trimmed, forKey: "baseURL")
        }
    }
    @Published var bearer: String = "" {
        didSet {
            let trimmed = bearer.trimmingCharacters(in: .whitespacesAndNewlines)
            UserDefaults.standard.set(trimmed, forKey: "bearer")
            warnedAboutAnonymousDevRequest = false
        }
    }
    @Published var userId: String = "" {
        didSet {
            let trimmed = userId.trimmingCharacters(in: .whitespacesAndNewlines)
            UserDefaults.standard.set(trimmed, forKey: "userId")
            warnedAboutAnonymousDevRequest = false
        }
    }
    private var warnedAboutAnonymousDevRequest = false

    // MARK: - UI status + log
    @Published var statusLines: [String] = []
    @Published var log: [String] = []
    @Published var lastLogAppendAt: Date = .distantPast
    @Published var symptomQueueCount: Int = 0
    @Published var backendDBAvailable: Bool = true
    @Published var suspendNonessentialNetworkRefresh: Bool = false

    private var cachedAPIClient: APIClient?
    private var cachedAPIClientSignature: String?

    // MARK: - BLE (CoreBluetooth HR)
    // MARK: - HealthKit
    private let healthStore = HKHealthStore()
    @Published var selectedHealthPermissionKeys: Set<String> = HealthPermissionOption.defaultSelection {
        didSet {
            let normalized = Self.normalizeHealthPermissionKeys(selectedHealthPermissionKeys)
            if normalized != selectedHealthPermissionKeys {
                selectedHealthPermissionKeys = normalized
                return
            }
            selectedHealthPermissionKeysRaw = Self.serializeHealthPermissionKeys(normalized)
        }
    }
    @AppStorage("gaia.healthkit.selected_permission_keys") private var selectedHealthPermissionKeysRaw: String = HealthPermissionOption.defaultStorageValue

    private static func normalizeHealthPermissionKeys(_ keys: Set<String>) -> Set<String> {
        let valid = Set(HealthPermissionOption.allCases.map(\.rawValue))
        return keys.intersection(valid)
    }

    private static func serializeHealthPermissionKeys(_ keys: Set<String>) -> String {
        keys.sorted().joined(separator: ",")
    }

    private static func deserializeHealthPermissionKeys(_ raw: String) -> Set<String> {
        let keys = Set(
            raw.split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        )
        return normalizeHealthPermissionKeys(Set(keys))
    }

    private func makeHealthReadTypes() -> Set<HKObjectType> {
        var types = Set<HKObjectType>()
        let selectedOptions = selectedHealthPermissionKeys.compactMap(HealthPermissionOption.init(rawValue:))
        for option in selectedOptions {
            switch option {
            case .heartRate:
                if let hr = HKObjectType.quantityType(forIdentifier: .heartRate) { types.insert(hr) }
            case .heartRateVariability:
                if let hrv = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { types.insert(hrv) }
            case .sleep:
                if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { types.insert(sleep) }
            case .spo2:
                if let spo2 = HKObjectType.quantityType(forIdentifier: .oxygenSaturation) { types.insert(spo2) }
            case .respiratoryRate:
                if let respiratory = HKObjectType.quantityType(forIdentifier: .respiratoryRate) { types.insert(respiratory) }
            case .restingHeartRate:
                if let restingHR = HKObjectType.quantityType(forIdentifier: .restingHeartRate) { types.insert(restingHR) }
            case .bloodPressure:
                if let sys = HKObjectType.quantityType(forIdentifier: .bloodPressureSystolic) { types.insert(sys) }
                if let dia = HKObjectType.quantityType(forIdentifier: .bloodPressureDiastolic) { types.insert(dia) }
            case .wristTemperature:
                if #available(iOS 16.0, *),
                   let wristTemp = HKObjectType.quantityType(forIdentifier: .appleSleepingWristTemperature) {
                    types.insert(wristTemp)
                }
            case .cycleTracking:
                if let menstrualFlow = HKObjectType.categoryType(forIdentifier: .menstrualFlow) { types.insert(menstrualFlow) }
            case .stepCount:
                if let steps = HKObjectType.quantityType(forIdentifier: .stepCount) { types.insert(steps) }
            }
        }
        return types
    }
    private lazy var ble = BleManager()
    @Published var bleDevices: [CBPeripheral] = []
    @Published var bleConnected: CBPeripheral?
    @Published var bleAutoUpload: Bool = true
    @Published var lastBPM: Int?
    @Published var lastRRTime: Date?
    @Published var lastBlePeripheralUUID: String?

    private var hrSession: HrSession?
    private var hrUploader: HrUploader?

    // Auto‑reconnect window
    private var bleTargetId: UUID?
    private var bleReconnectUntil: Date?

    // MARK: - Polar
    private lazy var polar = PolarManager()
    @AppStorage("polarDeviceId") var polarDeviceId: String = ""   // short ID like 05A2BB3A
    @Published var polarConnectedId: String?
    @Published var polarDeviceName: String?
    @Published var lastEcgSampleAt: Date?
    @Published var isEcgStreaming: Bool = false
    @Published var ecgNote: String?
    private var hrPausedForECG: Bool = false
    @AppStorage("gaia.healthkit.requested_at") var healthkitRequestedAtISO: String = ""
    @AppStorage("gaia.healthkit.last_backfill_at") var lastHealthBackfillAtISO: String = ""

    // Periodic status refresh (e.g., surface BG timestamps)
    private var statusTimer: Timer?

    // MARK: - Init
    init() {
        let defaults = UserDefaults.standard
        if let storedBase = defaults.string(forKey: "baseURL"), !storedBase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            baseURLString = storedBase
        } else {
            defaults.set(baseURLString, forKey: "baseURL")
        }
        if let storedBearer = defaults.string(forKey: "bearer") {
            let trimmed = storedBearer.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.lowercased() == DeveloperAuthDefaults.bearer.lowercased() {
                bearer = ""
                defaults.removeObject(forKey: "bearer")
            } else if !trimmed.isEmpty {
                bearer = trimmed
            } else {
                defaults.set(bearer, forKey: "bearer")
            }
        } else {
            defaults.set(bearer, forKey: "bearer")
        }
        if let storedUser = defaults.string(forKey: "userId") {
            let trimmed = storedUser.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty || trimmed.lowercased() == "anonymous" {
                userId = ""
                defaults.removeObject(forKey: "userId")
            } else if trimmed == DeveloperAuthDefaults.userId && bearer.isEmpty {
                userId = ""
                defaults.removeObject(forKey: "userId")
            } else {
                userId = trimmed
            }
        } else {
            defaults.set(userId, forKey: "userId")
        }

        selectedHealthPermissionKeys = Self.deserializeHealthPermissionKeys(selectedHealthPermissionKeysRaw)

        ble.delegate = self
        polar.delegate = self
        // Refresh visible status + /health flag periodically
        statusTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.updateBackendDBFlag()
                self?.refreshStatus()
            }
        }
        // Run an initial health probe on launch so backendDBAvailable is up‑to‑date
        Task { [weak self] in
            await self?.updateBackendDBFlag()
        }
        // Ensure observers are registered and run a quick delta sweep on launch
        Task {
            try? HealthKitBackgroundSync.shared.registerObservers()
            await HealthKitBackgroundSync.shared.ensurePhase2RecentBackfillIfNeeded()
            await HealthKitBackgroundSync.shared.kickOnce(reason: "app launch")
        }
        HealthKitBackgroundSync.shared.registerAppState(self)
        Task { [weak self] in
            await self?.refreshSymptomQueueCount()
            let token = await AuthManager.shared.validAccessToken()
            let hasAuth = !(token?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
                || !(self?.bearer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
            if hasAuth {
                await self?.flushQueuedSymptoms()
            }
        }
        // One-shot debug: log SpO₂ snapshot from /v1/diag/features on launch
        Task { [weak self] in
            let token = await AuthManager.shared.validAccessToken()
            guard !(token?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true) else { return }
            await self?.debugLogFeaturesSpO2()
        }
    }

    deinit { statusTimer?.invalidate() }

    // MARK: - Logging helpers
    @MainActor func append(_ line: String) {
        log.append(line)
        lastLogAppendAt = Date()
        if log.count > 500 { log.removeFirst(log.count - 500) }
    }
    func clearLog() { Task { @MainActor in self.log.removeAll() } }

    private func readISODate(forKey key: String) -> Date? {
        if let s = UserDefaults.standard.string(forKey: key) {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
        }
        return nil
    }
    private func fmt(_ d: Date) -> String {
        DateFormatter.localizedString(from: d, dateStyle: .none, timeStyle: .short)
    }

    func refreshSymptomQueueCount() async {
        let count = await SymptomLogQueue.shared.count()
        symptomQueueCount = count
    }

    private func effectiveDeveloperUserId() -> String? {
        guard isDeveloperBearer else { return nil }
        let trimmedUserId = userId.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedUserId.isEmpty || trimmedUserId.lowercased() == "anonymous" {
            return nil
        }
        return trimmedUserId
    }

    func enqueueSymptom(_ event: SymptomQueuedEvent) async {
        await SymptomLogQueue.shared.enqueue(event)
        await refreshSymptomQueueCount()
        append("[Symptoms] queued \(event.symptomCode) (severity=\(event.severity ?? -1))")
    }

    func flushQueuedSymptoms(api override: APIClient? = nil) async {
        let queue = SymptomLogQueue.shared
        let pending = await queue.all()
        guard !pending.isEmpty else {
            symptomQueueCount = 0
            return
        }
        _ = override ?? apiWithAuth()
        var sentIds = Set<UUID>()
        for event in pending {
            do {
                let resp = try await self.postSymptomEvent(from: event)
                sentIds.insert(event.id)
                let idText = resp.id?.uuidString ?? "-"
                append("[Symptoms] uploaded \(event.symptomCode) → id=\(idText)")
            } catch LocalSymptomUploadError.unknownSymptomCode {
                appLog("[SYM] using code=OTHER (fallback)")
                append("[SYM] using code=OTHER (fallback)")
                let fallbackEvent = event.replacingSymptomCode(with: SymptomCodeHelper.fallbackCode, keepId: true)
                do {
                    let resp = try await self.postSymptomEvent(from: fallbackEvent)
                    sentIds.insert(fallbackEvent.id)
                    let idText = resp.id?.uuidString ?? "-"
                    append("[Symptoms] uploaded \(fallbackEvent.symptomCode) → id=\(idText)")
                } catch {
                    await queue.replace(id: event.id, with: fallbackEvent)
                    append("[Symptoms] upload failed for \(event.symptomCode): \(error.localizedDescription)")
                    appLog("[SYM] POST queued (offline)")
                }
            } catch {
                append("[Symptoms] upload failed for \(event.symptomCode): \(error.localizedDescription)")
            }
        }
        if !sentIds.isEmpty {
            await queue.remove(ids: sentIds)
            NotificationCenter.default.post(name: .featuresShouldRefresh, object: nil)
            NotificationCenter.default.post(name: .dashboardShouldRefresh, object: nil)
        }
        await refreshSymptomQueueCount()
    }

    // MARK: - API client
    func apiWithAuth() -> APIClient {
        let trimmedBase = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        let storedBearer = bearer.trimmingCharacters(in: .whitespacesAndNewlines)
        let supabaseBearer = AuthManager.shared.supabaseAccessToken?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let trimmedBearer = supabaseBearer.isEmpty ? storedBearer : supabaseBearer
        let trimmedUserId = userId.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedBase = trimmedBase.isEmpty ? "http://127.0.0.1:8000" : trimmedBase
        let clientSignature = "\(normalizedBase)|\(trimmedBearer)"
        let cfg = APIConfig(baseURLString: trimmedBase.isEmpty ? "http://127.0.0.1:8000" : trimmedBase,
                            bearer: trimmedBearer,
                            timeout: 60)
        let client: APIClient
        if let cached = cachedAPIClient, cachedAPIClientSignature == clientSignature {
            client = cached
        } else {
            client = APIClient(config: cfg)
            cachedAPIClient = client
            cachedAPIClientSignature = clientSignature
            append("[NET] client ready base=\(cfg.baseURLString) bearer=\(!trimmedBearer.isEmpty) uid=\(trimmedUserId.isEmpty ? "nil" : trimmedUserId)")
        }
        // Scope only developer-token calls. Supabase JWTs are already account-scoped.
        if supabaseBearer.isEmpty, let eff = effectiveDeveloperUserId() {
            client.devUserId = eff
        } else {
            client.devUserId = nil
        }
        client.bearerProvider = {
            await AuthManager.shared.validAccessToken()
        }
        client.forceBearerRefreshProvider = {
            await AuthManager.shared.forceRefreshAccessToken()
        }
        client.logger = { [weak self] msg in Task { @MainActor in self?.append("[NET] \(msg)") } }
        if developerCredentialsAreMissingUserId && !warnedAboutAnonymousDevRequest {
            append("⚠️ Developer bearer requests need X-Dev-UserId; tap ‘Use Developer Credentials’ in Connection Settings.")
            warnedAboutAnonymousDevRequest = true
        }
        return client
    }

    func applyDeveloperCredentials() {
        baseURLString = DeveloperAuthDefaults.baseURL
        bearer = DeveloperAuthDefaults.bearer
        userId = DeveloperAuthDefaults.userId
        warnedAboutAnonymousDevRequest = false
        append("[NET] Applied developer defaults (X-Dev-UserId=\(DeveloperAuthDefaults.userId))")
    }

    var isDeveloperBearer: Bool {
        let trimmed = bearer.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return trimmed == DeveloperAuthDefaults.bearer.lowercased() || trimmed.contains("gaia-dev")
    }

    var developerCredentialsAreMissingUserId: Bool {
        guard isDeveloperBearer else { return false }
        let trimmed = userId.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty || trimmed.lowercased() == "anonymous"
    }

    // MARK: - Symptoms upload helper (uses raw URLSession)
    private func postSymptomEvent(from event: SymptomQueuedEvent) async throws -> SymptomPOSTResponse {
        let base = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: (base.isEmpty ? "http://127.0.0.1:8000" : base))?.appendingPathComponent("v1/symptoms") else {
            throw LocalSymptomUploadError.server("bad_url")
        }
        let storedBearer = bearer.trimmingCharacters(in: .whitespacesAndNewlines)
        let supabaseBearer = AuthManager.shared.supabaseAccessToken?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let activeBearer = supabaseBearer.isEmpty ? storedBearer : supabaseBearer
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !activeBearer.isEmpty { req.setValue("Bearer \(activeBearer)", forHTTPHeaderField: "Authorization") }
        if supabaseBearer.isEmpty, let eff = effectiveDeveloperUserId() { req.setValue(eff, forHTTPHeaderField: "X-Dev-UserId") }
        appLog("[SYM] POST /v1/symptoms X-Dev-UserId=\(req.value(forHTTPHeaderField: "X-Dev-UserId") ?? "nil") bearerEmpty=\(bearer.isEmpty)")
        struct Body: Encodable {
            let symptom_code: String
            let ts_utc: String?
            let severity: Int?
            let free_text: String?
            let tags: [String]?
        }
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let body = Body(
            symptom_code: event.symptomCode,
            ts_utc: iso.string(from: event.tsUtc),
            severity: event.severity,
            free_text: event.freeText,
            tags: event.tags
        )
        req.httpBody = try JSONEncoder().encode(body)
        // Short request timeout via task cancellation window
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw LocalSymptomUploadError.server("no_http") }
        // Accept 200 even on logical errors; backend envelopes errors in JSON
        if (200..<300).contains(http.statusCode) {
            let dec = JSONDecoder(); dec.keyDecodingStrategy = .convertFromSnakeCase
            if let env = try? dec.decode(SymptomEnvelope.self, from: data) {
                if env.ok == true, let out = env.data { return out }
                let msg = (env.error ?? "upload_failed").lowercased()
                if msg.contains("unknown") && msg.contains("symptom") { throw LocalSymptomUploadError.unknownSymptomCode }
                throw LocalSymptomUploadError.server(env.error ?? "upload_failed")
            } else {
                // Some servers may return bare {id,ts_utc}
                if let out = try? dec.decode(SymptomPOSTResponse.self, from: data) { return out }
                throw LocalSymptomUploadError.server("decode_failed")
            }
        } else {
            let preview = String(data: data.prefix(200), encoding: .utf8) ?? "<non-utf8>"
            throw LocalSymptomUploadError.server("http_\(http.statusCode): \(preview)")
        }
    }

    // MARK: - Status
    func refreshStatus() {
        var rows: [String] = []
        if let dev = bleConnected?.name { rows.append("BLE HR: \(dev)") } else { rows.append("BLE HR: not connected") }
        if let bpm = lastBPM { rows.append("Last BPM: \(bpm)") }
        if let t = lastRRTime {
            let ts = DateFormatter.localizedString(from: t, dateStyle: .none, timeStyle: .short)
            rows.append("Last RR: \(ts)")
        }
        if let pid = polarConnectedId { rows.append("Polar: connected (\(pid))") } else { rows.append("Polar: not connected") }
        if isEcgStreaming {
            rows.append("ECG: streaming")
            if let t = lastEcgSampleAt {
                let ts = DateFormatter.localizedString(from: t, dateStyle: .none, timeStyle: .short)
                rows.append("ECG last sample: \(ts)")
            }
        } else {
            rows.append("ECG: idle")
            if let note = ecgNote, !note.isEmpty {
                rows.append("ECG note: \(note)")
            }
        }
        // BG / uploader timestamps (if any are persisted)
        var bgRows: [String] = []
        if let d = readISODate(forKey: "gaia.bg.lastSweep") { bgRows.append("BG sweep: \(fmt(d))") }
        if let d = readISODate(forKey: "gaia.upload.heart_rate") { bgRows.append("HR upload: \(fmt(d))") }
        if let d = readISODate(forKey: "gaia.upload.step_count") { bgRows.append("Steps upload: \(fmt(d))") }
        if let d = readISODate(forKey: "gaia.upload.spo2") { bgRows.append("SpO₂ upload: \(fmt(d))") }
        if let d = readISODate(forKey: "gaia.upload.sleep") { bgRows.append("Sleep upload: \(fmt(d))") }
        if let d = readISODate(forKey: "gaia.upload.hrv_sdnn") { bgRows.append("HRV upload: \(fmt(d))") }
        if !bgRows.isEmpty {
            rows.append(contentsOf: bgRows)
        }
        Task { @MainActor in self.statusLines = rows }
    }

    // MARK: - Health permissions
    @MainActor func requestHealthPermissions() async -> Bool {
        append("Requesting Health permissions…")
        append("Cycle tracking stays optional. Expanded recovery metrics sync only when your device provides them.")
        let stamp = ISO8601DateFormatter().string(from: Date())
        healthkitRequestedAtISO = stamp
        guard HKHealthStore.isHealthDataAvailable() else {
            append("❌ Health data not available on this device")
            return false
        }
        let toRead = makeHealthReadTypes()
        if toRead.isEmpty {
            append("❌ No Health metrics selected. Choose at least one item or skip for now.")
            return false
        }
        do {
            try await healthStore.requestAuthorization(toShare: [], read: toRead)
            append("✅ Health permissions granted")
            // Register observers and do a one-time sweep
            do {
                try HealthKitBackgroundSync.shared.registerObservers()
                append("✅ Health observers registered")
            } catch {
                append("❌ Observer registration failed: \(error.localizedDescription)")
            }
            await HealthKitBackgroundSync.shared.ensurePhase2RecentBackfillIfNeeded()
            await HealthKitBackgroundSync.shared.kickOnce(reason: "permissions granted")
            return true
        } catch {
            append("❌ Health permission error: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Debug: SpO₂ snapshot from /v1/diag/features
    private struct DiagFeatures: Decodable {
        struct Snapshot: Decodable {
            struct Metrics: Decodable { let spo2_avg: Double? }
            let metrics: Metrics?
        }
        let cache_snapshot_final: Snapshot?
        let mart_snapshot: Snapshot?
    }

    // Lightweight envelope to decode /v1/features/today payload
    private struct FeaturesTodayEnvelope: Decodable {
        struct Payload: Decodable { let spo2_avg: Double? }
        let payload: Payload?
    }

    @MainActor
    func debugLogFeaturesSpO2() async {
        let api = apiWithAuth()
        // 1) Diag snapshots
        do {
            let diag: DiagFeatures = try await api.getJSON("/v1/diag/features", as: DiagFeatures.self)
            let vCache = diag.cache_snapshot_final?.metrics?.spo2_avg
            let vMart  = diag.mart_snapshot?.metrics?.spo2_avg
            if let vCache {
                append("[DEBUG] /v1/diag/features cache.metrics.spo2_avg=\(String(format: "%.2f", vCache))")
            } else {
                append("[DEBUG] /v1/diag/features cache.metrics.spo2_avg=nil")
            }
            if let vMart {
                append("[DEBUG] /v1/diag/features mart.metrics.spo2_avg=\(String(format: "%.2f", vMart))")
            } else {
                append("[DEBUG] /v1/diag/features mart.metrics.spo2_avg=nil")
            }
        } catch {
            append("❌ SpO₂ debug (diag) failed: \(error.localizedDescription)")
        }
        // 2) Features Today payload
        do {
            let today: FeaturesTodayEnvelope = try await api.getJSON("/v1/features/today", as: FeaturesTodayEnvelope.self)
            if let v = today.payload?.spo2_avg {
                append("[DEBUG] /v1/features/today payload.spo2_avg=\(String(format: "%.2f", v))")
            } else {
                append("[DEBUG] /v1/features/today payload.spo2_avg=nil")
            }
        } catch {
            append("❌ SpO₂ debug (features/today) failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Ping API
    @MainActor func pingAPI() async {
        append("Pinging API /health…")
        let api = apiWithAuth()
        do {
            // Try to decode as a simple JSON object like {"ok":true} or {"status":"ok"}
            let resp: [String: AnyDecodable] = try await api.getJSON("health", as: [String: AnyDecodable].self)
            // Render a compact preview for the log
            let preview = resp.map { "\($0.key)=\($0.value.description)" }.joined(separator: " ")
            append("[API] ↩︎ 200 \(preview)")
        } catch {
            append("❌ Ping error: \(error.localizedDescription)")
        }
    }

    // MARK: - Backend DB availability
    @MainActor func updateBackendDBFlag() async {
        let api = apiWithAuth()
        do {
            // Lightweight /health probe with short timeout and 1 retry
            let resp: [String: AnyDecodable] = try await api.getJSON("health", as: [String: AnyDecodable].self)
            let dbVal = resp["db"].map { ($0.value as? Bool) ?? true } ?? true
            let was = backendDBAvailable
            backendDBAvailable = dbVal
            append("[API] /health db=\(dbVal)")
            // If DB recovered, signal the UI to refresh immediately
            if was == false && dbVal == true {
                append("[API] DB recovered; triggering UI refresh")
                NotificationCenter.default.post(name: .gaiaBackendDBRecovered, object: nil)
            }
        } catch is CancellationError {
            append("[API] /health probe cancelled; leaving db=\(backendDBAvailable)")
        } catch let uerr as URLError where [
            .cancelled,
            .timedOut,
            .networkConnectionLost,
            .cannotConnectToHost,
            .notConnectedToInternet,
            .cannotFindHost,
            .dnsLookupFailed,
        ].contains(uerr.code) {
            append("[API] /health probe transient failure; leaving db=\(backendDBAvailable): \(uerr.localizedDescription)")
        } catch {
            // If probe fails, assume unavailable until next successful check
            backendDBAvailable = false
            append("[API] /health probe failed; assuming db=false: \(error.localizedDescription)")
        }
    }

    @MainActor
    func fetchSpaceVisuals() async -> SpaceVisualsPayload? {
        do {
            let payload: SpaceVisualsPayload = try await apiWithAuth().getJSON("/v1/space/visuals", as: SpaceVisualsPayload.self)
            if let imgs = payload.images, !imgs.isEmpty {
                append("[UI] space visuals updated: images=\(imgs.count)")
                return payload
            } else if let items = payload.items, !items.isEmpty {
                append("[UI] space visuals updated via items: count=\(items.count)")
                return payload
            } else {
                append("[UI] space visuals empty; keeping last snapshot")
                return nil
            }
        } catch {
            append("[UI] space visuals decode failed: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Sync stubs (keep buttons working)
    @MainActor func syncSteps7d() async { append("Sync Steps (7d)…") }
    @MainActor func syncHR7d() async { append("Sync HR (7d)…") }
    @MainActor func syncHRV7d() async { append("Sync HRV (7d)…") }
    @MainActor func syncSpO27d() async { append("Sync SpO₂ (7d)…") }
    @MainActor func syncBP30d() async { append("Sync BP (30d)…") }
    @MainActor func syncSleep7d() async {
        append("Sync Sleep (7d)…")
        let exporter = HealthKitSleepExporter()
        do {
            try await exporter.requestAuthorization()
            let api = apiWithAuth()
            let uploadUserId = AuthManager.shared.currentSupabaseUserId() ?? userId
            let uploaded = try await exporter.syncSleep(lastDays: 7, api: api, userId: uploadUserId)
            append("[SLEEP] uploaded \(uploaded) segments (7d)")
            // stamp last upload time so Status shows it
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            UserDefaults.standard.set(f.string(from: Date()), forKey: "gaia.upload.sleep")
            refreshStatus()
        } catch {
            append("❌ Sleep sync error: \(error.localizedDescription)")
        }
    }

    @MainActor
    func syncHealthBackfillLast30Days(
        onProgress: (@MainActor (String) -> Void)? = nil
    ) async -> HealthBackfillSummary {
        append("Sync HealthKit last 30 days…")
        guard HKHealthStore.isHealthDataAvailable() else {
            append("❌ Health data not available on this device")
            return HealthBackfillSummary(totalMetrics: 0, failedMetrics: ["health_data_unavailable"])
        }
        let start = Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date(timeIntervalSinceNow: -(30 * 24 * 60 * 60))
        let summary = await HealthKitBackgroundSync.shared.forceBackfill(
            since: start,
            onProgress: { message in
                await MainActor.run {
                    onProgress?(message)
                }
            }
        )
        if summary.didUploadAnyData || summary.isSuccessful {
            lastHealthBackfillAtISO = ISO8601DateFormatter().string(from: Date())
        }
        if summary.didUploadAnyData {
            append("✅ Last 30 days import finished")
        } else if summary.isSuccessful {
            append("✅ Last 30 days import finished (no importable data found)")
        } else {
            append("⚠️ Last 30 days import finished with issues")
        }
        refreshStatus()
        return summary
    }

    // MARK: - BLE controls
    func startBleScan() { ble.startScan() }
    func stopBleScan() { ble.stopScan() }
    func refreshBleDevices() { bleDevices = ble.devices }
    func connectBle(to p: CBPeripheral) { ble.connect(to: p) }
    func disconnectBle() {
        ble.disconnect()
        bleConnected = nil
        hrSession = nil
        hrUploader = nil
    }

    // Prefer reconnecting to the last known peripheral UUID; fall back to scanning
    @MainActor private func attemptAutoReconnectHR() {
        if let uuidStr = lastBlePeripheralUUID, let uuid = UUID(uuidString: uuidStr) {
            append("[BLE] Trying known‑UUID reconnect…")
            ble.connectToKnown(uuid: uuid)
        } else {
            startBleScan()
        }
    }

    // MARK: - BleManagerDelegate
    nonisolated func bleManagerDidUpdateDevices(_ devices: [CBPeripheral]) {
        Task { @MainActor in
            self.bleDevices = devices
            if let until = self.bleReconnectUntil, Date() < until, let target = self.bleTargetId {
                if let match = devices.first(where: { $0.identifier == target }) {
                    self.append("[BLE] Auto‑reconnect to \(match.name ?? "Unknown")")
                    self.connectBle(to: match)
                    self.bleReconnectUntil = nil
                    self.stopBleScan()
                }
            } else if self.bleReconnectUntil != nil {
                self.bleReconnectUntil = nil
                self.stopBleScan()
            }
        }
    }

    nonisolated func bleManagerDidConnect(_ peripheral: CBPeripheral) {
        Task { @MainActor in
            self.bleConnected = peripheral
            self.append("[BLE] Connected to \(peripheral.name ?? "Unknown")")
            let uuidStr = peripheral.identifier.uuidString
            self.lastBlePeripheralUUID = uuidStr
            self.append("[BLE] Peripheral UUID: \(uuidStr)")
            self.bleTargetId = peripheral.identifier
            self.bleReconnectUntil = nil
            // Start HR session
            let s = HrSession(peripheral: peripheral)
            s.delegate = self
            self.hrSession = s
            self.hrUploader = HrUploader(api: self.apiWithAuth(), userId: self.userId)
        }
    }

    nonisolated func bleManagerDidDisconnect(_ peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            self.append("[BLE] Disconnected: \(error?.localizedDescription ?? "OK")")
            self.bleConnected = nil
            self.hrSession = nil
            self.hrUploader = nil
            if self.bleAutoUpload {
                self.bleReconnectUntil = Date().addingTimeInterval(20)
                self.attemptAutoReconnectHR()
            }
        }
    }

    nonisolated func bleManagerLog(_ msg: String) { Task { @MainActor in self.append("[BLE] \(msg)") } }

    nonisolated func bleManagerDidReceiveHeartRate(_ bpm: Int, rr: [Double]?, from peripheral: CBPeripheral) {
        // Forward Polar/HRM heart-rate stream into the session (RR provided in seconds)
        Task { @MainActor in
            self.hrSession?.ingestHR(bpm: bpm, rrSec: rr)
        }
    }

    // MARK: - HrSessionDelegate
    nonisolated func hrSessionLog(_ msg: String) { Task { @MainActor in self.append("[HR] \(msg)") } }
    nonisolated func hrSessionDidParse(hrBpm: Int?, rrMs: [Int]) {
        Task { @MainActor in
            self.append("[HR] bpm=\(hrBpm.map(String.init) ?? "-") rrCount=\(rrMs.count)")
            if let hr = hrBpm { self.lastBPM = hr }
            if !rrMs.isEmpty { self.lastRRTime = Date() }
            guard self.bleAutoUpload, let up = self.hrUploader else { return }
            Task { await up.upload(hrBpm: hrBpm, rrMs: rrMs) }
        }
    }

    // Derive the Polar short device ID (e.g., 05A2BB3A) from the current BLE HR peripheral name
    // and store it into @AppStorage("polarDeviceId"). Useful when the user connected HR first.
    @MainActor func setPolarIdFromBleName() {
        guard let name = bleConnected?.name?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty else {
            append("❌ No BLE HR device connected; cannot extract Polar ID")
            return
        }
        // Heuristic: take the last whitespace-separated token that looks like 6–10 hex chars
        let parts = name.split(separator: " ")
        if let last = parts.last, last.count >= 6, last.count <= 10,
           last.allSatisfy({ ("0"..."9").contains($0) || ("A"..."F").contains($0) }) {
            let id = String(last)
            polarDeviceId = id
            append("[Polar] Set Device ID → \(id) from BLE name \(name)")
        } else {
            append("❌ Could not parse Polar short ID from BLE name: \(name)")
        }
    }

    // Convenience: derive Polar ID from BLE name and attempt a Polar connect
    @MainActor func quickPolarConnectViaBLE() {
        setPolarIdFromBleName()
        let id = polarDeviceId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else { return }
        connectPolar()
    }

    // MARK: - Polar controls with preflight pause/resume
    @MainActor func connectPolar() {
        let id = polarDeviceId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else { append("❌ Set 'Device ID' to connect") ; return }
        polar.connect(deviceId: id)
    }
    @MainActor func disconnectPolar() { polar.disconnect() }

    @MainActor func startPolarEcg() {
        append("[ECG] preflight… pausing GATT HR and trying Polar ECG")
        if bleConnected != nil { hrPausedForECG = true; disconnectBle() }
        let uploader = EcgUploader(api: apiWithAuth(), userId: userId)
        polar.startEcgStreaming(uploader: uploader)
        Task { @MainActor in
            do { try await Task.sleep(nanoseconds: 6_000_000_000) } catch {}
            if self.isEcgStreaming == false {
                self.append("[ECG] not running after preflight window; resuming GATT HR")
                if self.hrPausedForECG {
                    self.hrPausedForECG = false
                    self.bleReconnectUntil = Date().addingTimeInterval(20)
                    self.attemptAutoReconnectHR()
                }
            }
        }
    }

    @MainActor func stopPolarEcg() {
        polar.stopEcgStreaming()
        if hrPausedForECG {
            hrPausedForECG = false
            append("[ECG] stopped; resuming GATT HR auto‑reconnect")
            bleReconnectUntil = Date().addingTimeInterval(20)
            attemptAutoReconnectHR()
        }
    }

    // MARK: - PolarManagerDelegate
    nonisolated func polarLog(_ msg: String) {
        Task { @MainActor in
            self.append(msg)
            // Capture notable ECG messages for the Status panel
            let lower = msg.lowercased()
            if lower.contains("[ecg]") {
                if lower.contains("waiting for sdk ecg feature ready") {
                    self.ecgNote = "waiting for ECG feature"
                } else if lower.contains("settings received; enumerating") {
                    self.ecgNote = "trying settings"
                } else if lower.contains("trying sr=") {
                    // keep last tried tuple
                    self.ecgNote = msg.replacingOccurrences(of: "[Polar] ", with: "")
                } else if lower.contains("combo failed") {
                    self.ecgNote = "combo failed; trying next"
                } else if lower.contains("all combinations failed") {
                    self.ecgNote = "no supported ECG setting"
                } else if lower.contains("streaming started") {
                    self.ecgNote = nil
                }
            }
        }
    }
    nonisolated func polarDidConnect(deviceId: String, name: String?) {
        Task { @MainActor in
            self.append("[Polar] Connected \(deviceId)")
            self.polarConnectedId = deviceId
            self.polarDeviceName = name
        }
    }
    nonisolated func polarDidDisconnect(deviceId: String, error: Error?) {
        Task { @MainActor in
            self.append("[Polar] Disconnected \(deviceId): \(error?.localizedDescription ?? "OK")")
            self.polarConnectedId = nil
            self.isEcgStreaming = false
        }
    }
    nonisolated func polarEcgDidStart()  { Task { @MainActor in self.isEcgStreaming = true; self.lastEcgSampleAt = Date(); self.ecgNote = nil; self.append("[ECG] streaming started"); self.hrPausedForECG = false } }
    nonisolated func polarEcgDidStop()   { Task { @MainActor in self.isEcgStreaming = false; self.lastEcgSampleAt = nil; self.append("[ECG] streaming stopped"); if self.hrPausedForECG { self.hrPausedForECG = false; self.bleReconnectUntil = Date().addingTimeInterval(20); self.attemptAutoReconnectHR() } } }
}
