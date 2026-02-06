import Foundation

enum MediaBase {
    static let pages = URL(string: "https://gaiaeyeshq.github.io/gaiaeyes-media")!
    static let cdn = URL(string: "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main")!
}

enum MediaPaths {
    private static let legacyReplacements: [String: String] = [
        "gennwu.github.io/gaiaeyes-media": "gaiaeyeshq.github.io/gaiaeyes-media",
        
        "cdn.jsdelivr.net/gh/gennwu/gaiaeyes-media@main": "cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main",
        "cdn.jsdelivr.net/gh/gennwu/gaiaeyes-media": "cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main",
        "cdn.jsdelivr.net/gh/GaiaEyesHQ/backgrounds": "cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/backgrounds",
        "cdn.jsdelivr.net/gh/gennwu/backgrounds": "cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/backgrounds"
    ]

    static func earthscopeDailyJSON() -> URL {
        MediaBase.cdn
            .appendingPathComponent("data")
            .appendingPathComponent("earthscope_daily.json")
    }

    static func spaceWeatherJSON() -> URL {
        MediaBase.cdn
            .appendingPathComponent("data")
            .appendingPathComponent("space_weather.json")
    }

    static func pulseJSON() -> URL {
        MediaBase.cdn
            .appendingPathComponent("data")
            .appendingPathComponent("pulse.json")
    }

    static func captionImage() -> URL {
        MediaBase.cdn
            .appendingPathComponent("social")
            .appendingPathComponent("earthscope")
            .appendingPathComponent("latest")
            .appendingPathComponent("daily_caption.jpg")
    }

    static func statsImage() -> URL {
        MediaBase.cdn
            .appendingPathComponent("social")
            .appendingPathComponent("earthscope")
            .appendingPathComponent("latest")
            .appendingPathComponent("daily_stats.jpg")
    }

    static func affectsImage() -> URL {
        MediaBase.cdn
            .appendingPathComponent("social")
            .appendingPathComponent("earthscope")
            .appendingPathComponent("latest")
            .appendingPathComponent("daily_affects.jpg")
    }

    static func playbookImage() -> URL {
        MediaBase.cdn
            .appendingPathComponent("social")
            .appendingPathComponent("earthscope")
            .appendingPathComponent("latest")
            .appendingPathComponent("daily_playbook.jpg")
    }

    static func sanitize(_ url: URL) -> URL {
        if let scheme = url.scheme, !scheme.isEmpty {
            var absolute = url.absoluteString
            for (legacy, updated) in legacyReplacements {
                absolute = absolute.replacingOccurrences(of: legacy, with: updated)
            }
            // ----- Idempotent jsDelivr normalization -----
            // Collapse duplicated @main tokens
            while absolute.contains("@main@main") {
                absolute = absolute.replacingOccurrences(of: "@main@main", with: "@main")
            }
            // Ensure exactly one @main immediately after the repo name
            let repoNeedle = "cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media"
            if let range = absolute.range(of: repoNeedle) {
                let insertIndex = range.upperBound
                if insertIndex == absolute.endIndex {
                    absolute.append("@main")
                } else if absolute[insertIndex] != "@" {
                    absolute.insert(contentsOf: "@main", at: insertIndex)
                }
            }
            // One more collapse pass (in case earlier logic produced adjacent tokens)
            while absolute.contains("@main@main") {
                absolute = absolute.replacingOccurrences(of: "@main@main", with: "@main")
            }
            return URL(string: absolute) ?? url
        }
        // Treat bare/relative URLs as relative to the CDN base.
        let relative = url.relativeString
        return sanitize(relative) ?? url
    }

    static func sanitize(_ raw: String?) -> URL? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        if let absolute = URL(string: trimmed), let scheme = absolute.scheme, !scheme.isEmpty {
            return sanitize(absolute)
        }

        // Resolve relative paths (with or without a leading slash) against the CDN base.
        let cleaned = trimmed.hasPrefix("/") ? String(trimmed.dropFirst()) : trimmed
        guard let resolved = URL(string: cleaned, relativeTo: MediaBase.cdn) else { return nil }
        return sanitize(resolved.absoluteURL)
    }
}
