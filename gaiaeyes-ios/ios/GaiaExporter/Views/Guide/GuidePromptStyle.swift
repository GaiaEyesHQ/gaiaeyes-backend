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
                return "Use this space for quick orientation, light feedback, and a calmer read on the day."
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
            return "Follow-up prompts appear here and in Body when Gaia needs another symptom update."
        case .balanced:
            return "When Gaia needs one more body detail, the follow-up lands here and in Body instead of scattering around the app."
        case .humorous:
            switch profile.guideType {
            case .cat:
                return "If Gaia wants one more body clue, it parks the follow-up here instead of batting it around the app."
            case .dog:
                return "If Gaia needs one more body detail, it brings the follow-up here instead of letting it run loose."
            case .robot:
                return "If Gaia needs another body datapoint, the follow-up queues here instead of free-roaming across the app."
            }
        }
    }

    static func understandingCardMessage(for profile: GuideProfile) -> String {
        switch (profile.mode, profile.tone) {
        case (.scientific, .straight):
            return "See what Gaia watches, how it compares signals with feedback, and where the limits are."
        case (.scientific, .balanced):
            return "See what Gaia watches, how it compares signals with feedback, and where it keeps its limits visible."
        case (.scientific, .humorous):
            return "See what Gaia watches, how the loop works, and where the app refuses to cosplay as certainty."
        case (.mystical, .straight):
            return "See what Gaia watches, how it turns patterns into guidance, and where that guidance stops."
        case (.mystical, .balanced):
            return "See what Gaia watches, how it turns patterns into guidance, and where the edges of that guidance stay honest."
        case (.mystical, .humorous):
            return "See what Gaia watches, how it learns, and where it politely declines to pretend it knows everything."
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
                return "A quick pulse keeps the guide loop current without opening the full symptom workflow."
            case .balanced:
                return "A quick pulse keeps the guide loop current without making you do the full symptom routine."
            case .humorous:
                switch profile.guideType {
                case .cat:
                    return "One small answer keeps the guide loop fed without opening the full symptom circus."
                case .dog:
                    return "One small answer keeps the guide loop current without launching the whole symptom parade."
                case .robot:
                    return "One tiny datapoint keeps the loop current without booting the full symptom console."
                }
            }
        case .symptomPulse:
            switch profile.tone {
            case .straight:
                return "A light answer keeps the guide current without turning this into a full check-in."
            case .balanced:
                return "A light answer keeps the guide current and leaves the longer check-in optional."
            case .humorous:
                return "A light answer keeps the guide current without summoning the whole check-in opera."
            }
        case .compareDay:
            switch profile.tone {
            case .straight:
                return "A fast compare keeps the guide current even when you skip the longer check-in."
            case .balanced:
                return "A fast compare keeps the guide current and gives the day a little extra context."
            case .humorous:
                return "A fast compare keeps the guide current without making you file a novel about the day."
            }
        }
    }
}
