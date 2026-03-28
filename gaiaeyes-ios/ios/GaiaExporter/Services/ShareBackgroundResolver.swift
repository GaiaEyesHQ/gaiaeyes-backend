#if canImport(UIKit)
import UIKit

enum ShareBackgroundResolver {
    private static let cache = NSCache<NSURL, UIImage>()

    static func loadImage(for background: ShareCardBackground) async -> UIImage? {
        for url in background.candidateURLs {
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
}
#endif
