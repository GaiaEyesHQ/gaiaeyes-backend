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

struct GeomagneticContextSummary: Codable, Hashable {
    let label: String?
    let classRaw: String?
    let confidenceScore: Double?
    let confidenceLabel: String?
    let regionalIntensity: Double?
    let regionalCoherence: Double?
    let regionalPersistence: Double?
    let qualityFlags: [String]?
    let isProvisional: Bool?
    let isUsable: Bool?
    let isHighConfidence: Bool?
    let stationCount: Int?
    let missingSamples: Bool?
    let lowHistory: Bool?
    let tsUtc: String?
}

struct LunarContextSummary: Codable, Hashable {
    let utcDate: String?
    let moonPhaseFraction: Double?
    let moonIlluminationPct: Double?
    let moonPhaseLabel: String?
    let daysFromFullMoon: Int?
    let daysFromNewMoon: Int?
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
    let respiratoryRateAvg: Num?
    let respiratoryRateSleepAvg: Num?
    let respiratoryRateBaselineDelta: Num?
    let temperatureDeviation: Num?
    let temperatureDeviationBaselineDelta: Num?
    let temperatureSource: String?
    let restingHrAvg: Num?
    let restingHrBaselineDelta: Num?
    let bedtimeConsistencyScore: Num?
    let waketimeConsistencyScore: Num?
    let sleepDebtProxy: Num?
    let sleepVs14dBaselineDelta: Num?
    let cycleTrackingEnabled: Bool?
    let cyclePhase: String?
    let menstrualActive: Bool?
    let cycleDay: Num?
    let cycleUpdatedAt: String?
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
    let moonPhaseFraction: Num?
    let moonIlluminationPct: Num?
    let moonPhaseLabel: String?
    let daysFromFullMoon: Num?
    let daysFromNewMoon: Num?
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
    let auroraHpNorthGw: Num?
    let auroraHpSouthGw: Num?
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

    // Geomagnetic context
    let ulfContextClassRaw: String?
    let ulfContextLabel: String?
    let ulfConfidenceScore: Double?
    let ulfConfidenceLabel: String?
    let ulfRegionalIntensity: Double?
    let ulfRegionalCoherence: Double?
    let ulfRegionalPersistence: Double?
    let ulfQualityFlags: [String]?
    let ulfIsProvisional: Bool?
    let ulfIsUsable: Bool?
    let ulfIsHighConfidence: Bool?
    let ulfStationCount: Int?
    let ulfMissingSamples: Bool?
    let ulfLowHistory: Bool?
    let geomagneticContext: GeomagneticContextSummary?
    let lunarContext: LunarContextSummary?

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

    var effectiveGeomagneticContext: GeomagneticContextSummary? {
        if let geomagneticContext {
            return geomagneticContext
        }

        let hasFlatContext =
            ulfContextLabel != nil ||
            ulfContextClassRaw != nil ||
            ulfConfidenceScore != nil ||
            ulfRegionalIntensity != nil ||
            ulfRegionalCoherence != nil ||
            ulfRegionalPersistence != nil
        guard hasFlatContext else { return nil }

        return GeomagneticContextSummary(
            label: ulfContextLabel,
            classRaw: ulfContextClassRaw,
            confidenceScore: ulfConfidenceScore,
            confidenceLabel: ulfConfidenceLabel,
            regionalIntensity: ulfRegionalIntensity,
            regionalCoherence: ulfRegionalCoherence,
            regionalPersistence: ulfRegionalPersistence,
            qualityFlags: ulfQualityFlags,
            isProvisional: ulfIsProvisional,
            isUsable: ulfIsUsable,
            isHighConfidence: ulfIsHighConfidence,
            stationCount: ulfStationCount,
            missingSamples: ulfMissingSamples,
            lowHistory: ulfLowHistory,
            tsUtc: nil
        )
    }

    var effectiveLunarContext: LunarContextSummary? {
        if let lunarContext {
            return lunarContext
        }

        let hasFlatContext =
            moonPhaseFraction?.value != nil ||
            moonIlluminationPct?.value != nil ||
            moonPhaseLabel != nil ||
            daysFromFullMoon?.value != nil ||
            daysFromNewMoon?.value != nil
        guard hasFlatContext else { return nil }

        return LunarContextSummary(
            utcDate: day,
            moonPhaseFraction: moonPhaseFraction?.value,
            moonIlluminationPct: moonIlluminationPct?.value,
            moonPhaseLabel: moonPhaseLabel,
            daysFromFullMoon: daysFromFullMoon?.value.map { Int($0.rounded()) },
            daysFromNewMoon: daysFromNewMoon?.value.map { Int($0.rounded()) }
        )
    }
}
