import Foundation
import HealthKit

@MainActor
final class HealthKitManager: NSObject, ObservableObject {
    private let healthStore = HKHealthStore()
    @Published var isAuthorized = false

    private let hrType = HKObjectType.quantityType(forIdentifier: .heartRate)!
    private let hrvType = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!
    private let stepsType = HKObjectType.quantityType(forIdentifier: .stepCount)!
    private let spo2Type = HKObjectType.quantityType(forIdentifier: .oxygenSaturation)!

    func bootstrap() {
        // Placeholder for restoring anchors later if you add them.
    }

    func requestAuthorization(completion: @escaping (Bool)->Void) {
        let types: Set<HKObjectType> = [
            hrType, hrvType, stepsType, spo2Type,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
            HKObjectType.workoutType()
        ]
        healthStore.requestAuthorization(toShare: nil, read: types) { [weak self] ok, _ in
            DispatchQueue.main.async {
                self?.isAuthorized = ok
                completion(ok)
            }
        }
    }

    func collectRecentSamples() async throws -> [SampleOut] {
        guard isAuthorized else { return [] }
        // Simple v1: last 24 hours, manual sync.
        let now = Date()
        let start = Calendar.current.date(byAdding: .day, value: -1, to: now)!

        let hr = try await readQuantitySamples(type: hrType,
                                               unit: .count().unitDivided(by: .minute()),
                                               typeName: "heart_rate",
                                               start: start, end: now)

        let hrv = try await readQuantitySamples(type: hrvType,
                                                unit: HKUnit.secondUnit(with: .milli),
                                                typeName: "hrv",
                                                start: start, end: now)

        let steps = try await readQuantitySamples(type: stepsType,
                                                  unit: .count(),
                                                  typeName: "steps",
                                                  start: start, end: now)

        let spo2 = try await readQuantitySamples(type: spo2Type,
                                                 unit: HKUnit.percent(),
                                                 typeName: "spo2",
                                                 start: start, end: now)

        return hr + hrv + steps + spo2
    }

    private func readQuantitySamples(type: HKQuantityType,
                                     unit: HKUnit,
                                     typeName: String,
                                     start: Date,
                                     end: Date) async throws -> [SampleOut] {
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(sampleType: type, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error = error {
                    cont.resume(throwing: error)
                    return
                }
                guard let qSamples = samples as? [HKQuantitySample] else {
                    cont.resume(returning: [])
                    return
                }
                let userId = UserDefaults.standard.string(forKey: "userId") ?? "00000000-0000-0000-0000-000000000000"
                let formatter = ISO8601DateFormatter()
                let out: [SampleOut] = qSamples.map { qs in
                    let v = qs.quantity.doubleValue(for: unit)
                    return SampleOut(
                        user_id: userId,
                        device_os: "ios",
                        source: qs.sourceRevision.source.name,
                        type: typeName,
                        start_time: formatter.string(from: qs.startDate),
                        end_time: formatter.string(from: qs.endDate),
                        value: v,
                        unit: unit.description,
                        value_text: nil
                    )
                }
                cont.resume(returning: out)
            }
            self.healthStore.execute(query)
        }
    }
}
