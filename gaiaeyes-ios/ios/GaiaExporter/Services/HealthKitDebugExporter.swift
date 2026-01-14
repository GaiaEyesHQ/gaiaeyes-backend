//
//  HealthKitDebugExporter.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/18/25.
//

//
//  HealthKitDebugExporter.swift
//  GaiaExporter
//
//  Drop-in diagnostics to figure out why non-HR data stopped after 9/9.
//  iOS 15+ (uses async/await wrappers for readability).
//

import Foundation
import HealthKit

@MainActor
final class HealthKitDebugExporter: ObservableObject {
    static let shared = HealthKitDebugExporter()

    private let healthStore = HKHealthStore()
    private let tz = TimeZone(identifier: "America/Chicago") ?? .current
    private let defaultSince: Date = {
        // start right after 9/09 local midnight
        var comps = DateComponents()
        comps.year = 2025; comps.month = 9; comps.day = 10; comps.hour = 0; comps.minute = 0
        return Calendar(identifier: .gregorian).date(from: comps) ?? Date().addingTimeInterval(-7*24*3600)
    }()

    private func isAuthorized(_ type: HKObjectType) -> Bool {
        return healthStore.authorizationStatus(for: type) == .sharingAuthorized
    }

    // MARK: - Types

    private var quantityTypes: [HKQuantityTypeIdentifier] = [
        .heartRate,
        .oxygenSaturation,
        .stepCount,
        .heartRateVariabilitySDNN
    ]


    // BP correlation
    private let bloodPressureType = HKObjectType.correlationType(forIdentifier: .bloodPressure)!

    // Sleep categories (stages are values on this)
    private let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!

    // Anchors (optional: if your app keeps them, use these keys)
    private let anchorKeys: [String: HKSampleType] = [:] // fill if you use anchors externally

    // MARK: - Public API

    /// Requests permissions for all relevant types (skips BP if disallowed).
    func requestPermissions() async throws {
        // Request quantities + sleep only; exclude BP correlation for diagnostics to avoid OS crash when disallowed
        var objs = [HKObjectType]()
        objs.append(contentsOf: quantityTypes.compactMap { HKObjectType.quantityType(forIdentifier: $0) })
        objs.append(sleepType)
        let readAll = Set(objs)

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            healthStore.requestAuthorization(toShare: nil, read: readAll) { ok, err in
                if let err = err { cont.resume(throwing: err); return }
                guard ok else {
                    cont.resume(throwing: NSError(domain: "HKAuth", code: 1, userInfo: [NSLocalizedDescriptionKey: "Authorization not granted"]))
                    return
                }
                cont.resume()
            }
        }
    }

    /// Enables background delivery for each type (best-effort, logs results).
    func enableBackgroundDelivery() {
        for qtId in quantityTypes {
            if let t = HKObjectType.quantityType(forIdentifier: qtId), isAuthorized(t) {
                healthStore.enableBackgroundDelivery(for: t, frequency: .immediate) { ok, err in
                    appLog("[HKDBG] enableBackgroundDelivery \(qtId.rawValue): \(ok ? "OK" : "FAIL") \(err?.localizedDescription ?? "")")
                }
            } else {
                appLog("[HKDBG] Skipping enableBackgroundDelivery for \(qtId.rawValue) (not authorized)")
            }
        }
    }

    /// Clears any locally stored anchors (if you use them) so next sync refetches everything.
    func resetAnchors() {
        let ud = UserDefaults.standard
        for key in anchorKeys.keys {
            ud.removeObject(forKey: "hk_anchor_\(key)")
        }
        ud.synchronize()
        appLog("[HKDBG] Anchors cleared.")
    }

    /// Run the full diagnostic sweep.
    func runDiagnostics(since: Date? = nil) async {
        let sinceDate = since ?? defaultSince
        appLog("========== HealthKit Diagnostics (Anchored) ==========")
        appLog("Since (local): \(sinceDate)  Using HKAnchoredObjectQuery like BackgroundSync")

        do {
            try await requestPermissions()
        } catch {
            appLog("[HKDBG] Authorization failed: \(error.localizedDescription)")
            return
        }

        enableBackgroundDelivery()

        for qtId in quantityTypes {
            guard let t = HKObjectType.quantityType(forIdentifier: qtId) else { continue }
            if isAuthorized(t) {
                await anchoredCountQuantitySamples(type: t, label: qtId.rawValue, since: sinceDate)
            } else {
                appLog("[HKDBG] Skipping \(qtId.rawValue) (not authorized)")
            }
        }

        if !isAuthorized(sleepType) {
            appLog("[HKDBG] Skipping sleepAnalysis (not authorized)")
            appLog("=====================================================")
            return
        }

        await analyzeSleep(since: sinceDate)

        appLog("=====================================================")
    }

    // MARK: - Helpers (Quantities)

    private func anchoredCountQuantitySamples(type: HKQuantityType, label: String, since: Date) async {
        let predicate = HKQuery.predicateForSamples(withStart: Date.distantPast, end: Date(), options: [])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        var anchor: HKQueryAnchor? = nil
        var total = 0
        var first: Date?
        var last: Date?

        while true {
            let (newAnchor, batch, more) = await anchoredFetch(type: type, predicate: predicate, anchor: anchor, limit: 500, sort: sort)
            anchor = newAnchor
            if !batch.isEmpty {
                total += batch.count
                if first == nil { first = batch.first?.startDate }
                last = batch.last?.endDate
            }
            if !more { break }
        }

        appLog("[HKDBG] \(label): count=\(total) first=\(fmt(first)) last=\(fmt(last))")
    }

    private func anchoredFetch(type: HKSampleType, predicate: NSPredicate?, anchor: HKQueryAnchor?, limit: Int, sort: NSSortDescriptor) async -> (HKQueryAnchor?, [HKSample], Bool) {
        await withCheckedContinuation { cont in
            let q = HKAnchoredObjectQuery(type: type, predicate: predicate, anchor: anchor, limit: limit) { _, samples, _, newAnchor, error in
                if let error = error {
                    appLog("[HKDBG] anchoredFetch error (\(type)): \(error.localizedDescription)")
                    cont.resume(returning: (anchor, [], false))
                    return
                }
                let sorted = (samples ?? []).sorted { $0.startDate < $1.startDate }
                cont.resume(returning: (newAnchor, sorted, (samples?.count ?? 0) == limit))
            }
            self.healthStore.execute(q)
        }
    }

    // MARK: - Blood Pressure (Correlation)

    private func countBloodPressure(since: Date) async {
        if !isAuthorized(bloodPressureType) {
            appLog("[HKDBG] Skipping BP correlation (not authorized)")
            return
        }
        appLog("[HKDBG] Skipped (no BP correlation diagnostics implemented)")
    }

    // MARK: - Sleep (Category samples, with stage breakdown)

    private func analyzeSleep(since: Date) async {
        let exporter = HealthKitSleepExporter()
        do {
            let segs = try await exporter.fetchSleepStages(from: since, to: Date())
            let mins = exporter.summarizeMinutes(segs)
            let total = (mins[.rem] ?? 0) + (mins[.core] ?? 0) + (mins[.deep] ?? 0)
            appLog("[HKDBG] sleepAnalysis: segments=\(segs.count) total=\(total)m REM=\(mins[.rem] ?? 0) CORE=\(mins[.core] ?? 0) DEEP=\(mins[.deep] ?? 0) AWAKE=\(mins[.awake] ?? 0) INBED=\(mins[.inBed] ?? 0)")
        } catch {
            appLog("[HKDBG] sleepAnalysis error: \(error.localizedDescription)")
        }
    }

    /// Convenience: run a one-shot sleep sync and log results
    func syncSleepNow(api: APIClient, userId: String, days: Int = 2) async {
        let exporter = HealthKitSleepExporter()
        do {
            try await exporter.requestAuthorization()
            let uploaded = try await exporter.syncSleep(lastDays: days, api: api, userId: userId)
            appLog("[HKDBG] syncSleepNow uploaded=\(uploaded)")
        } catch {
            appLog("[HKDBG] syncSleepNow error: \(error.localizedDescription)")
        }
    }

    // MARK: - Heartbeat Series (RR intervals)

    private func analyzeHeartbeatSeries(since: Date) async {
        print("[HKDBG] Skipped (not part of BackgroundSync quantity set)")
    }

    // MARK: - Utils

    private func fmt(_ d: Date?) -> String {
        guard let d = d else { return "nil" }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        f.timeZone = tz
        return f.string(from: d)
    }
}
