import Foundation

enum ShareHistoryStore {
    private static let defaultsKey = "gaia.share.history"
    private static let maxEntries = 24

    private static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }

    private static let decoder = JSONDecoder()

    static func recentEntries() -> [ShareHistoryEntry] {
        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
              let entries = try? decoder.decode([ShareHistoryEntry].self, from: data) else {
            return []
        }
        return entries
    }

    static func recordCompletedShare(_ draft: ShareDraft) {
        var entries = recentEntries()
        let entry = ShareHistoryEntry(
            id: UUID().uuidString,
            shareType: draft.shareType,
            surface: draft.surface,
            key: draft.analyticsKey,
            timestamp: isoTimestamp()
        )
        entries.insert(entry, at: 0)
        if entries.count > maxEntries {
            entries = Array(entries.prefix(maxEntries))
        }
        guard let data = try? encoder.encode(entries) else { return }
        UserDefaults.standard.set(data, forKey: defaultsKey)
    }

    private static func isoTimestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }
}
