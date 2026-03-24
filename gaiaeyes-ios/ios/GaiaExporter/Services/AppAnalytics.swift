import Foundation

enum AppAnalytics {
    static func track(_ name: String, properties: [String: String] = [:]) {
        let normalized = properties
            .map { key, value in "\(key)=\(value)" }
            .sorted()
            .joined(separator: " ")
        if normalized.isEmpty {
            appLog("[ANALYTICS] \(name)")
        } else {
            appLog("[ANALYTICS] \(name) \(normalized)")
        }
    }
}
