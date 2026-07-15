import Foundation

struct ExposureOption: Identifiable, Hashable {
    let id: String
    let label: String
    let systemImage: String

    static let everyday: [ExposureOption] = [
        ExposureOption(id: "fragrance_scented_products", label: "Fragrance / scented products", systemImage: "sparkles"),
        ExposureOption(id: "cleaning_products", label: "Cleaning products", systemImage: "spray.sparkle"),
        ExposureOption(id: "plastics_heated_food", label: "Plastics or heated food containers", systemImage: "takeoutbag.and.cup.and.straw"),
        ExposureOption(id: "ultra_processed_meal", label: "Ultra-processed meal", systemImage: "fork.knife.circle"),
        ExposureOption(id: "alcohol", label: "Alcohol", systemImage: "wineglass"),
        ExposureOption(id: "high_histamine_foods", label: "High-histamine foods", systemImage: "leaf"),
        ExposureOption(id: "pesticide_heavy_produce", label: "Pesticide-heavy produce", systemImage: "carrot"),
        ExposureOption(id: "mold_damp_space", label: "Mold or damp space", systemImage: "drop.triangle"),
        ExposureOption(id: "workplace_exposure", label: "Workplace exposure", systemImage: "building.2"),
        ExposureOption(id: "heavy_traffic", label: "Heavy traffic", systemImage: "car.2"),
        ExposureOption(id: "poor_air_quality", label: "Poor air quality", systemImage: "aqi.medium"),
        ExposureOption(id: "rapid_temperature_change", label: "Rapid temperature change", systemImage: "thermometer"),
        ExposureOption(id: "new_supplement_medication", label: "New supplement or medication", systemImage: "pills"),
    ]

    static let checkIn: [ExposureOption] = [
        ExposureOption(id: "overexertion", label: "Heavy activity / overdid it", systemImage: "figure.run"),
        ExposureOption(id: "allergen_exposure", label: "Allergen exposure", systemImage: "allergens"),
        ExposureOption(id: "temporary_illness", label: "Cold / flu / temporary illness", systemImage: "cross.case"),
    ] + everyday

    static let migraineFocus: [ExposureOption] = [
        ExposureOption(id: "fragrance_scented_products", label: "Fragrance / scented products", systemImage: "sparkles"),
        ExposureOption(id: "cleaning_products", label: "Cleaning products", systemImage: "spray.sparkle"),
        ExposureOption(id: "poor_air_quality", label: "Poor air quality", systemImage: "aqi.medium"),
        ExposureOption(id: "rapid_temperature_change", label: "Rapid temperature change", systemImage: "thermometer"),
        ExposureOption(id: "heavy_traffic", label: "Heavy traffic", systemImage: "car.2"),
        ExposureOption(id: "mold_damp_space", label: "Mold or damp space", systemImage: "drop.triangle"),
        ExposureOption(id: "alcohol", label: "Alcohol", systemImage: "wineglass"),
        ExposureOption(id: "high_histamine_foods", label: "High-histamine foods", systemImage: "leaf"),
        ExposureOption(id: "new_supplement_medication", label: "New supplement or medication", systemImage: "pills"),
    ]

    static func label(for id: String) -> String {
        if let match = (checkIn + everyday).first(where: { $0.id == id }) {
            return match.label
        }
        return id.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

enum ExposureLogFocus: Hashable {
    case general
    case migraine
}

struct ExposureEventOut: Decodable, Hashable {
    let id: String?
    let exposureKey: String
    let intensity: Int
    let eventTsUtc: String?
    let source: String
    let noteText: String?
}
