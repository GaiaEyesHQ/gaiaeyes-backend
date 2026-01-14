// Services/Polar/PolarECGSession.swift
import Foundation

#if canImport(PolarBleSdk)
import PolarBleSdk
import RxSwift
#endif

final class PolarECGSession {

    #if canImport(PolarBleSdk)
    private struct EcgSettingCandidate {
        let setting: PolarSensorSetting
        let description: String
    };

    private let api: PolarBleApi
    private let deviceId: String
    private let disposeBag = DisposeBag()
    private var ecgDisposable: Disposable?
    private var hasRetriedOnce = false
    private var isRunning = false
    #endif

    private let uploader: EcgUploader
    var onLog: ((String) -> Void)?
    var onState: ((Bool) -> Void)?    // true started, false stopped

    #if canImport(PolarBleSdk)
    init(deviceId: String, api: PolarBleApi, uploader: EcgUploader) {
        self.deviceId = deviceId
        self.api = api
        self.uploader = uploader
    }
    #else
    // Stub initializer used when PolarBleSdk is not available
    init(deviceId: String, uploader: EcgUploader) {
        self.uploader = uploader
    }
    #endif

    @MainActor
    func start() {
        #if canImport(PolarBleSdk)
        guard !isRunning else { return }
        onLog?("ECG start: requesting settings for \(deviceId)")

        Task { [weak self] in
            guard let self else { return }
            do {
                // Request settings (may throw)
                let settings = try await requestEcgSettings()

                // Enumerate concrete combinations from the supported options
                let candidates = makeEcgSettingCandidates(from: settings)
                guard !candidates.isEmpty else {
                    self.onLog?("ECG start failed: no valid ECG setting combinations")
                    self.onState?(false)
                    return
                }

                var lastError: Error?
                for candidate in candidates {
                    self.onLog?("ECG start: trying \(candidate.description)")
                    do {
                        let disposable = try await startStreaming(settings: candidate.setting)
                        self.ecgDisposable = disposable
                        self.isRunning = true
                        self.onState?(true)
                        self.onLog?("ECG stream running (\(candidate.description))")
                        return
                    } catch {
                        lastError = error
                        self.onLog?("ECG start: combination \(candidate.description) failed — \(error.localizedDescription)")
                    }
                }

                if let lastError {
                    throw lastError
                }
            } catch {
                let ns = error as NSError
                if ns.domain.contains("PolarBleSdk"), ns.code == 9, self.hasRetriedOnce == false {
                    self.hasRetriedOnce = true
                    self.onLog?("ECG start: Polar error 9 (invalid state), retrying once after 0.7s…")
                    try? await Task.sleep(nanoseconds: 700_000_000)
                    self.start() // single retry
                    return
                }
                self.onLog?("ECG start failed: \(error.localizedDescription)")
                self.onState?(false)
            }
        }
        #else
        onLog?("[ECG] Polar SDK not present")
        onState?(false)
        #endif
    }

    @MainActor
    func stop() {
        #if canImport(PolarBleSdk)
        guard isRunning || ecgDisposable != nil else { return }
        onLog?("ECG stop: stopping stream")
        if let disposable = ecgDisposable {
            disposable.dispose()
        }
        ecgDisposable = nil
        isRunning = false
        hasRetriedOnce = false
        onState?(false)
        #else
        onLog?("[ECG] Polar SDK not present")
        #endif
    }

    #if canImport(PolarBleSdk)
    private func makeEcgSettingCandidates(from setting: PolarSensorSetting) -> [EcgSettingCandidate] {
        let options = setting.settings
        let sampleRates = Array(options[.sampleRate] ?? []).sorted()
        let resolutions = Array(options[.resolution] ?? []).sorted()
        let ranges = Array(options[.range] ?? []).sorted()

        onLog?("ECG start: settings options sr=\(sampleRates), res=\(resolutions)\(ranges.isEmpty ? "" : ", range=\(ranges)")")

        guard !sampleRates.isEmpty, !resolutions.isEmpty else {
            return []
        }

        var candidates: [EcgSettingCandidate] = []

        func appendCandidate(sr: UInt32, res: UInt32, range: UInt32?) {
            var dict: [PolarSensorSetting.SettingType: UInt32] = [
                .sampleRate: sr,
                .resolution: res
            ]
            if let range {
                dict[.range] = range
            }

            do {
                let setting = try PolarSensorSetting(dict)
                let description: String
                if let range {
                    description = "sr=\(sr)Hz res=\(res)bits range=\(range)"
                } else {
                    description = "sr=\(sr)Hz res=\(res)bits"
                }
                candidates.append(EcgSettingCandidate(setting: setting, description: description))
            } catch {
                let rangeText = range != nil ? " range=\(range!)" : ""
                onLog?("ECG start: invalid setting sr=\(sr)Hz res=\(res)bits\(rangeText) — \(error.localizedDescription)")
            }
        }

        for sr in sampleRates {
            for res in resolutions {
                appendCandidate(sr: sr, res: res, range: nil)
            }
        }

        if !ranges.isEmpty {
            for sr in sampleRates {
                for res in resolutions {
                    for range in ranges {
                        appendCandidate(sr: sr, res: res, range: range)
                    }
                }
            }
        }

        return candidates
    }

    private func requestEcgSettings() async throws -> PolarSensorSetting {
        try await withCheckedThrowingContinuation { continuation in
            api.requestStreamSettings(deviceId, feature: .ecg)
                .subscribe(onSuccess: { setting in
                    continuation.resume(returning: setting)
                }, onFailure: { error in
                    continuation.resume(throwing: error)
                })
                .disposed(by: disposeBag)
        }
    }

    private func startStreaming(settings: PolarSensorSetting) async throws -> Disposable {
        try await withCheckedThrowingContinuation { continuation in
            // Create the subscription first, then immediately resume with the disposable
            // to avoid any double-resume races if the stream emits/terminates early.
            let disposable = api.startEcgStreaming(deviceId, settings: settings)
                .subscribe(
                    onNext: { [weak self] (data: PolarEcgData) in
                        self?.handle(sample: data)
                    },
                    onError: { [weak self] error in
                        // We already returned the disposable to the caller; just log and stop.
                        self?.onLog?("ECG stream error: \(error.localizedDescription)")
                        Task { @MainActor in self?.stop() }
                    },
                    onCompleted: { [weak self] in
                        self?.onLog?("ECG stream completed")
                        Task { @MainActor in self?.stop() }
                    }
                )
            continuation.resume(returning: disposable)
        }
    }

    private func handle(sample: PolarEcgData) {
        // PolarEcgData in this SDK build is an array of tuples: (timeStamp: UInt64, voltage: Int32)
        let mv: [Double] = sample.map { Double($0.voltage) / 1_000_000.0 }
        uploader.push(samplesMv: mv)
    }
    #endif
}
