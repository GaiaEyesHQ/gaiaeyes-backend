import Foundation

struct CameraPPGMetrics: Codable {
    let bpm: Double?
    let avnnMs: Double?
    let sdnnMs: Double?
    let rmssdMs: Double?
    let pnn50: Double?
    let lnRmssd: Double?
    let stressIndex: Double?
    let respRateBpm: Double?
}

struct CameraPPGArtifacts: Codable {
    let droppedFrames: Int
    let droppedFrameRatio: Double
    let saturationHitRatio: Double
    let motionScore: Double
    let validIbiCount: Int
    let totalIbiCount: Int
}

struct CameraPPGComputedResult: Codable {
    let durationSec: Int
    let fps: Int?
    let quality: PPGQualityAssessment
    let metrics: CameraPPGMetrics
    let artifacts: CameraPPGArtifacts
    let ibiMs: [Double]
    let ibiTimestampsMs: [Double]
    let ppgDownsampled: [Double]
    let ppgDownsampledHz: Double?
}

final class CameraPPGProcessor {
    let warmupDurationSec: Double = 3.0
    let minRecordDurationSec: Double = 30.0
    let maxRecordDurationSec: Double = 45.0

    private let targetHz: Double = 30.0
    private let maxDownsampledPoints = 1500

    private var captureStartTime: TimeInterval?
    private var frameTimes: [Double] = []
    private var frameSignal: [Double] = []
    private var saturationRatios: [Double] = []
    private var motionSamples: [Double] = []
    private var droppedFrames: Int = 0
    private var totalFrames: Int = 0
    private var lastFrameTimestamp: TimeInterval?
    private var lastAutoStopEvalAt: TimeInterval = 0
    private var lastAutoStopDecision: Bool = false

    func reset(startTime: TimeInterval) {
        captureStartTime = startTime
        frameTimes.removeAll(keepingCapacity: true)
        frameSignal.removeAll(keepingCapacity: true)
        saturationRatios.removeAll(keepingCapacity: true)
        motionSamples.removeAll(keepingCapacity: true)
        droppedFrames = 0
        totalFrames = 0
        lastFrameTimestamp = nil
        lastAutoStopEvalAt = 0
        lastAutoStopDecision = false
    }

    func ingestFrame(timestamp: TimeInterval, greenMean: Double, saturationRatio: Double, motionScore: Double) {
        guard let start = captureStartTime else { return }
        totalFrames += 1

        if let lastTs = lastFrameTimestamp {
            let delta = timestamp - lastTs
            if delta > 0 {
                let expected = 1.0 / targetHz
                if delta > (expected * 1.8) {
                    let estimatedDrops = Int((delta / expected).rounded()) - 1
                    droppedFrames += max(0, estimatedDrops)
                }
            }
        }
        lastFrameTimestamp = timestamp

        let elapsed = timestamp - start
        guard elapsed >= warmupDurationSec else { return }
        let t = elapsed - warmupDurationSec
        frameTimes.append(t)
        frameSignal.append(greenMean)
        saturationRatios.append(clamp(saturationRatio, min: 0, max: 1))
        motionSamples.append(clamp(motionScore, min: 0, max: 1))
    }

    func warmupRemaining(now: TimeInterval) -> Double {
        guard let start = captureStartTime else { return warmupDurationSec }
        return max(0.0, warmupDurationSec - (now - start))
    }

    func recordElapsed(now: TimeInterval) -> Double {
        guard let start = captureStartTime else { return 0.0 }
        return max(0.0, (now - start) - warmupDurationSec)
    }

    func progress(now: TimeInterval) -> Double {
        let elapsed = recordElapsed(now: now)
        guard maxRecordDurationSec > 0 else { return 0 }
        return clamp(elapsed / maxRecordDurationSec, min: 0.0, max: 1.0)
    }

    func shouldAutoStop(now: TimeInterval) -> Bool {
        let elapsed = recordElapsed(now: now)
        if elapsed >= maxRecordDurationSec {
            return true
        }
        guard elapsed >= minRecordDurationSec else {
            return false
        }
        if now - lastAutoStopEvalAt < 1.0 {
            return lastAutoStopDecision
        }
        lastAutoStopEvalAt = now
        guard let preview = computeResult(now: now, requireQualityForHRV: false) else {
            lastAutoStopDecision = false
            return false
        }
        lastAutoStopDecision = preview.quality.label == .good && preview.artifacts.validIbiCount >= 25
        return lastAutoStopDecision
    }

    func finalize(now: TimeInterval) -> CameraPPGComputedResult? {
        return computeResult(now: now, requireQualityForHRV: true)
    }

    private func computeResult(now: TimeInterval, requireQualityForHRV: Bool) -> CameraPPGComputedResult? {
        let elapsed = recordElapsed(now: now)
        guard elapsed >= 8.0 else { return nil }
        guard frameTimes.count >= 120 else { return nil }

        let window = buildResampledWindow(maxDuration: min(elapsed, maxRecordDurationSec))
        guard window.times.count >= 120 else { return nil }
        let hz = estimatedHz(times: window.times)

        let dcRemoved = removeDC(signal: window.values, sampleRate: hz)
        let bandpassed = bandpass(signal: dcRemoved, sampleRate: hz)
        let residual = zip(dcRemoved, bandpassed).map { $0 - $1 }

        let peakIndices = detectPeaks(signal: bandpassed, sampleRate: hz)
        let rawIbi = computeIBI(from: peakIndices, sampleRate: hz)
        let cleaned = rejectArtifacts(ibiMs: rawIbi.ms, ibiTsMs: rawIbi.tsMs)

        let saturationHitRatio = average(saturationRatios)
        let motionScore = average(motionSamples)
        let droppedFrameRatio = totalFrames > 0 ? Double(droppedFrames) / Double(totalFrames) : 0.0
        let quality = PPGSignalQuality.assess(
            validIBICount: cleaned.ms.count,
            totalIBICount: rawIbi.ms.count,
            filteredSignal: bandpassed,
            residualSignal: residual,
            ibiMs: cleaned.ms,
            saturationHitRatio: saturationHitRatio,
            motionScore: motionScore,
            droppedFrameRatio: droppedFrameRatio
        )

        let avnn = mean(cleaned.ms)
        let bpmStable = bpm(fromAvnn: avnn, ibIs: cleaned.ms)
        let canComputeHRV = cleaned.ms.count >= 20 && quality.score >= 0.65 && quality.label != .poor

        let hrvMetrics: (sdnn: Double?, rmssd: Double?, pnn50: Double?, lnRmssd: Double?, stress: Double?, resp: Double?)
        if canComputeHRV || !requireQualityForHRV {
            let sdnn = sdnnMs(cleaned.ms)
            let rmssd = rmssdMs(cleaned.ms)
            let pnn50 = pnn50(cleaned.ms)
            let ln = rmssd.flatMap { $0 > 0 ? log($0) : nil }
            let stress = baevskyStressIndex(ibiMs: cleaned.ms)
            let respiration = estimateRespirationRate(ibiMs: cleaned.ms, ibiTsMs: cleaned.tsMs, qualityScore: quality.score)
            hrvMetrics = (
                sdnn,
                rmssd,
                pnn50,
                ln,
                stress,
                respiration
            )
        } else {
            hrvMetrics = (nil, nil, nil, nil, nil, nil)
        }

        let outputMetrics = CameraPPGMetrics(
            bpm: bpmStable,
            avnnMs: canComputeHRV ? avnn : nil,
            sdnnMs: canComputeHRV ? hrvMetrics.sdnn : nil,
            rmssdMs: canComputeHRV ? hrvMetrics.rmssd : nil,
            pnn50: canComputeHRV ? hrvMetrics.pnn50 : nil,
            lnRmssd: canComputeHRV ? hrvMetrics.lnRmssd : nil,
            stressIndex: canComputeHRV ? hrvMetrics.stress : nil,
            respRateBpm: canComputeHRV ? hrvMetrics.resp : nil
        )

        let artifacts = CameraPPGArtifacts(
            droppedFrames: droppedFrames,
            droppedFrameRatio: round3(droppedFrameRatio),
            saturationHitRatio: round3(saturationHitRatio),
            motionScore: round3(motionScore),
            validIbiCount: cleaned.ms.count,
            totalIbiCount: rawIbi.ms.count
        )

        return CameraPPGComputedResult(
            durationSec: Int(elapsed.rounded()),
            fps: fpsEstimate(recordDuration: elapsed),
            quality: quality,
            metrics: outputMetrics,
            artifacts: artifacts,
            ibiMs: cleaned.ms.map(round2),
            ibiTimestampsMs: cleaned.tsMs.map(round1),
            ppgDownsampled: Array(bandpassed.prefix(maxDownsampledPoints)).map(round5),
            ppgDownsampledHz: round2(hz)
        )
    }

    private func buildResampledWindow(maxDuration: Double) -> (times: [Double], values: [Double]) {
        guard !frameTimes.isEmpty else { return ([], []) }
        let endT = min(maxDuration, frameTimes.last ?? 0.0)
        let startT = max(0.0, endT - maxRecordDurationSec)

        var clippedTimes: [Double] = []
        var clippedValues: [Double] = []
        clippedTimes.reserveCapacity(frameTimes.count)
        clippedValues.reserveCapacity(frameSignal.count)

        for index in frameTimes.indices {
            let t = frameTimes[index]
            guard t >= startT, t <= endT else { continue }
            clippedTimes.append(t - startT)
            clippedValues.append(frameSignal[index])
        }
        guard clippedTimes.count >= 4 else { return ([], []) }

        let hz = estimatedHz(times: clippedTimes)
        if hz <= targetHz + 2.0 {
            return (clippedTimes, clippedValues)
        }
        return resample(times: clippedTimes, values: clippedValues, targetHz: targetHz)
    }

    private func resample(times: [Double], values: [Double], targetHz: Double) -> (times: [Double], values: [Double]) {
        guard times.count == values.count, times.count > 2, targetHz > 0 else { return (times, values) }
        let dt = 1.0 / targetHz
        let end = times.last ?? 0.0
        var outputT: [Double] = []
        var outputV: [Double] = []
        outputT.reserveCapacity(min(maxDownsampledPoints, Int((end / dt).rounded()) + 1))
        outputV.reserveCapacity(outputT.capacity)

        var sourceIndex = 0
        var t = 0.0
        while t <= end && outputT.count < maxDownsampledPoints {
            while sourceIndex + 1 < times.count && times[sourceIndex + 1] < t {
                sourceIndex += 1
            }
            if sourceIndex + 1 >= times.count {
                break
            }
            let t0 = times[sourceIndex]
            let t1 = times[sourceIndex + 1]
            let v0 = values[sourceIndex]
            let v1 = values[sourceIndex + 1]
            let frac: Double
            if t1 <= t0 {
                frac = 0.0
            } else {
                frac = clamp((t - t0) / (t1 - t0), min: 0.0, max: 1.0)
            }
            outputT.append(t)
            outputV.append(v0 + ((v1 - v0) * frac))
            t += dt
        }
        return (outputT, outputV)
    }

    private func removeDC(signal: [Double], sampleRate: Double) -> [Double] {
        guard !signal.isEmpty else { return [] }
        let window = max(3, Int(sampleRate.rounded()))
        var out: [Double] = Array(repeating: 0.0, count: signal.count)
        var running = 0.0
        for i in signal.indices {
            running += signal[i]
            if i >= window {
                running -= signal[i - window]
            }
            let count = i + 1 < window ? i + 1 : window
            let mean = running / Double(count)
            out[i] = signal[i] - mean
        }
        return out
    }

    private func bandpass(signal: [Double], sampleRate: Double) -> [Double] {
        guard signal.count > 4 else { return signal }
        var hp = Biquad.highPass(sampleRate: sampleRate, cutoffHz: 0.7, q: 0.707)
        var lp = Biquad.lowPass(sampleRate: sampleRate, cutoffHz: 3.5, q: 0.707)
        return signal.map { lp.process(hp.process($0)) }
    }

    private func detectPeaks(signal: [Double], sampleRate: Double) -> [Int] {
        guard signal.count > 6 else { return [] }
        let globalStd = max(standardDeviation(signal), 1e-6)
        let window = max(5, Int((sampleRate * 1.2).rounded()))
        let minDistance = max(5, Int((sampleRate * 0.33).rounded()))
        var peaks: [Int] = []
        var lastPeak = -minDistance

        for i in 1..<(signal.count - 1) {
            let current = signal[i]
            if current <= signal[i - 1] || current < signal[i + 1] {
                continue
            }
            if (i - lastPeak) < minDistance {
                continue
            }
            let left = max(0, i - window)
            let right = min(signal.count - 1, i + window)
            let local = Array(signal[left...right])
            let localMean = mean(local) ?? 0.0
            let localStd = standardDeviation(local)
            let threshold = localMean + max(globalStd * 0.10, localStd * 0.25)
            if current >= threshold {
                peaks.append(i)
                lastPeak = i
            }
        }
        return peaks
    }

    private func computeIBI(from peakIndices: [Int], sampleRate: Double) -> (ms: [Double], tsMs: [Double]) {
        guard peakIndices.count >= 2, sampleRate > 0 else { return ([], []) }
        var ibiMs: [Double] = []
        var ibiTs: [Double] = []
        ibiMs.reserveCapacity(peakIndices.count - 1)
        ibiTs.reserveCapacity(peakIndices.count - 1)

        for i in 1..<peakIndices.count {
            let prev = peakIndices[i - 1]
            let curr = peakIndices[i]
            let intervalMs = (Double(curr - prev) / sampleRate) * 1000.0
            ibiMs.append(intervalMs)
            ibiTs.append((Double(curr) / sampleRate) * 1000.0)
        }
        return (ibiMs, ibiTs)
    }

    private func rejectArtifacts(ibiMs: [Double], ibiTsMs: [Double]) -> (ms: [Double], tsMs: [Double]) {
        guard ibiMs.count == ibiTsMs.count else { return ([], []) }
        if ibiMs.isEmpty { return ([], []) }

        var boundedMs: [Double] = []
        var boundedTs: [Double] = []
        boundedMs.reserveCapacity(ibiMs.count)
        boundedTs.reserveCapacity(ibiTsMs.count)

        for i in ibiMs.indices {
            let value = ibiMs[i]
            guard value >= 300, value <= 2000 else { continue }
            boundedMs.append(value)
            boundedTs.append(ibiTsMs[i])
        }
        guard boundedMs.count >= 4 else { return (boundedMs, boundedTs) }

        let med = median(boundedMs)
        let deviations = boundedMs.map { abs($0 - med) }
        let mad = median(deviations)
        let robustStd = max(1.4826 * mad, 1.0)
        let tolerance = max(250.0, robustStd * 3.0)

        var cleanedMs: [Double] = []
        var cleanedTs: [Double] = []
        cleanedMs.reserveCapacity(boundedMs.count)
        cleanedTs.reserveCapacity(boundedTs.count)

        for i in boundedMs.indices {
            let value = boundedMs[i]
            if abs(value - med) <= tolerance {
                cleanedMs.append(value)
                cleanedTs.append(boundedTs[i])
            }
        }
        return (cleanedMs, cleanedTs)
    }

    private func bpm(fromAvnn avnn: Double?, ibIs: [Double]) -> Double? {
        guard let avnn, avnn > 0 else { return nil }
        guard ibIs.count >= 8 else { return nil }
        let variability = (standardDeviation(ibIs) / avnn)
        guard variability <= 0.25 else { return nil }
        return round1(60000.0 / avnn)
    }

    private func sdnnMs(_ ibi: [Double]) -> Double? {
        guard ibi.count >= 2 else { return nil }
        return round2(standardDeviation(ibi))
    }

    private func rmssdMs(_ ibi: [Double]) -> Double? {
        guard ibi.count >= 3 else { return nil }
        var squared: [Double] = []
        squared.reserveCapacity(ibi.count - 1)
        for i in 1..<ibi.count {
            let diff = ibi[i] - ibi[i - 1]
            squared.append(diff * diff)
        }
        guard let avg = mean(squared) else { return nil }
        return round2(sqrt(max(0.0, avg)))
    }

    private func pnn50(_ ibi: [Double]) -> Double? {
        guard ibi.count >= 3 else { return nil }
        var count = 0
        var total = 0
        for i in 1..<ibi.count {
            total += 1
            if abs(ibi[i] - ibi[i - 1]) > 50.0 {
                count += 1
            }
        }
        guard total > 0 else { return nil }
        return round2((Double(count) / Double(total)) * 100.0)
    }

    private func baevskyStressIndex(ibiMs: [Double]) -> Double? {
        guard ibiMs.count >= 20 else { return nil }
        let ibiSec = ibiMs.map { $0 / 1000.0 }
        guard let minVal = ibiSec.min(), let maxVal = ibiSec.max(), maxVal > minVal else {
            return nil
        }
        let binWidth = 0.05
        let bins = max(1, Int(((maxVal - minVal) / binWidth).rounded()))
        var histogram: [Int] = Array(repeating: 0, count: bins + 1)
        for value in ibiSec {
            let index = min(histogram.count - 1, max(0, Int(((value - minVal) / binWidth).rounded())))
            histogram[index] += 1
        }
        guard let maxBinCount = histogram.max(), maxBinCount > 0 else { return nil }
        let modeIndex = histogram.firstIndex(of: maxBinCount) ?? 0
        let mode = minVal + (Double(modeIndex) * binWidth)
        guard mode > 0 else { return nil }
        let amo = (Double(maxBinCount) / Double(ibiSec.count)) * 100.0
        let mxdmn = maxVal - minVal
        guard mxdmn > 0 else { return nil }
        let si = amo / (2.0 * mode * mxdmn)
        return si.isFinite ? round2(si) : nil
    }

    private func estimateRespirationRate(ibiMs: [Double], ibiTsMs: [Double], qualityScore: Double) -> Double? {
        guard qualityScore >= 0.70 else { return nil }
        guard ibiMs.count >= 24, ibiMs.count == ibiTsMs.count else { return nil }
        guard let durationMs = ibiTsMs.last, durationMs >= 20_000 else { return nil }

        // Convert IBI to instantaneous heart period modulation and lightly smooth.
        let centered = ibiMs.map { $0 - (mean(ibiMs) ?? 0.0) }
        let smoothed = movingAverage(centered, window: 4)
        let sampleRate = max(0.5, Double(smoothed.count) / (durationMs / 1000.0))
        guard sampleRate >= 0.6 else { return nil }

        let filtered = bandpassResp(signal: smoothed, sampleRate: sampleRate)
        let peaks = detectRespPeaks(signal: filtered, sampleRate: sampleRate)
        guard peaks.count >= 3 else { return nil }

        let durationSec = durationMs / 1000.0
        let breathsPerMinute = (Double(peaks.count - 1) / durationSec) * 60.0
        guard breathsPerMinute >= 6.0, breathsPerMinute <= 24.0 else { return nil }

        let amplitude = standardDeviation(filtered)
        let confidence = clamp(amplitude / 25.0, min: 0.0, max: 1.0)
        guard confidence >= 0.55 else { return nil }
        return round1(breathsPerMinute)
    }

    private func bandpassResp(signal: [Double], sampleRate: Double) -> [Double] {
        guard signal.count > 6 else { return signal }
        var hp = Biquad.highPass(sampleRate: sampleRate, cutoffHz: 0.08, q: 0.707)
        var lp = Biquad.lowPass(sampleRate: sampleRate, cutoffHz: 0.45, q: 0.707)
        return signal.map { lp.process(hp.process($0)) }
    }

    private func detectRespPeaks(signal: [Double], sampleRate: Double) -> [Int] {
        guard signal.count > 5 else { return [] }
        let minDistance = max(1, Int((sampleRate * 1.6).rounded()))
        let threshold = (mean(signal) ?? 0.0) + (standardDeviation(signal) * 0.20)
        var peaks: [Int] = []
        var lastPeak = -minDistance
        for i in 1..<(signal.count - 1) {
            if signal[i] <= threshold { continue }
            if signal[i] <= signal[i - 1] || signal[i] < signal[i + 1] { continue }
            if (i - lastPeak) < minDistance { continue }
            peaks.append(i)
            lastPeak = i
        }
        return peaks
    }

    private func movingAverage(_ values: [Double], window: Int) -> [Double] {
        guard !values.isEmpty, window > 1 else { return values }
        var out: [Double] = Array(repeating: 0.0, count: values.count)
        var running = 0.0
        for i in values.indices {
            running += values[i]
            if i >= window {
                running -= values[i - window]
            }
            let count = i + 1 < window ? i + 1 : window
            out[i] = running / Double(count)
        }
        return out
    }

    private func fpsEstimate(recordDuration: Double) -> Int? {
        guard recordDuration > 0, !frameTimes.isEmpty else { return nil }
        return Int((Double(frameTimes.count) / recordDuration).rounded())
    }

    private func estimatedHz(times: [Double]) -> Double {
        guard times.count >= 2 else { return targetHz }
        let span = (times.last ?? 0.0) - (times.first ?? 0.0)
        guard span > 0 else { return targetHz }
        return Double(times.count - 1) / span
    }

    private func round1(_ value: Double) -> Double {
        (value * 10).rounded() / 10
    }

    private func round2(_ value: Double) -> Double {
        (value * 100).rounded() / 100
    }

    private func round3(_ value: Double) -> Double {
        (value * 1000).rounded() / 1000
    }

    private func round5(_ value: Double) -> Double {
        (value * 100_000).rounded() / 100_000
    }

    private func mean(_ values: [Double]) -> Double? {
        guard !values.isEmpty else { return nil }
        return values.reduce(0.0, +) / Double(values.count)
    }

    private func average(_ values: [Double]) -> Double {
        mean(values) ?? 0.0
    }

    private func standardDeviation(_ values: [Double]) -> Double {
        guard values.count > 1 else { return 0.0 }
        let mean = values.reduce(0.0, +) / Double(values.count)
        let variance = values.reduce(0.0) { acc, value in
            let delta = value - mean
            return acc + (delta * delta)
        } / Double(values.count - 1)
        return sqrt(max(0.0, variance))
    }

    private func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0.0 }
        let sorted = values.sorted()
        if sorted.count.isMultiple(of: 2) {
            let upper = sorted.count / 2
            return (sorted[upper - 1] + sorted[upper]) / 2.0
        }
        return sorted[sorted.count / 2]
    }

    private func clamp(_ value: Double, min minValue: Double, max maxValue: Double) -> Double {
        Swift.min(maxValue, Swift.max(minValue, value))
    }
}

private struct Biquad {
    let b0: Double
    let b1: Double
    let b2: Double
    let a1: Double
    let a2: Double
    var z1: Double = 0
    var z2: Double = 0

    mutating func process(_ input: Double) -> Double {
        let out = (b0 * input) + z1
        z1 = (b1 * input) - (a1 * out) + z2
        z2 = (b2 * input) - (a2 * out)
        return out
    }

    static func lowPass(sampleRate: Double, cutoffHz: Double, q: Double) -> Biquad {
        let omega = 2.0 * Double.pi * cutoffHz / sampleRate
        let alpha = sin(omega) / (2.0 * q)
        let cosw = cos(omega)

        let b0 = (1.0 - cosw) / 2.0
        let b1 = 1.0 - cosw
        let b2 = (1.0 - cosw) / 2.0
        let a0 = 1.0 + alpha
        let a1 = -2.0 * cosw
        let a2 = 1.0 - alpha
        return Biquad(
            b0: b0 / a0,
            b1: b1 / a0,
            b2: b2 / a0,
            a1: a1 / a0,
            a2: a2 / a0
        )
    }

    static func highPass(sampleRate: Double, cutoffHz: Double, q: Double) -> Biquad {
        let omega = 2.0 * Double.pi * cutoffHz / sampleRate
        let alpha = sin(omega) / (2.0 * q)
        let cosw = cos(omega)

        let b0 = (1.0 + cosw) / 2.0
        let b1 = -(1.0 + cosw)
        let b2 = (1.0 + cosw) / 2.0
        let a0 = 1.0 + alpha
        let a1 = -2.0 * cosw
        let a2 = 1.0 - alpha
        return Biquad(
            b0: b0 / a0,
            b1: b1 / a0,
            b2: b2 / a0,
            a1: a1 / a0,
            a2: a2 / a0
        )
    }
}
