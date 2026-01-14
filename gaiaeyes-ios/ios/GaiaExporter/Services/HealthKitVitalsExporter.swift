import Foundation
import HealthKit

final class HealthKitVitalsExporter {
    private let healthStore = HKHealthStore()

    // MARK: - Permissions
    func requestPermissions() async throws {
        var toRead = Set<HKObjectType>()
        if let hr    = HKObjectType.quantityType(forIdentifier: .heartRate) { toRead.insert(hr) }
        if let spo2  = HKObjectType.quantityType(forIdentifier: .oxygenSaturation) { toRead.insert(spo2) }
        if let hrv   = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { toRead.insert(hrv) }
        if let steps = HKObjectType.quantityType(forIdentifier: .stepCount) { toRead.insert(steps) }
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { toRead.insert(sleep) }
        if let bp = HKObjectType.correlationType(forIdentifier: .bloodPressure) { toRead.insert(bp) }

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            self.healthStore.requestAuthorization(toShare: nil, read: toRead) { ok, err in
                if let err = err { cont.resume(throwing: err); return }
                guard ok else {
                    cont.resume(throwing: NSError(domain: "HealthKit", code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "User denied HealthKit access"]))
                    return
                }
                cont.resume(returning: ())
            }
        }
    }

    func requestBloodPressurePermission() async throws {
        guard let bp = HKObjectType.correlationType(forIdentifier: .bloodPressure) else { return }
        let toRead: Set<HKObjectType> = [bp]
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            self.healthStore.requestAuthorization(toShare: nil, read: toRead) { ok, err in
                if let err = err { cont.resume(throwing: err); return }
                guard ok else {
                    cont.resume(throwing: NSError(
                        domain: "HealthKit",
                        code: 2,
                        userInfo: [NSLocalizedDescriptionKey:
                            "Blood Pressure permission not granted. Open Health → Profile → Privacy → Apps → Gaia Exporter and enable Blood Pressure."]
                    ))
                    return
                }
                cont.resume(returning: ())
            }
        }
    }

    // MARK: - ISO helper
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    // MARK: - Steps
    func fetchSteps(from start: Date, to end: Date) async throws -> [(Date, Date, Double)] {
        guard let qtype = HKObjectType.quantityType(forIdentifier: .stepCount) else { return [] }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [.strictStartDate, .strictEndDate])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Date, Date, Double)], Error>) in
            let q = HKSampleQuery(sampleType: qtype, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, err in
                if let err = err { cont.resume(throwing: err); return }
                let out: [(Date, Date, Double)] =
                    (samples as? [HKQuantitySample])?.map {
                        let v = $0.quantity.doubleValue(for: HKUnit.count())
                        return ($0.startDate, $0.endDate, v)
                    } ?? []
                cont.resume(returning: out)
            }
            self.healthStore.execute(q)
        }
    }

    // MARK: - Heart Rate
    func fetchHeartRate(from start: Date, to end: Date) async throws -> [(Date, Date, Double)] {
        guard let qtype = HKObjectType.quantityType(forIdentifier: .heartRate) else { return [] }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [.strictStartDate, .strictEndDate])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Date, Date, Double)], Error>) in
            let q = HKSampleQuery(sampleType: qtype, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, err in
                if let err = err { cont.resume(throwing: err); return }
                let out: [(Date, Date, Double)] =
                    (samples as? [HKQuantitySample])?.map {
                        let bpm = $0.quantity.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute()))
                        return ($0.startDate, $0.endDate, bpm)
                    } ?? []
                cont.resume(returning: out)
            }
            self.healthStore.execute(q)
        }
    }

    // MARK: - HRV SDNN
    func fetchHRV_SDNN(from start: Date, to end: Date) async throws -> [(Date, Date, Double)] {
        guard let qtype = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) else { return [] }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [.strictStartDate, .strictEndDate])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Date, Date, Double)], Error>) in
            let q = HKSampleQuery(sampleType: qtype, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, err in
                if let err = err { cont.resume(throwing: err); return }
                let out: [(Date, Date, Double)] =
                    (samples as? [HKQuantitySample])?.map {
                        let ms = $0.quantity.doubleValue(for: HKUnit.secondUnit(with: .milli))
                        return ($0.startDate, $0.endDate, ms)
                    } ?? []
                cont.resume(returning: out)
            }
            self.healthStore.execute(q)
        }
    }

    // MARK: - SpO2
    func fetchSpO2(from start: Date, to end: Date) async throws -> [(Date, Date, Double)] {
        guard let qtype = HKObjectType.quantityType(forIdentifier: .oxygenSaturation) else { return [] }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [.strictStartDate, .strictEndDate])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Date, Date, Double)], Error>) in
            let q = HKSampleQuery(sampleType: qtype, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, err in
                if let err = err { cont.resume(throwing: err); return }
                let out: [(Date, Date, Double)] =
                    (samples as? [HKQuantitySample])?.map {
                        // HealthKit stores SpO2 as 0.0–1.0 fraction
                        let pct = $0.quantity.doubleValue(for: HKUnit.percent()) * 100.0
                        return ($0.startDate, $0.endDate, pct)
                    } ?? []
                cont.resume(returning: out)
            }
            self.healthStore.execute(q)
        }
    }

    // MARK: - Blood Pressure (Correlation)
    func fetchBloodPressure(from start: Date, to end: Date) async throws -> [(Date, Date, Double?, Double?)] {
        guard let ctype = HKObjectType.correlationType(forIdentifier: .bloodPressure) else { return [] }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [.strictStartDate, .strictEndDate])
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        // cache quantity types once
        let systolicType  = HKObjectType.quantityType(forIdentifier: .bloodPressureSystolic)
        let diastolicType = HKObjectType.quantityType(forIdentifier: .bloodPressureDiastolic)

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Date, Date, Double?, Double?)], Error>) in
            let q = HKSampleQuery(sampleType: ctype, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, err in
                if let err = err { cont.resume(throwing: err); return }
                var out: [(Date, Date, Double?, Double?)] = []
                if let corr = samples as? [HKCorrelation] {
                    for c in corr {
                        let start = c.startDate
                        let end   = c.endDate
                        var sys: Double? = nil
                        var dia: Double? = nil
                        for s in c.objects.compactMap({ $0 as? HKQuantitySample }) {
                            if let st = systolicType, s.quantityType == st {
                                let v = s.quantity.doubleValue(for: .millimeterOfMercury())
                                if v.isFinite, v >= 40, v <= 260 { sys = v }
                            } else if let dt = diastolicType, s.quantityType == dt {
                                let v = s.quantity.doubleValue(for: .millimeterOfMercury())
                                if v.isFinite, v >= 30, v <= 180 { dia = v }
                            }
                        }
                        out.append((start, end, sys, dia))
                    }
                }
                cont.resume(returning: out)
            }
            self.healthStore.execute(q)
        }
    }
}
