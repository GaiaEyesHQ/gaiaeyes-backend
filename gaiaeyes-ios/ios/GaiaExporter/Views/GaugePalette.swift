import SwiftUI

enum GaugePalette {
    static let low = Color(red: 99.0 / 255.0, green: 183.0 / 255.0, blue: 135.0 / 255.0)
    static let mild = Color(red: 158.0 / 255.0, green: 166.0 / 255.0, blue: 108.0 / 255.0)
    static let elevated = Color(red: 200.0 / 255.0, green: 146.0 / 255.0, blue: 91.0 / 255.0)
    static let high = Color(red: 201.0 / 255.0, green: 117.0 / 255.0, blue: 109.0 / 255.0)
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
}
