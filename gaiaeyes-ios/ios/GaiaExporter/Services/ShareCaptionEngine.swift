import Foundation

enum ShareCaptionEngine {
    static func signalSnapshot(
        mode: ExperienceMode,
        tone: ToneStyle,
        title: String,
        state: String?,
        value: String?,
        interpretation: String,
        bullets: [String]
    ) -> ShareCaptionSet {
        let trimmedBullets = Array(bullets.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }.prefix(3))
        let stateLine = [title, state].compactMap { valueOrNil($0) }.joined(separator: " — ")
        let valueLine = valueOrNil(value)
        let bulletLine = trimmedBullets.joined(separator: " • ")
        let scientific = [
            valueLine.map { "\(stateLine) at \($0)." } ?? "\(stateLine).",
            interpretation,
            valueOrNil(bulletLine),
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let balancedIntro = tone.resolveCopy(
            straight: "\(stateLine).",
            balanced: "\(stateLine).",
            humorous: "\(stateLine)."
        )
        let balanced = [
            balancedIntro,
            interpretation,
            trimmedBullets.isEmpty ? nil : "You might notice: \(bulletLine).",
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let playfulCloser: String
        switch mode {
        case .scientific:
            playfulCloser = tone == .humorous ? "My system: ???" : "Worth keeping an eye on."
        case .mystical:
            playfulCloser = tone == .humorous ? "My field: not subtle." : "The energy feels a little louder today."
        }
        let humorous = [
            valueLine.map { "\(stateLine). \($0)." } ?? "\(stateLine).",
            trimmedBullets.first,
            playfulCloser,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        return ShareCaptionSet(scientific: scientific, balanced: balanced, humorous: humorous)
    }

    static func personalPattern(
        mode: ExperienceMode,
        relationship: String,
        evidenceCount: Int?,
        lagText: String?,
        confidence: String?,
        explanation: String
    ) -> ShareCaptionSet {
        let evidenceLine = evidenceCount.map { "Observed across \($0) events." }
        let lagLine = valueOrNil(lagText).map { "Lag: \($0)." }
        let confidenceLine = valueOrNil(confidence).map { "Confidence: \($0)." }

        let scientific = [
            "Pattern detected.",
            relationship + ".",
            evidenceLine,
            lagLine,
            confidenceLine,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let balancedLead = mode == .mystical ? "This pattern keeps showing up." : "It may not be random."
        let balanced = [
            balancedLead,
            relationship + ".",
            evidenceLine,
            lagLine,
            explanation,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let humorous = [
            "Pattern detected.",
            relationship + ".",
            evidenceCount.map { "Seen \($0) times." },
            mode == .mystical ? "Apparently the universe left receipts." : "Apparently the data kept receipts."
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        return ShareCaptionSet(scientific: scientific, balanced: balanced, humorous: humorous)
    }

    static func dailyState(
        mode: ExperienceMode,
        title: String,
        leading: String,
        supporting: [String],
        interpretation: String
    ) -> ShareCaptionSet {
        let supportingLine = supporting.isEmpty ? nil : supporting.joined(separator: ", ")
        let scientific = [
            "\(title).",
            "Leading driver: \(leading).",
            supportingLine.map { "Also in play: \($0)." },
            interpretation,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let balanced = [
            "\(title).",
            "\(leading) is leading.",
            supportingLine.map { "\($0) is also in play." },
            interpretation,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let humorousCloser = mode == .mystical ? "The field is making itself known." : "The dashboard is not being subtle."
        let humorous = [
            "\(title).",
            "\(leading) is doing the loudest talking.",
            supportingLine.map { "\($0) is chiming in too." },
            humorousCloser,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        return ShareCaptionSet(scientific: scientific, balanced: balanced, humorous: humorous)
    }

    static func event(
        mode: ExperienceMode,
        title: String,
        severity: String?,
        context: String,
        bullets: [String],
        earthDirectedNote: String?
    ) -> ShareCaptionSet {
        let header = [title, valueOrNil(severity)].compactMap { $0 }.joined(separator: " — ")
        let bulletLine = Array(bullets.prefix(3)).joined(separator: " • ")

        let scientific = [
            "\(header).",
            context,
            earthDirectedNote,
            valueOrNil(bulletLine),
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let balanced = [
            "\(header).",
            context,
            earthDirectedNote,
            valueOrNil(bulletLine),
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let humorousTail = mode == .mystical ? "Cosmic weather has entered the chat." : "Space weather is not being quiet."
        let humorous = [
            "\(header).",
            context,
            earthDirectedNote,
            humorousTail,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        return ShareCaptionSet(scientific: scientific, balanced: balanced, humorous: humorous)
    }

    static func outlook(
        mode: ExperienceMode,
        windowTitle: String,
        primaryDriver: String,
        supportingDrivers: [String],
        affectedDomains: [String],
        actionLine: String
    ) -> ShareCaptionSet {
        let supportingLine = supportingDrivers.isEmpty ? nil : supportingDrivers.joined(separator: ", ")
        let domainsLine = affectedDomains.isEmpty ? nil : affectedDomains.joined(separator: ", ")

        let scientific = [
            "\(windowTitle).",
            "Primary driver: \(primaryDriver).",
            supportingLine.map { "Supporting drivers: \($0)." },
            domainsLine.map { "Likely affected domains: \($0)." },
            actionLine,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let balanced = [
            "\(windowTitle).",
            "\(primaryDriver) looks most worth watching.",
            supportingLine.map { "\($0) may add context." },
            domainsLine.map { "\($0) may stand out more in this window." },
            actionLine,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        let humorousTail = mode == .mystical ? "Future-you may want softer edges." : "Future-me may want fewer plans."
        let humorous = [
            "\(windowTitle).",
            "\(primaryDriver) is lining up first.",
            supportingLine.map { "\($0) is tagging along." },
            humorousTail,
            actionLine,
        ].compactMap { valueOrNil($0) }.joined(separator: " ")

        return ShareCaptionSet(scientific: scientific, balanced: balanced, humorous: humorous)
    }

    private static func valueOrNil(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
