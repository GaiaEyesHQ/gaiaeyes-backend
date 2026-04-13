#if canImport(UIKit)
import UIKit

enum ShareBackgroundResolver {
    private static let cache = NSCache<NSURL, UIImage>()
    private static let themedCandidateLimit = 18
    private static let candidateTimeout: TimeInterval = 1.2

    static func loadImage(for background: ShareCardBackground) async -> UIImage? {
        for url in candidateURLs(for: background) {
            if let cached = cache.object(forKey: url as NSURL) {
                return cached
            }
            do {
                var request = URLRequest(url: url)
                request.timeoutInterval = candidateTimeout
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let image = UIImage(data: data) else {
                    continue
                }
                cache.setObject(image, forKey: url as NSURL)
                return image
            } catch {
                continue
            }
        }
        return nil
    }

    private static func candidateURLs(for background: ShareCardBackground) -> [URL] {
        var seen = Set<String>()
        let themed = Array(themedCandidateURLs(for: background).prefix(themedCandidateLimit))
        return (background.candidateURLs + themed + defaultCandidateURLs(for: background.style)).filter { url in
            let key = url.absoluteString
            if seen.contains(key) {
                return false
            }
            seen.insert(key)
            return true
        }
    }

    private static func themedCandidateURLs(for background: ShareCardBackground) -> [URL] {
        let folders = [
            "social/share/backgrounds",
            "backgrounds/share",
            "backgrounds/square",
        ]
        let exts = ["jpg", "png", "jpeg", "webp"]
        let themeKeys = background.themeKeys
            .map(normalizedThemeKey)
            .filter { !$0.isEmpty }

        var urls: [URL] = []
        for folder in folders {
            for ext in exts {
                for key in themeKeys.prefix(3) {
                    let stems = uniquePreservingOrder([
                        key,
                        key.replacingOccurrences(of: "_", with: "-"),
                    ]).filter { !$0.isEmpty }
                    for stem in stems {
                        if let url = MediaPaths.storageURL("\(folder)/\(stem).\(ext)") {
                            urls.append(url)
                        }
                    }
                }
            }
        }

        return urls
    }

    private static func defaultCandidateURLs(for style: ShareBackgroundStyle) -> [URL] {
        switch style {
        case .schumann:
            return [
                MediaPaths.storageURL("social/earthscope/backgrounds/current_drivers.png"),
                MediaPaths.captionImage(),
            ].compactMap { $0 }
        case .solar:
            return [
                spaceVisualURL("nasa/aia_304/latest.jpg"),
                spaceVisualURL("nasa/geospace_3h/latest.jpg"),
                MediaPaths.statsImage(),
                MediaPaths.playbookImage(),
            ].compactMap { $0 }
        case .cme:
            return [
                spaceVisualURL("nasa/lasco_c2/latest.jpg"),
                spaceVisualURL("nasa/lasco_c3/latest.jpg"),
                MediaPaths.playbookImage(),
            ].compactMap { $0 }
        case .atmospheric:
            return [
                MediaPaths.storageURL("social/earthscope/backgrounds/checkin.png"),
                MediaPaths.storageURL("social/earthscope/backgrounds/current_drivers.png"),
                MediaPaths.affectsImage(),
            ].compactMap { $0 }
        case .abstract:
            return [
                MediaPaths.storageURL("social/earthscope/backgrounds/current_drivers.png"),
                MediaPaths.storageURL("social/earthscope/backgrounds/actions.png"),
                MediaPaths.captionImage(),
            ].compactMap { $0 }
        }
    }

    private static func spaceVisualURL(_ relativePath: String) -> URL? {
        MediaPaths.storageURL(relativePath)
    }

    private static func normalizedThemeKey(_ raw: String) -> String {
        raw.lowercased().map { character -> Character in
            if character.isLetter || character.isNumber {
                return character
            }
            return "_"
        }
        .reduce(into: "") { partial, character in
            if character == "_" {
                if partial.last != "_" {
                    partial.append(character)
                }
            } else {
                partial.append(character)
            }
        }
        .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
    }

    private static func uniquePreservingOrder(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }
}
#endif
