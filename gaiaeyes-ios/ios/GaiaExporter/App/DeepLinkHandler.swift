import Foundation

struct DeepLinkHandler {
    static func handle(url: URL) async -> Bool {
        if await AuthManager.shared.handleMagicLink(url) {
            return true
        }
        return false
    }
}
