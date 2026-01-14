import Foundation

struct EnvelopeDiagnosticsFlag: Decodable {
    private let storedBool: Bool?
    private let storedString: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            storedBool = nil
            storedString = nil
        } else if let boolValue = try? container.decode(Bool.self) {
            storedBool = boolValue
            storedString = nil
        } else if let stringValue = try? container.decode(String.self) {
            storedBool = nil
            storedString = stringValue
        } else {
            storedBool = nil
            storedString = nil
        }
    }

    /// Whether the diagnostic entry represents an active condition.
    var isActive: Bool {
        if let storedBool { return storedBool }
        guard let storedString else { return false }
        let trimmed = storedString.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return false }
        switch trimmed.lowercased() {
        case "false", "0", "no", "disabled":
            return false
        case "true", "1", "yes", "enabled":
            return true
        default:
            return true
        }
    }

    /// Provides the textual representation of the diagnostic if available.
    var displayText: String? {
        if let storedString {
            let trimmed = storedString.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        if let storedBool {
            return storedBool ? "true" : "false"
        }
        return nil
    }
}

struct EnvelopeDiagnostics: Decodable {
    let cacheFallback: EnvelopeDiagnosticsFlag?
    let poolTimeout: EnvelopeDiagnosticsFlag?
    let error: EnvelopeDiagnosticsFlag?
}

struct Envelope<T: Decodable>: Decodable {
    let ok: Bool?
    let data: T?
    let error: String?
    let source: String?
    let snapshot: T?
    let cancellations: [String]?
    let diagnostics: EnvelopeDiagnostics?

    /// Returns the primary payload, falling back to a bundled snapshot if necessary.
    var payload: T? {
        data ?? snapshot
    }
}
