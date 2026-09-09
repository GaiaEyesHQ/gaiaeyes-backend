import Foundation

enum MigraineStructuredFollowUpFeature {
    static let launchArgument = "-gaia-enable-structured-migraine-follow-up"
    static let environmentKey = "GAIA_ENABLE_STRUCTURED_MIGRAINE_FOLLOW_UP"

    static var isEnabled: Bool {
        resolve(
            isDebugBuild: _isDebugAssertConfiguration(),
            arguments: ProcessInfo.processInfo.arguments,
            environment: ProcessInfo.processInfo.environment
        )
    }

    static func resolve(
        isDebugBuild: Bool,
        arguments: [String],
        environment: [String: String]
    ) -> Bool {
        guard isDebugBuild else { return false }
        return arguments.contains(launchArgument) || environment[environmentKey] == "1"
    }
}

struct MigraineEpisodeTimestamp: Codable, Hashable {
    let utc: String
    let originalTime: String?
    let timezoneName: String?
    let utcOffsetMinutes: Int?
    let timezoneSource: String

    // Compare the instant, but keep the original spelling and provenance for
    // re-encoding. Pydantic normalizes .000Z / offsets without changing time.
    func matches(_ other: Self) -> Bool {
        guard let left = MigraineFollowUpDraft.parseDate(utc),
              let right = MigraineFollowUpDraft.parseDate(other.utc) else { return false }
        return abs(left.timeIntervalSince(right)) < 0.000001
            && originalTime == other.originalTime
            && timezoneName == other.timezoneName
            && utcOffsetMinutes == other.utcOffsetMinutes
            && timezoneSource == other.timezoneSource
    }

    static func matches(_ left: Self?, _ right: Self?) -> Bool {
        switch (left, right) {
        case (nil, nil): return true
        case let (left?, right?): return left.matches(right)
        default: return false
        }
    }

    private enum EncodingKeys: String, CodingKey {
        case utc
        case originalTime = "original_time"
        case timezoneName = "timezone_name"
        case utcOffsetMinutes = "utc_offset_minutes"
        case timezoneSource = "timezone_source"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: EncodingKeys.self)
        try container.encode(utc, forKey: .utc)
        try container.encodeIfPresent(originalTime, forKey: .originalTime)
        try container.encodeIfPresent(timezoneName, forKey: .timezoneName)
        try container.encodeIfPresent(utcOffsetMinutes, forKey: .utcOffsetMinutes)
        try container.encode(timezoneSource, forKey: .timezoneSource)
    }
}

struct MigraineEarlySign: Codable, Hashable {
    let label: String
    let code: String?
    let reportedAt: MigraineEpisodeTimestamp?
    let notes: String?

    func matches(_ other: Self) -> Bool {
        label == other.label && code == other.code && notes == other.notes
            && MigraineEpisodeTimestamp.matches(reportedAt, other.reportedAt)
    }

    private enum EncodingKeys: String, CodingKey {
        case label
        case code
        case reportedAt = "reported_at"
        case notes
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: EncodingKeys.self)
        try container.encode(label, forKey: .label)
        try container.encodeIfPresent(code, forKey: .code)
        try container.encodeIfPresent(reportedAt, forKey: .reportedAt)
        try container.encodeIfPresent(notes, forKey: .notes)
    }
}

struct MigraineEpisodeContext: Codable, Hashable {
    let kind: String
    let label: String
    let code: String?
    let observedAt: MigraineEpisodeTimestamp?
    let source: String
    let notes: String?

    func matches(_ other: Self) -> Bool {
        kind == other.kind && label == other.label && code == other.code
            && source == other.source && notes == other.notes
            && MigraineEpisodeTimestamp.matches(observedAt, other.observedAt)
    }

    private enum EncodingKeys: String, CodingKey {
        case kind
        case label
        case code
        case observedAt = "observed_at"
        case source
        case notes
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: EncodingKeys.self)
        try container.encode(kind, forKey: .kind)
        try container.encode(label, forKey: .label)
        try container.encodeIfPresent(code, forKey: .code)
        try container.encodeIfPresent(observedAt, forKey: .observedAt)
        try container.encode(source, forKey: .source)
        try container.encodeIfPresent(notes, forKey: .notes)
    }
}

struct MigraineMedicineTaken: Codable, Hashable {
    let name: String
    let takenAt: MigraineEpisodeTimestamp
    let doseAmount: Decimal?
    let doseUnit: String?
    let reportedRelief: String?
    let reliefReportedAt: MigraineEpisodeTimestamp?
    let notes: String?

    func matches(_ other: Self) -> Bool {
        name == other.name && takenAt.matches(other.takenAt)
            && doseAmount == other.doseAmount && doseUnit == other.doseUnit
            && reportedRelief == other.reportedRelief && notes == other.notes
            && MigraineEpisodeTimestamp.matches(reliefReportedAt, other.reliefReportedAt)
    }

    private enum EncodingKeys: String, CodingKey {
        case name
        case takenAt = "taken_at"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case reportedRelief = "reported_relief"
        case reliefReportedAt = "relief_reported_at"
        case notes
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: EncodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(takenAt, forKey: .takenAt)
        try container.encodeIfPresent(doseAmount, forKey: .doseAmount)
        try container.encodeIfPresent(doseUnit, forKey: .doseUnit)
        try container.encodeIfPresent(reportedRelief, forKey: .reportedRelief)
        try container.encodeIfPresent(reliefReportedAt, forKey: .reliefReportedAt)
        try container.encodeIfPresent(notes, forKey: .notes)
    }
}

extension MigraineMedicineTaken {
    private enum DecodingKeys: String, CodingKey {
        case name, takenAt, doseAmount, doseUnit, reportedRelief, reliefReportedAt, notes
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DecodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        takenAt = try container.decode(MigraineEpisodeTimestamp.self, forKey: .takenAt)
        if let text = try? container.decode(String.self, forKey: .doseAmount) {
            guard text.range(of: #"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"#, options: .regularExpression) != nil,
                  let value = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")) else {
                throw DecodingError.dataCorruptedError(forKey: .doseAmount, in: container, debugDescription: "Invalid decimal dose")
            }
            doseAmount = value
        } else {
            doseAmount = try container.decodeIfPresent(Decimal.self, forKey: .doseAmount)
        }
        doseUnit = try container.decodeIfPresent(String.self, forKey: .doseUnit)
        reportedRelief = try container.decodeIfPresent(String.self, forKey: .reportedRelief)
        reliefReportedAt = try container.decodeIfPresent(MigraineEpisodeTimestamp.self, forKey: .reliefReportedAt)
        notes = try container.decodeIfPresent(String.self, forKey: .notes)
    }
}

struct MigraineEpisodeProvenance: Codable, Hashable {
    let sourceType: String
    let sourcePlatform: String
    let sourceProvider: String?
    let externalEventId: String?
    let sourceFileHash: String?
    let importRunId: String?
    let rawRowRef: String?
    let mappingVersion: String?
}

struct MigraineEpisodeLifecycle: Codable, Hashable {
    let revision: Int
    let createdAt: String
    let updatedAt: String
    let deletedAt: String?
    let deletionScope: String?
}

struct MigraineEpisode: Codable, Hashable {
    let schemaVersion: String
    let episodeId: String
    let symptomEventId: String?
    let symptomCode: String
    let state: String
    let start: MigraineEpisodeTimestamp
    let end: MigraineEpisodeTimestamp?
    let severity: Int?
    let earlySigns: [MigraineEarlySign]
    let contexts: [MigraineEpisodeContext]
    let medicines: [MigraineMedicineTaken]
    let notes: String?
    let provenance: MigraineEpisodeProvenance
    let lifecycle: MigraineEpisodeLifecycle
}

struct MigraineEpisodeDetail: Codable, Hashable {
    let revision: Int
    let changed: Bool
    let episode: MigraineEpisode
}

enum MigraineTextChange: Hashable {
    case retain
    case set(String)
    case clear
}

struct MigraineStructuredEdit: Encodable, Hashable {
    let expectedRevision: Int
    let earlySigns: [MigraineEarlySign]?
    let contexts: [MigraineEpisodeContext]?
    let medicines: [MigraineMedicineTaken]?
    let notes: MigraineTextChange

    private enum CodingKeys: String, CodingKey {
        case expectedRevision = "expected_revision"
        case earlySigns = "early_signs"
        case contexts
        case medicines
        case notes
    }

    var hasChanges: Bool {
        earlySigns != nil || contexts != nil || medicines != nil || notes != .retain
    }

    var followUpNoteText: String? {
        guard case .set(let value) = notes else { return nil }
        return value
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(expectedRevision, forKey: .expectedRevision)
        try container.encodeIfPresent(earlySigns, forKey: .earlySigns)
        try container.encodeIfPresent(contexts, forKey: .contexts)
        try container.encodeIfPresent(medicines, forKey: .medicines)
        switch notes {
        case .retain:
            break
        case .set(let value):
            try container.encode(value, forKey: .notes)
        case .clear:
            try container.encodeNil(forKey: .notes)
        }
    }

    func matches(_ detail: MigraineEpisodeDetail) -> Bool {
        guard detail.revision >= expectedRevision else { return false }
        if let earlySigns,
           (earlySigns.count != detail.episode.earlySigns.count
            || !zip(earlySigns, detail.episode.earlySigns).allSatisfy({ $0.matches($1) })) { return false }
        if let contexts,
           (contexts.count != detail.episode.contexts.count
            || !zip(contexts, detail.episode.contexts).allSatisfy({ $0.matches($1) })) { return false }
        if let medicines,
           (medicines.count != detail.episode.medicines.count
            || !zip(medicines, detail.episode.medicines).allSatisfy({ $0.matches($1) })) { return false }
        switch notes {
        case .retain:
            break
        case .set(let value):
            if detail.episode.notes != value { return false }
        case .clear:
            if detail.episode.notes != nil { return false }
        }
        return true
    }
}

enum MigraineMedicineChoice: String, CaseIterable, Identifiable {
    case retain
    case taken
    case add
    case removeFirst
    case none

    var id: String { rawValue }

    var label: String {
        switch self {
        case .retain: return "Not adding medicine"
        case .taken: return "I took medicine"
        case .add: return "Add another medicine"
        case .removeFirst: return "Remove first saved medicine"
        case .none: return "No medicine taken"
        }
    }
}

enum MigraineReliefChoice: String, CaseIterable, Identifiable {
    case unknown
    case none
    case aLittle = "a_little"
    case some
    case aLot = "a_lot"
    case complete

    var id: String { rawValue }

    var label: String {
        switch self {
        case .unknown: return "Not sure yet"
        case .none: return "No relief"
        case .aLittle: return "A little"
        case .some: return "Some"
        case .aLot: return "A lot"
        case .complete: return "Complete"
        }
    }
}

enum MigraineDraftError: Error, LocalizedError {
    case accountChanged
    case medicineNameRequired
    case incompleteDose

    var errorDescription: String? {
        switch self {
        case .accountChanged:
            return "Your signed-in account changed. Close this form and open it again before saving."
        case .medicineNameRequired:
            return "Add the medicine name or choose No medicine taken."
        case .incompleteDose:
            return "Enter both a dose amount and unit, or leave both blank."
        }
    }
}

struct MigraineFollowUpDraft: Hashable {
    let accountScope: String
    let promptId: String
    let episodeId: String
    let responseTimestamp: Date

    private(set) var expectedRevision: Int = 0
    private(set) var originalEarlySigns: [MigraineEarlySign] = []
    private(set) var originalMedicines: [MigraineMedicineTaken] = []
    private(set) var originalNotes: String?

    var earlySignsText: String = ""
    var medicineChoice: MigraineMedicineChoice = .retain
    var medicineName: String = ""
    var medicineTakenAt: Date
    var doseAmountText: String = ""
    var doseUnit: String = ""
    var reliefChoice: MigraineReliefChoice = .unknown
    var medicineNotesText: String = ""
    var noteText: String = ""

    init(accountScope: String, promptId: String, episodeId: String, responseTimestamp: Date = Date()) {
        self.accountScope = accountScope
        self.promptId = promptId
        self.episodeId = episodeId
        self.responseTimestamp = responseTimestamp
        self.medicineTakenAt = responseTimestamp
    }

    mutating func apply(_ detail: MigraineEpisodeDetail, forAccountScope currentScope: String) throws {
        guard accountScope == currentScope, episodeId == detail.episode.episodeId else {
            throw MigraineDraftError.accountChanged
        }
        expectedRevision = detail.revision
        originalEarlySigns = detail.episode.earlySigns
        originalMedicines = detail.episode.medicines
        originalNotes = detail.episode.notes
        earlySignsText = detail.episode.earlySigns.map(\.label).joined(separator: ", ")
        noteText = detail.episode.notes ?? ""

        resetMedicineFields()

        if let medicine = detail.episode.medicines.first {
            medicineChoice = .taken
            medicineName = medicine.name
            medicineTakenAt = Self.parseDate(medicine.takenAt.utc) ?? responseTimestamp
            if let amount = medicine.doseAmount {
                doseAmountText = NSDecimalNumber(decimal: amount).stringValue
            }
            doseUnit = medicine.doseUnit ?? ""
            reliefChoice = MigraineReliefChoice(rawValue: medicine.reportedRelief ?? "") ?? .unknown
            medicineNotesText = medicine.notes ?? ""
        }
    }

    mutating func chooseMedicine(_ choice: MigraineMedicineChoice) {
        if choice == .add && medicineChoice != .add {
            resetMedicineFields()
        }
        medicineChoice = choice
    }

    private mutating func resetMedicineFields() {
        medicineChoice = .retain
        medicineName = ""
        medicineTakenAt = responseTimestamp
        doseAmountText = ""
        doseUnit = ""
        reliefChoice = .unknown
        medicineNotesText = ""
    }

    func makeStructuredEdit(currentAccountScope: String) throws -> MigraineStructuredEdit? {
        guard accountScope == currentAccountScope else { throw MigraineDraftError.accountChanged }

        let labels = earlySignsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let originalLabels = originalEarlySigns.map(\.label)
        var remainingSigns = originalEarlySigns
        let earlySigns: [MigraineEarlySign]? = labels == originalLabels ? nil : labels.map { label in
            // Match each occurrence once: untouched entries retain every field,
            // including duplicate-label entries with distinct provenance.
            if let index = remainingSigns.firstIndex(where: { $0.label == label }) {
                return remainingSigns.remove(at: index)
            }
            return MigraineEarlySign(label: label, code: nil, reportedAt: Self.timestamp(responseTimestamp), notes: nil)
        }

        let medicines: [MigraineMedicineTaken]?
        switch medicineChoice {
        case .retain:
            medicines = nil
        case .none:
            medicines = []
        case .removeFirst:
            medicines = originalMedicines.isEmpty ? nil : Array(originalMedicines.dropFirst())
        case .taken, .add:
            let name = medicineName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { throw MigraineDraftError.medicineNameRequired }
            let amountText = doseAmountText.trimmingCharacters(in: .whitespacesAndNewlines)
            let unit = doseUnit.trimmingCharacters(in: .whitespacesAndNewlines)
            guard amountText.isEmpty == unit.isEmpty else { throw MigraineDraftError.incompleteDose }
            let amount = amountText.isEmpty ? nil : Decimal(string: amountText, locale: Locale(identifier: "en_US_POSIX"))
            if !amountText.isEmpty && (amount == nil || amount! <= 0) { throw MigraineDraftError.incompleteDose }
            let original = medicineChoice == .taken ? originalMedicines.first : nil
            let originalDate = original.flatMap { Self.parseDate($0.takenAt.utc) }
            let originalReliefChoice = MigraineReliefChoice(rawValue: original?.reportedRelief ?? "") ?? .unknown
            let reliefUnchanged = original != nil && reliefChoice == originalReliefChoice
            let relief = reliefUnchanged ? original?.reportedRelief : reliefChoice.rawValue
            let note = medicineNotesText.trimmingCharacters(in: .whitespacesAndNewlines)
            let candidate = MigraineMedicineTaken(
                name: name,
                takenAt: originalDate == medicineTakenAt ? original!.takenAt : Self.timestamp(medicineTakenAt),
                doseAmount: amount,
                doseUnit: unit.isEmpty ? nil : unit,
                reportedRelief: relief,
                reliefReportedAt: reliefUnchanged ? original?.reliefReportedAt : Self.timestamp(responseTimestamp),
                notes: note == (original?.notes ?? "") ? original?.notes : (note.isEmpty ? nil : note)
            )
            if candidate == original {
                medicines = nil
            } else if medicineChoice == .add || originalMedicines.isEmpty {
                medicines = originalMedicines + [candidate]
            } else {
                medicines = [candidate] + originalMedicines.dropFirst()
            }
        }

        let trimmedNote = noteText.trimmingCharacters(in: .whitespacesAndNewlines)
        let originalTrimmed = originalNotes?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let notes: MigraineTextChange
        if trimmedNote == originalTrimmed {
            notes = .retain
        } else if trimmedNote.isEmpty {
            notes = .clear
        } else {
            notes = .set(trimmedNote)
        }

        let edit = MigraineStructuredEdit(
            expectedRevision: expectedRevision,
            earlySigns: earlySigns,
            contexts: nil,
            medicines: medicines,
            notes: notes
        )
        return edit.hasChanges ? edit : nil
    }

    static func timestamp(_ date: Date) -> MigraineEpisodeTimestamp {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let zone = TimeZone.current
        return MigraineEpisodeTimestamp(
            utc: formatter.string(from: date),
            originalTime: nil,
            timezoneName: zone.identifier,
            utcOffsetMinutes: zone.secondsFromGMT(for: date) / 60,
            timezoneSource: "device"
        )
    }

    static func parseDate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
}
