import Foundation

struct DeepLinkHandler {
    static func handle(url: URL) async -> Bool {
        if await AuthManager.shared.handleMagicLink(url) {
            return true
        }
        if let route = GaiaPushRoute(url: url) {
            NotificationCenter.default.post(name: .gaiaPushDeepLinkReceived, object: nil, userInfo: route.userInfo)
            return true
        }
        return false
    }
}
