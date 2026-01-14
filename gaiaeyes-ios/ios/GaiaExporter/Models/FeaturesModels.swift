import Foundation

struct Num: Codable {
    let value: Double?
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let doubleValue = try? container.decode(Double.self) {
            value = doubleValue
            return
        }
        if let stringValue = try? container.decode(String.self) {
            // Tolerate percent strings or other decorated numerics by filtering to digits, dot, and minus
            let filtered = stringValue.filter { "0123456789.-".contains($0) }
            if let v = Double(filtered) {
                value = v
                return
            }
        }
        value = nil
    }
}

struct EarthscopeImages: Codable {
    let caption: String?
    let stats: String?
    let affects: String?
    let playbook: String?
}

struct HealthSection: Codable {
    let spo2Avg: Num?
}

struct FeaturesToday: Codable {
    let day: String
    let stepsTotal: Num?
    let hrMin: Num?
    let hrvAvg: Num?
    let spo2Avg: Num?
    // Tolerant alternate SpO₂ keys (backend variants)
    let spo2AvgPct: Num?
    let spo2AvgPercent: Num?
    let spo2Mean: Num?
    let health: HealthSection?
    let sleepTotalMinutes: Num?
    let remM: Num?
    let coreM: Num?
    let deepM: Num?
    let awakeM: Num?
    let inbedM: Num?
    let sleepEfficiency: Num?
    let kpMax: Num?
    let bzMin: Num?
    let swSpeedAvg: Num?
    let flaresCount: Num?
    let cmesCount: Num?

    // Schumann
    let schStation: String?
    let schF0Hz: Num?
    let schF1Hz: Num?
    let schF2Hz: Num?
    let schH3Hz: Num?
    let schH4Hz: Num?

    // New health fields and alerts
    let hrMax: Num?
    let bpSysAvg: Num?
    let bpDiaAvg: Num?

    // Space weather current Kp and alerts
    let kpCurrent: Num?
    let kpAlert: Bool?
    let flareAlert: Bool?

    // Updated timestamp
    let updatedAt: String?

    // Aurora + overlays
    let auroraProbability: Num?
    let auroraProbabilityNh: Num?
    let auroraProbabilitySh: Num?
    let auroraPowerGw: Num?
    let auroraPowerNhGw: Num?
    let auroraPowerShGw: Num?
    let visualsOverlayCount: Num?
    let visualsUpdatedAt: String?

    // Earthquakes
    let earthquakeCount: Num?
    let earthquakeMaxMag: Num?
    let earthquakeMaxRegion: String?

    // Earthscope content
    let postTitle: String?
    let postCaption: String?
    let postBody: String?
    let postHashtags: String?

    // Earthscope images
    let earthscopeImages: EarthscopeImages?
}

extension FeaturesToday {
    /// Normalized SpO₂ average for display (0–100%). Accepts 0–1.0 scale and various backend variants.
    var spo2AvgDisplay: Double? {
        // Prefer explicit average, then health nested, then pct/percent variants, then mean
        let raw = spo2Avg?.value
                ?? health?.spo2Avg?.value
                ?? spo2AvgPct?.value
                ?? spo2AvgPercent?.value
                ?? spo2Mean?.value

        guard let v = raw else { return nil }

        // Normalize if the backend sends fraction (0–1)
        if v > 0, v <= 1.0 { return min(100, v * 100.0) }

        // Filter obviously bogus/placeholder values, otherwise clamp
        if v < 60 { return nil }
        if v > 100 { return 100 }
        return v
    }
}
