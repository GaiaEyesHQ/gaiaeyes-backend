import SwiftUI

enum GaiaAtmosphereVariant {
    case appShell
    case onboarding
    case modal

    var baseColors: [Color] {
        switch self {
        case .appShell:
            return [
                Color(red: 0.015, green: 0.018, blue: 0.028),
                Color(red: 0.035, green: 0.055, blue: 0.08),
                Color(red: 0.015, green: 0.022, blue: 0.04),
            ]
        case .onboarding:
            return [
                Color(red: 0.04, green: 0.045, blue: 0.08),
                Color(red: 0.05, green: 0.085, blue: 0.12),
                Color(red: 0.02, green: 0.025, blue: 0.045),
            ]
        case .modal:
            return [
                Color.black,
                Color(red: 0.035, green: 0.05, blue: 0.075),
            ]
        }
    }

    var accent: Color {
        switch self {
        case .appShell:
            return Color(red: 0.17, green: 0.55, blue: 0.72)
        case .onboarding:
            return Color(red: 0.45, green: 0.72, blue: 0.88)
        case .modal:
            return Color(red: 0.24, green: 0.62, blue: 0.66)
        }
    }

    var secondaryAccent: Color {
        switch self {
        case .appShell:
            return Color(red: 0.86, green: 0.72, blue: 0.36)
        case .onboarding:
            return Color(red: 0.22, green: 0.72, blue: 0.62)
        case .modal:
            return Color(red: 0.42, green: 0.55, blue: 0.86)
        }
    }
}

struct GaiaAtmosphereBackground: View {
    let variant: GaiaAtmosphereVariant

    private let specks: [(x: CGFloat, y: CGFloat, size: CGFloat, opacity: Double)] = [
        (0.10, 0.10, 1.1, 0.12),
        (0.34, 0.06, 0.8, 0.10),
        (0.71, 0.13, 1.3, 0.14),
        (0.88, 0.22, 0.7, 0.10),
        (0.22, 0.31, 1.0, 0.12),
        (0.58, 0.38, 0.8, 0.10),
        (0.80, 0.49, 1.2, 0.12),
        (0.13, 0.63, 0.7, 0.09),
        (0.44, 0.72, 1.1, 0.11),
        (0.93, 0.78, 0.9, 0.10),
    ]

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                LinearGradient(
                    colors: variant.baseColors,
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                RadialGradient(
                    colors: [variant.accent.opacity(0.20), .clear],
                    center: .center,
                    startRadius: 0,
                    endRadius: max(size.width, size.height) * 0.56
                )
                .frame(width: size.width * 1.35, height: size.width * 1.35)
                .position(x: size.width * 0.12, y: size.height * 0.12)
                .blendMode(.screen)

                RadialGradient(
                    colors: [variant.secondaryAccent.opacity(0.14), .clear],
                    center: .center,
                    startRadius: 0,
                    endRadius: max(size.width, size.height) * 0.52
                )
                .frame(width: size.width * 1.2, height: size.width * 1.2)
                .position(x: size.width * 0.92, y: size.height * 0.72)
                .blendMode(.screen)

                RoundedRectangle(cornerRadius: size.width * 0.45, style: .continuous)
                    .stroke(variant.accent.opacity(0.07), lineWidth: 1)
                    .frame(width: size.width * 1.15, height: size.width * 0.46)
                    .rotationEffect(.degrees(-18))
                    .offset(x: size.width * 0.36, y: -size.height * 0.08)
                    .blendMode(.screen)

                ForEach(Array(specks.enumerated()), id: \.offset) { _, speck in
                    Circle()
                        .fill(Color.white.opacity(speck.opacity))
                        .frame(width: speck.size, height: speck.size)
                        .position(x: size.width * speck.x, y: size.height * speck.y)
                }

                Color.black.opacity(variant == .appShell ? 0.22 : 0.08)
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }
}
