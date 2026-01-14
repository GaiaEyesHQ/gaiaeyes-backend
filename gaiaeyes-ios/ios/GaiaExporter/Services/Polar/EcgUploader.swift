// Services/Polar/EcgUploader.swift
import Foundation

final class EcgUploader {
    private let api: APIClient
    private let userId: String
    private let windowSeconds: TimeInterval
    private var buffer: [Double] = []
    private var windowStart: Date?
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    init(api: APIClient, userId: String, windowSeconds: TimeInterval = 2.0) {
        self.api = api
        self.userId = userId
        self.windowSeconds = windowSeconds
    }

    func push(samplesMv: [Double]) {
        guard !samplesMv.isEmpty else { return }
        let now = Date()
        if windowStart == nil { windowStart = now }
        buffer.append(contentsOf: samplesMv)

        // flush if window elapsed
        if let start = windowStart, now.timeIntervalSince(start) >= windowSeconds {
            Task { await flush() }
        }
    }

    private func encodeJson(_ arr: [Double]) -> String? {
        guard let d = try? JSONSerialization.data(withJSONObject: arr, options: []) else { return nil }
        return String(data: d, encoding: .utf8)
    }

    @MainActor private func resetWindow(_ now: Date) {
        buffer.removeAll(keepingCapacity: true)
        windowStart = now
    }

    @MainActor func flush() async {
        guard let start = windowStart, !buffer.isEmpty else { return }
        let end = Date()
        let json = encodeJson(buffer) ?? "[]"
        let samples: [Sample] = [
            Sample(user_id: userId,
                   device_os: "ios",
                   source: "polar",
                   type: "ecg",
                   start_time: iso.string(from: start),
                   end_time: iso.string(from: end),
                   value: nil,
                   unit: nil,
                   value_text: json)
        ]
        do {
            let uploaded = try await api.postSamplesChunked(samples, chunkSize: 50)
            if uploaded {
                await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: samples.count, source: "polar:ecg")
            }
        } catch {
            api.logger?("[ECG] upload error: \(error.localizedDescription)")
        }
        resetWindow(end)
    }
}
