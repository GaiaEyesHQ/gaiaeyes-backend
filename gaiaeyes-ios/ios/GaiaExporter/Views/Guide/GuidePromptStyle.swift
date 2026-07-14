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
        switch (profile.guideType, profile.mode) {
        case (.cat, .scientific):
            return "Here's today’s signal mix."
        case (.cat, .mystical):
            return "Here’s what seems active today."
        case (.dog, .scientific):
            return "A steady read on today’s strongest inputs."
        case (.dog, .mystical):
            return "Here's what may be nudging the day."
        case (.robot, .scientific):
            return "Current signal scan: highest-relevance items first."
        case (.robot, .mystical):
            return "Pattern scan: most likely influences first."
        }
    }

    static func headerSupportLine(for profile: GuideProfile) -> String {
        switch profile.tone {
        case .straight:
            return "Start with the essentials, then open the deeper layers only if you need them."
        case .balanced:
            switch profile.guideType {
            case .cat:
                return "Start with what your body may notice, then open deeper context if you need it."
            case .dog:
                return "Use this space to get oriented fast, leave a little feedback, and keep the day grounded."
            case .robot:
                return "Use this space to orient quickly, add lightweight feedback, and keep the day legible."
            }
        case .humorous:
            switch profile.guideType {
            case .cat:
                return "Quick scan first. No need to cannonball into the signal soup."
            case .dog:
                return "Quick scan first. No need to chase every squirrel in the data."
            case .robot:
                return "Quick scan first. No need to overclock the signal spaghetti."
            }
        }
    }

    static func earthscopeFallbackMessage(for profile: GuideProfile) -> String {
        switch (profile.mode, profile.tone) {
        case (.scientific, .straight):
            return "EarthScope holds the current snapshot, highlighted drivers, and the quickest route into the deeper signal layers."
        case (.scientific, .balanced):
            return "EarthScope holds the day’s translated snapshot plus the strongest current drivers."
        case (.scientific, .humorous):
            return profile.guideType == .robot
                ? "EarthScope has the current scan, the loudest drivers, and the route into the nerdier layers."
                : "EarthScope has the day’s snapshot, the loudest drivers, and the clean route into the deeper layers."
        case (.mystical, .straight):
            return "EarthScope holds the day’s translated field read and the influences standing out most."
        case (.mystical, .balanced):
            return "EarthScope holds the day’s translated field read plus the clearest influences in play."
        case (.mystical, .humorous):
            return "EarthScope has the day’s field read and the influences making the most polite amount of noise."
        }
    }

    static func followUpFallbackMessage(for profile: GuideProfile) -> String {
        switch profile.tone {
        case .straight:
            return "Follow-up questions appear here and in Body when a symptom is ready for an update."
        case .balanced:
            return "When a symptom is ready for an update, you can answer here or in Body."
        case .humorous:
            switch profile.guideType {
            case .cat:
                return "When a symptom needs a quick update, the question waits here—no chasing required."
            case .dog:
                return "When a symptom needs a quick update, the question waits here and in Body."
            case .robot:
                return "When a symptom needs a quick update, the question is ready here and in Body."
            }
        }
    }

    static func understandingCardMessage(for profile: GuideProfile) -> String {
        switch (profile.mode, profile.tone) {
        case (.scientific, .straight):
            return "Learn what Gaia Eyes watches, how it connects patterns, and what its guidance can—and cannot—tell you."
        case (.scientific, .balanced):
            return "Learn what Gaia Eyes watches, how it connects patterns, and where its guidance has limits."
        case (.scientific, .humorous):
            return "See how Gaia Eyes connects patterns without pretending every signal is a certainty."
        case (.mystical, .straight):
            return "Learn what Gaia Eyes watches, how it turns patterns into guidance, and where that guidance stops."
        case (.mystical, .balanced):
            return "Learn how Gaia Eyes connects patterns while keeping the limits of its guidance clear."
        case (.mystical, .humorous):
            return "See how Gaia Eyes connects patterns while politely declining to know everything."
        }
    }

    enum DailyPollContext {
        case followUp
        case symptomPulse
        case compareDay
    }

    static func dailyPollSupportLine(for profile: GuideProfile, context: DailyPollContext) -> String {
        switch context {
        case .followUp:
            switch profile.tone {
            case .straight:
                return "One quick answer helps compare this symptom with today’s signals."
            case .balanced:
                return "A quick answer adds context without asking you to complete the full check-in."
            case .humorous:
                switch profile.guideType {
                case .cat:
                    return "One small answer adds context—no full symptom circus required."
                case .dog:
                    return "One small answer adds context without the whole check-in."
                case .robot:
                    return "One quick input adds context without opening the full check-in."
                }
            }
        case .symptomPulse:
            switch profile.tone {
            case .straight:
                return "A quick answer adds context without opening the full check-in."
            case .balanced:
                return "A quick answer adds context while leaving the longer check-in optional."
            case .humorous:
                return "One quick answer adds context—no full check-in opera required."
            }
        case .compareDay:
            switch profile.tone {
            case .straight:
                return "A quick comparison helps Gaia Eyes understand how today differed from yesterday."
            case .balanced:
                return "A quick comparison gives today a little more context."
            case .humorous:
                return "A quick comparison adds context without asking for a novel about the day."
            }
        }
    }
}
