import Foundation
import HealthKit

// This file extends HealthKitVitalsExporter with concrete sync implementations.
// It does NOT declare APIClient; it only uses the APIClient type that already exists in Services/APIClient.swift.

extension HealthKitVitalsExporter {

    // MARK: - HRV SDNN
    func syncHRV_SDNN(lastDays: Int, api: APIClient, userId: String) async {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: end) else { return }
        do {
            let items = try await fetchHRV_SDNN(from: start, to: end)  // [(Date, Date, Double)]
            if items.isEmpty {
                api.logger?("No HRV SDNN samples found in the last \(lastDays)d")
                return
            }
            api.logger?("Found \(items.count) HRV SDNN samples")
            let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let samples: [Sample] = items.map { (s, e, ms) in
                Sample(user_id: userId, device_os: "ios", source: "healthkit",
                       type: "hrv_sdnn",
                       start_time: iso.string(from: s), end_time: iso.string(from: e),
                       value: ms, unit: "ms", value_text: nil)
            }
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            StatusStore.shared.setUpload(for: "hrv_sdnn")
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:hrv_sdnn")
            }
        } catch {
            api.logger?("HRV SDNN error: \(error.localizedDescription)")
        }
    }

    // MARK: - Steps
    func syncSteps(lastDays: Int, api: APIClient, userId: String) async {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: end) else { return }
        do {
            let items = try await fetchSteps(from: start, to: end)  // [(Date, Date, Double)]
            if items.isEmpty {
                api.logger?("No Steps found in the last \(lastDays)d")
                return
            }
            api.logger?("Found \(items.count) step samples")
            let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let samples: [Sample] = items.map { (s, e, count) in
                Sample(user_id: userId, device_os: "ios", source: "healthkit",
                       type: "step_count",
                       start_time: iso.string(from: s), end_time: iso.string(from: e),
                       value: count, unit: "count", value_text: nil)
            }
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            StatusStore.shared.setUpload(for: "step_count")
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:step_count")
            }
        } catch {
            api.logger?("Steps error: \(error.localizedDescription)")
        }
    }

    // MARK: - Heart Rate
    func syncHeartRate(lastDays: Int, api: APIClient, userId: String) async {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: end) else { return }
        do {
            let items = try await fetchHeartRate(from: start, to: end)  // [(Date, Date, Double)]
            if items.isEmpty {
                api.logger?("No Heart Rate samples found in the last \(lastDays)d")
                return
            }
            api.logger?("Found \(items.count) HR samples")
            let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let samples: [Sample] = items.map { (s, e, bpm) in
                Sample(user_id: userId, device_os: "ios", source: "healthkit",
                       type: "heart_rate",
                       start_time: iso.string(from: s), end_time: iso.string(from: e),
                       value: bpm, unit: "bpm", value_text: nil)
            }
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            StatusStore.shared.setUpload(for: "heart_rate")
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:heart_rate")
            }
        } catch {
            api.logger?("HR error: \(error.localizedDescription)")
        }
    }

    // MARK: - SpO₂
    func syncSpO2(lastDays: Int, api: APIClient, userId: String) async {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: end) else { return }
        do {
            let items = try await fetchSpO2(from: start, to: end)  // [(Date, Date, Double)]
            if items.isEmpty {
                api.logger?("No SpO₂ samples found in the last \(lastDays)d")
                return
            }
            api.logger?("Found \(items.count) SpO₂ samples")
            let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let samples: [Sample] = items.map { (s, e, pct) in
                Sample(user_id: userId, device_os: "ios", source: "healthkit",
                       type: "spo2",
                       start_time: iso.string(from: s), end_time: iso.string(from: e),
                       value: pct, unit: "%", value_text: nil)
            }
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            StatusStore.shared.setUpload(for: "spo2")
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:spo2")
            }
        } catch {
            api.logger?("SpO₂ error: \(error.localizedDescription)")
        }
    }

    // MARK: - Blood Pressure
    func syncBloodPressure(lastDays: Int, api: APIClient, userId: String) async {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -lastDays, to: end) else { return }
        do {
            // [(Date, Date, Double?, Double?)]
            let items = try await fetchBloodPressure(from: start, to: end)
            if items.isEmpty {
                api.logger?("No Blood Pressure readings found in the last \(lastDays)d")
                return
            }
            api.logger?("Found \(items.count) BP readings (correlations)")
            let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var samples: [Sample] = []
            samples.reserveCapacity(items.count * 2)
            for (s, e, sys, dia) in items {
                if let v = sys {
                    samples.append(Sample(user_id: userId, device_os: "ios", source: "healthkit",
                                          type: "blood_pressure_systolic",
                                          start_time: iso.string(from: s), end_time: iso.string(from: e),
                                          value: v, unit: "mmHg", value_text: nil))
                }
                if let v = dia {
                    samples.append(Sample(user_id: userId, device_os: "ios", source: "healthkit",
                                          type: "blood_pressure_diastolic",
                                          start_time: iso.string(from: s), end_time: iso.string(from: e),
                                          value: v, unit: "mmHg", value_text: nil))
                }
            }
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 200)
            StatusStore.shared.setUpload(for: "blood_pressure")
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "hk:blood_pressure")
            }
        } catch {
            api.logger?("BP error: \(error.localizedDescription)")
        }
    }
}
