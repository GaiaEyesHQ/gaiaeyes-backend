import SwiftUI

struct GuideProfile: Equatable {
    var guideType: GuideType
    var mode: ExperienceMode
    var tone: ToneStyle
    var useGuideAppIcon: Bool

    init(
        guideType: GuideType = .cat,
        mode: ExperienceMode = .scientific,
        tone: ToneStyle = .balanced,
        useGuideAppIcon: Bool = false
    ) {
        self.guideType = guideType
        self.mode = mode
        self.tone = tone
        self.useGuideAppIcon = useGuideAppIcon
    }

    init(experienceProfile: UserExperienceProfile, useGuideAppIcon: Bool = false) {
        self.init(
            guideType: experienceProfile.guide,
            mode: experienceProfile.mode,
            tone: experienceProfile.tone,
            useGuideAppIcon: useGuideAppIcon
        )
    }
}

@MainActor
final class GuideProfileStore: ObservableObject {
    static let useGuideAppIconDefaultsKey = "gaia.guide.use_app_icon"

    @Published private(set) var profile: GuideProfile
    @Published private(set) var supportsAlternateIcons: Bool

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let prefersGuideIcon = defaults.bool(forKey: Self.useGuideAppIconDefaultsKey)
        self.profile = GuideProfile(useGuideAppIcon: prefersGuideIcon)
        self.supportsAlternateIcons = Self.detectAlternateIconSupport()
    }

    func sync(from experienceProfile: UserExperienceProfile) {
        let next = GuideProfile(
            experienceProfile: experienceProfile,
            useGuideAppIcon: profile.useGuideAppIcon
        )
        guard next != profile else { return }
        profile = next
    }

    func setUseGuideAppIcon(_ enabled: Bool) {
        defaults.set(enabled, forKey: Self.useGuideAppIconDefaultsKey)
        var updated = profile
        updated.useGuideAppIcon = enabled
        profile = updated
    }

    var iconPreferenceFootnote: String {
        if supportsAlternateIcons {
            return "When guide-linked alternate app icons are configured, Gaia Eyes can keep the app icon aligned with your guide selection."
        }
        return "Guide-linked alternate app icons are not configured yet, but the preference path is reserved."
    }

    private static func detectAlternateIconSupport() -> Bool {
        guard
            let icons = Bundle.main.infoDictionary?["CFBundleIcons"] as? [String: Any],
            let alternates = icons["CFBundleAlternateIcons"] as? [String: Any]
        else {
            return false
        }
        return !alternates.isEmpty
    }
}
