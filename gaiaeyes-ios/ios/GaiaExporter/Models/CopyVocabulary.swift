import Foundation

enum CopyRefiner {
    private static let directReplacements: [(String, String)] = [
        ("based on your data history", "in your history"),
        ("in your data history", "in your history"),
        ("based on your data", ""),
        ("This suggests that ", ""),
        ("this suggests that ", ""),
        ("This suggests ", ""),
        ("this suggests ", ""),
        ("have shown up before", "have appeared before"),
        ("has shown up before", "has appeared before"),
        ("showed up before", "appeared before"),
        ("shown up before", "appeared before"),
        ("show up before", "appear before"),
        ("most likely to affect", "most likely to line up with"),
        ("likely to affect", "likely to line up with"),
        ("stand out more", "be more noticeable"),
    ]

    private static let regexReplacements: [(String, String)] = [
        (#"(?i)\bmay cause\b"#, "may line up with"),
        (#"(?i)\bcausing\b"#, "appearing alongside"),
        (#"(?i)\bcaused\b"#, "appeared alongside"),
        (#"(?i)\bcause\b"#, "line up with"),
    ]

    static func refine(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let normalized = raw.replacingOccurrences(of: "\r\n", with: "\n")
        let lines = normalized
            .components(separatedBy: "\n")
            .map { rewriteLine($0) }
            .filter { !$0.isEmpty }

        guard !lines.isEmpty else { return nil }
        return dedupePreservingOrder(lines).joined(separator: "\n")
    }

    static func refineLines(_ lines: [String]) -> [String] {
        let cleaned = lines
            .compactMap { refine($0) }
            .filter { !$0.isEmpty }
        return dedupePreservingOrder(cleaned)
    }

    private static func rewriteLine(_ raw: String) -> String {
        var result = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !result.isEmpty else { return "" }

        for replacement in directReplacements {
            result = result.replacingOccurrences(of: replacement.0, with: replacement.1)
        }

        for replacement in regexReplacements {
            result = result.replacingOccurrences(
                of: replacement.0,
                with: replacement.1,
                options: .regularExpression
            )
        }

        result = result.replacingOccurrences(of: #"\s+([,.;:])"#, with: "$1", options: .regularExpression)
        result = result.replacingOccurrences(of: #"\s{2,}"#, with: " ", options: .regularExpression)
        result = result.replacingOccurrences(of: #" \."#, with: ".", options: .regularExpression)
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func dedupePreservingOrder(_ items: [String]) -> [String] {
        var seen: Set<String> = []
        var output: [String] = []
        for item in items {
            let key = item
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            guard !key.isEmpty, seen.insert(key).inserted else { continue }
            output.append(item)
        }
        return output
    }
}

struct CopyVocabulary {
    let mode: ExperienceMode
    let schumannLabel: String
    let solarWindLabel: String
    let geomagneticLabel: String
    let kpLabel: String
    let bzLabel: String
    let ulfLabel: String
    let pressureSwingLabel: String
    let temperatureSwingLabel: String
    let aqiLabel: String
    let allergensLabel: String
    let currentSymptomsLabel: String
    let whatMattersNowLabel: String
    let allDriversLabel: String
    let outlookLabel: String
    let patternsLabel: String
    let missionControlLabel: String
    let flareLabel: String
    let cmeLabel: String
    let sepLabel: String
    let drapLabel: String

    static func resolve(for mode: ExperienceMode) -> CopyVocabulary {
        switch mode {
        case .scientific:
            return CopyVocabulary(
                mode: mode,
                schumannLabel: "Schumann",
                solarWindLabel: "Solar Wind",
                geomagneticLabel: "Geomagnetic Activity",
                kpLabel: "Kp",
                bzLabel: "Bz",
                ulfLabel: "ULF",
                pressureSwingLabel: "Pressure Swing",
                temperatureSwingLabel: "Temperature Swing",
                aqiLabel: "AQI",
                allergensLabel: "Allergens",
                currentSymptomsLabel: "Current Symptoms",
                whatMattersNowLabel: "What Matters Now",
                allDriversLabel: "All Drivers",
                outlookLabel: "Outlook",
                patternsLabel: "Patterns",
                missionControlLabel: "Mission Control",
                flareLabel: "Solar Flares",
                cmeLabel: "CME Activity",
                sepLabel: "SEP Activity",
                drapLabel: "DRAP"
            )
        case .mystical:
            return CopyVocabulary(
                mode: mode,
                schumannLabel: "Earth’s Resonance",
                solarWindLabel: "Cosmic Pressure",
                geomagneticLabel: "Magnetic Weather",
                kpLabel: "Storm Intensity",
                bzLabel: "Field Alignment",
                ulfLabel: "Energy Waves",
                pressureSwingLabel: "Pressure Shift",
                temperatureSwingLabel: "Temperature Shift",
                aqiLabel: "Air Clarity",
                allergensLabel: "Seasonal Irritants",
                currentSymptomsLabel: "How You’re Feeling Right Now",
                whatMattersNowLabel: "What’s Shaping Today",
                allDriversLabel: "What’s Active Right Now",
                outlookLabel: "What’s Coming Next",
                patternsLabel: "Recurring Patterns",
                missionControlLabel: "Mission Control",
                flareLabel: "Solar Flares",
                cmeLabel: "Solar Waves",
                sepLabel: "Particle Weather",
                drapLabel: "Radio Haze"
            )
        }
    }

    func driverLabel(for key: String, fallback: String) -> String {
        let normalized = key
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "-", with: "_")
            .lowercased()

        switch normalized {
        case "solar_wind":
            return solarWindLabel
        case "schumann":
            return schumannLabel
        case "ulf":
            return ulfLabel
        case "kp":
            return kpLabel
        case "bz":
            return bzLabel
        case "pressure":
            return pressureSwingLabel
        case "temp":
            return temperatureSwingLabel
        case "aqi":
            return aqiLabel
        case "allergens":
            return allergensLabel
        case "flare":
            return flareLabel
        case "cme":
            return cmeLabel
        case "sep":
            return sepLabel
        case "drap":
            return drapLabel
        default:
            return fallback
        }
    }

    func translating(_ raw: String?) -> String? {
        guard let raw, !raw.isEmpty else { return nil }
        guard mode == .mystical else { return raw }

        let replacements: [(String, String)] = [
            ("Solar wind", solarWindLabel),
            ("solar wind", solarWindLabel.lowercased()),
            ("Solar Wind", solarWindLabel),
            ("Schumann resonance", schumannLabel),
            ("Schumann Resonance", schumannLabel),
            ("Schumann", schumannLabel),
            ("schumann", schumannLabel.lowercased()),
            ("ULF activity", ulfLabel),
            ("ULF", ulfLabel),
            ("Geomagnetic activity", geomagneticLabel),
            ("geomagnetic activity", geomagneticLabel.lowercased()),
            ("Geomagnetic", geomagneticLabel),
            ("geomagnetic", geomagneticLabel.lowercased()),
            ("Pressure swing", pressureSwingLabel),
            ("pressure swing", pressureSwingLabel.lowercased()),
            ("Temperature swing", temperatureSwingLabel),
            ("temperature swing", temperatureSwingLabel.lowercased()),
            ("Allergens", allergensLabel),
            ("allergens", allergensLabel.lowercased()),
            ("AQI", aqiLabel),
            ("CME", cmeLabel),
            ("SEP", sepLabel),
            ("DRAP", drapLabel),
        ]

        return replacements.reduce(raw) { partial, replacement in
            partial.replacingOccurrences(of: replacement.0, with: replacement.1)
        }
    }

    func presenting(_ raw: String?) -> String? {
        CopyRefiner.refine(translating(raw))
    }
}

extension ExperienceMode {
    var copyVocabulary: CopyVocabulary {
        CopyVocabulary.resolve(for: self)
    }
}

extension ToneStyle {
    func resolveCopy(
        straight: String? = nil,
        balanced: String,
        humorous: String? = nil
    ) -> String {
        switch self {
        case .straight:
            return straight ?? balanced
        case .balanced:
            return balanced
        case .humorous:
            return humorous ?? balanced
        }
    }
}
