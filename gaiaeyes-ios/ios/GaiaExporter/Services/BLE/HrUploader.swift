//
//  HrUploader.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/6/25.
//


import Foundation

private actor UploadGate {
    private var isUploading = false
    func acquire() async { while isUploading { try? await Task.sleep(nanoseconds: 5_000_000) } ; isUploading = true }
    func release() { isUploading = false }
}

final class HrUploader {
    private let api: APIClient
    private let userId: String
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    // Coalescing queue to avoid flooding the server with tiny requests
    private var queue: [Sample] = []
    private var flushTask: Task<Void, Never>?
    private let flushInterval: TimeInterval = 2.0   // seconds
    private let maxBatch: Int = 180                 // send up to this many at once
    private let gate = UploadGate()                 // serialize actual network sends
    private var backoffUntil: Date?

    init(api: APIClient, userId: String) {
        self.api = api
        self.userId = userId
    }

    @MainActor
    func upload(hrBpm: Int?, rrMs: [Int]) async {
        // If we've recently seen repeated 500s/timeouts, pause briefly
        if let until = backoffUntil, Date() < until { return }

        let now = Date()
        var toEnqueue: [Sample] = []
        if let hr = hrBpm {
            toEnqueue.append(Sample(user_id: userId, device_os: "ios", source: "ble",
                                    type: "heart_rate",
                                    start_time: iso.string(from: now), end_time: iso.string(from: now),
                                    value: Double(hr), unit: "bpm", value_text: nil))
        }
        for rr in rrMs {
            toEnqueue.append(Sample(user_id: userId, device_os: "ios", source: "ble",
                                    type: "heart_rate_rr",
                                    start_time: iso.string(from: now), end_time: iso.string(from: now),
                                    value: Double(rr), unit: "ms", value_text: nil))
        }
        guard !toEnqueue.isEmpty else { return }

        // Enqueue
        queue.append(contentsOf: toEnqueue)

        // If enough rows, flush immediately; otherwise schedule a one‑shot flush soon
        if queue.count >= maxBatch {
            await flush()
        } else if flushTask == nil {
            flushTask = Task { [weak self] in
                guard let self = self else { return }
                do { try await Task.sleep(nanoseconds: UInt64(self.flushInterval * 1_000_000_000)) } catch {}
                await self.flush()
                self.flushTask = nil
            }
        }
    }

    @MainActor
    func flush() async {
        guard !queue.isEmpty else { return }
        // Take up to maxBatch rows
        let chunk = Array(queue.prefix(maxBatch))
        queue.removeFirst(min(maxBatch, queue.count))

        // Serialize actual network upload
        await gate.acquire()
        defer { Task { await gate.release() } }

        do {
            let uploaded = try await api.postSamplesChunked(chunk, chunkSize: maxBatch)
            StatusStore.shared.setUpload(for: "heart_rate")
            if uploaded {
                // Give the backend a moment to materialize today's mart, then trigger a single refetch
                let rows = chunk.count
                api.logger?("[BG] upload ok (heart_rate): inserted=\(rows); scheduling features refetch in ~4s…")
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 4_000_000_000)
                    // Clear any client-side debounce/guard indirectly by emitting the standard refresh signal
                    NotificationCenter.default.post(name: .featuresShouldRefresh, object: nil)
                    await HealthKitBackgroundSync.shared.requestFeaturesRefreshAfterUpload(rows: rows, source: "ble:heart_rate")
                }
            }
        } catch {
            api.logger?("BLE upload error: \(error.localizedDescription)")
            // Simple backoff window after repeated 500s/timeouts
            let msg = error.localizedDescription.lowercased()
            if msg.contains("500") || msg.contains("timed out") || (error as NSError).domain == "HTTP" {
                backoffUntil = Date().addingTimeInterval(10)
            }
        }
    }

    deinit { flushTask?.cancel() }
}
