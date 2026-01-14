import Foundation

struct SpaceVisualsPayload: Codable {
    var ok: Bool?
    var schemaVersion: Int?
    var cdnBase: String?
    var items: [SpaceVisualItem]?
    var images: [SpaceVisualImage]?
    var series: [SpaceVisualSeries]?

    // Back-compat: accept array-root by decoding an array of SpaceVisualImage
    init(from decoder: Decoder) throws {
        let obj = try? decoder.container(keyedBy: CodingKeys.self)
        if let c = obj {
            ok = try? c.decodeIfPresent(Bool.self, forKey: .ok)
            schemaVersion = try? c.decodeIfPresent(Int.self, forKey: .schemaVersion)
            cdnBase = try? c.decodeIfPresent(String.self, forKey: .cdnBase)
            items = try? c.decodeIfPresent([SpaceVisualItem].self, forKey: .items)
            images = try? c.decodeIfPresent([SpaceVisualImage].self, forKey: .images)
            series = try? c.decodeIfPresent([SpaceVisualSeries].self, forKey: .series)
            return
        }
        var single = try decoder.unkeyedContainer()
        var imgs: [SpaceVisualImage] = []
        while !single.isAtEnd {
            if let img = try? single.decode(SpaceVisualImage.self) { imgs.append(img) }
            else { _ = try? single.decode(Discardable.self) }
        }
        ok = true
        images = imgs
    }

    private struct Discardable: Codable {}
}

struct SpaceVisualItem: Codable, Hashable {
    var id: String?
    var title: String?
    var credit: String?
    var url: String?
    var meta: [String: String]?
    var series: [String: [[Double]]]? // map of name -> [[t,v]]
}

struct SpaceVisualImage: Codable, Hashable {
    var key: String?
    var url: String?
    var capturedAt: String?
    var caption: String?
    var source: String?
    var credit: String?
    var featureFlags: [String: Bool]?
    var imagePath: String?
    var thumb: String?
    var overlay: String?
    var mediaType: String?
    var meta: [String: String]?

    enum CodingKeys: String, CodingKey {
        case key, url, capturedAt, caption, source, credit, featureFlags, imagePath, thumb, overlay, mediaType, meta
    }
}

struct SpaceVisualSeries: Codable, Hashable {
    var name: String?
    var label: String?
    var unit: String?
    var latestValue: Double?
}
