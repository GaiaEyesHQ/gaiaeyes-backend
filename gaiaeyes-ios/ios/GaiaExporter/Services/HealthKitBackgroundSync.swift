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

        healthStore.enableBackgroundDelivery(for: hrType,   frequency: .immediate) { ok, err in appLog("[HK] bg delivery heart_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        healthStore.enableBackgroundDelivery(for: spo2Type, frequency: .immediate) { ok, err in appLog("[HK] bg delivery spo2: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        healthStore.enableBackgroundDelivery(for: stepsType,frequency: .immediate) { ok, err in appLog("[HK] bg delivery step_count: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        healthStore.enableBackgroundDelivery(for: hrvType,  frequency: .immediate) { ok, err in appLog("[HK] bg delivery hrv_sdnn: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        // Blood pressure background delivery is not supported by HealthKit.
        appLog("[HK] bg delivery blood_pressure: skipped (not supported)")
        healthStore.enableBackgroundDelivery(for: sleepType,frequency: .immediate) { ok, err in appLog("[HK] bg delivery sleep_stage: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        if let respiratoryRateType {
            healthStore.enableBackgroundDelivery(for: respiratoryRateType, frequency: .immediate) { ok, err in appLog("[HK] bg delivery respiratory_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        }
        if let restingHeartRateType {
            healthStore.enableBackgroundDelivery(for: restingHeartRateType, frequency: .immediate) { ok, err in appLog("[HK] bg delivery resting_heart_rate: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        }
        if let temperatureDeviationType {
            healthStore.enableBackgroundDelivery(for: temperatureDeviationType, frequency: .immediate) { ok, err in appLog("[HK] bg delivery temperature_deviation: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        }
        if let menstrualFlowType {
            healthStore.enableBackgroundDelivery(for: menstrualFlowType, frequency: .immediate) { ok, err in appLog("[HK] bg delivery menstrual_flow: \(ok ? "enabled" : "failed") \(err?.localizedDescription ?? "")") }
        }
    }

    private func registerObserver(for type: HKSampleType, key: String) throws {
        let query = HKObserverQuery(sampleType: type, predicate: nil) { [weak self] _, completion, error in
            guard let self else { completion(); return }
            if let error = error { appLog("Observer error \(key): \(error.localizedDescription)"); completion(); return }
            Task { [weak self] in
                guard let self else { return }
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
        let pred = HKQuery.predicateForSamples(withStart: Date.distantPast, end: Date(), options: [])
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
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
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
            return
        }

        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(out, chunkSize: 200)
            let windowStart = out.map { $0.start_time }.min() ?? "-"
            let windowEnd = out.map { $0.end_time }.max() ?? "-"
            appLog("[HK-UP] \(anchorKey) rows=\(out.count) window=\(windowStart)..\(windowEnd)")
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
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
            return
        }

        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(out, chunkSize: 200)
            let windowStart = out.map { $0.start_time }.min() ?? "-"
            let windowEnd = out.map { $0.end_time }.max() ?? "-"
            appLog("[HK-UP] \(anchorKey) rows=\(out.count) window=\(windowStart)..\(windowEnd)")
            anchorStore.setAnchor(anchor, forKey: anchorKey)
            StatusStore.shared.setUpload(for: anchorKey)
            if uploaded {
                await requestFeaturesRefreshAfterUpload(rows: out.count, source: "hk:menstrual_flow")
            }
        } catch {
            appLog("Upload error \(anchorKey): \(error.localizedDescription)")
        }
    }

    private func anchoredQuery(type: HKSampleType, predicate: NSPredicate?, anchor: HKQueryAnchor?, limit: Int, sort: NSSortDescriptor) async throws -> (HKQueryAnchor?, [HKSample], Bool) {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<(HKQueryAnchor?, [HKSample], Bool), Error>) in
            let q = HKAnchoredObjectQuery(type: type, predicate: predicate, anchor: anchor, limit: limit) { _, samples, _, newAnchor, error in
                if let error = error { cont.resume(throwing: error); return }
                let sorted = (samples ?? []).sorted { $0.startDate < $1.startDate }
                cont.resume(returning: (newAnchor, sorted, (samples?.count ?? 0) == limit))
            }
            self.healthStore.execute(q)
        }
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
    private func buildAPI() -> APIClient {
        // Read persisted config that @AppStorage writes
        let rawBase = UserDefaults.standard.string(forKey: "baseURL") ?? ""
        let base = rawBase.trimmingCharacters(in: .whitespacesAndNewlines)
        let bearer = (UserDefaults.standard.string(forKey: "bearer") ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let uid = currentUserId().trimmingCharacters(in: .whitespacesAndNewlines)

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
        api.devUserId = uid
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
        let backendAvailable = await MainActor.run { [weak self] in
            self?.appState?.backendDBAvailable ?? true
        }
        guard backendAvailable else {
            appLog("[BG] skip refresh; backend DB=false")
            await logRefreshBlocked()
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
            await backfillOne(type: respiratoryRateType, anchorKey: "respiratory_rate", pred: pred, sort: sort)
        }
        if let restingHeartRateType {
            await backfillOne(type: restingHeartRateType, anchorKey: "resting_heart_rate", pred: pred, sort: sort)
        }
        if let temperatureDeviationType {
            await backfillOne(type: temperatureDeviationType, anchorKey: "temperature_deviation", pred: pred, sort: sort)
        }
        await backfillCycle(pred: pred, sort: sort)
        defaults.set(Self.phase2BackfillVersion, forKey: Self.phase2BackfillMarkerKey)
        await phase2BackfillState.end()
    }

    /// Clear anchors and backfill all supported quantity types from `start` until now.
    /// This is safe to run manually (e.g., from a Debug button) to recover from gaps.
    func forceBackfill(since start: Date) async {
        let keys = [
            "heart_rate",
            "spo2",
            "step_count",
            "hrv_sdnn",
            "respiratory_rate",
            "resting_heart_rate",
            "temperature_deviation",
            "blood_pressure",
            "sleep_stage",
            "menstrual_flow",
        ]
        anchorStore.clear(keys: keys)

        let pred = HKQuery.predicateForSamples(withStart: start, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        await backfillOne(type: hrType,   anchorKey: "heart_rate", pred: pred, sort: sort)
        await backfillOne(type: spo2Type, anchorKey: "spo2",       pred: pred, sort: sort)
        await backfillOne(type: stepsType,anchorKey: "step_count",  pred: pred, sort: sort)
        await backfillOne(type: hrvType,  anchorKey: "hrv_sdnn",    pred: pred, sort: sort)
        if let respiratoryRateType {
            await backfillOne(type: respiratoryRateType, anchorKey: "respiratory_rate", pred: pred, sort: sort)
        }
        if let restingHeartRateType {
            await backfillOne(type: restingHeartRateType, anchorKey: "resting_heart_rate", pred: pred, sort: sort)
        }
        if let temperatureDeviationType {
            await backfillOne(type: temperatureDeviationType, anchorKey: "temperature_deviation", pred: pred, sort: sort)
        }
        await backfillOne(type: bpType,  anchorKey: "blood_pressure", pred: pred, sort: sort)
        await backfillSleep(pred: pred, sort: sort)
        await backfillCycle(pred: pred, sort: sort)
    }
    private func backfillSleep(pred: NSPredicate, sort: NSSortDescriptor) async {
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true
        while more {
            do {
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: sleepType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
            } catch {
                appLog("[Backfill] anchoredQuery error sleep_stage: \(error.localizedDescription)")
                return
            }
        }
        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for sleep_stage in range")
            return
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
        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            appLog("[Backfill] uploaded \(samples.count) sleep_stage samples")
            if uploaded {
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_sleep")
            }
        } catch {
            appLog("[Backfill] upload error sleep_stage: \(error.localizedDescription)")
        }
    }

    private func backfillCycle(pred: NSPredicate, sort: NSSortDescriptor) async {
        guard let menstrualFlowType else { return }
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true
        while more {
            do {
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: menstrualFlowType, predicate: pred, anchor: anchor, limit: 500, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
            } catch {
                appLog("[Backfill] anchoredQuery error menstrual_flow: \(error.localizedDescription)")
                return
            }
        }
        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for menstrual_flow in range")
            return
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
        do {
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            anchorStore.setAnchor(anchor, forKey: "menstrual_flow")
            StatusStore.shared.setUpload(for: "menstrual_flow")
            appLog("[Backfill] uploaded \(samples.count) menstrual_flow samples")
            if uploaded {
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_menstrual_flow")
            }
        } catch {
            appLog("[Backfill] upload error menstrual_flow: \(error.localizedDescription)")
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

    private func backfillOne(type: HKSampleType, anchorKey: String, pred: NSPredicate, sort: NSSortDescriptor) async {
        var anchor: HKQueryAnchor? = nil
        var collected: [HKSample] = []
        var more = true

        while more {
            do {
                let (newAnchor, batch, hasMore) = try await anchoredQuery(type: type, predicate: pred, anchor: anchor, limit: 500, sort: sort)
                anchor = newAnchor
                if !batch.isEmpty { collected.append(contentsOf: batch) }
                more = hasMore
            } catch {
                appLog("[Backfill] anchoredQuery error \(anchorKey): \(error.localizedDescription)")
                return
            }
        }

        guard !collected.isEmpty else {
            appLog("[Backfill] no samples for \(anchorKey) in range")
            return
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

        do {
            let chunkSize = (anchorKey == "heart_rate" ? 100 : 200)
            let api = buildAPI()
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: chunkSize)
            anchorStore.setAnchor(anchor, forKey: anchorKey) // store last anchor so observers resume from here
            StatusStore.shared.setUpload(for: anchorKey)
            appLog("[Backfill] uploaded \(samples.count) \(anchorKey) samples")
            if uploaded {
                await requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:backfill_\(anchorKey)")
            }
        } catch {
            appLog("[Backfill] upload error \(anchorKey): \(error.localizedDescription)")
        }
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
    func anchor(forKey key: String) -> HKQueryAnchor? {
        guard let data = UserDefaults.standard.data(forKey: "hk_anchor_\(key)") else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    /// If `anchor` is nil, the stored anchor is removed (used to recover from stuck anchors).
    func setAnchor(_ anchor: HKQueryAnchor?, forKey key: String) {
        let k = "hk_anchor_\(key)"
        guard let anchor = anchor else {
            UserDefaults.standard.removeObject(forKey: k)
            return
        }
        if let data = try? NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true) {
            UserDefaults.standard.set(data, forKey: k)
        }
    }

    /// Clear multiple anchors by their keys (e.g., ["heart_rate","spo2","step_count","hrv_sdnn"]).
    func clear(keys: [String]) {
        for key in keys { UserDefaults.standard.removeObject(forKey: "hk_anchor_\(key)") }
    }
}
