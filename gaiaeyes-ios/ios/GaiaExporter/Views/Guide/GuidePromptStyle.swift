import SwiftUI

enum GuideAvatarTintMode {
    case fullColor
    case softened
}

struct GuidePromptStyle {
    let accent: Color
    let glow: Color
    let cardFill: Color
    let cardBorder: Color
    let plateFill: Color
    let plateBorder: Color
    let primaryText: Color
    let secondaryText: Color
    let tertiaryText: Color

    static func style(for guide: GuideType, emphasis: GuideAvatarEmphasis = .standard) -> GuidePromptStyle {
        let baseAccent: Color
        switch guide {
        case .cat:
            baseAccent = Color(red: 0.29, green: 0.79, blue: 0.96)
        case .dog:
            baseAccent = Color(red: 0.24, green: 0.76, blue: 0.86)
        case .robot:
            baseAccent = Color(red: 0.33, green: 0.71, blue: 0.99)
        }

        let glowOpacity: Double
        let fillOpacity: Double
        let borderOpacity: Double
        switch emphasis {
        case .quiet:
            glowOpacity = 0.16
            fillOpacity = 0.06
            borderOpacity = 0.10
        case .standard:
            glowOpacity = 0.24
            fillOpacity = 0.08
            borderOpacity = 0.14
        case .elevated:
            glowOpacity = 0.34
            fillOpacity = 0.10
            borderOpacity = 0.18
        case .active:
            glowOpacity = 0.40
            fillOpacity = 0.12
            borderOpacity = 0.22
        }

        return GuidePromptStyle(
            accent: baseAccent,
            glow: baseAccent.opacity(glowOpacity),
            cardFill: Color.white.opacity(fillOpacity),
            cardBorder: baseAccent.opacity(borderOpacity),
            plateFill: Color.white.opacity(0.18 + (fillOpacity * 0.9)),
            plateBorder: baseAccent.opacity(borderOpacity),
            primaryText: .white.opacity(0.94),
            secondaryText: .white.opacity(0.72),
            tertiaryText: .white.opacity(0.58)
        )
    }

    static func headerLine(for profile: GuideProfile) -> String {
        switch profile.guideType {
        case .cat:
            return profile.mode == .scientific
                ? "Here’s what’s worth checking today."
                : "I’ll help translate what feels active today."
        case .dog:
            return profile.mode == .scientific
                ? "A steady read on what matters most today."
                : "A grounded read on what may stand out today."
        case .robot:
            return profile.mode == .scientific
                ? "A clean path through today’s signal context."
                : "A clear map of what may matter next."
        }
    }

    static func headerSupportLine(for profile: GuideProfile) -> String {
        switch profile.tone {
        case .straight:
            return "Start with the essentials, then open the deeper layers only if you need them."
        case .balanced:
            return "Use this space for quick orientation, lightweight feedback, and a clearer sense of the day."
        case .humorous:
            return "A calm place to check what the day is doing before the signal soup gets louder."
        }
    }
}
