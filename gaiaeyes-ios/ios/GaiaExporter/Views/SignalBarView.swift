import SwiftUI

enum SignalBarState: String, Codable, Hashable {
    case quiet
    case watch
    case elevated
    case strong

    var title: String {
        switch self {
        case .quiet:
            return "Quiet"
        case .watch:
            return "Watch"
        case .elevated:
            return "Elevated"
        case .strong:
            return "Strong"
        }
    }

    var tint: Color {
        switch self {
        case .quiet:
            return Color(red: 0.29, green: 0.52, blue: 0.88)
        case .watch:
            return Color(red: 0.85, green: 0.73, blue: 0.30)
        case .elevated:
            return GaugePalette.elevated
        case .strong:
            return GaugePalette.high
        }
    }

    var glowRadius: CGFloat {
        switch self {
        case .elevated:
            return 10
        case .strong:
            return 14
        case .quiet, .watch:
            return 0
        }
    }

    var glowOpacity: Double {
        switch self {
        case .elevated:
            return 0.28
        case .strong:
            return 0.36
        case .quiet, .watch:
            return 0.0
        }
    }
}

struct SignalPill: Identifiable, Codable, Hashable {
    let key: String
    let label: String
    let value: String
    let state: SignalBarState
    let driverKey: String?
    let detailTarget: String?
    let updatedAt: String?

    var id: String { key }

    private static func placeholder(
        key: String,
        label: String,
        driverKey: String?,
        detailTarget: String?
    ) -> SignalPill {
        SignalPill(
            key: key,
            label: label,
            value: "—",
            state: .quiet,
            driverKey: driverKey,
            detailTarget: detailTarget,
            updatedAt: nil
        )
    }

    static let placeholders: [SignalPill] = [
        .placeholder(key: "kp", label: "KP", driverKey: "kp", detailTarget: "driver"),
        .placeholder(key: "solar_wind", label: "SW", driverKey: "solar_wind", detailTarget: "driver"),
        .placeholder(key: "schumann", label: "SR", driverKey: "schumann", detailTarget: "schumann"),
        .placeholder(key: "pressure", label: "hPa", driverKey: "pressure", detailTarget: "local_conditions"),
    ]
}

struct SignalBarSnapshot: Codable, Hashable {
    let updatedAt: String?
    let items: [SignalPill]
}

struct SignalBarView: View {
    let signals: [SignalPill]
    var onTap: ((SignalPill) -> Void)? = nil

    private var resolvedSignals: [SignalPill] {
        signals.isEmpty ? SignalPill.placeholders : signals
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(resolvedSignals) { signal in
                    SignalBarButton(signal: signal, onTap: onTap)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.black.opacity(0.72))
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.white.opacity(0.10), lineWidth: 1)
                )
        )
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .padding(.bottom, 8)
    }
}

private struct SignalBarButton: View {
    let signal: SignalPill
    let onTap: ((SignalPill) -> Void)?

    private var displayValue: String {
        let trimmed = signal.value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || trimmed == "—" {
            return signal.state.title
        }
        return trimmed
    }

    var body: some View {
        Button {
            onTap?(signal)
        } label: {
            HStack(spacing: 6) {
                Text(signal.label)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundColor(signal.state.tint.opacity(0.96))
                Text(displayValue)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .minimumScaleFactor(0.84)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(signal.state.tint.opacity(0.16))
            .overlay(
                RoundedRectangle(cornerRadius: 999, style: .continuous)
                    .stroke(signal.state.tint.opacity(0.52), lineWidth: 1)
            )
            .clipShape(Capsule())
            .shadow(color: signal.state.tint.opacity(signal.state.glowOpacity), radius: signal.state.glowRadius, x: 0, y: 0)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(signal.label) \(displayValue), \(signal.state.title)")
    }
}
