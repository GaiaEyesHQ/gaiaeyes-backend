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
        if let earlySigns, detail.episode.earlySigns != earlySigns { return false }
        if let contexts, detail.episode.contexts != contexts { return false }
        if let medicines, detail.episode.medicines != medicines { return false }
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
    case none

    var id: String { rawValue }

    var label: String {
        switch self {
        case .retain: return "Not adding medicine"
        case .taken: return "I took medicine"
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

        if let medicine = detail.episode.medicines.first {
            medicineChoice = .taken
            medicineName = medicine.name
            medicineTakenAt = Self.parseDate(medicine.takenAt.utc) ?? responseTimestamp
            if let amount = medicine.doseAmount {
                doseAmountText = NSDecimalNumber(decimal: amount).stringValue
            }
            doseUnit = medicine.doseUnit ?? ""
            reliefChoice = MigraineReliefChoice(rawValue: medicine.reportedRelief ?? "") ?? .unknown
        }
    }

    func makeStructuredEdit(currentAccountScope: String) throws -> MigraineStructuredEdit? {
        guard accountScope == currentAccountScope else { throw MigraineDraftError.accountChanged }

        let labels = earlySignsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let originalLabels = originalEarlySigns.map(\.label)
        let earlySigns: [MigraineEarlySign]? = labels == originalLabels ? nil : labels.map {
            MigraineEarlySign(
                label: $0,
                code: nil,
                reportedAt: Self.timestamp(responseTimestamp),
                notes: nil
            )
        }

        let medicines: [MigraineMedicineTaken]?
        switch medicineChoice {
        case .retain:
            medicines = nil
        case .none:
            medicines = []
        case .taken:
            let name = medicineName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { throw MigraineDraftError.medicineNameRequired }
            let amountText = doseAmountText.trimmingCharacters(in: .whitespacesAndNewlines)
            let unit = doseUnit.trimmingCharacters(in: .whitespacesAndNewlines)
            guard amountText.isEmpty == unit.isEmpty else { throw MigraineDraftError.incompleteDose }
            let amount = amountText.isEmpty ? nil : Decimal(string: amountText)
            if !amountText.isEmpty && amount == nil { throw MigraineDraftError.incompleteDose }
            let relief = reliefChoice == .unknown ? nil : reliefChoice.rawValue
            let candidate = [
                MigraineMedicineTaken(
                    name: name,
                    takenAt: Self.timestamp(medicineTakenAt),
                    doseAmount: amount,
                    doseUnit: unit.isEmpty ? nil : unit,
                    reportedRelief: relief,
                    reliefReportedAt: relief == nil ? nil : Self.timestamp(responseTimestamp),
                    notes: nil
                )
            ]
            let original = originalMedicines.count == 1 ? originalMedicines[0] : nil
            let originalDate = original.flatMap { Self.parseDate($0.takenAt.utc) }
            let medicineIsUnchanged = original != nil
                && original?.name == name
                && originalDate.map { abs($0.timeIntervalSince(medicineTakenAt)) < 0.5 } == true
                && original?.doseAmount == amount
                && original?.doseUnit == (unit.isEmpty ? nil : unit)
                && original?.reportedRelief == relief
            medicines = medicineIsUnchanged ? nil : candidate
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
