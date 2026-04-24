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
        throw NSError(
            domain: "HealthKit",
            code: 2,
            userInfo: [NSLocalizedDescriptionKey: "Blood pressure correlation reads are not supported on this device."]
        )
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
        _ = start
        _ = end
        return []
    }
}
