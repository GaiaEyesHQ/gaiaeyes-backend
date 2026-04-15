import SwiftUI

enum GaugePalette {
    static let low = Color(red: 99.0 / 255.0, green: 183.0 / 255.0, blue: 135.0 / 255.0)
    static let mild = Color(red: 158.0 / 255.0, green: 166.0 / 255.0, blue: 108.0 / 255.0)
    static let elevated = Color(red: 200.0 / 255.0, green: 146.0 / 255.0, blue: 91.0 / 255.0)
    static let high = Color(red: 201.0 / 255.0, green: 117.0 / 255.0, blue: 109.0 / 255.0)
    static let aqua = Color(red: 82.0 / 255.0, green: 205.0 / 255.0, blue: 218.0 / 255.0)
    static let sky = Color(red: 94.0 / 255.0, green: 142.0 / 255.0, blue: 245.0 / 255.0)
    static let rose = Color(red: 226.0 / 255.0, green: 112.0 / 255.0, blue: 132.0 / 255.0)
    static let violet = Color(red: 162.0 / 255.0, green: 130.0 / 255.0, blue: 224.0 / 255.0)
    static let ringBackground = Color.white.opacity(0.10)
    static let marker = Color.white

    static var arcGradient: AngularGradient {
        AngularGradient(
            gradient: Gradient(stops: [
                .init(color: low, location: 0.00),
                .init(color: mild, location: 0.40),
                .init(color: elevated, location: 0.70),
                .init(color: high, location: 1.00),
            ]),
            center: .center,
            startAngle: .degrees(-90),
            endAngle: .degrees(270)
        )
    }

    static func zoneColor(_ raw: String?) -> Color {
        switch (raw ?? "").lowercased() {
        case "low":
            return low
        case "mild":
            return mild
        case "elevated":
            return elevated
        case "high":
            return high
        default:
            return Color.secondary
        }
    }

    static func glowRadius(_ raw: String?) -> CGFloat {
        switch (raw ?? "").lowercased() {
        case "low":
            return 1.5
        case "mild":
            return 2.5
        case "elevated":
            return 4.5
        case "high":
            return 6.5
        default:
            return 0
        }
    }

    static func glowOpacity(_ raw: String?) -> Double {
        switch (raw ?? "").lowercased() {
        case "low":
            return 0.22
        case "mild":
            return 0.28
        case "elevated":
            return 0.38
        case "high":
            return 0.52
        default:
            return 0.0
        }
    }

    static func contextAccent(_ raw: String?) -> Color {
        let text = (raw ?? "").lowercased()

        if text.contains("pain") || text.contains("symptom") || text.contains("illness") {
            return rose
        }
        if text.contains("sleep") || text.contains("lunar") || text.contains("moon") {
            return violet
        }
        if text.contains("focus") || text.contains("mind") || text.contains("pattern") {
            return aqua
        }
        if text.contains("heart") || text.contains("recovery") || text.contains("health") || text.contains("body") {
            return low
        }
        if text.contains("energy") || text.contains("solar") || text.contains("flare") || text.contains("cme") || text.contains("kp") {
            return elevated
        }
        if text.contains("schumann") || text.contains("resonance") || text.contains("space") || text.contains("earth") || text.contains("explore") {
            return sky
        }
        if text.contains("weather") || text.contains("local") || text.contains("pressure") || text.contains("air") || text.contains("allergen") || text.contains("humidity") {
            return mild
        }

        return aqua
    }

    static func softCardGradient(
        accent: Color,
        highlightOpacity: Double = 0.12,
        baseOpacity: Double = 0.055,
        shadowOpacity: Double = 0.18
    ) -> LinearGradient {
        LinearGradient(
            colors: [
                accent.opacity(highlightOpacity),
                Color.white.opacity(baseOpacity),
                Color.black.opacity(shadowOpacity)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}
