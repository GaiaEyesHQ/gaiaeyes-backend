//
//  HealthKitBackgroundSync.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/2/25.
//

import Foundation
import HealthKit
import BackgroundTasks

extension Notification.Name {
    static let featuresShouldRefresh = Notification.Name("FeaturesShouldRefresh")
}

struct HealthBackfillSummary: Sendable {
    let totalMetrics: Int
    var completedMetrics: Int = 0
    var uploadedMetrics: Int = 0
    var uploadedRows: Int = 0
    var failedMetrics: [String] = []
    var timedOutMetrics: [String] = []

    var didUploadAnyData: Bool { uploadedRows > 0 }
    var isSuccessful: Bool { failedMetrics.isEmpty && timedOutMetrics.isEmpty }

    var userFacingMessage: String {
        if didUploadAnyData {
            return "Imported \(uploadedRows) HealthKit rows across \(uploadedMetrics) signals."
        }
        if isSuccessful {
            return "Gaia checked the last 30 days, but there was no importable Health data yet."
        }
        if !timedOutMetrics.isEmpty {
            let labels = timedOutMetrics.joined(separator: ", ")
            return "Import took longer than expected on \(labels). You can continue and retry from Settings."
        }
        return "Some Health data could not be imported. You can continue and retry from Settings."
    }
}

private struct HealthBackfillMetricResult: Sendable {
    let collectedCount: Int
    let uploadedRows: Int
    let failureDescription: String?

    var didUploadAnyData: Bool { uploadedRows > 0 }
}

private typealias AnchoredQueryContinuation = CheckedContinuation<(HKQueryAnchor?, [HKSample], Bool), Error>
private typealias SampleQueryContinuation = CheckedContinuation<[HKSample], Error>

private struct HealthKitQueryTimeoutError: LocalizedError, Sendable {
    var errorDescription: String? {
        "The HealthKit query took longer than expected."
    }
}

private final class HealthKitAnchoredQueryBox: @unchecked Sendable {
    private let lock = NSLock()
    private var query: HKQuery?
    private var continuation: AnchoredQueryContinuation?
    private var isResolved = false

    func prepare(_ query: HKQuery, continuation: AnchoredQueryContinuation) {
        lock.lock()
        self.query = query
        self.continuation = continuation
        lock.unlock()
    }

    func complete(samples: [HKSample]?, newAnchor: HKQueryAnchor?, limit: Int, error: Error?) {
        lock.lock()
        guard !isResolved else {
            lock.unlock()
            return
        }
        isResolved = true
        let continuation = self.continuation
        self.continuation = nil
        query = nil
        lock.unlock()

        guard let continuation else { return }
        if let error {
            continuation.resume(throwing: error)
            return
        }
        let sorted = (samples ?? []).sorted { $0.startDate < $1.startDate }
        continuation.resume(returning: (newAnchor, sorted, (samples?.count ?? 0) == limit))
    }

    func cancel(using store: HKHealthStore) {
        lock.lock()
        guard !isResolved else {
            lock.unlock()
            return
        }
        isResolved = true
        let query = self.query
        let continuation = self.continuation
        self.query = nil
        self.continuation = nil
        lock.unlock()
        if let query {
            store.stop(query)
        }
        continuation?.resume(throwing: CancellationError())
    }
}

private final class HealthKitSampleQueryBox: @unchecked Sendable {
    private let lock = NSLock()
    private var query: HKQuery?
    private var continuation: SampleQueryContinuation?
    private var isResolved = false

    func prepare(_ query: HKQuery, continuation: SampleQueryContinuation) {
        lock.lock()
        self.query = query
        self.continuation = continuation
        lock.unlock()
    }

    func complete(samples: [HKSample]?, error: Error?) {
        lock.lock()
        guard !isResolved else {
            lock.unlock()
            return
        }
        isResolved = true
        let continuation = self.continuation
        self.continuation = nil
        query = nil
        lock.unlock()

        guard let continuation else { return }
        if let error {
            continuation.resume(throwing: error)
            return
        }
        let sorted = (samples ?? []).sorted { $0.startDate < $1.startDate }
        continuation.resume(returning: sorted)
    }

    func cancel(using store: HKHealthStore, error: Error = CancellationError()) {
        lock.lock()
        guard !isResolved else {
            lock.unlock()
            return
        }
        isResolved = true
        let query = self.query
        let continuation = self.continuation
        self.query = nil
        self.continuation = nil
        lock.unlock()
        if let query {
            store.stop(query)
        }
        continuation?.resume(throwing: error)
    }
}

private actor FeaturesRefreshDebouncer {
    private var isRunning = false
    private var pending = false

    func schedule(fetch: @escaping () async -> Void) async {
        pending = true
        guard !isRunning else { return }
        isRunning = true
        Task { await run(fetch: fetch) }
    }

    private func run(fetch: @escaping () async -> Void) async {
        while true {
            pending = false
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            await MainActor.run {
                NotificationCenter.default.post(name: .featuresShouldRefresh, object: nil)
            }
            await fetch()
            if !pending { break }
        }
        isRunning = false
    }
}

private actor ProcessingGate {
    private var running: Set<String> = []
    func runOnce(key: String, op: @escaping () async -> Void) async {
        guard !running.contains(key) else { return }
        running.insert(key)
        await op()
        running.remove(key)
    }
}

private actor Phase2BackfillState {
    private var inProgress = false

    func beginIfNeeded() -> Bool {
        guard !inProgress else { return false }
        inProgress = true
        return true
    }

    func end() {
        inProgress = false
    }

    func isInProgress() -> Bool {
        inProgress
    }
}

final class HealthKitBackgroundSync {
    static let shared = HealthKitBackgroundSync()
    private static let phase2BackfillVersion = 1
    private static let phase2BackfillMarkerKey = "gaia.hk.phase2BackfillVersion"

    private static func isoString(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    private let healthStore = HKHealthStore()
    private let anchorStore = AnchorStore()
    private let featuresRefresher = FeaturesRefreshDebouncer()
    private let processingGate = ProcessingGate()
    private let phase2BackfillState = Phase2BackfillState()
    @MainActor private weak var appState: AppState?
    private var didRegisterObservers = false
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    @MainActor private var lastKickAt: Date? = nil

    private func diagnosticsKey(_ prefix: String, metric: String) -> String {
        "gaia.hk.\(prefix).\(metric)"
    }

    private func setDiagnosticsValue(_ value: String?, prefix: String, metric: String) {
        let key = diagnosticsKey(prefix, metric: metric)
        let defaults = UserDefaults.standard
        if let value, !value.isEmpty {
            defaults.set(value, forKey: key)
        } else {
            defaults.removeObject(forKey: key)
        }
    }

    private func setDiagnosticsDate(_ date: Date, prefix: String, metric: String) {
        setDiagnosticsValue(Self.isoString(date), prefix: prefix, metric: metric)
    }

    private func recordObserverEvent(for metric: String, date: Date = Date()) {
        setDiagnosticsDate(date, prefix: "observer_event", metric: metric)
    }

    private func recordBackgroundDeliveryStatus(for metric: String, enabled: Bool, error: String? = nil) {
        setDiagnosticsValue(enabled ? "enabled" : "failed", prefix: "bg_delivery_status", metric: metric)
        setDiagnosticsDate(Date(), prefix: "bg_delivery_checked_at", metric: metric)
        setDiagnosticsValue(error?.trimmingCharacters(in: .whitespacesAndNewlines), prefix: "bg_delivery_error", metric: metric)
    }

    private func recordBackgroundDeliverySkipped(for metric: String, reason: String) {
        setDiagnosticsValue("skipped", prefix: "bg_delivery_status", metric: metric)
        setDiagnosticsDate(Date(), prefix: "bg_delivery_checked_at", metric: metric)
        setDiagnosticsValue(reason, prefix: "bg_delivery_error", metric: metric)
    }

    private func recordAnchorAdvance(for metric: String, date: Date = Date()) {
        setDiagnosticsDate(date, prefix: "anchor_advanced", metric: metric)
    }

    private func recordImportedSampleMetadata(for metric: String, samples: [HKSample]) {
        guard let latest = samples.max(by: { $0.endDate < $1.endDate }) else { return }
        setDiagnosticsDate(latest.endDate, prefix: "last_sample", metric: metric)
        let sourceName = latest.sourceRevision.source.name.trimmingCharacters(in: .whitespacesAndNewlines)
        setDiagnosticsValue(sourceName.isEmpty ? nil : sourceName, prefix: "last_source", metric: metric)
        UserDefaults.standard.set(ISO8601DateFormatter().string(from: Date()), forKey: "gaia.healthkit.read_verified_at")
        UserDefaults.standard.removeObject(forKey: "gaia.healthkit.read_unavailable_at")
    }

    // Types
    private var hrType  = HKObjectType.quantityType(forIdentifier: .heartRate)!
    private var spo2Type = HKObjectType.quantityType(forIdentifier: .oxygenSaturation)!
    private var stepsType = HKObjectType.quantityType(forIdentifier: .stepCount)!
    private var hrvType = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!
    private var respiratoryRateType = HKObjectType.quantityType(forIdentifier: .respiratoryRate)
    private var restingHeartRateType = HKObjectType.quantityType(forIdentifier: .restingHeartRate)
    private var bpType = HKObjectType.correlationType(forIdentifier: .bloodPressure)!
    private var sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!
    private var menstrualFlowType = HKObjectType.categoryType(forIdentifier: .menstrualFlow)
    private var temperatureDeviationType: HKQuantityType? {
        if #available(iOS 16.0, *) {
            return HKObjectType.quantityType(forIdentifier: .appleSleepingWristTemperature)
        }
        return nil
    }

    private enum InteractiveBackfillMetric: CaseIterable {
        case heartRate
        case spo2
        case hrv
        case respiratoryRate
        case restingHeartRate
        case temperatureDeviation
        case bloodPressure
        case sleep
        case menstrualFlow

        var key: String {
            switch self {
            case .heartRate: return "heart_rate"
            case .spo2: return "spo2"
            case .hrv: return "hrv_sdnn"
            case .respiratoryRate: return "respiratory_rate"
            case .restingHeartRate: return "resting_heart_rate"
            case .temperatureDeviation: return "temperature_deviation"
            case .bloodPressure: return "blood_pressure"
            case .sleep: return "sleep_stage"
            case .menstrualFlow: return "menstrual_flow"
            }
        }

        var label: String {
            switch self {
            case .heartRate: return "heart rate"
            case .spo2: return "SpO2"
            case .hrv: return "HRV"
            case .respiratoryRate: return "respiratory rate"
            case .restingHeartRate: return "resting heart rate"
            case .temperatureDeviation: return "temperature deviation"
            case .bloodPressure: return "blood pressure"
            case .sleep: return "sleep"
            case .menstrualFlow: return "cycle history"
            }
        }

    }

    // Register observers
    func registerObservers() throws {
        guard !didRegisterObservers else {
            appLog("[HK] registerObservers: skipped (already registered)")
            return
        }
        didRegisterObservers = true
        try registerObserver(for: hrType, key: "heart_rate")
        try registerObserver(for: spo2Type, key: "spo2")
        try registerObserver(for: stepsType, key: "step_count")
        try registerObserver(for: hrvType, key: "hrv_sdnn")
        try registerObserver(for: bpType, key: "blood_pressure")
        try registerObserver(for: sleepType, key: "sleep_stage")
        if let respiratoryRateType {
            try registerObserver(for: respiratoryRateType, key: "respiratory_rate")
        }
        if let restingHeartRateType {
            try registerObserver(for: restingHeartRateType, key: "resting_heart_rate")
        }
        if let temperatureDeviationType {
            try registerObserver(for: temperatureDeviationType, key: "temperature_deviation")
        }
        if let menstrualFlowType {
            try registerObserver(for: menstrualFlowType, key: "menstrual_flow")
        }

        healthStore.enableBackgroundDelivery(for: hrType, frequency: .immediate) { ok, err in
            self.recordBackgroundDeliveryStatus(for: "heart_rate", enabled: ok, error: err?.localizedDescription)
            appLog("[HK] bg delivery heart_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
        }
        healthStore.enableBackgroundDelivery(for: spo2Type, frequency: .immediate) { ok, err in
            self.recordBackgroundDeliveryStatus(for: "spo2", enabled: ok, error: err?.localizedDescription)
            appLog("[HK] bg delivery spo2: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
        }
        healthStore.enableBackgroundDelivery(for: stepsType, frequency: .immediate) { ok, err in
            self.recordBackgroundDeliveryStatus(for: "step_count", enabled: ok, error: err?.localizedDescription)
            appLog("[HK] bg delivery step_count: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
        }
        healthStore.enableBackgroundDelivery(for: hrvType, frequency: .immediate) { ok, err in
            self.recordBackgroundDeliveryStatus(for: "hrv_sdnn", enabled: ok, error: err?.localizedDescription)
            appLog("[HK] bg delivery hrv_sdnn: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
        }
        // Blood pressure background delivery is not supported by HealthKit.
        recordBackgroundDeliverySkipped(for: "blood_pressure", reason: "not supported")
        appLog("[HK] bg delivery blood_pressure: skipped (not supported)")
        healthStore.enableBackgroundDelivery(for: sleepType, frequency: .immediate) { ok, err in
            self.recordBackgroundDeliveryStatus(for: "sleep_stage", enabled: ok, error: err?.localizedDescription)
            appLog("[HK] bg delivery sleep_stage: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
        }
        if let respiratoryRateType {
            healthStore.enableBackgroundDelivery(for: respiratoryRateType, frequency: .immediate) { ok, err in
                self.recordBackgroundDeliveryStatus(for: "respiratory_rate", enabled: ok, error: err?.localizedDescription)
                appLog("[HK] bg delivery respiratory_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
            }
        }
        if let restingHeartRateType {
            healthStore.enableBackgroundDelivery(for: restingHeartRateType, frequency: .immediate) { ok, err in
                self.recordBackgroundDeliveryStatus(for: "resting_heart_rate", enabled: ok, error: err?.localizedDescription)
                appLog("[HK] bg delivery resting_heart_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
            }
        }
        if let temperatureDeviationType {
            healthStore.enableBackgroundDelivery(for: temperatureDeviationType, frequency: .immediate) { ok, err in
                self.recordBackgroundDeliveryStatus(for: "temperature_deviation", enabled: ok, error: err?.localizedDescription)
                appLog("[HK] bg delivery temperature_deviation: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
            }
        }
        if let menstrualFlowType {
            healthStore.enableBackgroundDelivery(for: menstrualFlowType, frequency: .immediate) { ok, err in
                self.recordBackgroundDeliveryStatus(for: "menstrual_flow", enabled: ok, error: err?.localizedDescription)
                appLog("[HK] bg delivery menstrual_flow: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")")
            }
        }
    }

    private func registerObserver(for type: HKSampleType, key: String) throws {
        let query = HKObserverQuery(sampleType: type, predicate: nil) { [weak self] _, completion, error in
            guard let self else { completion(); return }
            if let error = error { appLog("Observer error \(key): \(error.localizedDescription)"); completion(); return }
            self.recordObserverEvent(for: key)
            Task { [weak self] in
                guard let self else { return }
                guard self.passiveHealthSyncAllowed() else {
                    appLog("[HK] observer \(key): skipped until account onboarding is complete")
                    completion()
                    return
                }
                await self.processingGate.runOnce(key: key, op: {
                    do {
                        if type.isEqual(self.sleepType) {
                            try await self.processSleepDeltas(anchorKey: key)
                        } else if let menstrualFlowType = self.menstrualFlowType, type.isEqual(menstrualFlowType) {
                            try await self.processCycleDeltas(anchorKey: key)
                        } else {
                            try await self.processDeltas(for: type, anchorKey: key)
                        }
                    } catch {
                        appLog("Process delta error \(key): \(error.localizedDescription)")
                    }
                    completion()
                })
            }
        }
        healthStore.execute(query)
    }

    // Process new samples
    private func processDeltas(for type: HKSampleType, anchorKey: String) async throws {
        var anchor = anchorStore.anchor(forKey: anchorKey)
        let seedStart = anchor == nil ? anchorStore.seedStart(forKey: anchorKey) : nil
        if let seedStart {
            appLog("[HK] resuming \(anchorKey) deltas from seed \(iso.string(from: seedStart))")
        }
        let pred = HKQuery.predicateForSamples(withStart: seedStart ?? Date.distantPast, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        var collected: [HKSample] = []
        var done = false

        while !done {
            let (newAnchor, batch, more) = try await anchoredQuery(type: type, predicate: pred, anchor: anchor, limit: 500, sort: sort)
            anchor = newAnchor
            if !batch.isEmpty { collected.append(contentsOf: batch) }
            done = !more
        }

        guard !collected.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        var samples: [Sample] = []
        for s in collected {
            if let q = s as? HKQuantitySample {
                if matchesQuantityType(q, type: hrType) {
                    let bpm = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
                    guard bpm.isFinite, bpm >= 20, bpm <= 250 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "heart_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: bpm, unit: "bpm", value_text: nil))
                } else if matchesQuantityType(q, type: spo2Type) {
                    let pct = q.quantity.doubleValue(for: HKUnit.percent()) * 100.0
                    guard pct.isFinite, pct >= 50, pct <= 100 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "spo2", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: pct, unit: "%", value_text: nil))
                } else if matchesQuantityType(q, type: stepsType) {
                    let cnt = q.quantity.doubleValue(for: HKUnit.count())
                    guard cnt.isFinite, cnt >= 0 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "step_count", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: cnt, unit: "count", value_text: nil))
                } else if matchesQuantityType(q, type: hrvType) {
                    let ms = q.quantity.doubleValue(for: HKUnit.secondUnit(with: .milli))
                    guard ms.isFinite, ms >= 0, ms <= 600 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "hrv_sdnn", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: ms, unit: "ms", value_text: nil))
                } else if matchesQuantityType(q, type: respiratoryRateType) {
                    let breathsPerMinute = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
                    guard breathsPerMinute.isFinite, breathsPerMinute >= 4, breathsPerMinute <= 80 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "respiratory_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: breathsPerMinute, unit: "br/min", value_text: nil))
                } else if matchesQuantityType(q, type: restingHeartRateType) {
                    let bpm = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
                    guard bpm.isFinite, bpm >= 20, bpm <= 180 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "resting_heart_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: bpm, unit: "bpm", value_text: nil))
                } else if matchesQuantityType(q, type: temperatureDeviationType) {
                    let deltaC = q.quantity.doubleValue(for: HKUnit.degreeCelsius())
                    guard deltaC.isFinite, deltaC >= -10, deltaC <= 10 else { continue }
                    samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "temperature_deviation", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate), value: deltaC, unit: "degC", value_text: "apple_sleeping_wrist_temperature"))
                }
            } else if let c = s as? HKCorrelation, c.correlationType == bpType {
                let systolicType  = HKObjectType.quantityType(forIdentifier: .bloodPressureSystolic)!
                let diastolicType = HKObjectType.quantityType(forIdentifier: .bloodPressureDiastolic)!
                for obj in c.objects.compactMap({ $0 as? HKQuantitySample }) {
                    if obj.quantityType == systolicType {
                        let mmHg = obj.quantity.doubleValue(for: HKUnit.millimeterOfMercury())
                        guard mmHg.isFinite, mmHg >= 40, mmHg <= 260 else { continue }
                        samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "blood_pressure_systolic", start_time: iso.string(from: obj.startDate), end_time: iso.string(from: obj.endDate), value: mmHg, unit: "mmHg", value_text: nil))
                    } else if obj.quantityType == diastolicType {
                        let mmHg = obj.quantity.doubleValue(for: HKUnit.millimeterOfMercury())
                        guard mmHg.isFinite, mmHg >= 30, mmHg <= 180 else { continue }
                        samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "blood_pressure_diastolic", start_time: iso.string(from: obj.startDate), end_time: iso.string(from: obj.endDate), value: mmHg, unit: "mmHg", value_text: nil))
                    }
                }
            }
        }
        logQuantityMapping(anchorKey: anchorKey, collected: collected, mappedCount: samples.count)
        prioritizeRecentUploads(anchorKey: anchorKey, samples: &samples)

        guard !samples.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        let api = buildAPI()
        do {
            let chunkSize = (anchorKey == "heart_rate" ? 100 : 200)
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: chunkSize)
            let windowStart = samples.map { $0.start_time }.min() ?? "-"
            let windowEnd = samples.map { $0.end_time }.max() ?? "-"
            appLog("[HK-UP] \(anchorKey) rows=\(samples.count) window=\(windowStart)..\(windowEnd)")
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
                recordImportedSampleMetadata(for: anchorKey, samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:\(anchorKey)")
            }
        } catch {
            appLog("Upload error \(anchorKey): \(error.localizedDescription)")
        }
    }

    private func processSleepDeltas(anchorKey: String) async throws {
        var anchor = anchorStore.anchor(forKey: anchorKey)
        let pred  = HKQuery.predicateForSamples(withStart: Date.distantPast, end: Date(), options: [])
        let sort  = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        var collected: [HKSample] = []
        var done = false
        while !done {
            let (newAnchor, batch, more) = try await anchoredQuery(type: sleepType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
            anchor = newAnchor
            if !batch.isEmpty { collected.append(contentsOf: batch) }
            done = !more
        }

        guard !collected.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        var out: [Sample] = []
        for s in collected {
            guard let cat = s as? HKCategorySample else { continue }
            let stage: String
            switch cat.value {
            case HKCategoryValueSleepAnalysis.inBed.rawValue: stage = "inBed"
            case HKCategoryValueSleepAnalysis.awake.rawValue: stage = "awake"
            case HKCategoryValueSleepAnalysis.asleepREM.rawValue: stage = "rem"
            case HKCategoryValueSleepAnalysis.asleepCore.rawValue: stage = "core"
            case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: stage = "deep"
            default: stage = "asleep"
            }
            out.append(Sample(
                user_id: currentUserId(), device_os: "ios", source: "healthkit",
                type: "sleep_stage",
                start_time: iso.string(from: cat.startDate),
                end_time:   iso.string(from: cat.endDate),
                value: nil, unit: nil, value_text: stage
            ))
        }

        guard !out.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(out, chunkSize: 200)
            let windowStart = out.map { $0.start_time }.min() ?? "-"
            let windowEnd = out.map { $0.end_time }.max() ?? "-"
            appLog("[HK-UP] \(anchorKey) rows=\(out.count) window=\(windowStart)..\(windowEnd)")
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
                recordImportedSampleMetadata(for: anchorKey, samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: out.count, source: "hk:sleep_stage")
            }
        } catch {
            appLog("Upload error \(anchorKey): \(error.localizedDescription)")
        }
    }

    private func processCycleDeltas(anchorKey: String) async throws {
        guard let menstrualFlowType else { return }
        var anchor = anchorStore.anchor(forKey: anchorKey)
        let pred = HKQuery.predicateForSamples(withStart: Date.distantPast, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        var collected: [HKSample] = []
        var done = false
        while !done {
            let (newAnchor, batch, more) = try await anchoredQuery(type: menstrualFlowType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
            anchor = newAnchor
            if !batch.isEmpty { collected.append(contentsOf: batch) }
            done = !more
        }

        guard !collected.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        let out: [Sample] = collected.compactMap { sample in
            guard let cat = sample as? HKCategorySample else { return nil }
            return Sample(
                user_id: currentUserId(),
                device_os: "ios",
                source: "healthkit",
                type: "menstrual_flow",
                start_time: iso.string(from: cat.startDate),
                end_time: iso.string(from: cat.endDate),
                value: nil,
                unit: nil,
                value_text: "active"
            )
        }

        guard !out.isEmpty else {
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            return
        }

        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(out, chunkSize: 200)
            let windowStart = out.map { $0.start_time }.min() ?? "-"
            let windowEnd = out.map { $0.end_time }.max() ?? "-"
            appLog("[HK-UP] \(anchorKey) rows=\(out.count) window=\(windowStart)..\(windowEnd)")
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            recordAnchorAdvance(for: anchorKey)
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
                recordImportedSampleMetadata(for: anchorKey, samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: out.count, source: "hk:menstrual_flow")
            }
        } catch {
            appLog("Upload error \(anchorKey): \(error.localizedDescription)")
        }
    }

    private func anchoredQuery(type: HKSampleType, predicate: NSPredicate?, anchor: HKQueryAnchor?, limit: Int, sort: NSSortDescriptor) async throws -> (HKQueryAnchor?, [HKSample], Bool) {
        let queryBox = HealthKitAnchoredQueryBox()
        return try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { (cont: AnchoredQueryContinuation) in
                let q = HKAnchoredObjectQuery(type: type, predicate: predicate, anchor: anchor, limit: limit) { _, samples, _, newAnchor, error in
                    queryBox.complete(samples: samples, newAnchor: newAnchor, limit: limit, error: error)
                }
                queryBox.prepare(q, continuation: cont)
                if Task.isCancelled {
                    queryBox.cancel(using: self.healthStore)
                    return
                }
                self.healthStore.execute(q)
            }
        }, onCancel: {
            queryBox.cancel(using: self.healthStore)
        })
    }

    private func sampleQuery(
        type: HKSampleType,
        predicate: NSPredicate?,
        sort: NSSortDescriptor,
        timeout: TimeInterval? = nil,
        limit: Int = HKObjectQueryNoLimit
    ) async throws -> [HKSample] {
        let queryBox = HealthKitSampleQueryBox()
        return try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { (cont: SampleQueryContinuation) in
                let q = HKSampleQuery(sampleType: type, predicate: predicate, limit: limit, sortDescriptors: [sort]) { _, samples, error in
                    queryBox.complete(samples: samples, error: error)
                }
                queryBox.prepare(q, continuation: cont)
                let store = self.healthStore
                if let timeout, timeout > 0 {
                    DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + timeout) {
                        queryBox.cancel(using: store, error: HealthKitQueryTimeoutError())
                    }
                }
                if Task.isCancelled {
                    queryBox.cancel(using: store)
                    return
                }
                store.execute(q)
            }
        }, onCancel: {
            queryBox.cancel(using: self.healthStore)
        })
    }

    private func matchesQuantityType(_ sample: HKQuantitySample, type: HKQuantityType?) -> Bool {
        guard let type else { return false }
        return sample.quantityType.identifier == type.identifier
    }

    private func logQuantityMapping(anchorKey: String, collected: [HKSample], mappedCount: Int) {
        guard anchorKey == "respiratory_rate" else { return }
        let quantitySamples = collected.compactMap { $0 as? HKQuantitySample }
        let identifiers = Array(Set(quantitySamples.map { $0.quantityType.identifier })).sorted()
        let identifierList = identifiers.joined(separator: ",")
        let windowStart = collected.map(\.startDate).min()
        let windowEnd = collected.map(\.endDate).max()
        let startText = windowStart.map { iso.string(from: $0) } ?? "-"
        let endText = windowEnd.map { iso.string(from: $0) } ?? "-"
        appLog("[HK-DIAG] respiratory collected=\(collected.count) quantity=\(quantitySamples.count) mapped=\(mappedCount) identifiers=\(identifierList) window=\(startText)..\(endText)")
    }

    private func prioritizeRecentUploads(anchorKey: String, samples: inout [Sample]) {
        guard anchorKey == "respiratory_rate" else { return }
        samples.sort { $0.start_time > $1.start_time }
    }

    // BG task
    static let refreshTaskId = "com.gaiaexporter.refresh"
    static let processingTaskId = "com.gaiaexporter.processing"

    func registerBGTask() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.refreshTaskId, using: nil) { task in
            if let bg = task as? BGAppRefreshTask {
                self.handleRefresh(task: bg)
                Task {
                    guard self.passiveHealthSyncAllowed() else { return }
                    try? await self.processSleepDeltas(anchorKey: "sleep_stage")
                    try? await self.processCycleDeltas(anchorKey: "menstrual_flow")
                }
            } else {
                task.setTaskCompleted(success: true)
            }
        }
        appLog("[BG] registered refresh task")
    }

    func registerProcessingTask() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.processingTaskId, using: nil) { task in
            guard let p = task as? BGProcessingTask else { task.setTaskCompleted(success: true); return }
            self.handleProcessing(task: p)
        }
    }

    func scheduleRefresh(after minutes: Int = 30) {
        let req = BGAppRefreshTaskRequest(identifier: Self.refreshTaskId)
        req.earliestBeginDate = Date(timeIntervalSinceNow: TimeInterval(minutes * 60))
        try? BGTaskScheduler.shared.submit(req)
    }

    func scheduleProcessing(after minutes: Int = 120) {
        let req = BGProcessingTaskRequest(identifier: Self.processingTaskId)
        req.earliestBeginDate = Date(timeIntervalSinceNow: TimeInterval(minutes * 60))
        req.requiresNetworkConnectivity = true
        req.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(req)
    }

    private func handleRefresh(task: BGAppRefreshTask) {
        scheduleRefresh(after: 30)
        StatusStore.shared.setBackgroundRun()
        let op = BlockOperation {
            Task {
                guard self.passiveHealthSyncAllowed() else {
                    appLog("[BG] refresh skipped until account onboarding is complete")
                    return
                }
                try? await self.processDeltas(for: self.hrType, anchorKey: "heart_rate")
                try? await self.processDeltas(for: self.spo2Type, anchorKey: "spo2")
                try? await self.processDeltas(for: self.stepsType, anchorKey: "step_count")
                try? await self.processDeltas(for: self.hrvType, anchorKey: "hrv_sdnn")
                if let respiratoryRateType = self.respiratoryRateType {
                    try? await self.processDeltas(for: respiratoryRateType, anchorKey: "respiratory_rate")
                }
                if let restingHeartRateType = self.restingHeartRateType {
                    try? await self.processDeltas(for: restingHeartRateType, anchorKey: "resting_heart_rate")
                }
                if let temperatureDeviationType = self.temperatureDeviationType {
                    try? await self.processDeltas(for: temperatureDeviationType, anchorKey: "temperature_deviation")
                }
                try? await self.processSleepDeltas(anchorKey: "sleep_stage")
                try? await self.processCycleDeltas(anchorKey: "menstrual_flow")
            }
        }
        task.expirationHandler = { op.cancel() }
        OperationQueue().addOperation(op)
        task.setTaskCompleted(success: true)
    }

    private func handleProcessing(task: BGProcessingTask) {
        // Reschedule first to keep cadence even if the task expires
        scheduleProcessing(after: 120)
        StatusStore.shared.setBackgroundRun()
        let op = BlockOperation {
            Task {
                guard self.passiveHealthSyncAllowed() else {
                    appLog("[BG] processing skipped until account onboarding is complete")
                    return
                }
                await self.kickOnce(reason: "processing")
                try? await self.processSleepDeltas(anchorKey: "sleep_stage")
                try? await self.processCycleDeltas(anchorKey: "menstrual_flow")
            }
        }
        task.expirationHandler = { op.cancel() }
        OperationQueue().addOperation(op)
        task.setTaskCompleted(success: true)
    }

    // Helpers
    private func currentUserId() -> String {
        UserDefaults.standard.string(forKey: "userId") ?? ""
    }

    private func passiveHealthSyncAllowed() -> Bool {
        let defaults = UserDefaults.standard
        let uid = currentUserId().trimmingCharacters(in: .whitespacesAndNewlines)
        guard uid.count == 36 else { return false }
        guard defaults.bool(forKey: "gaia.onboarding.completed") else { return false }
        return defaults.string(forKey: "gaia.auth.last_user_scope") == uid
    }

    private func buildAPI() -> APIClient {
        // Read persisted config that @AppStorage writes
        let rawBase = UserDefaults.standard.string(forKey: "baseURL") ?? ""
        let base = rawBase.trimmingCharacters(in: .whitespacesAndNewlines)
        let bearer = (UserDefaults.standard.string(forKey: "bearer") ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let uid = currentUserId().trimmingCharacters(in: .whitespacesAndNewlines)
        let bearerLower = bearer.lowercased()
        let isDeveloperBearer = bearerLower == DeveloperAuthDefaults.bearer.lowercased() || bearerLower.contains("gaia-dev")

        // Sanity logging so we can see why a -1011 or 401/422 might happen
        if base.isEmpty || URL(string: base) == nil {
            appLog("[BG] Missing/invalid baseURL: '\(rawBase)'")
        }
        if bearer.isEmpty {
            appLog("[BG] Missing bearer (auth token)")
        }
        if uid.count != 36 {
            appLog("[BG] Missing/invalid userId (need 36-char UUID), got: '\(uid)'")
        }

        // Build client and surface HTTP logs
        let api = APIClient(config: APIConfig(baseURLString: base, bearer: bearer, timeout: 60))
        api.devUserId = isDeveloperBearer ? uid : nil
        api.bearerProvider = {
            await AuthManager.shared.validAccessToken()
        }
        api.logger = { message in
            appLog("[BG] \(message)")
        }
        return api
    }

    @MainActor
    func registerAppState(_ state: AppState) {
        appState = state
    }

    func requestFeaturesRefreshAfterUpload(rows: Int, source: String) async {
        guard rows > 0 else {
            appLog("[BG] skip refresh; no rows to refresh")
            return
        }
        let refreshState = await MainActor.run { [weak self] in
            (
                self?.appState?.backendDBAvailable ?? true,
                self?.appState?.suspendNonessentialNetworkRefresh ?? false
            )
        }
        let backendAvailable = refreshState.0
        let suspendRefresh = refreshState.1
        guard backendAvailable else {
            appLog("[BG] skip refresh; backend DB=false")
            await logRefreshBlocked()
            return
        }
        guard !suspendRefresh else {
            appLog("[BG] skip refresh; nonessential network refresh suspended")
            return
        }
        await featuresRefresher.schedule { [weak self] in
            guard let self else { return }
            await self.fetchFeaturesSnapshot(reason: source)
        }
    }

    private func logRefreshBlocked() async {
        await MainActor.run { [weak self] in
            self?.appState?.append("[BG] refresh blocked: backend DB unavailable")
        }
    }

    private func fetchFeaturesSnapshot(reason: String) async {
        let api = buildAPI()
        do {
            let envelope: Envelope<FeaturesToday> = try await api.getJSON("v1/features/today", as: Envelope<FeaturesToday>.self)
            if let data = envelope.payload,
               let encoded = try? JSONEncoder().encode(data),
               let json = String(data: encoded, encoding: .utf8) {
                await MainActor.run {
                    UserDefaults.standard.set(json, forKey: "features_cache_json")
                }
                let okText = envelope.ok.map { $0 ? "true" : "false" } ?? "nil"
                let sourceText = envelope.source ?? "live"
                appLog("[BG] refreshed features snapshot after upload (\(reason)) ok=\(okText) source=\(sourceText)")
            } else {
                let okText = envelope.ok.map { $0 ? "true" : "false" } ?? "nil"
                appLog("[BG] features snapshot missing data after upload (\(reason)) ok=\(okText)")
            }
        } catch is CancellationError {
            return
        } catch let uerr as URLError where uerr.code == .cancelled {
            return
        } catch {
            appLog("[BG] features snapshot error after upload (\(reason)): \(error.localizedDescription)")
        }
    }

    /// Clear stale anchors for newly-expanded context signals once so recent history
    /// is re-uploaded even if prior anchors stopped advancing.
    func ensurePhase2RecentBackfillIfNeeded() async {
        guard passiveHealthSyncAllowed() else {
            appLog("[Backfill] phase2 recent backfill skipped until account onboarding is complete")
            return
        }
        let defaults = UserDefaults.standard
        let appliedVersion = defaults.integer(forKey: Self.phase2BackfillMarkerKey)
        guard appliedVersion < Self.phase2BackfillVersion else { return }
        let started = await phase2BackfillState.beginIfNeeded()
        guard started else { return }

        let keys = [
            "respiratory_rate",
            "resting_heart_rate",
            "temperature_deviation",
            "menstrual_flow",
        ]
        anchorStore.clear(keys: keys)
        appLog("[Backfill] phase2 recent backfill starting")

        let start = Calendar.current.date(byAdding: .day, value: -180, to: Date()) ?? Date(timeIntervalSinceNow: -180 * 24 * 60 * 60)
        let pred = HKQuery.predicateForSamples(withStart: start, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        if let respiratoryRateType {
            _ = await backfillOne(type: respiratoryRateType, anchorKey: "respiratory_rate", pred: pred, sort: sort)
        }
        if let restingHeartRateType {
            _ = await backfillOne(type: restingHeartRateType, anchorKey: "resting_heart_rate", pred: pred, sort: sort)
        }
        if let temperatureDeviationType {
            _ = await backfillOne(type: temperatureDeviationType, anchorKey: "temperature_deviation", pred: pred, sort: sort)
        }
        _ = await backfillCycle(pred: pred, sort: sort)
        defaults.set(Self.phase2BackfillVersion, forKey: Self.phase2BackfillMarkerKey)
        await phase2BackfillState.end()
    }

    private func reportBackfillProgress(
        _ message: String,
        onProgress: (@Sendable (String) async -> Void)?
    ) async {
        appLog("[Backfill] \(message)")
        if let onProgress {
            await onProgress(message)
        }
    }

    private func interactiveChunkSize(for metric: InteractiveBackfillMetric) -> Int {
        switch metric {
        case .heartRate:
            return 40
        case .bloodPressure:
            return 60
        default:
            return 80
        }
    }

    private var interactiveRetryLimit: Int { 1 }

    private func performInteractiveBackfillMetric(
        _ metric: InteractiveBackfillMetric,
        start: Date,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillMetricResult {
        let pred = HKQuery.predicateForSamples(withStart: start, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
        switch metric {
        case .heartRate:
            return await backfillHeartRateStatistics(
                anchorKey: metric.key,
                start: start,
                end: Date(),
                windowDays: 5,
                intervalMinutes: 15,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit,
                onProgress: onProgress
            )
        case .spo2:
            return await backfillOne(
                type: spo2Type,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .hrv:
            return await backfillOne(
                type: hrvType,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .respiratoryRate:
            guard let respiratoryRateType else {
                return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
            }
            return await backfillOne(
                type: respiratoryRateType,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .restingHeartRate:
            guard let restingHeartRateType else {
                return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
            }
            return await backfillOne(
                type: restingHeartRateType,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .temperatureDeviation:
            guard let temperatureDeviationType else {
                return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
            }
            return await backfillOne(
                type: temperatureDeviationType,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .bloodPressure:
            return await backfillOne(
                type: bpType,
                anchorKey: metric.key,
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .sleep:
            return await backfillSleep(
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        case .menstrualFlow:
            return await backfillCycle(
                pred: pred,
                sort: sort,
                chunkSize: interactiveChunkSize(for: metric),
                maxRetries: interactiveRetryLimit
            )
        }
    }

    /// Clear anchors and backfill the onboarding-relevant HealthKit signals from `start` until now.
    /// This keeps the first-run import focused on the signals Gaia actually interprets immediately.
    func forceBackfill(
        since start: Date,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillSummary {
        let metrics = InteractiveBackfillMetric.allCases
        var summary = HealthBackfillSummary(totalMetrics: metrics.count)
        guard currentUserId().trimmingCharacters(in: .whitespacesAndNewlines).count == 36 else {
            summary.failedMetrics = ["signed-in user"]
            await reportBackfillProgress("Sign in before importing Health data.", onProgress: onProgress)
            return summary
        }
        anchorStore.clear(keys: metrics.map(\.key))

        await reportBackfillProgress("Preparing 30-day import…", onProgress: onProgress)

        for (index, metric) in metrics.enumerated() {
            let ordinal = index + 1
            await reportBackfillProgress(
                "Collecting \(metric.label) (\(ordinal)/\(metrics.count))…",
                onProgress: onProgress
            )

            let result = await self.performInteractiveBackfillMetric(metric, start: start, onProgress: onProgress)
            summary.completedMetrics = ordinal
            if let failure = result.failureDescription {
                summary.failedMetrics.append(metric.label)
                await reportBackfillProgress(
                    "Could not import \(metric.label). \(failure)",
                    onProgress: onProgress
                )
            } else if result.didUploadAnyData {
                summary.uploadedMetrics += 1
                summary.uploadedRows += result.uploadedRows
                await reportBackfillProgress(
                    "Imported \(result.uploadedRows) \(metric.label) rows.",
                    onProgress: onProgress
                )
            } else {
                await reportBackfillProgress(
                    "No \(metric.label) samples found in the last 30 days.",
                    onProgress: onProgress
                )
            }
        }

        await reportBackfillProgress(summary.userFacingMessage, onProgress: onProgress)
        return summary
    }
    private func backfillSleep(
        pred: NSPredicate,
        sort: NSSortDescriptor,
        chunkSize: Int = 200,
        maxRetries: Int = 3
    ) async -> HealthBackfillMetricResult {
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true
        var page = 0
        while more {
            do {
                page += 1
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: sleepType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
                if page == 1 || page % 5 == 0 {
                    appLog("[Backfill] sleep_stage collected \(collected.count) raw samples after page \(page)")
                }
            } catch {
                appLog("[Backfill] anchoredQuery error sleep_stage: \(error.localizedDescription)")
                return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
            }
        }
        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for sleep_stage in range")
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }
        var samples: [Sample] = []
        for s in collected {
            guard let cat = s as? HKCategorySample else { continue }
            let stage: String
            switch cat.value {
            case HKCategoryValueSleepAnalysis.inBed.rawValue: stage = "inBed"
            case HKCategoryValueSleepAnalysis.awake.rawValue: stage = "awake"
            case HKCategoryValueSleepAnalysis.asleepREM.rawValue: stage = "rem"
            case HKCategoryValueSleepAnalysis.asleepCore.rawValue: stage = "core"
            case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: stage = "deep"
            default: stage = "asleep"
            }
            samples.append(Sample(
                user_id: currentUserId(), device_os: "ios", source: "healthkit",
                type: "sleep_stage",
                start_time: iso.string(from: cat.startDate),
                end_time:   iso.string(from: cat.endDate),
                value: nil, unit: nil, value_text: stage
            ))
        }
        appLog("[Backfill] sleep_stage mapped \(samples.count) upload rows from \(collected.count) raw samples")
        guard !samples.isEmpty else {
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: nil)
        }
        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: chunkSize, maxRetries: maxRetries)
            appLog("[Backfill] uploaded \(samples.count) sleep_stage samples")
            if uploaded {
                StatusStore.shared.setUpload(for: "sleep_stage")
                recordImportedSampleMetadata(for: "sleep_stage", samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_sleep")
            }
            return HealthBackfillMetricResult(
                collectedCount: collected.count,
                uploadedRows: uploaded ? samples.count : 0,
                failureDescription: uploaded ? nil : "The server did not accept any sleep rows."
            )
        } catch {
            appLog("[Backfill] upload error sleep_stage: \(error.localizedDescription)")
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
        }
    }

    private func backfillCycle(
        pred: NSPredicate,
        sort: NSSortDescriptor,
        chunkSize: Int = 200,
        maxRetries: Int = 3
    ) async -> HealthBackfillMetricResult {
        guard let menstrualFlowType else {
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true
        var page = 0
        while more {
            do {
                page += 1
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: menstrualFlowType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
                if page == 1 || page % 5 == 0 {
                    appLog("[Backfill] menstrual_flow collected \(collected.count) raw samples after page \(page)")
                }
            } catch {
                appLog("[Backfill] anchoredQuery error menstrual_flow: \(error.localizedDescription)")
                return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
            }
        }
        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for menstrual_flow in range")
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }
        let samples: [Sample] = collected.compactMap { sample in
            guard let cat = sample as? HKCategorySample else { return nil }
            return Sample(
                user_id: currentUserId(),
                device_os: "ios",
                source: "healthkit",
                type: "menstrual_flow",
                start_time: iso.string(from: cat.startDate),
                end_time: iso.string(from: cat.endDate),
                value: nil,
                unit: nil,
                value_text: "active"
            )
        }
        appLog("[Backfill] menstrual_flow mapped \(samples.count) upload rows from \(collected.count) raw samples")
        guard !samples.isEmpty else {
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: nil)
        }
        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: chunkSize, maxRetries: maxRetries)
            anchorStore.setAnchor(anchor, forKey: "menstrual_flow")
            recordAnchorAdvance(for: "menstrual_flow")
            StatusStore.shared.setUpload(for: "menstrual_flow")
            appLog("[Backfill] uploaded \(samples.count) menstrual_flow samples")
            if uploaded {
                recordImportedSampleMetadata(for: "menstrual_flow", samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_menstrual_flow")
            }
            return HealthBackfillMetricResult(
                collectedCount: collected.count,
                uploadedRows: uploaded ? samples.count : 0,
                failureDescription: uploaded ? nil : "The server did not accept any cycle rows."
            )
        } catch {
            appLog("[Backfill] upload error menstrual_flow: \(error.localizedDescription)")
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
        }
    }

    /// Lightweight sweep that mimics an observer firing now; useful for foreground or manual "sync now".
    func kickOnce(reason: String) async {
        let now = Date()
        let suppressed: Bool = await MainActor.run { () -> Bool in
            let last = lastKickAt ?? .distantPast
            let ok = now.timeIntervalSince(last) > 12
            if ok { lastKickAt = now }
            return !ok
        }
        if suppressed {
            appLog("[BG] kickOnce suppressed (recent)")
            return
        }
        guard passiveHealthSyncAllowed() else {
            appLog("[BG] kickOnce skipped until account onboarding is complete")
            return
        }
        appLog("[BG] kickOnce: \(reason)")
        let phase2BackfillInProgress = await phase2BackfillState.isInProgress()
        if phase2BackfillInProgress {
            appLog("[BG] kickOnce: phase2 context backfill in progress; skipping duplicate respiratory/recovery fetches")
        }
        await self.processingGate.runOnce(key: "heart_rate") {
            do { try await self.processDeltas(for: self.hrType, anchorKey: "heart_rate") } catch { appLog("[BG] kickOnce hr error: \(error.localizedDescription)") }
        }
        await self.processingGate.runOnce(key: "spo2") {
            do { try await self.processDeltas(for: self.spo2Type, anchorKey: "spo2") } catch { appLog("[BG] kickOnce spo2 error: \(error.localizedDescription)") }
        }
        await self.processingGate.runOnce(key: "step_count") {
            do { try await self.processDeltas(for: self.stepsType, anchorKey: "step_count") } catch { appLog("[BG] kickOnce steps error: \(error.localizedDescription)") }
        }
        await self.processingGate.runOnce(key: "hrv_sdnn") {
            do { try await self.processDeltas(for: self.hrvType, anchorKey: "hrv_sdnn") } catch { appLog("[BG] kickOnce hrv error: \(error.localizedDescription)") }
        }
        if !phase2BackfillInProgress, let respiratoryRateType {
            await self.processingGate.runOnce(key: "respiratory_rate") {
                do { try await self.processDeltas(for: respiratoryRateType, anchorKey: "respiratory_rate") } catch { appLog("[BG] kickOnce respiratory error: \(error.localizedDescription)") }
            }
        }
        if !phase2BackfillInProgress, let restingHeartRateType {
            await self.processingGate.runOnce(key: "resting_heart_rate") {
                do { try await self.processDeltas(for: restingHeartRateType, anchorKey: "resting_heart_rate") } catch { appLog("[BG] kickOnce resting HR error: \(error.localizedDescription)") }
            }
        }
        if !phase2BackfillInProgress, let temperatureDeviationType {
            await self.processingGate.runOnce(key: "temperature_deviation") {
                do { try await self.processDeltas(for: temperatureDeviationType, anchorKey: "temperature_deviation") } catch { appLog("[BG] kickOnce temperature error: \(error.localizedDescription)") }
            }
        }
        await self.processingGate.runOnce(key: "blood_pressure") {
            do { try await self.processDeltas(for: self.bpType, anchorKey: "blood_pressure") } catch { appLog("[BG] kickOnce bp error: \(error.localizedDescription)") }
        }
        await self.processingGate.runOnce(key: "sleep_stage") {
            do { try await self.processSleepDeltas(anchorKey: "sleep_stage") } catch { appLog("[BG] kickOnce sleep error: \(error.localizedDescription)") }
        }
        if !phase2BackfillInProgress {
            await self.processingGate.runOnce(key: "menstrual_flow") {
                do { try await self.processCycleDeltas(anchorKey: "menstrual_flow") } catch { appLog("[BG] kickOnce cycle error: \(error.localizedDescription)") }
            }
        }
        StatusStore.shared.setBackgroundRun()
    }

    private func backfillOne(
        type: HKSampleType,
        anchorKey: String,
        pred: NSPredicate,
        sort: NSSortDescriptor,
        chunkSize: Int = 200,
        maxRetries: Int = 3,
        pageLimit: Int = 500,
        persistAnchor: Bool = true,
        requestRefresh: Bool = true
    ) async -> HealthBackfillMetricResult {
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true
        var page = 0

        while more {
            do {
                page += 1
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: type, predicate: pred, anchor: anchor, limit: pageLimit, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
                if page == 1 || page % 5 == 0 {
                    appLog("[Backfill] \(anchorKey) collected \(collected.count) raw samples after page \(page)")
                }
            } catch {
                appLog("[Backfill] anchoredQuery error \(anchorKey): \(error.localizedDescription)")
                return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
            }
        }
        return await uploadBackfillSamples(
            collected,
            anchorKey: anchorKey,
            anchor: anchor,
            chunkSize: chunkSize,
            maxRetries: maxRetries,
            persistAnchor: persistAnchor,
            requestRefresh: requestRefresh
        )
    }

    private func uploadBackfillSamples(
        _ collected: [HKSample],
        anchorKey: String,
        anchor: HKQueryAnchor? = nil,
        chunkSize: Int = 200,
        maxRetries: Int = 3,
        persistAnchor: Bool = true,
        requestRefresh: Bool = true
    ) async -> HealthBackfillMetricResult {
        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for \(anchorKey) in range")
            if persistAnchor {
                anchorStore.setAnchor(anchor, forKey: anchorKey)
                recordAnchorAdvance(for: anchorKey)
            }
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }

        var samples: [Sample] = []
        for s in collected {
            if let q = s as? HKQuantitySample, let mapped = mapQuantitySampleToWire(q) {
                samples.append(mapped)
            } else if let c = s as? HKCorrelation, c.correlationType == bpType {
                let systolicType  = HKObjectType.quantityType(forIdentifier: .bloodPressureSystolic)!
                let diastolicType = HKObjectType.quantityType(forIdentifier: .bloodPressureDiastolic)!
                for obj in c.objects.compactMap({ $0 as? HKQuantitySample }) {
                    if obj.quantityType == systolicType {
                        let mmHg = obj.quantity.doubleValue(for: HKUnit.millimeterOfMercury())
                        guard mmHg.isFinite, mmHg >= 40, mmHg <= 260 else { continue }
                        samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "blood_pressure_systolic", start_time: iso.string(from: obj.startDate), end_time: iso.string(from: obj.endDate), value: mmHg, unit: "mmHg", value_text: nil))
                    } else if obj.quantityType == diastolicType {
                        let mmHg = obj.quantity.doubleValue(for: HKUnit.millimeterOfMercury())
                        guard mmHg.isFinite, mmHg >= 30, mmHg <= 180 else { continue }
                        samples.append(Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit", type: "blood_pressure_diastolic", start_time: iso.string(from: obj.startDate), end_time: iso.string(from: obj.endDate), value: mmHg, unit: "mmHg", value_text: nil))
                    }
                }
            }
        }
        logQuantityMapping(anchorKey: anchorKey, collected: collected, mappedCount: samples.count)
        prioritizeRecentUploads(anchorKey: anchorKey, samples: &samples)
        appLog("[Backfill] \(anchorKey) mapped \(samples.count) upload rows from \(collected.count) raw samples")

        guard !samples.isEmpty else {
            if persistAnchor {
                anchorStore.setAnchor(anchor, forKey: anchorKey)
                recordAnchorAdvance(for: anchorKey)
            }
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: nil)
        }

        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: chunkSize, maxRetries: maxRetries)
            if persistAnchor {
                anchorStore.setAnchor(anchor, forKey: anchorKey)
                recordAnchorAdvance(for: anchorKey)
            }
            StatusStore.shared.setUpload(for: anchorKey)
            appLog("[Backfill] uploaded \(samples.count) \(anchorKey) samples")
            if uploaded && requestRefresh {
                recordImportedSampleMetadata(for: anchorKey, samples: collected)
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_\(anchorKey)")
            }
            return HealthBackfillMetricResult(
                collectedCount: collected.count,
                uploadedRows: uploaded ? samples.count : 0,
                failureDescription: uploaded ? nil : "The server did not accept any \(anchorKey) rows."
            )
        } catch {
            appLog("[Backfill] upload error \(anchorKey): \(error.localizedDescription)")
            return HealthBackfillMetricResult(collectedCount: collected.count, uploadedRows: 0, failureDescription: error.localizedDescription)
        }
    }

    private func backfillOneWindowed(
        type: HKSampleType,
        anchorKey: String,
        start: Date,
        end: Date,
        sort: NSSortDescriptor,
        windowDays: Int,
        pageLimit: Int = 500,
        chunkSize: Int = 200,
        maxRetries: Int = 3,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillMetricResult {
        let windows = recentBackfillWindows(start: start, end: end, windowDays: windowDays)
        guard !windows.isEmpty else {
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }

        var totalCollected = 0
        var totalUploaded = 0

        for (index, window) in windows.enumerated() {
            let windowLabel = "\(index + 1)/\(windows.count)"
            await reportBackfillProgress(
                "Collecting \(anchorKey.replacingOccurrences(of: "_", with: " ")) window \(windowLabel)…",
                onProgress: onProgress
            )
            let pred = HKQuery.predicateForSamples(
                withStart: window.start,
                end: window.end,
                options: [.strictStartDate]
            )
            let result = await backfillOne(
                type: type,
                anchorKey: anchorKey,
                pred: pred,
                sort: sort,
                chunkSize: chunkSize,
                maxRetries: maxRetries,
                pageLimit: pageLimit,
                persistAnchor: index == 0,
                requestRefresh: false
            )
            totalCollected += result.collectedCount
            totalUploaded += result.uploadedRows
            if let failure = result.failureDescription {
                return HealthBackfillMetricResult(
                    collectedCount: totalCollected,
                    uploadedRows: totalUploaded,
                    failureDescription: failure
                )
            }
            if result.didUploadAnyData {
                await reportBackfillProgress(
                    "Imported \(result.uploadedRows) \(anchorKey.replacingOccurrences(of: "_", with: " ")) rows from window \(windowLabel).",
                    onProgress: onProgress
                )
            } else {
                await reportBackfillProgress(
                    "No \(anchorKey.replacingOccurrences(of: "_", with: " ")) samples found in window \(windowLabel).",
                    onProgress: onProgress
                )
            }
        }

        if totalUploaded > 0 {
            await requestFeaturesRefreshAfterUpload(rows: totalUploaded, source: "hk:backfill_\(anchorKey)")
        }

        return HealthBackfillMetricResult(
            collectedCount: totalCollected,
            uploadedRows: totalUploaded,
            failureDescription: nil
        )
    }

    private func backfillAdaptiveSampleWindow(
        type: HKSampleType,
        anchorKey: String,
        window: DateInterval,
        sort: NSSortDescriptor,
        chunkSize: Int,
        maxRetries: Int,
        windowLabel: String,
        minimumWindowMinutes: Int = 60,
        queryTimeout: TimeInterval = 12,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillMetricResult {
        let pred = HKQuery.predicateForSamples(
            withStart: window.start,
            end: window.end,
            options: [.strictStartDate, .strictEndDate]
        )
        let windowRange = "\(iso.string(from: window.start))..\((iso.string(from: window.end)))"

        do {
            let batch = try await sampleQuery(
                type: type,
                predicate: pred,
                sort: sort,
                timeout: queryTimeout
            )
            appLog("[Backfill] \(anchorKey) sample query collected \(batch.count) raw samples in window \(windowLabel) \(windowRange)")
            return await uploadBackfillSamples(
                batch,
                anchorKey: anchorKey,
                chunkSize: chunkSize,
                maxRetries: maxRetries,
                persistAnchor: false,
                requestRefresh: false
            )
        } catch is HealthKitQueryTimeoutError {
            let minimumWindowDuration = TimeInterval(max(30, minimumWindowMinutes) * 60)
            guard window.duration > minimumWindowDuration else {
                appLog("[Backfill] \(anchorKey) sample query timed out at minimum window \(windowLabel) \(windowRange)")
                return HealthBackfillMetricResult(
                    collectedCount: 0,
                    uploadedRows: 0,
                    failureDescription: "The \(anchorKey.replacingOccurrences(of: "_", with: " ")) import is still taking too long."
                )
            }

            let midpoint = window.start.addingTimeInterval(window.duration / 2)
            let recentWindow = DateInterval(start: midpoint, end: window.end)
            let olderWindow = DateInterval(start: window.start, end: midpoint)
            appLog("[Backfill] \(anchorKey) window \(windowLabel) is slow; splitting \(windowRange)")
            await reportBackfillProgress(
                "Collecting \(anchorKey.replacingOccurrences(of: "_", with: " ")) window \(windowLabel) in smaller ranges…",
                onProgress: onProgress
            )

            let recentResult = await backfillAdaptiveSampleWindow(
                type: type,
                anchorKey: anchorKey,
                window: recentWindow,
                sort: sort,
                chunkSize: chunkSize,
                maxRetries: maxRetries,
                windowLabel: "\(windowLabel)a",
                minimumWindowMinutes: minimumWindowMinutes,
                queryTimeout: queryTimeout,
                onProgress: onProgress
            )
            let olderResult = await backfillAdaptiveSampleWindow(
                type: type,
                anchorKey: anchorKey,
                window: olderWindow,
                sort: sort,
                chunkSize: chunkSize,
                maxRetries: maxRetries,
                windowLabel: "\(windowLabel)b",
                minimumWindowMinutes: minimumWindowMinutes,
                queryTimeout: queryTimeout,
                onProgress: onProgress
            )
            return HealthBackfillMetricResult(
                collectedCount: recentResult.collectedCount + olderResult.collectedCount,
                uploadedRows: recentResult.uploadedRows + olderResult.uploadedRows,
                failureDescription: recentResult.failureDescription ?? olderResult.failureDescription
            )
        } catch {
            appLog("[Backfill] sampleQuery error \(anchorKey) window \(windowLabel): \(error.localizedDescription)")
            return HealthBackfillMetricResult(
                collectedCount: 0,
                uploadedRows: 0,
                failureDescription: error.localizedDescription
            )
        }
    }

    private func fetchHeartRateStatisticsSamples(
        start: Date,
        end: Date,
        intervalMinutes: Int
    ) async throws -> [Sample] {
        let userId = currentUserId()
        let quantityType = hrType
        let store = healthStore
        let predicate = HKQuery.predicateForSamples(
            withStart: start,
            end: end,
            options: [.strictStartDate, .strictEndDate]
        )
        let interval = DateComponents(minute: max(5, intervalMinutes))
        let anchorDate = Calendar.current.startOfDay(for: start)
        let unit = HKUnit.count().unitDivided(by: HKUnit.minute())

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[Sample], Error>) in
            let query = HKStatisticsCollectionQuery(
                quantityType: quantityType,
                quantitySamplePredicate: predicate,
                options: [.discreteAverage],
                anchorDate: anchorDate,
                intervalComponents: interval
            )
            query.initialResultsHandler = { _, collection, error in
                if let error {
                    cont.resume(throwing: error)
                    return
                }
                var samples: [Sample] = []
                collection?.enumerateStatistics(from: start, to: end) { stats, _ in
                    guard let avg = stats.averageQuantity()?.doubleValue(for: unit) else { return }
                    guard avg.isFinite, avg >= 20, avg <= 250 else { return }
                    let intervalEnd = min(stats.endDate, end)
                    samples.append(
                        Sample(
                            user_id: userId,
                            device_os: "ios",
                            source: "healthkit",
                            type: "heart_rate",
                            start_time: Self.isoString(stats.startDate),
                            end_time: Self.isoString(intervalEnd),
                            value: avg,
                            unit: "bpm",
                            value_text: "discrete_average_15m"
                        )
                    )
                }
                cont.resume(returning: samples)
            }
            store.execute(query)
        }
    }

    private func backfillHeartRateStatistics(
        anchorKey: String,
        start: Date,
        end: Date,
        windowDays: Int,
        intervalMinutes: Int,
        chunkSize: Int = 200,
        maxRetries: Int = 3,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillMetricResult {
        let windows = recentBackfillWindows(start: start, end: end, windowDays: windowDays)
        guard !windows.isEmpty else {
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }

        var totalCollected = 0
        var totalUploaded = 0

        for (index, window) in windows.enumerated() {
            let windowLabel = "\(index + 1)/\(windows.count)"
            await reportBackfillProgress(
                "Collecting \(anchorKey.replacingOccurrences(of: "_", with: " ")) window \(windowLabel)…",
                onProgress: onProgress
            )
            do {
                let rows = try await fetchHeartRateStatisticsSamples(
                    start: window.start,
                    end: window.end,
                    intervalMinutes: intervalMinutes
                )
                totalCollected += rows.count
                appLog("[Backfill] \(anchorKey) statistics collected \(rows.count) aggregate rows in window \(windowLabel)")

                guard !rows.isEmpty else {
                    await reportBackfillProgress(
                        "No \(anchorKey.replacingOccurrences(of: "_", with: " ")) samples found in window \(windowLabel).",
                        onProgress: onProgress
                    )
                    continue
                }

                let api = buildAPI()
                let uploaded = try await api.postSamplesChunked(rows, chunkSize: max(200, chunkSize), maxRetries: maxRetries)
                StatusStore.shared.setUpload(for: anchorKey)
                if !uploaded {
                    return HealthBackfillMetricResult(
                        collectedCount: totalCollected,
                        uploadedRows: totalUploaded,
                        failureDescription: "The server did not accept any \(anchorKey) rows."
                    )
                }

                totalUploaded += rows.count
                await reportBackfillProgress(
                    "Imported \(rows.count) \(anchorKey.replacingOccurrences(of: "_", with: " ")) rows from window \(windowLabel).",
                    onProgress: onProgress
                )
            } catch {
                appLog("[Backfill] statistics query error \(anchorKey) window \(windowLabel): \(error.localizedDescription)")
                return HealthBackfillMetricResult(
                    collectedCount: totalCollected,
                    uploadedRows: totalUploaded,
                    failureDescription: error.localizedDescription
                )
            }
        }

        anchorStore.setSeedStart(end, forKey: anchorKey)
        if totalUploaded > 0 {
            await requestFeaturesRefreshAfterUpload(rows: totalUploaded, source: "hk:backfill_\(anchorKey)")
        }

        return HealthBackfillMetricResult(
            collectedCount: totalCollected,
            uploadedRows: totalUploaded,
            failureDescription: nil
        )
    }

    private func backfillOneWindowedSampleQuery(
        type: HKSampleType,
        anchorKey: String,
        start: Date,
        end: Date,
        sort: NSSortDescriptor,
        windowDays: Int,
        chunkSize: Int = 200,
        maxRetries: Int = 3,
        onProgress: (@Sendable (String) async -> Void)? = nil
    ) async -> HealthBackfillMetricResult {
        let windows = recentBackfillWindows(start: start, end: end, windowDays: windowDays)
        guard !windows.isEmpty else {
            return HealthBackfillMetricResult(collectedCount: 0, uploadedRows: 0, failureDescription: nil)
        }

        var totalCollected = 0
        var totalUploaded = 0

        for (index, window) in windows.enumerated() {
            let windowLabel = "\(index + 1)/\(windows.count)"
            await reportBackfillProgress(
                "Collecting \(anchorKey.replacingOccurrences(of: "_", with: " ")) window \(windowLabel)…",
                onProgress: onProgress
            )
            let result = await backfillAdaptiveSampleWindow(
                type: type,
                anchorKey: anchorKey,
                window: window,
                sort: sort,
                chunkSize: chunkSize,
                maxRetries: maxRetries,
                windowLabel: windowLabel,
                onProgress: onProgress
            )
            totalCollected += result.collectedCount
            totalUploaded += result.uploadedRows
            if let failure = result.failureDescription {
                return HealthBackfillMetricResult(
                    collectedCount: totalCollected,
                    uploadedRows: totalUploaded,
                    failureDescription: failure
                )
            }
            if result.didUploadAnyData {
                await reportBackfillProgress(
                    "Imported \(result.uploadedRows) \(anchorKey.replacingOccurrences(of: "_", with: " ")) rows from window \(windowLabel).",
                    onProgress: onProgress
                )
            } else {
                await reportBackfillProgress(
                    "No \(anchorKey.replacingOccurrences(of: "_", with: " ")) samples found in window \(windowLabel).",
                    onProgress: onProgress
                )
            }
        }

        anchorStore.setSeedStart(end, forKey: anchorKey)
        if totalUploaded > 0 {
            await requestFeaturesRefreshAfterUpload(rows: totalUploaded, source: "hk:backfill_\(anchorKey)")
        }

        return HealthBackfillMetricResult(
            collectedCount: totalCollected,
            uploadedRows: totalUploaded,
            failureDescription: nil
        )
    }

    private func recentBackfillWindows(start: Date, end: Date, windowDays: Int) -> [DateInterval] {
        guard start < end else { return [] }
        let calendar = Calendar.current
        let safeWindowDays = max(1, windowDays)
        var windows: [DateInterval] = []
        var windowEnd = end

        while windowEnd > start {
            let candidateStart = calendar.date(byAdding: .day, value: -safeWindowDays, to: windowEnd) ?? start
            let windowStart = candidateStart > start ? candidateStart : start
            windows.append(DateInterval(start: windowStart, end: windowEnd))
            windowEnd = windowStart
        }

        return windows
    }

    /// Mirrors the mapping in processDeltas so backfill writes identical rows.
    private func mapQuantitySampleToWire(_ q: HKQuantitySample) -> Sample? {
        if matchesQuantityType(q, type: hrType) {
            let bpm = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
            guard bpm.isFinite, bpm >= 20, bpm <= 250 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "heart_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: bpm, unit: "bpm", value_text: nil)
        } else if matchesQuantityType(q, type: spo2Type) {
            let pct = q.quantity.doubleValue(for: HKUnit.percent()) * 100.0
            guard pct.isFinite, pct >= 50, pct <= 100 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "spo2", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: pct, unit: "%", value_text: nil)
        } else if matchesQuantityType(q, type: stepsType) {
            let cnt = q.quantity.doubleValue(for: HKUnit.count())
            guard cnt.isFinite, cnt >= 0 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "step_count", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: cnt, unit: "count", value_text: nil)
        } else if matchesQuantityType(q, type: hrvType) {
            let ms = q.quantity.doubleValue(for: HKUnit.secondUnit(with: .milli))
            guard ms.isFinite, ms >= 0, ms <= 600 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "hrv_sdnn", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: ms, unit: "ms", value_text: nil)
        } else if matchesQuantityType(q, type: respiratoryRateType) {
            let breathsPerMinute = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
            guard breathsPerMinute.isFinite, breathsPerMinute >= 4, breathsPerMinute <= 80 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "respiratory_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: breathsPerMinute, unit: "br/min", value_text: nil)
        } else if matchesQuantityType(q, type: restingHeartRateType) {
            let bpm = q.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
            guard bpm.isFinite, bpm >= 20, bpm <= 180 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "resting_heart_rate", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: bpm, unit: "bpm", value_text: nil)
        } else if matchesQuantityType(q, type: temperatureDeviationType) {
            let deltaC = q.quantity.doubleValue(for: HKUnit.degreeCelsius())
            guard deltaC.isFinite, deltaC >= -10, deltaC <= 10 else { return nil }
            return Sample(user_id: currentUserId(), device_os: "ios", source: "healthkit",
                          type: "temperature_deviation", start_time: iso.string(from: q.startDate), end_time: iso.string(from: q.endDate),
                          value: deltaC, unit: "degC", value_text: "apple_sleeping_wrist_temperature")
        }
        return nil
    }
}

private final class AnchorStore {
    private let anchorPrefix = "hk_anchor_"
    private let seedPrefix = "hk_seed_start_"

    func anchor(forKey key: String) -> HKQueryAnchor? {
        guard let data = UserDefaults.standard.data(forKey: "\(anchorPrefix)\(key)") else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    /// If `anchor` is nil, the stored anchor is removed (used to recover from stuck anchors).
    func setAnchor(_ anchor: HKQueryAnchor?, forKey key: String) {
        let k = "\(anchorPrefix)\(key)"
        guard let anchor = anchor else {
            UserDefaults.standard.removeObject(forKey: k)
            return
        }
        if let data = try? NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true) {
            UserDefaults.standard.set(data, forKey: k)
            UserDefaults.standard.removeObject(forKey: "\(seedPrefix)\(key)")
        }
    }

    func seedStart(forKey key: String) -> Date? {
        guard let raw = UserDefaults.standard.string(forKey: "\(seedPrefix)\(key)"), !raw.isEmpty else {
            return nil
        }
        let precise = ISO8601DateFormatter()
        precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return precise.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }

    func setSeedStart(_ date: Date?, forKey key: String) {
        let storageKey = "\(seedPrefix)\(key)"
        guard let date else {
            UserDefaults.standard.removeObject(forKey: storageKey)
            return
        }
        let precise = ISO8601DateFormatter()
        precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        UserDefaults.standard.set(precise.string(from: date), forKey: storageKey)
    }

    /// Clear multiple anchors by their keys (e.g., ["heart_rate","spo2","step_count","hrv_sdnn"]).
    func clear(keys: [String]) {
        for key in keys {
            UserDefaults.standard.removeObject(forKey: "\(anchorPrefix)\(key)")
            UserDefaults.standard.removeObject(forKey: "\(seedPrefix)\(key)")
        }
    }
}
