import UIKit

struct GuideAssetResolver {
    static func assetName(for guide: GuideType, expression: GuideExpression, size: GuideAvatarSize = .medium) -> String {
        let candidates = candidateAssetNames(for: guide, expression: expression, size: size)
        return candidates.first(where: assetExists(named:)) ?? "cat_avatar_neutral"
    }

    private static func candidateAssetNames(for guide: GuideType, expression: GuideExpression, size: GuideAvatarSize) -> [String] {
        switch guide {
        case .cat:
            return catCandidates(for: expression, size: size)
        case .dog:
            // Dog assets are not in the catalog yet. Probe future-friendly names first,
            // then fall back to the calmest cat equivalent so the UI never renders blank.
            return futureGuideCandidates(prefix: "dog", expression: expression, size: size) + fallbackCandidates(for: expression, size: size)
        case .robot:
            // Robot assets follow the same strategy: prefer future robot-specific assets
            // when they land, otherwise degrade gracefully to the shared cat fallback set.
            return futureGuideCandidates(prefix: "robot", expression: expression, size: size) + fallbackCandidates(for: expression, size: size)
        }
    }

    private static func catCandidates(for expression: GuideExpression, size: GuideAvatarSize) -> [String] {
        switch expression {
        case .neutral, .playful:
            return ["cat_avatar_neutral"]
        case .subtle:
            if size == .micro || size == .small {
                return ["cat_avatar_icon", "cat_avatar_neutral"]
            }
            return ["cat_avatar_neutral", "cat_avatar_icon"]
        case .calm:
            return ["cat_avatar_calm", "cat_avatar_neutral"]
        case .alert:
            return ["cat_avatar_alert", "cat_avatar_neutral"]
        case .curious, .followUp:
            return ["cat_avatar_curious", "cat_avatar_neutral"]
        case .helpful:
            return ["cat_avatar_sign", "cat_avatar_neutral"]
        case .guide:
            return ["cat_portrait_neutral", "cat_avatar_neutral"]
        }
    }

    private static func futureGuideCandidates(prefix: String, expression: GuideExpression, size: GuideAvatarSize) -> [String] {
        switch expression {
        case .guide:
            return [
                "\(prefix)_portrait_neutral",
                "\(prefix)_avatar_guide",
                "\(prefix)_avatar_neutral"
            ]
        case .subtle where size == .micro || size == .small:
            return [
                "\(prefix)_avatar_icon",
                "\(prefix)_avatar_subtle",
                "\(prefix)_avatar_neutral"
            ]
        default:
            return [
                "\(prefix)_avatar_\(expression.rawValue)",
                "\(prefix)_avatar_neutral"
            ]
        }
    }

    private static func fallbackCandidates(for expression: GuideExpression, size: GuideAvatarSize) -> [String] {
        switch expression {
        case .guide:
            return ["cat_portrait_neutral", "cat_avatar_neutral"]
        case .helpful:
            return ["cat_avatar_sign", "cat_avatar_neutral"]
        case .calm:
            return ["cat_avatar_calm", "cat_avatar_neutral"]
        case .alert:
            return ["cat_avatar_alert", "cat_avatar_neutral"]
        case .curious, .followUp:
            return ["cat_avatar_curious", "cat_avatar_neutral"]
        case .subtle where size == .micro || size == .small:
            return ["cat_avatar_icon", "cat_avatar_neutral"]
        case .neutral, .subtle, .playful:
            return ["cat_avatar_neutral"]
        }
    }

    private static func assetExists(named name: String) -> Bool {
        UIImage(named: name) != nil
    }
}
