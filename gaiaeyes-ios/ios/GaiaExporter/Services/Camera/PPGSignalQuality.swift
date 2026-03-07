import Foundation

enum PPGQualityLabel: String, Codable {
    case good
    case ok
    case poor
    case unknown
}

struct PPGQualityAssessment: Codable {
    let score: Double
    let label: PPGQualityLabel
    let validIBIRatio: Double
    let snrProxy: Double
    let stabilityScore: Double
    let saturationPenalty: Double
    let motionPenalty: Double
    let droppedFramePenalty: Double
}

enum PPGSignalQuality {
    static func assess(
        validIBICount: Int,
        totalIBICount: Int,
        filteredSignal: [Double],
        residualSignal: [Double],
        ibiMs: [Double],
        saturationHitRatio: Double,
        motionScore: Double,
        droppedFrameRatio: Double
    ) -> PPGQualityAssessment {
        let validRatio: Double = totalIBICount > 0
            ? Double(validIBICount) / Double(totalIBICount)
            : 0.0

        let snrProxy = normalizedSNR(filteredSignal: filteredSignal, residualSignal: residualSignal)
        let stability = ibiStabilityScore(ibiMs)
        let saturationPenalty = saturationPenalty(for: saturationHitRatio)
        let motionPenalty = clamp(max(0.0, motionScore - 0.10) * 0.25, min: 0, max: 0.20)
        let droppedPenalty = clamp(droppedFrameRatio * 0.45, min: 0, max: 0.20)

        var score =
            (0.40 * validRatio) +
            (0.28 * snrProxy) +
            (0.32 * stability) -
            saturationPenalty -
            motionPenalty -
            droppedPenalty

        if validIBICount < 8 {
            score *= 0.6
        }

        score = clamp(score, min: 0.0, max: 1.0)

        let label: PPGQualityLabel
        if score >= 0.80 {
            label = .good
        } else if score >= 0.65 {
            label = .ok
        } else {
            label = .poor
        }

        return PPGQualityAssessment(
            score: score,
            label: label,
            validIBIRatio: validRatio,
            snrProxy: snrProxy,
            stabilityScore: stability,
            saturationPenalty: saturationPenalty,
            motionPenalty: motionPenalty,
            droppedFramePenalty: droppedPenalty
        )
    }

    private static func normalizedSNR(filteredSignal: [Double], residualSignal: [Double]) -> Double {
        guard !filteredSignal.isEmpty else { return 0.0 }
        let signalStd = standardDeviation(filteredSignal)
        let noiseStd = max(standardDeviation(residualSignal), 1e-6)
        let ratio = signalStd / noiseStd
        // Typical usable camera PPG on phones often lands around 1.1-2.6.
        return clamp((ratio - 0.7) / 1.9, min: 0.0, max: 1.0)
    }

    private static func ibiStabilityScore(_ ibiMs: [Double]) -> Double {
        guard ibiMs.count >= 6 else { return 0.0 }
        let mean = ibiMs.reduce(0.0, +) / Double(ibiMs.count)
        guard mean > 0 else { return 0.0 }
        let std = standardDeviation(ibiMs)
        let cv = std / mean
        // CV of 0.03-0.12 is common for stable windows.
        return clamp(1.0 - (cv / 0.25), min: 0.0, max: 1.0)
    }

    private static func standardDeviation(_ values: [Double]) -> Double {
        guard values.count > 1 else { return 0.0 }
        let mean = values.reduce(0.0, +) / Double(values.count)
        let variance = values.reduce(0.0) { acc, value in
            let delta = value - mean
            return acc + (delta * delta)
        } / Double(values.count - 1)
        return sqrt(max(0.0, variance))
    }

    private static func saturationPenalty(for ratio: Double) -> Double {
        let clipped = clamp(ratio, min: 0.0, max: 1.0)
        let excess = max(0.0, clipped - 0.82)
        return clamp(excess * 0.70, min: 0.0, max: 0.16)
    }

    private static func clamp(_ value: Double, min minValue: Double, max maxValue: Double) -> Double {
        Swift.min(maxValue, Swift.max(minValue, value))
    }
}
