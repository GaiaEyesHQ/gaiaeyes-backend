import SwiftUI
import AVFoundation
import QuartzCore
#if canImport(UIKit)
import UIKit
#endif

struct CameraHealthCheckView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: CameraHealthCheckViewModel
    @AppStorage("camera_health_debug_export_enabled") private var debugExportEnabled: Bool = false
    @State private var copiedDebugJSON = false

    init(onSaved: (() -> Void)? = nil) {
        _viewModel = StateObject(wrappedValue: CameraHealthCheckViewModel(onSaved: onSaved))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ZStack {
                        CameraPreviewView(session: viewModel.previewSession)
                            .frame(height: 290)
                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

                        VStack(spacing: 12) {
                            ProgressRing(progress: viewModel.progress, secondsRemaining: viewModel.secondsRemaining)
                            Text(viewModel.statusText)
                                .font(.footnote.weight(.semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(Color.black.opacity(0.42))
                                .clipShape(Capsule())
                        }
                        .foregroundStyle(.white)
                        .padding()
                    }

                    Text("Estimates for wellness context only. Not medical advice.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if let result = viewModel.result {
                        resultCard(result)
                    } else if let err = viewModel.errorMessage {
                        GroupBox {
                            Text(err)
                                .font(.footnote)
                                .foregroundColor(.secondary)
                        } label: {
                            Label("Quick Check", systemImage: "exclamationmark.triangle")
                        }
                    }

                    actionButtons

                    if debugExportEnabled, let result = viewModel.result {
                        Button {
                            copyDebugJSON(result)
                        } label: {
                            Label(copiedDebugJSON ? "Debug JSON Copied" : "Copy Debug JSON", systemImage: "doc.on.doc")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding()
            }
            .navigationTitle("Quick Health Check")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear {
                viewModel.start()
            }
            .onDisappear {
                viewModel.stop(discardResult: true)
            }
        }
    }

    private var actionButtons: some View {
        VStack(spacing: 10) {
            if viewModel.isRunning {
                Button {
                    viewModel.stop(discardResult: false)
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            } else {
                Button {
                    copiedDebugJSON = false
                    viewModel.start()
                } label: {
                    Label(viewModel.result == nil ? "Start Check" : "Run Again", systemImage: "camera.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }

            if let saveState = viewModel.saveStateMessage {
                Text(saveState)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func resultCard(_ result: CameraPPGComputedResult) -> some View {
        let quality = result.quality.label
        return GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    MetricValueBlock(
                        title: "BPM",
                        value: result.metrics.bpm.map { String(Int($0.rounded())) } ?? "--",
                        subtitle: "Heart Rate"
                    )
                    if let rmssd = result.metrics.rmssdMs {
                        Spacer(minLength: 12)
                        MetricValueBlock(
                            title: "RMSSD",
                            value: "\(Int(rmssd.rounded())) ms",
                            subtitle: "HRV"
                        )
                    }
                }

                qualityBadge(quality, score: result.quality.score)

                if result.metrics.rmssdMs == nil {
                    let guidance = "Try lighter pressure, cover the flash and one rear lens (usually the 1x lens), and warm your fingers if cold."
                    if result.metrics.bpm != nil {
                        Text("Heart rate captured, but HRV was not reliable enough. \(guidance)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("Signal quality was low for both heart rate and HRV. \(guidance)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else {
                    HStack(spacing: 10) {
                        if let sdnn = result.metrics.sdnnMs {
                            smallMetric("SDNN", "\(Int(sdnn.rounded())) ms")
                        }
                        if let pnn50 = result.metrics.pnn50 {
                            smallMetric("pNN50", String(format: "%.1f%%", pnn50))
                        }
                        if let avnn = result.metrics.avnnMs {
                            smallMetric("AVNN", "\(Int(avnn.rounded())) ms")
                        }
                        if let ln = result.metrics.lnRmssd {
                            smallMetric("lnRMSSD", String(format: "%.2f", ln))
                        }
                    }
                }

                if result.metrics.rmssdMs == nil && result.metrics.bpm == nil {
                    Text("Re-run tip: keep your finger still for the full 30-45 seconds.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Text("Duration \(result.durationSec)s")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        } label: {
            Label("Latest Result", systemImage: "heart.text.square")
        }
    }

    private func smallMetric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
            Text(value)
                .font(.caption.weight(.semibold))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color.secondary.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func qualityBadge(_ quality: PPGQualityLabel, score: Double) -> some View {
        let text: String
        let color: Color
        switch quality {
        case .good:
            text = "Good"
            color = .green
        case .ok:
            text = "OK"
            color = .yellow
        case .poor:
            text = "Poor"
            color = .orange
        case .unknown:
            text = "Unknown"
            color = .gray
        }
        return HStack(spacing: 8) {
            Label("Quality \(text)", systemImage: "waveform.path.ecg")
                .font(.subheadline.weight(.semibold))
            Spacer()
            Text(String(format: "%.0f%%", score * 100.0))
                .font(.caption.weight(.bold))
        }
        .padding(10)
        .background(color.opacity(0.16))
        .foregroundColor(color)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func copyDebugJSON(_ result: CameraPPGComputedResult) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(result),
              let text = String(data: data, encoding: .utf8) else {
            return
        }
        #if canImport(UIKit)
        UIPasteboard.general.string = text
        #endif
        copiedDebugJSON = true
    }
}

private struct MetricValueBlock: View {
    let title: String
    let value: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
            Text(value)
                .font(.title3.weight(.bold))
            Text(subtitle)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }
}

private struct ProgressRing: View {
    let progress: Double
    let secondsRemaining: Int

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.25), lineWidth: 9)
            Circle()
                .trim(from: 0, to: max(0.01, progress))
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: [.green, .yellow, .orange, .green]),
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: 9, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
            VStack(spacing: 2) {
                Text("\(max(0, secondsRemaining))s")
                    .font(.title3.weight(.bold))
                Text("remaining")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.85))
            }
        }
        .frame(width: 108, height: 108)
        .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 4)
    }
}

private struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession?

    func makeUIView(context: Context) -> PreviewContainerView {
        let view = PreviewContainerView()
        view.previewLayer.videoGravity = .resizeAspectFill
        view.backgroundColor = .black
        return view
    }

    func updateUIView(_ uiView: PreviewContainerView, context: Context) {
        uiView.previewLayer.session = session
    }
}

private final class PreviewContainerView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}

final class CameraHealthCheckViewModel: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    enum Phase {
        case idle
        case requestingPermission
        case warmingUp
        case measuring
        case processing
        case completed
        case failed
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var progress: Double = 0
    @Published private(set) var secondsRemaining: Int = 45
    @Published private(set) var previewSession: AVCaptureSession?
    @Published private(set) var result: CameraPPGComputedResult?
    @Published private(set) var errorMessage: String?
    @Published private(set) var isRunning: Bool = false
    @Published private(set) var saveStateMessage: String?

    var statusText: String {
        switch phase {
        case .idle:
            return "Ready"
        case .requestingPermission:
            return "Requesting camera access"
        case .warmingUp:
            return "Warming up: keep finger steady"
        case .measuring:
            return "Measuring: keep still and cover flash + one rear lens"
        case .processing:
            return "Processing signal"
        case .completed:
            return "Measurement complete"
        case .failed:
            return "Could not complete measurement"
        }
    }

    private let processor = CameraPPGProcessor()
    private let supabase = CameraHealthSupabaseClient.shared
    private let sampleQueue = DispatchQueue(label: "camera.health.ppg.sample", qos: .userInitiated)
    private let onSaved: (() -> Void)?

    private var captureSession: AVCaptureSession?
    private var captureDevice: AVCaptureDevice?
    private var output: AVCaptureVideoDataOutput?
    private var isStopping = false
    private var lastGreenMean: Double?

    init(onSaved: (() -> Void)? = nil) {
        self.onSaved = onSaved
        super.init()
    }

    func start() {
        if isRunning { return }
        publish {
            self.errorMessage = nil
            self.result = nil
            self.progress = 0
            self.secondsRemaining = Int(self.processor.maxRecordDurationSec)
            self.saveStateMessage = nil
            self.phase = .requestingPermission
        }
        requestPermissionIfNeeded { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.publish {
                    self.phase = .failed
                    self.errorMessage = "Camera permission is required for the quick check."
                    self.isRunning = false
                }
                return
            }
            self.startCaptureSession()
        }
    }

    func stop(discardResult: Bool) {
        sampleQueue.async { [weak self] in
            guard let self else { return }
            if discardResult {
                self.stopCaptureSession()
                self.publish {
                    self.isRunning = false
                }
                return
            }
            self.finishCapture()
        }
    }

    private func requestPermissionIfNeeded(_ completion: @escaping (Bool) -> Void) {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            completion(true)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                completion(granted)
            }
        default:
            completion(false)
        }
    }

    private func startCaptureSession() {
        sampleQueue.async { [weak self] in
            guard let self else { return }
            self.stopCaptureSession()

            let session = AVCaptureSession()
            session.beginConfiguration()
            if session.canSetSessionPreset(.vga640x480) {
                session.sessionPreset = .vga640x480
            }

            guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                  let input = try? AVCaptureDeviceInput(device: device),
                  session.canAddInput(input) else {
                session.commitConfiguration()
                self.publish {
                    self.phase = .failed
                    self.errorMessage = "Could not access back camera."
                }
                return
            }
            session.addInput(input)

            let output = AVCaptureVideoDataOutput()
            output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
            output.alwaysDiscardsLateVideoFrames = true
            output.setSampleBufferDelegate(self, queue: self.sampleQueue)
            guard session.canAddOutput(output) else {
                session.commitConfiguration()
                self.publish {
                    self.phase = .failed
                    self.errorMessage = "Could not configure camera output."
                }
                return
            }
            session.addOutput(output)

            do {
                try device.lockForConfiguration()
                if device.isTorchModeSupported(.on) {
                    try device.setTorchModeOn(level: 1.0)
                }
                if device.isFocusModeSupported(.continuousAutoFocus) {
                    device.focusMode = .continuousAutoFocus
                }
                if device.isExposureModeSupported(.continuousAutoExposure) {
                    device.exposureMode = .continuousAutoExposure
                }
                device.unlockForConfiguration()
            } catch {
                // Continue even if torch config partially fails.
            }

            session.commitConfiguration()
            self.captureSession = session
            self.captureDevice = device
            self.output = output
            self.isStopping = false
            self.lastGreenMean = nil

            let startTime = CACurrentMediaTime()
            self.processor.reset(startTime: startTime)
            session.startRunning()

            self.publish {
                self.previewSession = session
                self.phase = .warmingUp
                self.isRunning = true
                self.progress = 0
                self.secondsRemaining = Int(self.processor.maxRecordDurationSec.rounded())
            }
        }
    }

    private func finishCapture() {
        guard !isStopping else { return }
        isStopping = true
        publish {
            self.phase = .processing
            self.isRunning = false
        }

        let now = CACurrentMediaTime()
        let computed = processor.finalize(now: now)
        stopCaptureSession()

        guard let computed else {
            publish {
                self.phase = .failed
                self.errorMessage = "Need a steadier 30-45 second signal. Keep still and retry."
            }
            return
        }

        publish {
            self.result = computed
            self.phase = .completed
            self.errorMessage = nil
        }
        saveResult(computed)
    }

    private func saveResult(_ result: CameraPPGComputedResult) {
        publish {
            self.saveStateMessage = "Saving check..."
        }
        Task {
            do {
                await MainActor.run {
                    AuthManager.shared.loadFromKeychain()
                }
                try await supabase.saveCheck(result)
                await MainActor.run {
                    self.saveStateMessage = "Saved to your account."
                    self.onSaved?()
                }
            } catch {
                await MainActor.run {
                    if let authError = error as? CameraHealthSupabaseError {
                        switch authError {
                        case .notAuthenticated, .missingUserId:
                            self.saveStateMessage = "Not synced: Supabase sign-in missing. Open Settings > Subscribe and sign in."
                        default:
                            self.saveStateMessage = "Sync failed: \(authError.localizedDescription)"
                        }
                    } else {
                        self.saveStateMessage = "Sync failed: \(error.localizedDescription)"
                    }
                }
            }
        }
    }

    private func stopCaptureSession() {
        output?.setSampleBufferDelegate(nil, queue: nil)
        output = nil
        if let device = captureDevice {
            do {
                try device.lockForConfiguration()
                if device.isTorchActive {
                    device.torchMode = .off
                }
                device.unlockForConfiguration()
            } catch {
                // ignore
            }
        }
        captureDevice = nil
        if let session = captureSession, session.isRunning {
            session.stopRunning()
        }
        captureSession = nil
        publish {
            self.previewSession = nil
        }
    }

    private func publish(_ updates: @escaping () -> Void) {
        DispatchQueue.main.async {
            updates()
        }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        if isStopping { return }
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let stats = pixelStats(from: pixelBuffer)
        let greenMean = stats.greenMean
        let saturation = stats.saturationRatio

        let motion: Double
        if let last = lastGreenMean {
            let delta = abs(greenMean - last)
            motion = min(1.0, max(0.0, (delta - 3.0) / 80.0))
        } else {
            motion = 0.0
        }
        lastGreenMean = greenMean

        let now = CACurrentMediaTime()
        processor.ingestFrame(
            timestamp: now,
            greenMean: greenMean,
            saturationRatio: saturation,
            motionScore: motion
        )

        let warmup = processor.warmupRemaining(now: now)
        let elapsed = processor.recordElapsed(now: now)
        let remaining = Int(max(0, ceil(processor.maxRecordDurationSec - elapsed)))
        let progress = processor.progress(now: now)

        publish {
            self.phase = warmup > 0 ? .warmingUp : .measuring
            self.secondsRemaining = remaining
            self.progress = progress
        }

        if processor.shouldAutoStop(now: now) {
            finishCapture()
        }
    }

    private func pixelStats(from pixelBuffer: CVPixelBuffer) -> (greenMean: Double, saturationRatio: Double) {
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else {
            return (0, 0)
        }

        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
        let pointer = baseAddress.assumingMemoryBound(to: UInt8.self)

        let minX = width / 4
        let maxX = (width * 3) / 4
        let minY = height / 4
        let maxY = (height * 3) / 4
        let stride = 2

        var greenSum = 0.0
        var saturationHits = 0
        var count = 0

        var y = minY
        while y < maxY {
            let row = pointer + (y * bytesPerRow)
            var x = minX
            while x < maxX {
                let px = row + (x * 4)
                let g = px[1]
                let r = px[2]
                greenSum += Double(g)
                if r >= 254 && g >= 254 {
                    saturationHits += 1
                }
                count += 1
                x += stride
            }
            y += stride
        }

        guard count > 0 else { return (0, 0) }
        let mean = greenSum / Double(count)
        let saturationRatio = Double(saturationHits) / Double(count)
        return (mean, saturationRatio)
    }
}
