import Foundation

private struct RequestCase: Encodable {
    let name: String
    let request: MigraineStructuredEdit
}

private struct ResultCase: Decodable {
    let name: String
    let detail: MigraineEpisodeDetail
}

@main
struct CurrentSourceMigraineProbe {
    static func require(_ value: Bool, _ message: String) {
        precondition(value, message)
        print("PASS \(message)")
    }

    static func main() throws {
        let mode = CommandLine.arguments[1]
        let directory = URL(fileURLWithPath: CommandLine.arguments[2])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode(MigraineEpisodeDetail.self, from: Data(contentsOf: directory.appendingPathComponent("backend-detail.json")))
        func draft() throws -> MigraineFollowUpDraft {
            var value = MigraineFollowUpDraft(accountScope: "synthetic-account", promptId: "synthetic-prompt", episodeId: detail.episode.episodeId,
                                              responseTimestamp: MigraineFollowUpDraft.parseDate("2026-09-08T05:30:00Z")!)
            try value.apply(detail, forAccountScope: "synthetic-account")
            return value
        }
        require(detail.episode.medicines[0].doseAmount == 10 && detail.episode.medicines[1].doseAmount == Decimal(string: "2.5"), "backend Decimal strings decode")
        let untouched = try draft().makeStructuredEdit(currentAccountScope: "synthetic-account")
        require(untouched == nil, "untouched two-medicine snapshot emits no replacement")
        var note = try draft(); note.noteText = "Updated episode note"
        let noteEdit = try note.makeStructuredEdit(currentAccountScope: "synthetic-account")!
        require(noteEdit.medicines == nil && noteEdit.earlySigns == nil, "note-only edit retains medicine and signs")
        var relief = try draft(); relief.reliefChoice = .aLot
        let reliefEdit = try relief.makeStructuredEdit(currentAccountScope: "synthetic-account")!
        require(reliefEdit.medicines?.count == 2, "relief-only edit preserves both medicines")
        require(reliefEdit.medicines?[0].notes == detail.episode.medicines[0].notes && reliefEdit.medicines?[0].takenAt == detail.episode.medicines[0].takenAt,
                "relief-only edit preserves notes and timestamp provenance")
        require(reliefEdit.medicines?[1] == detail.episode.medicines[1], "second medicine retained exactly")
        var medNote = try draft(); medNote.medicineNotesText = "Edited first medicine note"
        let medNoteEdit = try medNote.makeStructuredEdit(currentAccountScope: "synthetic-account")!
        require(medNoteEdit.medicines?[0].reliefReportedAt == detail.episode.medicines[0].reliefReportedAt, "medicine-note edit preserves relief provenance")
        var signs = try draft(); signs.earlySignsText += ", New synthetic sign"
        let signEdit = try signs.makeStructuredEdit(currentAccountScope: "synthetic-account")!
        require(Array(signEdit.earlySigns!.prefix(2)) == detail.episode.earlySigns, "early-sign addition retains untouched metadata")
        signs.earlySignsText = "Neck tension"
        require(try signs.makeStructuredEdit(currentAccountScope: "synthetic-account")!.earlySigns == [detail.episode.earlySigns[1]], "explicit sign removal preserves remaining metadata")
        var remove = try draft(); remove.medicineChoice = .removeFirst
        require(try remove.makeStructuredEdit(currentAccountScope: "synthetic-account")!.medicines == [detail.episode.medicines[1]], "explicit medicine removal preserves second entry")
        var clear = try draft(); clear.medicineChoice = .none
        require(try clear.makeStructuredEdit(currentAccountScope: "synthetic-account")!.medicines == [], "explicit clear removes all medicines")
        var requests = [RequestCase(name: "relief-only", request: reliefEdit), RequestCase(name: "note-only", request: noteEdit), RequestCase(name: "sign-add", request: signEdit)]
        for (label, utc) in [("zero-fraction", "2026-09-08T05:30:00Z"), ("fraction", "2026-09-08T05:30:00.125Z")] {
            var addition = try draft(); addition.chooseMedicine(.add)
            addition.medicineName = "Added synthetic medicine"
            addition.medicineTakenAt = MigraineFollowUpDraft.parseDate(utc)!
            addition.doseAmountText = "1.25"; addition.doseUnit = "mg"; addition.reliefChoice = .none
            let edit = try addition.makeStructuredEdit(currentAccountScope: "synthetic-account")!
            require(edit.medicines?.count == 3 && Array(edit.medicines!.prefix(2)) == detail.episode.medicines, "\(label) addition preserves saved list")
            requests.append(RequestCase(name: label, request: edit))
        }
        if mode == "emit" {
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(requests).write(to: directory.appendingPathComponent("swift-requests.json"))
        } else {
            let responses = try decoder.decode([ResultCase].self, from: Data(contentsOf: directory.appendingPathComponent("backend-roundtrips.json")))
            for response in responses {
                let request = requests.first { $0.name == response.name }!.request
                require(request.matches(response.detail), "\(response.name) request/backend/response confirmation")
            }
            let original = detail.episode.medicines[0].takenAt
            let normalized = MigraineEpisodeTimestamp(utc: "2026-09-08T04:45:00.000+00:00", originalTime: original.originalTime,
                timezoneName: original.timezoneName, utcOffsetMinutes: original.utcOffsetMinutes, timezoneSource: original.timezoneSource)
            require(original.matches(normalized), "equivalent UTC spellings compare as instants")
            require(original.utc == "2026-09-08T04:45:00Z" && normalized.utc.hasSuffix("+00:00"), "comparison preserves raw timestamp strings")
            print("MODEL CHECKPOINT PASSED: actual current Swift source and backend serializers")
        }
    }
}
