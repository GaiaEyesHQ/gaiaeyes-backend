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
        // Only the immediately completed revision can be our save/replay.
        // This content check alone never proves that a follow-up prompt answered.
        guard detail.revision == expectedRevision + 1 else { return false }
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
    case removeSelected
    case none

    var id: String { rawValue }

    var label: String {
        switch self {
        case .retain: return "Not adding medicine"
        case .taken: return "I took medicine"
        case .add: return "Add another medicine"
        case .removeSelected: return "Remove selected medicine"
        case .none: return "No medicine taken"
        }
    }
}

enum MigraineReliefChoice: String, CaseIterable, Identifiable {
    case notReported = ""
    case unknown
    case none
    case aLittle = "a_little"
    case some
    case aLot = "a_lot"
    case complete

    var id: String { rawValue }

    var label: String {
        switch self {
        case .notReported: return "Not recorded"
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
    case medicineListConflict

    var errorDescription: String? {
        switch self {
        case .accountChanged:
            return "Your signed-in account changed. Close this form and open it again before saving."
        case .medicineNameRequired:
            return "Add a name for each medicine entry, or remove the unfinished entry."
        case .incompleteDose:
            return "Enter both a dose amount and unit, or leave both blank."
        case .medicineListConflict:
            return "A medicine you edited or removed also changed elsewhere. Your draft is kept; review the saved version before deciding which entries to keep."
        }
    }
}

// Identity exists only in this draft. The API still stores the ordered array.
struct MigraineMedicineDraftRow: Identifiable, Hashable {
    let id: UUID
    var originalIndex: Int?
    let original: MigraineMedicineTaken?
    var name: String
    var takenAt: Date
    var doseAmountText: String
    var doseUnit: String
    var relief: MigraineReliefChoice
    var notes: String
    private let initialDate: Date

    init(id: UUID = UUID(), originalIndex: Int? = nil, original: MigraineMedicineTaken? = nil, date: Date) {
        self.id = id; self.originalIndex = originalIndex; self.original = original
        name = original?.name ?? ""
        initialDate = original.flatMap { MigraineFollowUpDraft.parseDate($0.takenAt.utc) } ?? date
        takenAt = initialDate
        doseAmountText = original?.doseAmount.map { NSDecimalNumber(decimal: $0).stringValue } ?? ""
        doseUnit = original?.doseUnit ?? ""
        relief = original?.reportedRelief.flatMap(MigraineReliefChoice.init(rawValue:)) ?? .notReported
        notes = original?.notes ?? ""
    }

    var hasFieldChanges: Bool {
        guard let original else { return true }
        return name != original.name || takenAt != initialDate
            || doseAmountText != (original.doseAmount.map({ NSDecimalNumber(decimal: $0).stringValue }) ?? "")
            || doseUnit != (original.doseUnit ?? "")
            || relief != (original.reportedRelief.flatMap(MigraineReliefChoice.init(rawValue:)) ?? .notReported)
            || notes != (original.notes ?? "")
    }

    func value(responseTimestamp: Date) throws -> MigraineMedicineTaken {
        if let original, !hasFieldChanges { return original }
        let cleanedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanedName.isEmpty else { throw MigraineDraftError.medicineNameRequired }
        let text = doseAmountText.trimmingCharacters(in: .whitespacesAndNewlines)
        let unit = doseUnit.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.isEmpty == unit.isEmpty else { throw MigraineDraftError.incompleteDose }
        guard text.isEmpty || text.range(of: #"^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"#, options: .regularExpression) != nil else {
            throw MigraineDraftError.incompleteDose
        }
        let amount = text.isEmpty ? nil : Decimal(string: text, locale: Locale(identifier: "en_US_POSIX"))
        if !text.isEmpty && (amount == nil || amount! <= 0 || !Self.exactDecimal(text, amount!)) { throw MigraineDraftError.incompleteDose }
        let originalRelief = original?.reportedRelief.flatMap(MigraineReliefChoice.init(rawValue:)) ?? .notReported
        let reliefUnchanged = original != nil && relief == originalRelief
        let reliefValue = relief == .notReported ? nil : relief.rawValue
        let note = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        return MigraineMedicineTaken(name: name == original?.name ? original!.name : cleanedName,
            takenAt: original != nil && takenAt == initialDate ? original!.takenAt : MigraineFollowUpDraft.timestamp(takenAt),
            doseAmount: amount, doseUnit: doseUnit == (original?.doseUnit ?? "") ? original?.doseUnit : (unit.isEmpty ? nil : unit),
            reportedRelief: reliefUnchanged ? original?.reportedRelief : reliefValue,
            reliefReportedAt: reliefUnchanged ? original?.reliefReportedAt : (reliefValue == nil ? nil : MigraineFollowUpDraft.timestamp(responseTimestamp)),
            notes: notes == (original?.notes ?? "") ? original?.notes : (note.isEmpty ? nil : note))
    }

    // Decimal(string:) can silently round beyond its precision. Accept only an
    // exactly represented decimal, comparing normalized digits and exponent.
    private static func exactDecimal(_ text: String, _ value: Decimal) -> Bool {
        func normalized(_ input: String) -> String? {
            let parts = input.lowercased().replacingOccurrences(of: "+", with: "").split(separator: "e", omittingEmptySubsequences: false)
            guard parts.count <= 2, let exponent = parts.count == 2 ? Int(parts[1]) : 0 else { return nil }
            let decimal = parts[0].split(separator: ".", omittingEmptySubsequences: false)
            var digits = decimal.joined(); var power = exponent - (decimal.count == 2 ? decimal[1].count : 0)
            while digits.first == "0" { digits.removeFirst() }
            while digits.last == "0" { digits.removeLast(); power += 1 }
            return digits + "e" + String(power)
        }
        return normalized(text) == normalized(NSDecimalNumber(decimal: value).stringValue)
    }

    func rebased(on saved: MigraineMedicineTaken, index: Int, responseTimestamp: Date) -> Self {
        let baseline = Self(original: original, date: initialDate)
        var row = Self(id: id, originalIndex: index, original: saved, date: responseTimestamp)
        for key in [\Self.name, \Self.doseAmountText, \Self.doseUnit, \Self.notes] where self[keyPath: key] != baseline[keyPath: key] {
            row[keyPath: key] = self[keyPath: key]
        }
        if takenAt != baseline.takenAt { row.takenAt = takenAt }
        if relief != baseline.relief { row.relief = relief }
        return row
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
    private var medicineMode: MigraineMedicineChoice = .retain
    private(set) var medicineRows: [MigraineMedicineDraftRow] = []
    private(set) var selectedMedicineID: UUID?
    private var removedMedicineIndices: Set<Int> = []
    var selectedMedicine: MigraineMedicineDraftRow? { medicineRows.first { $0.id == selectedMedicineID } }
    var medicineChoice: MigraineMedicineChoice {
        get { medicineMode }
        set { chooseMedicine(newValue) }
    }
    var medicineName: String {
        get { selectedMedicine?.name ?? "" }
        set { editSelected { $0.name = newValue } }
    }
    var medicineTakenAt: Date {
        get { selectedMedicine?.takenAt ?? responseTimestamp }
        set { editSelected { $0.takenAt = newValue } }
    }
    var doseAmountText: String {
        get { selectedMedicine?.doseAmountText ?? "" }
        set { editSelected { $0.doseAmountText = newValue } }
    }
    var doseUnit: String {
        get { selectedMedicine?.doseUnit ?? "" }
        set { editSelected { $0.doseUnit = newValue } }
    }
    var reliefChoice: MigraineReliefChoice {
        get { selectedMedicine?.relief ?? .notReported }
        set { editSelected { $0.relief = newValue } }
    }
    var medicineNotesText: String {
        get { selectedMedicine?.notes ?? "" }
        set { editSelected { $0.notes = newValue } }
    }
    var noteText: String = ""

    init(accountScope: String, promptId: String, episodeId: String, responseTimestamp: Date = Date()) {
        self.accountScope = accountScope
        self.promptId = promptId
        self.episodeId = episodeId
        self.responseTimestamp = responseTimestamp
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

        medicineRows = originalMedicines.enumerated().map {
            MigraineMedicineDraftRow(originalIndex: $0.offset, original: $0.element, date: responseTimestamp)
        }
        selectedMedicineID = medicineRows.first?.id
        removedMedicineIndices = []
        medicineMode = medicineRows.isEmpty ? .retain : .taken
    }

    // Move the concurrency baseline only when the time receipt proves that
    // stored non-time values are unchanged. Preserve the person's unsaved fields.
    @discardableResult
    mutating func advanceAfterTimeCorrection(_ saved: MigraineTimeContext, currentAccountScope: String) -> Bool {
        guard accountScope == currentAccountScope, episodeId == saved.episode.episodeId,
              saved.currentRevision == saved.appliedRevision, saved.revision == expectedRevision + 1,
              saved.currentCanonicalUpdatedAt == saved.canonicalUpdatedAt,
              originalNotes == saved.episode.notes,
              originalEarlySigns.elementsEqual(saved.episode.earlySigns, by: { $0.matches($1) }),
              originalMedicines.elementsEqual(saved.episode.medicines, by: { $0.matches($1) }) else { return false }
        expectedRevision = saved.revision
        return true
    }

    // The legacy response acknowledges only its submitted note, not a structured
    // revision or any medicine/sign changes. Never advance those from this route.
    mutating func acknowledgeLegacyNoteSave(episodeId savedEpisodeId: String, submittedNote: String,
                                            savedNote: String?, currentAccountScope: String) {
        let submitted = submittedNote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard accountScope == currentAccountScope, episodeId == savedEpisodeId,
              !submitted.isEmpty, savedNote == submitted else { return }
        originalNotes = savedNote
    }

    // Called only by the person's explicit reload/review action after a conflict.
    // Rebase changed controls onto the latest full detail; untouched controls and
    // all retained entries/provenance come from that freshly loaded baseline.
    mutating func rebasePreservingChanges(_ detail: MigraineEpisodeDetail, currentAccountScope: String) throws {
        guard accountScope == currentAccountScope, episodeId == detail.episode.episodeId else {
            throw MigraineDraftError.accountChanged
        }
        guard detail.revision >= expectedRevision else { throw MigraineSaveError.invalidResponse }
        let latest = detail.episode.medicines
        // No persistent IDs exist. A unique recorded name/time may anchor a row;
        // repeated anchors require the complete group to be unchanged and in order.
        func sameAnchor(_ a: MigraineMedicineTaken, _ b: MigraineMedicineTaken) -> Bool {
            a.name == b.name && a.takenAt.matches(b.takenAt)
        }
        func mappedIndex(_ index: Int) -> Int? {
            let before = originalMedicines.indices.filter { sameAnchor(originalMedicines[$0], originalMedicines[index]) }
            let after = latest.indices.filter { sameAnchor(latest[$0], originalMedicines[index]) }
            guard before.count == after.count, let ordinal = before.firstIndex(of: index) else { return nil }
            if before.count > 1 && !zip(before, after).allSatisfy({ originalMedicines[$0].matches(latest[$1]) }) { return nil }
            return after[ordinal]
        }
        var replacements: [Int: MigraineMedicineDraftRow] = [:]
        var removals: Set<Int> = []
        if medicineMode != .none && medicineMode != .retain {
            for row in medicineRows {
                guard let oldIndex = row.originalIndex else { continue }
                guard let newIndex = mappedIndex(oldIndex) else {
                    if row.hasFieldChanges { throw MigraineDraftError.medicineListConflict }
                    continue
                }
                replacements[newIndex] = row.rebased(on: latest[newIndex], index: newIndex, responseTimestamp: responseTimestamp)
            }
            for oldIndex in removedMedicineIndices {
                guard let index = mappedIndex(oldIndex) else { throw MigraineDraftError.medicineListConflict }
                removals.insert(index)
            }
        }
        var rebased = self
        try rebased.apply(detail, forAccountScope: currentAccountScope)
        if earlySignsText != originalEarlySigns.map(\.label).joined(separator: ", ") { rebased.earlySignsText = earlySignsText }
        if noteText != (originalNotes ?? "") { rebased.noteText = noteText }
        if medicineMode == .none {
            rebased.chooseMedicine(.none)
        } else if medicineMode != .retain {
            rebased.medicineRows = rebased.medicineRows.enumerated().compactMap { index, row in
                removals.contains(index) ? nil : replacements[index] ?? row
            } + medicineRows.filter { $0.originalIndex == nil }
            rebased.removedMedicineIndices = removals
            rebased.selectedMedicineID = rebased.medicineRows.contains(where: { $0.id == selectedMedicineID })
                ? selectedMedicineID : rebased.medicineRows.first?.id
            rebased.medicineMode = medicineMode
        }
        self = rebased
    }

    mutating func selectMedicine(_ id: UUID) {
        guard let row = medicineRows.first(where: { $0.id == id }) else { return }
        selectedMedicineID = id
        medicineMode = row.originalIndex == nil ? .add : .taken
    }

    mutating func addMedicine() {
        let row = MigraineMedicineDraftRow(date: responseTimestamp)
        medicineRows.append(row); selectedMedicineID = row.id; medicineMode = .add
    }

    mutating func removeSelectedMedicine() {
        guard let index = medicineRows.firstIndex(where: { $0.id == selectedMedicineID }) else { return }
        if let original = medicineRows[index].originalIndex { removedMedicineIndices.insert(original) }
        medicineRows.remove(at: index)
        selectedMedicineID = medicineRows.isEmpty ? nil : medicineRows[min(index, medicineRows.count - 1)].id
        medicineMode = medicineRows.isEmpty ? .removeSelected : .taken
    }

    mutating func chooseMedicine(_ choice: MigraineMedicineChoice) {
        switch choice {
        case .add: if medicineMode != .add { addMedicine() }
        case .taken:
            if let row = medicineRows.first { selectMedicine(row.id) } else { addMedicine() }
        case .removeSelected: removeSelectedMedicine()
        case .none:
            medicineRows = []; selectedMedicineID = nil
            removedMedicineIndices = Set(originalMedicines.indices); medicineMode = .none
        case .retain: medicineMode = .retain
        }
    }

    private mutating func editSelected(_ edit: (inout MigraineMedicineDraftRow) -> Void) {
        if selectedMedicine == nil { addMedicine() }
        guard let index = medicineRows.firstIndex(where: { $0.id == selectedMedicineID }) else { return }
        edit(&medicineRows[index])
    }

    func makeStructuredEdit(currentAccountScope: String) throws -> MigraineStructuredEdit? {
        guard accountScope == currentAccountScope else { throw MigraineDraftError.accountChanged }

        let labels = earlySignsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let originalLabels = originalEarlySigns.map(\.label)
        var remainingSigns = originalEarlySigns
        let earlySigns: [MigraineEarlySign]? = earlySignsText == originalLabels.joined(separator: ", ") ? nil : labels.map { label in
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
        case .taken, .add, .removeSelected:
            let values = try medicineRows.map { try $0.value(responseTimestamp: responseTimestamp) }
            medicines = values == originalMedicines ? nil : values
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
