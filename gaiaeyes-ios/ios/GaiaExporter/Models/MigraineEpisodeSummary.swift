import Foundation

// A projection of one validated saved snapshot; never an editor draft.
struct MigraineEpisodeSummary: Equatable {
    struct Entry: Identifiable, Equatable {
        let id: String
        let title: String
        let lines: [String]
    }
    let revision: Int
    let displayTimezone: String
    let timing: [Entry]
    let medicines: [Entry]
    let earlySigns: [Entry]
    let contexts: [Entry]
    let notes: String

    init(detail: MigraineEpisodeDetail, episodeID: String, timeZone: TimeZone, locale: Locale = .current) throws {
        let episode = detail.episode
        guard UUID(uuidString: episodeID) != nil, episode.episodeId == episodeID,
              episode.schemaVersion == "1.0", episode.symptomCode == "MIGRAINE",
              // A saved canonical episode without a structured row has stored
              // revision 0 and a revision-one candidate in the existing API.
              detail.revision >= 0, episode.lifecycle.revision == max(1, detail.revision),
              ["new", "ongoing", "improving", "worse", "resolved"].contains(episode.state),
              episode.severity.map({ (0...10).contains($0) }) ?? true else { throw MigraineSaveError.invalidResponse }
        guard episode.lifecycle.deletedAt == nil, episode.lifecycle.deletionScope == nil else {
            throw MigraineEpisodeSummaryError.unavailable
        }
        let formatter = DateFormatter()
        formatter.locale = locale; formatter.timeZone = timeZone
        formatter.dateFormat = "MMM d, yyyy 'at' h:mm:ss a z"
        func instant(_ value: String) throws -> Date {
            guard let result = MigraineFollowUpDraft.parseDate(value) else { throw MigraineSaveError.invalidResponse }
            return result
        }
        func time(_ value: MigraineEpisodeTimestamp?) throws -> String {
            guard let value else { return "Not recorded" }
            return formatter.string(from: try instant(value.utc))
        }
        func text(_ value: String?) -> String {
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return "Not recorded" }
            return value
        }
        let start = try instant(episode.start.utc)
        let end = try episode.end.map { try instant($0.utc) }
        guard end.map({ $0 >= start && episode.state == "resolved" }) ?? true else { throw MigraineSaveError.invalidResponse }
        let created = try instant(episode.lifecycle.createdAt), saved = try instant(episode.lifecycle.updatedAt)
        guard saved >= created else { throw MigraineSaveError.invalidResponse }
        var duration = "Not available without a recorded end time"
        if let end {
            let minutes = Int(end.timeIntervalSince(start) / 60)
            let hours = minutes / 60
            let minuteText = "\(minutes % 60) minute\(minutes % 60 == 1 ? "" : "s")"
            let hourText = "\(hours) hour\(hours == 1 ? "" : "s")"
            duration = minutes == 0 ? "Less than a minute" : hours == 0 ? minuteText
                : minutes % 60 == 0 ? hourText : "\(hourText), \(minuteText)"
        }
        revision = detail.revision; displayTimezone = timeZone.identifier
        timing = [Entry(id: "start", title: "Started", lines: [try time(episode.start)]),
                  Entry(id: "end", title: "Ended", lines: [try time(episode.end)]),
                  Entry(id: "state", title: "Saved state", lines: [episode.state.capitalized]),
                  Entry(id: "severity", title: "Severity", lines: [episode.severity.map { "\($0)/10" } ?? "Not recorded"]),
                  Entry(id: "duration", title: "Elapsed duration", lines: [duration])]
        medicines = try episode.medicines.enumerated().map { index, medicine in
            guard !medicine.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  (medicine.doseAmount == nil) == (medicine.doseUnit == nil),
                  medicine.doseAmount.map({ !$0.isNaN && $0 > 0 }) ?? true,
                  medicine.doseUnit.map({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) ?? true,
                  medicine.reportedRelief.map({ MigraineReliefChoice(rawValue: $0) != nil && !$0.isEmpty }) ?? true else {
                throw MigraineSaveError.invalidResponse
            }
            let dose = medicine.doseAmount.map { NSDecimalNumber(decimal: $0).stringValue + " " + medicine.doseUnit! } ?? "Not recorded"
            let relief = medicine.reportedRelief.flatMap(MigraineReliefChoice.init(rawValue:))?.label ?? "Not recorded"
            return Entry(id: "medicine-\(index)", title: "\(index + 1). \(medicine.name)", lines: [
                "Taken: \(try time(medicine.takenAt))", "Dose: \(dose)", "Reported relief: \(relief)",
                "Relief recorded: \(try time(medicine.reliefReportedAt))", "Note: \(text(medicine.notes))"])
        }
        earlySigns = try episode.earlySigns.enumerated().map { index, sign in
            guard !sign.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw MigraineSaveError.invalidResponse }
            return Entry(id: "sign-\(index)", title: sign.label,
                         lines: ["Recorded: \(try time(sign.reportedAt))", "Note: \(text(sign.notes))"])
        }
        contexts = try episode.contexts.enumerated().map { index, context in
            guard !context.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw MigraineSaveError.invalidResponse }
            return Entry(id: "context-\(index)", title: context.label,
                         lines: ["Observed: \(try time(context.observedAt))", "Note: \(text(context.notes))"])
        }
        // The lifecycle timestamp can predate a canonical note/state edit, so
        // it cannot provide a truthful last-updated label for this summary.
        notes = text(episode.notes)
    }
}

enum MigraineEpisodeSummaryError: Error {
    case unavailable
}
