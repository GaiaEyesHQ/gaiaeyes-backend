#if canImport(UIKit)
import UIKit

enum ShareBackgroundResolver {
    private static let cache = NSCache<NSURL, UIImage>()

    static func loadImage(for background: ShareCardBackground) async -> UIImage? {
        for url in candidateURLs(for: background) {
            if let cached = cache.object(forKey: url as NSURL) {
                return cached
            }
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
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
        return (background.candidateURLs + defaultCandidateURLs(for: background.style)).filter { url in
            let key = url.absoluteString
            if seen.contains(key) {
                return false
            }
            seen.insert(key)
            return true
        }
    }

    private static func defaultCandidateURLs(for style: ShareBackgroundStyle) -> [URL] {
        switch style {
        case .schumann:
            return [
                MediaPaths.sanitize("social/earthscope/latest/tomsk_latest.png"),
                MediaPaths.sanitize("social/earthscope/latest/cumiana_latest.png"),
                MediaPaths.sanitize("social/earthscope/backgrounds/current_drivers.png"),
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
                MediaPaths.sanitize("social/earthscope/backgrounds/checkin.png"),
                MediaPaths.sanitize("social/earthscope/backgrounds/current_drivers.png"),
                MediaPaths.affectsImage(),
            ].compactMap { $0 }
        case .abstract:
            return [
                MediaPaths.sanitize("social/earthscope/backgrounds/current_drivers.png"),
                MediaPaths.sanitize("social/earthscope/backgrounds/actions.png"),
                MediaPaths.captionImage(),
            ].compactMap { $0 }
        }
    }

    private static func spaceVisualURL(_ relativePath: String) -> URL? {
        URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals/\(relativePath)")
    }
}
#endif
