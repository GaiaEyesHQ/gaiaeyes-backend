import SwiftUI
import AVFoundation
import QuartzCore
#if canImport(UIKit)
import UIKit
#endif

enum CameraMeasurementMode: String, CaseIterable, Identifiable {
    case quickHR
    case hrv

    var id: String { rawValue }

    var title: String {
        switch self {
        case .quickHR: return "Quick HR"
        case .hrv: return "HRV Mode"
        }
    }

    var subtitle: String {
        switch self {
        case .quickHR:
            return "Faster capture focused on heart rate."
        case .hrv:
            return "Longer capture with stricter quality for HRV."
        }
    }

    var minRecordDurationSec: Double {
        switch self {
        case .quickHR: return 12
        case .hrv: return 45
        }
    }

    var maxRecordDurationSec: Double {
        switch self {
        case .quickHR: return 25
        case .hrv: return 60
        }
    }

    var allowsHRVOutput: Bool {
        switch self {
        case .quickHR: return false
        case .hrv: return true
        }
    }

    var minUploadQuality: Double {
        switch self {
        case .quickHR: return 0.60
        case .hrv: return 0.65
        }
    }
}

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
                    Picker("Mode", selection: $viewModel.selectedMode) {
                        ForEach(CameraMeasurementMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .disabled(viewModel.isRunning)

                    Text(viewModel.selectedMode.subtitle)
                        .font(.caption)
                        .foregroundColor(.secondary)

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

                    if let feedback = viewModel.liveFeedback, viewModel.isRunning {
                        liveSignalCard(feedback)
                    }

                    Text("Estimates for wellness context only. Not medical advice.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if let record = viewModel.result {
                        resultCard(record)
                    } else if let err = viewModel.errorMessage {
                        GroupBox {
                            VStack(alignment: .leading, spacing: 10) {
                                Text(err)
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                                if !viewModel.retryHints.isEmpty {
                                    retryChecklist(viewModel.retryHints)
                                }
                            }
                        } label: {
                            Label("Quick Check", systemImage: "exclamationmark.triangle")
                        }
                    }

                    actionButtons

                    if debugExportEnabled, let record = viewModel.result {
                        Button {
                            copyDebugJSON(record)
                        } label: {
                            Label(copiedDebugJSON ? "Debug JSON Copied" : "Open Debug JSON", systemImage: "doc.on.doc")
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
                    Label(viewModel.result == nil ? "Start \(viewModel.selectedMode.title)" : "Run Again", systemImage: "camera.fill")
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

    private func resultCard(_ record: CameraHealthCheckRecord) -> some View {
        let result = record.result
        let quality = result.quality.label
        return GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                saveStatusBanner

                if record.overallStatus != .poor {
                    HStack {
                        if record.hrStatus == .usable {
                            MetricValueBlock(
                                title: "BPM",
                                value: result.metrics.bpm.map { String(Int($0.rounded())) } ?? "--",
                                subtitle: "Heart Rate"
                            )
                        }
                        if record.hrvStatus == .usable, let rmssd = result.metrics.rmssdMs {
                            Spacer(minLength: 12)
                            MetricValueBlock(
                                title: "RMSSD",
                                value: "\(Int(rmssd.rounded())) ms",
                                subtitle: "HRV"
                            )
                        }
                    }
                }

                qualityBadge(quality, score: result.quality.score)

                if record.overallStatus == .good {
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
                } else if record.overallStatus == .partial {
                    Text(partialSummary(for: record))
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else if record.overallStatus == .poor {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("No reliable reading captured")
                            .font(.subheadline.weight(.semibold))
                        if let reason = record.debugMeta.failureReason {
                            Text(reason)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        if let nextStep = record.debugMeta.nextStepSuggestion {
                            Text(nextStep)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                if record.overallStatus != .good, !record.debugMeta.guidanceHints.isEmpty {
                    retryChecklist(record.debugMeta.guidanceHints)
                }

                Text("Duration \(result.durationSec)s")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        } label: {
            Label("Latest Result", systemImage: "heart.text.square")
        }
    }

    private func partialSummary(for record: CameraHealthCheckRecord) -> String {
        if record.hrStatus == .usable, record.hrvStatus == .notRequested {
            return "Heart rate was captured. Switch to HRV Mode when you want an HRV estimate."
        }
        if record.hrStatus == .usable {
            return "Heart rate was usable, but HRV quality was too low for a reliable estimate."
        }
        if record.hrvStatus == .usable {
            return "HRV was captured, but heart rate was too unstable to show confidently."
        }
        return "Only part of the signal was usable."
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

    private var saveStatusBanner: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: saveStatusIcon)
                .font(.subheadline.weight(.semibold))
            VStack(alignment: .leading, spacing: 3) {
                Text(viewModel.saveStatusTitle ?? "Saving check...")
                    .font(.subheadline.weight(.semibold))
                if let detail = viewModel.saveStatusDetail {
                    Text(detail)
                        .font(.caption)
                }
            }
            Spacer()
        }
        .padding(10)
        .background(saveStatusColor.opacity(0.14))
        .foregroundColor(saveStatusColor)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var saveStatusColor: Color {
        if viewModel.isSavingResult {
            return .blue
        }
        switch viewModel.saveScope {
        case .account:
            return .green
        case .localOnly:
            return .yellow
        case .notSaved:
            return .orange
        }
    }

    private var saveStatusIcon: String {
        if viewModel.isSavingResult {
            return "arrow.triangle.2.circlepath"
        }
        switch viewModel.saveScope {
        case .account:
            return "checkmark.circle.fill"
        case .localOnly:
            return "internaldrive.fill"
        case .notSaved:
            return "exclamationmark.triangle.fill"
        }
    }

    private func liveSignalCard(_ feedback: CameraPPGLiveFeedback) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Live Quality", systemImage: "waveform.path.ecg")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(feedback.state.rawValue.capitalized)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(liveQualityColor(feedback.state).opacity(0.16))
                    .foregroundColor(liveQualityColor(feedback.state))
                    .clipShape(Capsule())
            }

            ProgressView(value: feedback.score)
                .tint(liveQualityColor(feedback.state))

            VStack(alignment: .leading, spacing: 6) {
                ForEach(feedback.guidance, id: \.self) { hint in
                    Text(hint)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func liveQualityColor(_ state: CameraLiveQualityState) -> Color {
        switch state {
        case .weak:
            return .orange
        case .improving:
            return .yellow
        case .good:
            return .green
        case .excellent:
            return .mint
        }
    }

    private func retryChecklist(_ hints: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Retry checklist")
                .font(.caption.weight(.semibold))
            ForEach(hints, id: \.self) { hint in
                Text("- \(hint)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func copyDebugJSON(_ record: CameraHealthCheckRecord) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(record),
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
    @Published private(set) var secondsRemaining: Int = Int(CameraMeasurementMode.quickHR.maxRecordDurationSec)
    @Published private(set) var previewSession: AVCaptureSession?
    @Published private(set) var result: CameraHealthCheckRecord?
    @Published private(set) var errorMessage: String?
    @Published private(set) var isRunning: Bool = false
    @Published private(set) var liveFeedback: CameraPPGLiveFeedback?
    @Published private(set) var retryHints: [String] = []
    @Published private(set) var saveScope: CameraSaveScope = .notSaved
    @Published private(set) var isSavingResult: Bool = false
    @Published private(set) var saveStatusTitle: String?
    @Published private(set) var saveStatusDetail: String?
    @Published private(set) var saveStateMessage: String?
    @Published var selectedMode: CameraMeasurementMode = .quickHR {
        didSet {
            guard !isRunning else { return }
            secondsRemaining = Int(selectedMode.maxRecordDurationSec.rounded())
        }
    }
    @Published private(set) var lastRunMode: CameraMeasurementMode = .quickHR

    var statusText: String {
        let activeMode = isRunning ? lastRunMode : selectedMode
        switch phase {
        case .idle:
            return "Ready"
        case .requestingPermission:
            return "Requesting camera access"
        case .warmingUp:
            return "Warming up: keep finger steady"
        case .measuring:
            switch activeMode {
            case .quickHR:
                return "Measuring HR: keep still and cover flash + one rear lens"
            case .hrv:
                return "Measuring HRV: keep still and breathe naturally"
            }
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
    private var lastLiveFeedbackAt: TimeInterval = 0
    private var observedGuidanceHints: [String] = []

    init(onSaved: (() -> Void)? = nil) {
        self.onSaved = onSaved
        super.init()
    }

    func start() {
        if isRunning { return }
        let mode = selectedMode
        publish {
            self.errorMessage = nil
            self.result = nil
            self.progress = 0
            self.secondsRemaining = Int(mode.maxRecordDurationSec.rounded())
            self.liveFeedback = nil
            self.retryHints = []
            self.saveScope = .notSaved
            self.isSavingResult = false
            self.saveStatusTitle = nil
            self.saveStatusDetail = nil
            self.saveStateMessage = nil
            self.phase = .requestingPermission
            self.lastRunMode = mode
        }
        observedGuidanceHints = []
        lastLiveFeedbackAt = 0
        requestPermissionIfNeeded { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.publish {
                    self.phase = .failed
                    self.errorMessage = "Camera permission is required for the quick check."
                    self.isRunning = false
                    self.saveScope = .notSaved
                    self.saveStatusTitle = "Not saved"
                    self.saveStatusDetail = "Camera access is required to run the check."
                }
                return
            }
            self.startCaptureSession(mode: mode)
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

    private func startCaptureSession(mode: CameraMeasurementMode) {
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
                _ = self.configurePreferredFrameRate(device: device, preferredFPS: 60.0)
                if device.isTorchModeSupported(.on) {
                    try device.setTorchModeOn(level: 1.0)
                }
                if device.isFocusModeSupported(.locked) {
                    device.focusMode = .locked
                } else if device.isFocusModeSupported(.continuousAutoFocus) {
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
            self.processor.reset(
                startTime: startTime,
                warmupDurationSec: 3.0,
                minRecordDurationSec: mode.minRecordDurationSec,
                maxRecordDurationSec: mode.maxRecordDurationSec
            )
            session.startRunning()

            self.publish {
                self.previewSession = session
                self.phase = .warmingUp
                self.isRunning = true
                self.progress = 0
                self.secondsRemaining = Int(mode.maxRecordDurationSec.rounded())
            }
        }
    }

    private func finishCapture() {
        guard !isStopping else { return }
        let mode = lastRunMode
        isStopping = true
        publish {
            self.phase = .processing
            self.isRunning = false
            self.liveFeedback = nil
        }

        let now = CACurrentMediaTime()
        let computed = processor.finalize(now: now, allowHRVOutput: mode.allowsHRVOutput)
        stopCaptureSession()

        guard let computed else {
            let guidanceHints = fallbackGuidanceHints(for: mode)
            publish {
                self.phase = .failed
                self.retryHints = guidanceHints
                self.errorMessage = "No reliable reading captured. \(self.failureReason(for: guidanceHints, result: nil))"
                self.saveScope = .notSaved
                self.isSavingResult = false
                self.saveStatusTitle = "Not saved"
                self.saveStatusDetail = "No reliable reading was captured."
                self.saveStateMessage = "Not saved."
            }
            return
        }

        let record = buildRecord(from: computed, mode: mode)
        publish {
            self.result = record
            self.phase = .completed
            self.errorMessage = nil
            self.retryHints = record.debugMeta.guidanceHints
            self.saveScope = .notSaved
            self.isSavingResult = true
            self.saveStatusTitle = "Saving check..."
            self.saveStatusDetail = "Creating a local copy and preparing sync."
            self.saveStateMessage = "Saving check..."
        }
        saveResult(record)
    }

    private func saveResult(_ record: CameraHealthCheckRecord) {
        Task {
            var localRecord = record
            localRecord.saveScope = .localOnly
            await CameraHealthLocalStore.shared.save(record: localRecord, saveScope: .localOnly)
            await MainActor.run {
                self.result = localRecord
                self.onSaved?()
            }

            do {
                await MainActor.run {
                    AuthManager.shared.loadFromKeychain()
                }
                try await supabase.saveCheck(localRecord)
                var accountRecord = localRecord
                accountRecord.saveScope = .account
                await CameraHealthLocalStore.shared.save(record: accountRecord, saveScope: .account)
                await MainActor.run {
                    self.result = accountRecord
                    self.saveScope = .account
                    self.isSavingResult = false
                    self.saveStatusTitle = "Saved to your account"
                    self.saveStatusDetail = "This check is available on your account and this device."
                    self.saveStateMessage = "Saved to your account."
                    self.onSaved?()
                }
            } catch {
                await MainActor.run {
                    self.result = localRecord
                    self.saveScope = .localOnly
                    self.isSavingResult = false
                    if let authError = error as? CameraHealthSupabaseError {
                        switch authError {
                        case .notAuthenticated, .missingUserId:
                            self.saveStatusTitle = "Saved locally only"
                            self.saveStatusDetail = "Sign in to sync future checks to your account."
                            self.saveStateMessage = "Saved locally only."
                        case .server(_, let body)
                            where body.localizedCaseInsensitiveContains("permission denied for schema raw")
                            || body.localizedCaseInsensitiveContains("permission denied for schema marts")
                            || body.contains("\"code\":\"42501\""):
                            self.saveStatusTitle = "Saved locally only"
                            self.saveStatusDetail = "Sync is blocked by current camera-health permissions."
                            self.saveStateMessage = "Saved locally only."
                        default:
                            self.saveStatusTitle = "Saved locally only"
                            self.saveStatusDetail = "Sync failed this time, but the result is still on this device."
                            self.saveStateMessage = "Saved locally only."
                        }
                    } else {
                        self.saveStatusTitle = "Saved locally only"
                        self.saveStatusDetail = "Sync failed this time, but the result is still on this device."
                        self.saveStateMessage = "Saved locally only."
                    }
                }
            }
        }
    }

    private func buildRecord(from result: CameraPPGComputedResult, mode: CameraMeasurementMode) -> CameraHealthCheckRecord {
        let guidanceHints = fallbackGuidanceHints(for: mode, result: result)

        let hrStatus: CameraMetricStatus
        var hrReasons: [String] = []
        if result.metrics.bpm != nil {
            hrStatus = .usable
        } else if result.quality.label == .poor || result.quality.score < 0.50 || result.artifacts.validIbiCount < 6 {
            hrStatus = .withheldLowQuality
            hrReasons.append("low_signal_quality")
        } else {
            hrStatus = .notCaptured
            hrReasons.append("unstable_pulse")
        }

        let hrvStatus: CameraMetricStatus
        var hrvReasons: [String] = []
        if !mode.allowsHRVOutput {
            hrvStatus = .notRequested
            hrvReasons.append("mode_hr_only")
        } else if result.metrics.rmssdMs != nil {
            hrvStatus = .usable
        } else if result.quality.label == .poor || result.quality.score < 0.58 || result.artifacts.validIbiCount < 18 || (result.fps ?? 0) < 24 {
            hrvStatus = .withheldLowQuality
            if result.quality.score < 0.58 || result.quality.label == .poor {
                hrvReasons.append("low_signal_quality")
            }
            if result.artifacts.validIbiCount < 18 {
                hrvReasons.append("too_few_clean_beats")
            }
            if (result.fps ?? 0) < 24 {
                hrvReasons.append("low_frame_rate")
            }
        } else {
            hrvStatus = .notCaptured
            hrvReasons.append("insufficient_hrv_confidence")
        }

        let overallStatus: CameraCheckSummaryStatus
        switch (hrStatus, hrvStatus) {
        case (.usable, .usable):
            overallStatus = .good
        case (.usable, _), (_, .usable):
            overallStatus = .partial
        default:
            overallStatus = .poor
        }

        let failureReasonText = overallStatus == .good ? nil : failureReason(for: guidanceHints, result: result)
        let nextStepSuggestion = guidanceHints.first ?? defaultNextStep(for: mode)

        return CameraHealthCheckRecord(
            capturedAt: Date(),
            measurementMode: mode.rawValue,
            hrStatus: hrStatus,
            hrvStatus: hrvStatus,
            overallStatus: overallStatus,
            saveScope: .notSaved,
            result: result,
            debugMeta: CameraHealthDebugMeta(
                hrReasons: hrReasons,
                hrvReasons: hrvReasons,
                guidanceHints: guidanceHints,
                failureReason: failureReasonText,
                nextStepSuggestion: nextStepSuggestion,
                quality: CameraHealthQualityBreakdown(
                    validIBIRatio: result.quality.validIBIRatio,
                    snrProxy: result.quality.snrProxy,
                    stabilityScore: result.quality.stabilityScore,
                    saturationPenalty: result.quality.saturationPenalty,
                    motionPenalty: result.quality.motionPenalty,
                    droppedFramePenalty: result.quality.droppedFramePenalty
                )
            )
        )
    }

    private func fallbackGuidanceHints(for mode: CameraMeasurementMode, result: CameraPPGComputedResult? = nil) -> [String] {
        var hints = observedGuidanceHints
        if let result {
            if result.artifacts.motionScore > 0.20 {
                hints.append("Keep still")
            }
            if result.artifacts.saturationHitRatio > 0.88 {
                hints.append("Use lighter pressure")
            }
            if result.quality.snrProxy < 0.10 && result.artifacts.validIbiCount < 8 {
                hints.append("Cover flash and one rear lens fully")
            }
            if result.quality.snrProxy < 0.14 && result.artifacts.validIbiCount < 8 {
                hints.append("Warm fingers help")
            }
        }
        if hints.isEmpty {
            hints.append("Cover flash and one rear lens fully")
            hints.append(mode.allowsHRVOutput ? "Keep still" : "Use lighter pressure")
        }
        return Array(hints.uniqued().prefix(3))
    }

    private func failureReason(for guidanceHints: [String], result: CameraPPGComputedResult?) -> String {
        if guidanceHints.contains("Keep still") {
            return "Movement disrupted the signal."
        }
        if guidanceHints.contains("Use lighter pressure") {
            return "Pressure looked too heavy on the lens."
        }
        if guidanceHints.contains("Cover flash and one rear lens fully") {
            return "Finger placement did not fully cover the flash and lens."
        }
        if guidanceHints.contains("Warm fingers help") {
            return "The pulse signal stayed weak."
        }
        if let result, result.artifacts.validIbiCount < 6 {
            return "Too few clean pulse beats were captured."
        }
        return "The signal was not reliable enough."
    }

    private func defaultNextStep(for mode: CameraMeasurementMode) -> String {
        if mode.allowsHRVOutput {
            return "Keep still for the full capture and breathe naturally."
        }
        return "Keep still and cover the flash and one rear lens fully."
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

        if warmup <= 0, now - lastLiveFeedbackAt >= 1.0 {
            lastLiveFeedbackAt = now
            let feedback = processor.liveFeedback(now: now, allowHRVOutput: lastRunMode.allowsHRVOutput)
            if let feedback {
                observedGuidanceHints.append(contentsOf: feedback.guidance)
                observedGuidanceHints = Array(observedGuidanceHints.uniqued().prefix(4))
            }
            publish {
                self.liveFeedback = feedback
            }
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

    private func configurePreferredFrameRate(device: AVCaptureDevice, preferredFPS: Double) -> Double? {
        if let fast = bestFormat(device: device, preferredFPS: preferredFPS) {
            device.activeFormat = fast.format
            device.activeVideoMinFrameDuration = fast.frameDuration
            device.activeVideoMaxFrameDuration = fast.frameDuration
            return fast.fps
        }
        if let fallback = bestFormat(device: device, preferredFPS: 30.0) {
            device.activeFormat = fallback.format
            device.activeVideoMinFrameDuration = fallback.frameDuration
            device.activeVideoMaxFrameDuration = fallback.frameDuration
            return fallback.fps
        }
        return nil
    }

    private func bestFormat(device: AVCaptureDevice, preferredFPS: Double) -> (format: AVCaptureDevice.Format, frameDuration: CMTime, fps: Double)? {
        var best: (format: AVCaptureDevice.Format, frameDuration: CMTime, fps: Double, pixels: Int64)?

        for format in device.formats {
            let dims = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
            guard dims.width >= 640, dims.height >= 480 else { continue }
            let pixels = Int64(dims.width) * Int64(dims.height)

            for range in format.videoSupportedFrameRateRanges {
                guard range.maxFrameRate + 0.01 >= preferredFPS else { continue }
                let fps = min(preferredFPS, range.maxFrameRate)
                guard fps + 0.01 >= range.minFrameRate else { continue }

                let timescale = Int32(max(1, Int(fps.rounded())))
                let duration = CMTime(value: 1, timescale: timescale)

                if let current = best {
                    let hasHigherFPS = fps > current.fps + 0.1
                    let sameFPS = abs(fps - current.fps) <= 0.1
                    let hasMorePixels = pixels > current.pixels
                    if hasHigherFPS || (sameFPS && hasMorePixels) {
                        best = (format, duration, fps, pixels)
                    }
                } else {
                    best = (format, duration, fps, pixels)
                }
            }
        }

        guard let selected = best else { return nil }
        return (selected.format, selected.frameDuration, selected.fps)
    }
}

private extension Array where Element: Hashable {
    func uniqued() -> [Element] {
        var seen: Set<Element> = []
        return filter { seen.insert($0).inserted }
    }
}
