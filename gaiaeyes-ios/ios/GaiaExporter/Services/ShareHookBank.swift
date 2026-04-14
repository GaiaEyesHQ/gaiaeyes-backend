import Foundation

enum ShareHookCategory: String {
    case solar
    case earth
    case pressure
    case air
    case geomagnetic
    case pattern
    case body
}

enum ShareHookBank {
    static func category(
        for shareType: ShareType,
        analyticsKey: String?,
        title: String,
        backgroundStyle: ShareBackgroundStyle
    ) -> ShareHookCategory {
        if shareType == .personalPattern {
            return .pattern
        }

        let haystack = [analyticsKey, title, backgroundStyle.rawValue]
            .compactMap { $0?.lowercased() }
            .joined(separator: " ")

        if haystack.contains("temporary_illness")
            || haystack.contains("temporary illness")
            || haystack.contains("illness")
            || haystack.contains("sick")
            || haystack.contains("symptom")
            || haystack.contains("body_")
            || haystack.contains("body context") {
            return .body
        }
        if haystack.contains("pressure") || haystack.contains("temp") || haystack.contains("weather") {
            return .pressure
        }
        if haystack.contains("aqi") || haystack.contains("allergen") || haystack.contains("pollen") || haystack.contains("air") {
            return .air
        }
        if haystack.contains("schumann")
            || haystack.contains("geomagnetic")
            || haystack.contains("magnetic")
            || haystack.contains("kp")
            || haystack.contains("bz")
            || haystack.contains("ulf")
            || haystack.contains("resonance") {
            return .geomagnetic
        }
        if haystack.contains("solar")
            || haystack.contains("flare")
            || haystack.contains("cme")
            || haystack.contains("sep")
            || haystack.contains("drap") {
            return .solar
        }

        switch backgroundStyle {
        case .solar, .cme:
            return .solar
        case .schumann:
            return .geomagnetic
        case .atmospheric, .abstract:
            return .earth
        }
    }

    static func hook(for category: ShareHookCategory, mode: ExperienceMode) -> String {
        bank(for: category).randomElement()?.text(for: mode) ?? "Check your signals today"
    }

    private static func bank(for category: ShareHookCategory) -> [HookPair] {
        switch category {
        case .solar:
            return solarHooks
        case .earth:
            return earthHooks
        case .pressure:
            return pressureHooks
        case .air:
            return airHooks
        case .geomagnetic:
            return geomagneticHooks
        case .pattern:
            return patternHooks
        case .body:
            return bodyHooks
        }
    }

    private struct HookPair {
        let scientific: String
        let mystical: String

        func text(for mode: ExperienceMode) -> String {
            switch mode {
            case .scientific:
                return scientific
            case .mystical:
                return mystical
            }
        }
    }

    private static let solarHooks: [HookPair] = [
        HookPair(scientific: "The sun is throwing a tantrum", mystical: "The sun is throwing a tantrum"),
        HookPair(scientific: "The sun is stirring the sleep forecast", mystical: "The sun is stirring the sleep forecast"),
        HookPair(scientific: "A solar wave is moving through", mystical: "A solar wave is moving through"),
        HookPair(scientific: "The sun just woke up", mystical: "The sun just woke up"),
        HookPair(scientific: "Solar activity is heating up", mystical: "Solar fire is building"),
        HookPair(scientific: "That flare was not subtle", mystical: "That flare was not quiet"),
        HookPair(scientific: "Space weather just shifted", mystical: "The sky just changed its mood"),
        HookPair(scientific: "The solar background got louder", mystical: "The cosmic weather got louder"),
        HookPair(scientific: "Today has more solar motion in it", mystical: "Today carries a little more solar charge"),
        HookPair(scientific: "The sun is making itself known", mystical: "The sun is making itself felt"),
        HookPair(scientific: "Solar conditions are picking up", mystical: "The solar field is picking up"),
        HookPair(scientific: "The space weather feed is active", mystical: "The sky is stirring today"),
        HookPair(scientific: "Solar motion is building today", mystical: "Cosmic motion is building today"),
        HookPair(scientific: "The sun is having a louder day", mystical: "The sun is having a louder mood"),
        HookPair(scientific: "This is an active solar window", mystical: "This is a brighter cosmic window"),
        HookPair(scientific: "Solar conditions just sharpened", mystical: "The sky just sharpened"),
        HookPair(scientific: "Something solar just stepped forward", mystical: "Something cosmic just stepped forward"),
        HookPair(scientific: "The sun is not staying quiet", mystical: "The sun is not staying quiet"),
        HookPair(scientific: "Solar energy is turning up", mystical: "Solar fire is turning up"),
        HookPair(scientific: "The space weather mood changed", mystical: "The cosmos changed tone"),
        HookPair(scientific: "Today comes with extra solar context", mystical: "Today comes with extra sky noise"),
        HookPair(scientific: "The solar feed just got interesting", mystical: "The heavens just got interesting"),
        HookPair(scientific: "Solar conditions just moved fast", mystical: "Cosmic conditions just moved fast"),
    ]

    private static let earthHooks: [HookPair] = [
        HookPair(scientific: "Today is not as quiet as it looks", mystical: "Today is not as quiet as it looks"),
        HookPair(scientific: "Something subtle is shifting today", mystical: "Something subtle is shifting today"),
        HookPair(scientific: "This is a listen closely kind of day", mystical: "This is a listen closely kind of day"),
        HookPair(scientific: "Today may feel a little off", mystical: "Today may feel a little off"),
        HookPair(scientific: "There is more context in the background today", mystical: "There is more in the field today"),
        HookPair(scientific: "The day has a little more texture", mystical: "The day has a little more texture"),
        HookPair(scientific: "The background signals are not quiet today", mystical: "The background is not quiet today"),
        HookPair(scientific: "Something is nudging the day", mystical: "Something is nudging the day"),
        HookPair(scientific: "Today comes with extra signal context", mystical: "Today comes with extra energetic context"),
        HookPair(scientific: "There is a little more going on today", mystical: "There is a little more moving under the surface"),
        HookPair(scientific: "The day is carrying a stronger pattern", mystical: "The day is carrying a stronger pulse"),
        HookPair(scientific: "Conditions are more layered today", mystical: "The field feels more layered today"),
        HookPair(scientific: "Today has a sharper edge", mystical: "Today has a sharper edge"),
        HookPair(scientific: "The signal mix is a little louder", mystical: "The field mix is a little louder"),
        HookPair(scientific: "This day has some extra drag in it", mystical: "This day has some extra weight in it"),
        HookPair(scientific: "The background just moved a little", mystical: "The background just moved a little"),
        HookPair(scientific: "Today is carrying more friction", mystical: "Today is carrying more charge"),
        HookPair(scientific: "This is a pay attention day", mystical: "This is a pay attention day"),
        HookPair(scientific: "The day is giving more feedback", mystical: "The day is giving more feedback"),
        HookPair(scientific: "Today is doing a little more than usual", mystical: "Today is doing a little more than usual"),
    ]

    private static let pressureHooks: [HookPair] = [
        HookPair(scientific: "Pressure is shifting today", mystical: "Pressure is shifting today"),
        HookPair(scientific: "This is headache weather", mystical: "This is headache weather"),
        HookPair(scientific: "The air is moving and your body might notice", mystical: "The air is moving and your body might notice"),
        HookPair(scientific: "Weather like this rarely goes unnoticed", mystical: "Weather like this rarely goes unnoticed"),
        HookPair(scientific: "The pressure story changed fast", mystical: "The pressure story changed fast"),
        HookPair(scientific: "The weather just leaned harder", mystical: "The weather just leaned harder"),
        HookPair(scientific: "That pressure swing is not subtle", mystical: "That pressure swing is not subtle"),
        HookPair(scientific: "The atmosphere just changed gears", mystical: "The atmosphere just changed gears"),
        HookPair(scientific: "Today comes with a pressure shove", mystical: "Today comes with a pressure shove"),
        HookPair(scientific: "There is some body weather in the air", mystical: "There is some body weather in the air"),
        HookPair(scientific: "Pressure is making a bigger move today", mystical: "Pressure is making a bigger move today"),
        HookPair(scientific: "This is the kind of weather people feel", mystical: "This is the kind of weather people feel"),
        HookPair(scientific: "The air pressure changed its mind", mystical: "The air pressure changed its mind"),
        HookPair(scientific: "Today has a pressure edge to it", mystical: "Today has a pressure edge to it"),
        HookPair(scientific: "The barometer is doing more than usual", mystical: "The barometer is doing more than usual"),
        HookPair(scientific: "That weather shift may land in the body", mystical: "That weather shift may land in the body"),
        HookPair(scientific: "The weather is pressing a little harder", mystical: "The weather is pressing a little harder"),
        HookPair(scientific: "A pressure move is setting the tone", mystical: "A pressure move is setting the tone"),
        HookPair(scientific: "This looks like a pressure sensitive day", mystical: "This looks like a pressure sensitive day"),
        HookPair(scientific: "The air just got louder", mystical: "The air just got louder"),
    ]

    private static let airHooks: [HookPair] = [
        HookPair(scientific: "The air is doing more than you think today", mystical: "The air is doing more than you think today"),
        HookPair(scientific: "Pollen is not playing around today", mystical: "Pollen is not playing around today"),
        HookPair(scientific: "Your sinuses may already know", mystical: "Your sinuses already know"),
        HookPair(scientific: "The air looks heavier today", mystical: "The air feels heavier today"),
        HookPair(scientific: "There is extra irritant load in the air", mystical: "There is extra bite in the air"),
        HookPair(scientific: "Today has an air quality edge", mystical: "Today has an air quality edge"),
        HookPair(scientific: "The air is carrying more friction", mystical: "The air is carrying more friction"),
        HookPair(scientific: "Breathing may feel less effortless today", mystical: "Breathing may feel less easy today"),
        HookPair(scientific: "The atmosphere is a little busier today", mystical: "The atmosphere is a little busier today"),
        HookPair(scientific: "Something in the air is louder today", mystical: "Something in the air is louder today"),
        HookPair(scientific: "The pollen count has opinions today", mystical: "The pollen count has opinions today"),
        HookPair(scientific: "This is a nose knows kind of day", mystical: "This is a nose knows kind of day"),
        HookPair(scientific: "The air just got a little less forgiving", mystical: "The air just got a little less forgiving"),
        HookPair(scientific: "Today comes with extra air load", mystical: "Today comes with extra air load"),
        HookPair(scientific: "The air is more reactive today", mystical: "The air is more reactive today"),
        HookPair(scientific: "The pollen story is louder today", mystical: "The pollen story is louder today"),
        HookPair(scientific: "This may be an inhale carefully day", mystical: "This may be an inhale carefully day"),
        HookPair(scientific: "The air has a sharper texture today", mystical: "The air has a sharper texture today"),
        HookPair(scientific: "Irritants are building in the background", mystical: "Irritants are building in the background"),
        HookPair(scientific: "Today has some sinus energy", mystical: "Today has some sinus energy"),
    ]

    private static let geomagneticHooks: [HookPair] = [
        HookPair(scientific: "Schumann spike: embrace the energy", mystical: "Schumann spike: embrace the energy"),
        HookPair(scientific: "Earth's resonance is speaking up", mystical: "Gaia's resonance is speaking up"),
        HookPair(scientific: "The unseen signal just got louder", mystical: "The unseen signal just got louder"),
        HookPair(scientific: "The background just got louder", mystical: "The background just got louder"),
        HookPair(scientific: "Something in the field shifted", mystical: "Something in the field shifted"),
        HookPair(scientific: "It is one of those days", mystical: "It is one of those days"),
        HookPair(scientific: "The magnetic background is more active", mystical: "The field is more active"),
        HookPair(scientific: "Earth space just got a little louder", mystical: "Earth space just got a little louder"),
        HookPair(scientific: "The field has more motion today", mystical: "The field has more motion today"),
        HookPair(scientific: "Something subtle in the background turned up", mystical: "Something subtle in the background turned up"),
        HookPair(scientific: "The signal behind the day just shifted", mystical: "The pulse behind the day just shifted"),
        HookPair(scientific: "The field is not staying quiet", mystical: "The field is not staying quiet"),
        HookPair(scientific: "The background frequency feels louder", mystical: "The background frequency feels louder"),
        HookPair(scientific: "There is extra motion in the field today", mystical: "There is extra motion in the field today"),
        HookPair(scientific: "Magnetic conditions just sharpened", mystical: "Magnetic conditions just sharpened"),
        HookPair(scientific: "The unseen layer got a little louder", mystical: "The unseen layer got a little louder"),
        HookPair(scientific: "Today has more field texture", mystical: "Today has more field texture"),
        HookPair(scientific: "The quiet layer is not so quiet today", mystical: "The quiet layer is not so quiet today"),
        HookPair(scientific: "The field just leaned forward", mystical: "The field just leaned forward"),
        HookPair(scientific: "Something subtle is pulsing harder today", mystical: "Something subtle is pulsing harder today"),
        HookPair(scientific: "Earth signal is a little louder today", mystical: "Earth signal is a little louder today"),
        HookPair(scientific: "The resonance background changed tone", mystical: "The resonance background changed tone"),
        HookPair(scientific: "Today comes with extra field noise", mystical: "Today comes with extra field noise"),
    ]

    private static let patternHooks: [HookPair] = [
        HookPair(scientific: "This keeps showing up in your data", mystical: "This keeps showing up in your story"),
        HookPair(scientific: "Your pattern log noticed this again", mystical: "Your pattern log noticed this again"),
        HookPair(scientific: "This is not random anymore", mystical: "This is not random anymore"),
        HookPair(scientific: "Your data keeps circling back to this", mystical: "Your story keeps circling back to this"),
        HookPair(scientific: "There is a repeat signal here", mystical: "There is a repeat signal here"),
        HookPair(scientific: "This pattern has shown up before", mystical: "This pattern has shown up before"),
        HookPair(scientific: "Your history is connecting the dots", mystical: "Your history is connecting the dots"),
        HookPair(scientific: "This keeps landing in the same place", mystical: "This keeps landing in the same place"),
        HookPair(scientific: "The pattern is getting harder to ignore", mystical: "The pattern is getting harder to ignore"),
        HookPair(scientific: "This link keeps repeating", mystical: "This link keeps repeating"),
        HookPair(scientific: "Your log has seen this before", mystical: "Your log has seen this before"),
        HookPair(scientific: "This relationship keeps reappearing", mystical: "This relationship keeps reappearing"),
        HookPair(scientific: "There is a recurring match here", mystical: "There is a recurring match here"),
        HookPair(scientific: "The same signal is showing up again", mystical: "The same signal is showing up again"),
        HookPair(scientific: "Your history is leaving breadcrumbs", mystical: "Your history is leaving breadcrumbs"),
        HookPair(scientific: "The pattern has receipts", mystical: "The pattern has receipts"),
        HookPair(scientific: "This connection is becoming a theme", mystical: "This connection is becoming a theme"),
        HookPair(scientific: "Your data is flagging the repeat", mystical: "Your data is flagging the repeat"),
        HookPair(scientific: "This may be one of your real patterns", mystical: "This may be one of your real patterns"),
        HookPair(scientific: "This pattern keeps finding you", mystical: "This pattern keeps finding you"),
    ]

    private static let bodyHooks: [HookPair] = [
        HookPair(scientific: "Your body is part of the signal", mystical: "Your body is part of the signal"),
        HookPair(scientific: "Today's body context matters", mystical: "Today's body context matters"),
        HookPair(scientific: "Current symptoms are changing the read", mystical: "Current symptoms are changing the field"),
        HookPair(scientific: "This may be a sick-day signal", mystical: "This may be a sick-day signal"),
        HookPair(scientific: "Temporary illness changes the baseline", mystical: "Temporary illness changes the baseline"),
        HookPair(scientific: "Your symptoms are part of the story", mystical: "Your symptoms are part of the story"),
        HookPair(scientific: "The body signal is louder today", mystical: "The body signal is louder today"),
        HookPair(scientific: "Today needs body-context first", mystical: "Today needs body-context first"),
    ]
}
