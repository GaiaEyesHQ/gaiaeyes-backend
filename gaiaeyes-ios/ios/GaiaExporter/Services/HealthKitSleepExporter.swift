import Foundation
import HealthKit

final class HealthKitSleepExporter {
    private let healthStore = HKHealthStore()
    private let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!
    private let diagnosticsMetric = "sleep_stage"

    // ISO8601 formatter with fractional seconds for wire format
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    /// Sum minutes per sleep stage for a list of segments
    func summarizeMinutes(_ segments: [(stage: Stage, start: Date, end: Date)]) -> [Stage: Int] {
        var minutes: [Stage: Int] = [:]
        for seg in segments {
            let m = max(0, Int(seg.end.timeIntervalSince(seg.start) / 60))
            minutes[seg.stage, default: 0] += m
        }
        return minutes
    }

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
        setDiagnosticsValue(iso.string(from: date), prefix: prefix, metric: metric)
    }

    private func recordUploadedSleepDiagnostics(_ segments: [(stage: Stage, start: Date, end: Date)]) {
        guard let latestEnd = segments.map(\.end).max() else { return }
        StatusStore.shared.setUpload(for: diagnosticsMetric)
        setDiagnosticsDate(latestEnd, prefix: "last_sample", metric: diagnosticsMetric)
        setDiagnosticsValue("HealthKit sleep export", prefix: "last_source", metric: diagnosticsMetric)
    }

    enum Stage: String {
        case rem = "rem"
        case core = "core"     // Apple "asleepCore"
        case deep = "deep"
        case awake = "awake"
        case inBed = "inBed"
        case asleep = "asleep" // fallback when unspecified
    }

    // Request permission to read sleep
    func requestAuthorization() async throws {
        let typesToRead: Set<HKObjectType> = [sleepType]

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            healthStore.requestAuthorization(toShare: nil, read: typesToRead) { ok, err in
                if let err = err {
                    cont.resume(throwing: err)
                    return
                }
                guard ok else {
                    cont.resume(throwing: NSError(
                        domain: "HealthKit",
                        code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "User denied HealthKit access"]
                    ))
                    return
                }
                cont.resume()
            }
        }
    }

    // Fetch sleep (stages) in [start,end]
    func fetchSleepStages(from start: Date, to end: Date) async throws -> [(stage: Stage, start: Date, end: Date)] {
        let predicate = HKQuery.predicateForSamples(
            withStart: start,
            end: end,
            options: []
        )
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[(Stage, Date, Date)], Error>) in
            let query = HKSampleQuery(
                sampleType: sleepType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sort]
            ) { _, samples, err in
                if let err = err {
                    cont.resume(throwing: err)
                    return
                }
                guard let samples = samples as? [HKCategorySample] else {
                    cont.resume(returning: [])
                    return
                }
                let mapped: [(Stage, Date, Date)] = samples.compactMap { s in
                    let clampedStart = max(s.startDate, start)
                    let clampedEnd = min(s.endDate, end)
                    guard clampedEnd > clampedStart else { return nil }
                    let stage: Stage
                    switch s.value {
                    case HKCategoryValueSleepAnalysis.inBed.rawValue: stage = .inBed
                    case HKCategoryValueSleepAnalysis.awake.rawValue: stage = .awake
                    case HKCategoryValueSleepAnalysis.asleepREM.rawValue: stage = .rem
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue: stage = .core
                    case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: stage = .deep
                    default: stage = .asleep
                    }
                    return (stage, clampedStart, clampedEnd)
                }
                appLog("[SLEEP] fetched \(samples.count) raw HealthKit samples; mapped \(mapped.count) overlapping segments")
                cont.resume(returning: mapped)
            }
            self.healthStore.execute(query)
        }
    }
    
    /// Convert sleep segments into wire Samples the API expects.
    /// Emits one row per segment with minutes in `value`, unit="min", and `value_text` as the stage string.
    func makeSleepStageSamples(userId: String, segments: [(stage: Stage, start: Date, end: Date)]) -> [Sample] {
        var out: [Sample] = []
        for seg in segments {
            let minutes = max(0, seg.end.timeIntervalSince(seg.start) / 60.0)
            let row = Sample(
                user_id: userId,
                device_os: "ios",
                source: "healthkit",
                type: "sleep_stage",
                start_time: iso.string(from: seg.start),
                end_time: iso.string(from: seg.end),
                value: minutes,
                unit: "min",
                value_text: seg.stage.rawValue
            )
            out.append(row)
        }
        return out
    }

    /// Convenience: pull sleep for the last N days and upload via APIClient in batches.
    @discardableResult
    func syncSleep(lastDays: Int = 2, api: APIClient, userId: String) async throws -> Int {
        let now = Date()
        let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: now) ?? now.addingTimeInterval(-Double(lastDays) * 86400)
        let segs = try await fetchSleepStages(from: start, to: now)
        let samples = makeSleepStageSamples(userId: userId, segments: segs)
        guard !samples.isEmpty else { return 0 }
        let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
        if uploaded {
            recordUploadedSleepDiagnostics(segs)
            await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "sleep_exporter")
            return samples.count
        }
        return 0
    }
}
