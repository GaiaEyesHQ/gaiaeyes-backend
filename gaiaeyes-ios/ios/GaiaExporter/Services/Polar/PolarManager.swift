import Foundation
#if canImport(PolarBleSdk)
import PolarBleSdk
import RxSwift
#endif

protocol PolarManagerDelegate: AnyObject {
    func polarLog(_ msg: String)
    func polarDidConnect(deviceId: String, name: String?)
    func polarDidDisconnect(deviceId: String, error: Error?)
    func polarEcgDidStart()
    func polarEcgDidStop()
}

final class PolarManager: NSObject {
    weak var delegate: PolarManagerDelegate?

    #if canImport(PolarBleSdk)
    private var api: PolarBleApi = {
        // Enable HR + Online Streaming + Features Configuration + Device Info
        let feats: Set<PolarBleSdkFeature> = [
            .feature_hr,
            .feature_polar_online_streaming,
            .feature_polar_features_configuration_service,
            .feature_device_info
        ]
        return PolarBleApiDefaultImpl.polarImplementation(DispatchQueue.main, features: feats)
    }()
    
    #endif

    private(set) var deviceId: String?
    private(set) var deviceName: String?
    private(set) var isConnected: Bool = false

    private var ecgSession: PolarECGSession?
    private var ecgReady: Bool = false
    private var pendingUploader: EcgUploader?
    #if canImport(PolarBleSdk)
    private let disposeBag = DisposeBag()
    private var ecgProbeTask: Task<Void, Never>?
    private var sdkContact: Bool? = nil
    private var supportedStreams = Set<PolarDeviceDataType>()
    private var hrDisposable: Disposable?
    #endif

    override init() {
        super.init()
        #if canImport(PolarBleSdk)
        setupObservers()
        #endif
    }

    private func log(_ s: String) { delegate?.polarLog("[Polar] " + s) }

    // MARK: - Connect / Disconnect
    func connect(deviceId: String) {
        #if canImport(PolarBleSdk)
        log("Connecting to \(deviceId)")
        do { try api.connectToDevice(deviceId) } catch { log("Connect error: \(error.localizedDescription)") }
        #else
        log("Polar SDK not present; cannot connect")
        #endif
    }

    func disconnect() {
        #if canImport(PolarBleSdk)
        guard let id = deviceId else { return }
        do { try api.disconnectFromDevice(id) } catch { log("Disconnect error: \(error.localizedDescription)") }
        #else
        log("Polar SDK not present; cannot disconnect")
        #endif
    }

    // MARK: - ECG control
    func startEcgStreaming(uploader: EcgUploader) {
        #if canImport(PolarBleSdk)
        guard let id = deviceId else { log("No Polar device id set; enter the short deviceId in settings"); return }
        pendingUploader = uploader
        guard ecgReady else {
            log("ECG start requested for \(id) but waiting for SDK ECG feature ready…")
            probeEcgFeature(deviceId: id)
            return
        }
        startPreparedEcgSession(deviceId: id, uploader: uploader)
        #else
        log("Polar SDK not present; ECG not available")
        #endif
    }

    @MainActor func stopEcgStreaming() {
        #if canImport(PolarBleSdk)
        ecgSession?.stop()
        ecgSession = nil
        log("ECG streaming stopped (device remains connected)")
        // GATT HR resume will be handled by the caller (e.g. BleManager) if needed.
        #else
        log("Polar SDK not present; ECG not available")
        #endif
    }

    #if canImport(PolarBleSdk)
    private func setupObservers() {
        api.observer = self
        api.powerStateObserver = self
        api.deviceFeaturesObserver = self
    }

    @MainActor
    private func waitForContact(timeout: TimeInterval = 5.0) async -> Bool {
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            if sdkContact == true { return true }
            try? await Task.sleep(nanoseconds: 200_000_000) // 0.2s
        }
        return sdkContact == true
    }

    private func probeEcgFeature(deviceId: String) {
        // Cancel any prior probe first
        ecgProbeTask?.cancel()
        ecgProbeTask = Task { [weak self] in
            guard let self else { return }

            // 1) Wait until the device advertises ECG capability (max 10s)
            var waitedForCapability: TimeInterval = 0
            if !supportedStreams.contains(.ecg) {
                log("[Polar] ECG probe: waiting for ECG capability…")
            }
            while !Task.isCancelled && !self.supportedStreams.contains(.ecg) {
                try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s
                waitedForCapability += 0.3
                if waitedForCapability > 10 {
                    self.log("[Polar] ECG probe: ECG capability not advertised after 10s; aborting probe")
                    return
                }
            }
            guard !Task.isCancelled else { return }

            // 2) If contact is supported and OFF, wait briefly for contact to become ON
            if let contact = self.sdkContact, contact == false {
                self.log("[Polar] ECG probe: contact OFF; waiting up to 5s for contact…")
                let ok = await self.waitForContact(timeout: 5.0)
                if !ok {
                    self.log("[Polar] ECG probe: contact did not become ON within timeout; aborting probe")
                    return
                }
            }
            guard !Task.isCancelled else { return }

            // 3) Bounded attempts with short backoff on error 9
            let maxAttempts = 3
            for attempt in 1...maxAttempts {
                if Task.isCancelled { return }
                do {
                    _ = try await requestEcgSettings(deviceId: deviceId)
                    await MainActor.run {
                        self.markEcgReady(deviceId: deviceId, source: "stream settings probe #\(attempt)")
                    }
                    return
                } catch {
                    let ns = error as NSError
                    if ns.domain.contains("PolarBleSdk"), ns.code == 9 {
                        self.log("[Polar] ECG feature probe attempt \(attempt) got error 9 (invalid state); retrying after 0.7s…")
                        try? await Task.sleep(nanoseconds: 700_000_000)
                        continue
                    } else {
                        self.log("[Polar] ECG feature probe failed: \(error.localizedDescription); aborting probe")
                        return
                    }
                }
            }
            self.log("[Polar] ECG feature probe: giving up after \(maxAttempts) attempts")
        }
    }

    private func markEcgReady(deviceId: String, source: String) {
        guard !ecgReady else { return }
        ecgReady = true
        ecgProbeTask?.cancel()
        ecgProbeTask = nil
        log("ECG feature ready via \(source) for \(deviceId)")
        if let uploader = pendingUploader {
            pendingUploader = nil
            startPreparedEcgSession(deviceId: deviceId, uploader: uploader)
        }
    }

    private func startPreparedEcgSession(deviceId id: String, uploader: EcgUploader) {
        // Capability & contact gating to avoid Polar error 9 before requesting settings
        if !supportedStreams.contains(.ecg) {
            log("ECG start: .ecg not yet advertised; attempting settings anyway since online streaming is ready")
        }
        if let contact = sdkContact, contact == false {
            log("ECG start: contact OFF; please ensure strap contact is ON, then try again")
            delegate?.polarEcgDidStop()
            return
        }

        // Preflight: ensure GATT HR is paused by BleManager before this is called.
        // Some Polar H10 FW require a brief settle before requesting ECG; wait a moment before starting.
        if ecgSession == nil {
            let s = PolarECGSession(deviceId: id, api: api, uploader: uploader)
            s.onLog = { [weak self] m in self?.log(m) }
            s.onState = { [weak self] running in
                guard let self = self else { return }
                if running { self.delegate?.polarEcgDidStart() } else { self.delegate?.polarEcgDidStop() }
            }
            ecgSession = s
        }

        log("ECG preflight: waiting 1.0s before starting stream for \(id)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.ecgSession?.start()
        }
    }
    #endif
}

#if canImport(PolarBleSdk)
extension PolarManager: PolarBleApiObserver, PolarBleApiPowerStateObserver, PolarBleApiDeviceFeaturesObserver {
    // MARK: - PolarBleApiObserver (SDK 6.5.0)
    func deviceConnecting(_ identifier: PolarDeviceInfo) {
        log("Connecting… \(identifier.deviceId)")
    }

    func deviceConnected(_ identifier: PolarDeviceInfo) {
        self.isConnected = true
        self.deviceId = identifier.deviceId
        self.deviceName = identifier.name
        log("Connected \(identifier.deviceId)")
        // Give the SDK a brief moment to settle before starting HR stream
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { [weak self] in
            self?.startHrStreaming(identifier.deviceId)
        }
        // Proactively query available online data types so we don't block on the feature callback
        api.getAvailableOnlineStreamDataTypes(identifier.deviceId)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onSuccess: { [weak self] available in
                    self?.supportedStreams = available
                    let names = available.map { "\($0)" }.sorted().joined(separator: ", ")
                    self?.log("Streams (queried) on \(identifier.deviceId): [\(names)]")
                },
                onFailure: { [weak self] err in
                    let ns = err as NSError
                    self?.log("getAvailableOnlineStreamDataTypes error (\(ns.domain)#\(ns.code)): \(ns.localizedDescription)")
                }
            )
            .disposed(by: disposeBag)
        // Allow ECG attempts after connect; session will validate settings
        self.ecgReady = false
        delegate?.polarDidConnect(deviceId: identifier.deviceId, name: identifier.name)
        probeEcgFeature(deviceId: identifier.deviceId)
    }

    func deviceDisconnected(_ identifier: PolarDeviceInfo, pairingError: Bool) {
        log("Disconnected \(identifier.deviceId) pairingError=\(pairingError)")
        self.isConnected = false
        if self.deviceId == identifier.deviceId { self.deviceId = nil }
        self.pendingUploader = nil
        self.ecgReady = false
        stopHrStreaming()
        ecgProbeTask?.cancel()
        ecgProbeTask = nil
        delegate?.polarDidDisconnect(deviceId: identifier.deviceId, error: nil)
    }

    // MARK: - PolarBleApiPowerStateObserver
    func blePowerOn()  { log("BLE power ON") }
    func blePowerOff() { log("BLE power OFF") }

    // MARK: - PolarBleApiDeviceFeaturesObserver
    func bleSdkFeatureReady(_ identifier: String, feature: PolarBleSdkFeature) {
        log("Feature ready on \(identifier): \(feature)")
        let fname = String(describing: feature).lowercased()
        if fname.contains("online") || fname.contains("stream") || fname.contains("ecg") {
            // Online streaming is ready — refresh available stream types now
            api.getAvailableOnlineStreamDataTypes(identifier)
                .observe(on: MainScheduler.instance)
                .subscribe(
                    onSuccess: { [weak self] available in
                        self?.supportedStreams = available
                        let names = available.map { "\($0)" }.sorted().joined(separator: ", ")
                        self?.log("Streams (queried after feature ready) on \(identifier): [\(names)]")
                    },
                    onFailure: { [weak self] err in
                        let ns = err as NSError
                        self?.log("getAvailableOnlineStreamDataTypes (after feature ready) error (\(ns.domain)#\(ns.code)): \(ns.localizedDescription)")
                    }
                )
                .disposed(by: disposeBag)
            // Also mark ECG ‘potentially’ ready based on feature readiness.
            markEcgReady(deviceId: identifier, source: "feature notification \(feature)")
        }
    }

    private func requestEcgSettings(deviceId: String) async throws -> PolarSensorSetting {
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

    // MARK: - HR streaming via Online Streaming API
    private func startHrStreaming(_ identifier: String) {
        // Stop any existing HR stream
        hrDisposable?.dispose()
        hrDisposable = api.startHrStreaming(identifier)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { [weak self] samples in
                    guard let self else { return }
                    // PolarHrData in this SDK build is a collection of samples (tuples or structs)
                    guard let sample = samples.first else { return }
                    // Access by label to be version-safe
                    let hrBpm = Int(sample.hr)
                    if sample.contactStatusSupported {
                        self.sdkContact = sample.contactStatus
                        let txt = (self.sdkContact == true) ? "on" : "off"
                        self.log("HR stream: \(hrBpm) bpm, contact: \(txt)")
                    } else {
                        self.sdkContact = nil
                        self.log("HR stream: \(hrBpm) bpm, contact: unsupported")
                    }
                },
                onError: { [weak self] err in
                    let ns = err as NSError
                    self?.log("HR stream error (\(ns.domain)#\(ns.code)): \(ns.localizedDescription)")
                }
            )
    }

    private func stopHrStreaming() {
        hrDisposable?.dispose()
        hrDisposable = nil
    }

    // MARK: - Streaming features (capability)
    func deviceStreamingFeaturesReady(_ identifier: String, available: Set<PolarDeviceDataType>) {
        supportedStreams = available
        let names = available.map { "\($0)" }.sorted().joined(separator: ", ")
        log("Streams available on \(identifier): [\(names)]")
    }
}
#endif
