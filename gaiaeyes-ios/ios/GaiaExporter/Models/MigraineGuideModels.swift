import Foundation

private func migraineGuideDecoder() -> JSONDecoder {
    let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
    return decoder
}

/// Choices are draft input. They become observations only after an acknowledged save.
enum MigraineGuideStep: String, CaseIterable, Codable, Identifiable {
    case timing, severity, symptoms, location, medicines, relief, context, review
    var id: String { rawValue }
    var title: String {
        switch self {
        case .timing: return "When did it start?"
        case .severity: return "How severe is it now?"
        case .symptoms: return "What are you noticing?"
        case .location: return "Where is the pain?"
        case .medicines: return "Medicines taken"
        case .relief: return "Other relief tried"
        case .context: return "Anything else to note?"
        case .review: return "Review your migraine"
        }
    }
    var symbol: String {
        switch self {
        case .timing: return "clock"
        case .severity: return "slider.horizontal.3"
        case .symptoms: return "person.crop.circle"
        case .location: return "person.crop.square"
        case .medicines: return "pills"
        case .relief: return "leaf"
        case .context: return "note.text"
        case .review: return "checkmark.circle"
        }
    }
    var choices: [String] {
        switch self {
        case .symptoms: return ["Throbbing pain", "Nausea", "Light sensitivity", "Sound sensitivity", "Fatigue", "Visual changes"]
        case .location: return ["Your left temple", "Your right temple", "Forehead", "Behind your left eye", "Behind your right eye", "Back of head", "Neck", "Both sides"]
        case .relief: return ["Rest", "Dark room", "Sleep", "Cold pack", "Water", "Quiet space"]
        case .context: return ["Sleep change", "Missed meal", "Stress", "Strong smell", "Travel", "Weather change"]
        default: return []
        }
    }
}

struct MigraineGuideMedicine: Codable, Identifiable, Equatable {
    var id = UUID()
    var name = ""
    var takenAt: Date?
    var dose = ""
    var unit = ""
    var relief = ""
    var notes = ""
    var originalData: Data?

    var original: MigraineMedicineTaken? {
        originalData.flatMap { try? migraineGuideDecoder().decode(MigraineMedicineTaken.self, from: $0) }
    }
    init() {}
    init(_ saved: MigraineMedicineTaken) {
        name = saved.name; takenAt = MigraineFollowUpDraft.parseDate(saved.takenAt.utc)
        dose = saved.doseAmount.map { NSDecimalNumber(decimal: $0).stringValue } ?? ""
        unit = saved.doseUnit ?? ""; relief = saved.reportedRelief ?? ""; notes = saved.notes ?? ""
        originalData = try? JSONEncoder().encode(saved)
    }
    func value(reportedAt: Date) throws -> MigraineMedicineTaken {
        guard let takenAt else { throw MigraineGuideError.medicineTimeRequired }
        var row = MigraineMedicineDraftRow(original: original, date: takenAt)
        row.name = name; row.takenAt = takenAt; row.doseAmountText = dose; row.doseUnit = unit
        row.relief = MigraineReliefChoice(rawValue: relief) ?? .notReported; row.notes = notes
        return try row.value(responseTimestamp: reportedAt)
    }
}

struct MigraineGuideDraft: Codable, Equatable {
    var id = UUID()
    var episodeID: String?
    var onset: Date?
    var severity: Int?
    var severityChanged = false
    var symptoms: [String] = []
    var earlySigns: [String] = []
    var locations: [String] = []
    var medicines: [MigraineGuideMedicine] = []
    var reliefs: [String] = []
    var contexts: [String] = []
    var notes = ""
    var step: MigraineGuideStep = .timing
    var changed: Set<String> = []
    var baseData: Data?
    var pendingCreation = false
    var pendingDetails = false
    var pendingEditData: Data?
    var pendingSeverity = false
    var reportedAt: Date?

    var base: MigraineEpisodeDetail? {
        baseData.flatMap { try? migraineGuideDecoder().decode(MigraineEpisodeDetail.self, from: $0) }
    }
    var inputsLocked: Bool { pendingCreation || pendingDetails || pendingSeverity }
    mutating func load(_ detail: MigraineEpisodeDetail) throws {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        baseData = try encoder.encode(detail); episodeID = detail.episode.episodeId
        onset = MigraineFollowUpDraft.parseDate(detail.episode.start.utc)
        severity = nil // A previous severity is context, never a fresh answer.
        symptoms = (detail.episode.symptoms ?? []).map(\.label)
        earlySigns = detail.episode.earlySigns.map(\.label)
        locations = (detail.episode.painLocations ?? []).map(\.label)
        medicines = detail.episode.medicines.map(MigraineGuideMedicine.init)
        reliefs = (detail.episode.reliefs ?? []).map(\.label)
        contexts = detail.episode.contexts.map(\.label); notes = detail.episode.notes ?? ""
        changed = []; severityChanged = false; pendingCreation = false; pendingDetails = false; pendingEditData = nil; pendingSeverity = false; reportedAt = nil
    }
    func edit() throws -> MigraineStructuredEdit {
        if let pendingEditData { return try migraineGuideDecoder().decode(MigraineStructuredEdit.self, from: pendingEditData) }
        guard let base, let reportedAt else { throw MigraineSaveError.invalidResponse }
        func observations(_ labels: [String], original: [MigraineEarlySign]) -> [MigraineEarlySign] {
            labels.map { label in original.first(where: { $0.label == label })
                ?? MigraineEarlySign(label: label, code: nil, reportedAt: MigraineFollowUpDraft.timestamp(reportedAt), notes: nil) }
        }
        let episode = base.episode
        return try MigraineStructuredEdit(expectedRevision: base.revision,
            earlySigns: changed.contains("earlySigns") ? observations(earlySigns, original: episode.earlySigns) : nil,
            contexts: changed.contains("context") ? contexts.map { label in
                episode.contexts.first(where: { $0.label == label }) ?? MigraineEpisodeContext(kind: "context", label: label,
                    code: nil, observedAt: nil, source: "user_reported", notes: nil)
            } : nil,
            medicines: changed.contains("medicines") ? medicines.map { try $0.value(reportedAt: reportedAt) } : nil,
            notes: changed.contains("notes") ? (notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? .clear : .set(notes.trimmingCharacters(in: .whitespacesAndNewlines))) : .retain,
            symptoms: changed.contains("symptoms") ? observations(symptoms, original: episode.symptoms ?? []) : nil,
            painLocations: changed.contains("location") ? observations(locations, original: episode.painLocations ?? []) : nil,
            reliefs: changed.contains("relief") ? observations(reliefs, original: episode.reliefs ?? []) : nil)
    }
}

enum MigraineGuideError: Error, LocalizedError {
    case onsetRequired, medicineTimeRequired, signedOut
    var errorDescription: String? {
        switch self {
        case .onsetRequired: return "Choose when this migraine started. No start time has been assumed."
        case .medicineTimeRequired: return "Choose when each medicine was taken, or remove the unfinished entry."
        case .signedOut: return "Sign in before saving this migraine. Your draft stays on this device."
        }
    }
}

/// Account-scoped drafts and explicitly pinned names are not confirmed episode data.
/// No doses, event times or selected observations are reused as defaults.
@MainActor
enum MigraineGuideStorage {
    static func key(scope: String, episodeID: String?) -> String { "gaia.migraine.guide.\(scope).\(episodeID ?? "new")" }
    static func draft(scope: String, episodeID: String?, defaults: UserDefaults = .standard) -> MigraineGuideDraft? {
        defaults.data(forKey: key(scope: scope, episodeID: episodeID)).flatMap { try? JSONDecoder().decode(MigraineGuideDraft.self, from: $0) }
    }
    static func save(_ draft: MigraineGuideDraft, scope: String, defaults: UserDefaults = .standard) throws {
        defaults.set(try JSONEncoder().encode(draft), forKey: key(scope: scope, episodeID: draft.episodeID))
    }
    static func remove(scope: String, episodeID: String?, defaults: UserDefaults = .standard) {
        defaults.removeObject(forKey: key(scope: scope, episodeID: episodeID))
    }
    static func favorites(scope: String, category: String, defaults: UserDefaults = .standard) -> [String] {
        defaults.stringArray(forKey: "gaia.migraine.favorites.\(scope).\(category)") ?? []
    }
    static func toggleFavorite(_ label: String, scope: String, category: String, defaults: UserDefaults = .standard) {
        var values = favorites(scope: scope, category: category, defaults: defaults)
        if values.contains(label) { values.removeAll { $0 == label } } else { values.append(label) }
        defaults.set(values, forKey: "gaia.migraine.favorites.\(scope).\(category)")
    }
}
