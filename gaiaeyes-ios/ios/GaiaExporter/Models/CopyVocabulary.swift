import Foundation

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
