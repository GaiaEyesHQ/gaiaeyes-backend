import Foundation

enum ShareCaptionEngine {
    static func signalSnapshot(
        mode: ExperienceMode,
        tone: ToneStyle,
        category: ShareHookCategory,
        hook: String,
        title: String,
        insight: String,
        signText: String?,
        bullets: [String],
        value: String?,
        state: String?
    ) -> ShareCaptionSet {
        let dataLine = sentenceJoin([
            titleMetricLine(title: title, value: value, state: state),
            signText?.replacingOccurrences(of: "\n", with: " ")
        ], maxCount: 1)
        let feelLine = feelingLine(category: category, bullets: bullets, style: .scientific, mode: mode)
        _ = tone

        return ShareCaptionSet(
            scientific: scientificBulletCaption(
                hook: hook,
                lines: [
                    factLine("Signal", dataLine ?? insight),
                    factLine("Watch", feelLine),
                    factLine("Note", groundingLine(category: category, style: .scientific, mode: mode)),
                ],
                cta: signalCTA(category: category, style: .scientific, mode: mode)
            ),
            balanced: paragraphCaption(
                socialSignalLines(
                    mode: mode,
                    category: category,
                    hook: hook,
                    title: title,
                    insight: dataLine ?? insight,
                    bullets: bullets,
                    value: value,
                    state: state
                ),
                cta: nil
            ),
            humorous: paragraphCaption([
                hook,
                playfulLine(category: category, title: title, mode: mode),
                feelingLine(category: category, bullets: bullets, style: .humorous, mode: mode),
                groundingLine(category: category, style: .humorous, mode: mode),
            ], cta: signalCTA(category: category, style: .humorous, mode: mode))
        )
    }

    static func personalPattern(
        mode: ExperienceMode,
        hook: String,
        relationship: String,
        insight: String,
        bullets: [String],
        evidenceCount: Int?,
        lagText: String?,
        confidence: String?
    ) -> ShareCaptionSet {
        let evidenceLine = sentenceJoin([
            evidenceCount.map { "Seen \($0) times" },
            lagText.map { "Lag \($0)" },
            confidence.map { "Confidence \($0)" },
        ], maxCount: 1)

        return ShareCaptionSet(
            scientific: scientificBulletCaption(
                hook: hook,
                lines: [
                    factLine("Pattern", relationship),
                    factLine("Evidence", evidenceLine ?? bullets.first),
                ],
                cta: nil
            ),
            balanced: paragraphCaption([
                hook,
                insight,
                bullets.first ?? "It keeps showing up in the same direction",
            ], cta: nil),
            humorous: paragraphCaption([
                hook,
                "Your log keeps bringing this one back",
                bullets.first ?? evidenceLine ?? "Apparently the pattern has opinions",
                mode == .mystical ? "The universe left a sticky note" : "The data left a sticky note",
            ], cta: nil)
        )
    }

    static func dailyState(
        mode: ExperienceMode,
        category: ShareHookCategory,
        hook: String,
        title: String,
        insight: String,
        bullets: [String],
        leading: String,
        supporting: [String]
    ) -> ShareCaptionSet {
        let dataLine = sentenceJoin([
            "\(leading) is leading today",
            supporting.first.map { "\($0) is also in play" }
        ], maxCount: 1)

        return ShareCaptionSet(
            scientific: scientificBulletCaption(
                hook: hook,
                lines: [
                    factLine("Leading", dataLine ?? title),
                    factLine("Watch", bullets.first ?? feelingLine(category: category, bullets: [], style: .scientific, mode: mode)),
                    factLine("Note", groundingLine(category: category, style: .scientific, mode: mode)),
                ],
                cta: dailyStateCTA(style: .scientific, mode: mode)
            ),
            balanced: paragraphCaption([
                hook,
                insight,
                bullets.first ?? feelingLine(category: category, bullets: [], style: .balanced, mode: mode),
                groundingLine(category: category, style: .balanced, mode: mode),
            ], cta: dailyStateCTA(style: .balanced, mode: mode)),
            humorous: paragraphCaption([
                hook,
                "\(leading) is running the group chat",
                bullets.first ?? feelingLine(category: category, bullets: [], style: .humorous, mode: mode),
                groundingLine(category: category, style: .humorous, mode: mode),
            ], cta: dailyStateCTA(style: .humorous, mode: mode))
        )
    }

    static func event(
        mode: ExperienceMode,
        category: ShareHookCategory,
        hook: String,
        title: String,
        severity: String?,
        insight: String,
        bullets: [String]
    ) -> ShareCaptionSet {
        let dataLine = sentenceJoin([
            titleMetricLine(title: title, value: nil, state: severity),
            bullets.first
        ], maxCount: 1)

        return ShareCaptionSet(
            scientific: scientificBulletCaption(
                hook: hook,
                lines: [
                    factLine("Event", dataLine ?? insight),
                    factLine("Watch", feelingLine(category: category, bullets: bullets, style: .scientific, mode: mode)),
                    factLine("Note", groundingLine(category: category, style: .scientific, mode: mode)),
                ],
                cta: eventCTA(category: category, style: .scientific, mode: mode)
            ),
            balanced: paragraphCaption([
                hook,
                insight,
                feelingLine(category: category, bullets: bullets, style: .balanced, mode: mode),
                groundingLine(category: category, style: .balanced, mode: mode),
            ], cta: eventCTA(category: category, style: .balanced, mode: mode)),
            humorous: paragraphCaption([
                hook,
                playfulLine(category: category, title: title, mode: mode),
                feelingLine(category: category, bullets: bullets, style: .humorous, mode: mode),
                groundingLine(category: category, style: .humorous, mode: mode),
            ], cta: eventCTA(category: category, style: .humorous, mode: mode))
        )
    }

    static func outlook(
        mode: ExperienceMode,
        category: ShareHookCategory,
        hook: String,
        windowTitle: String,
        primaryDriver: String,
        insight: String,
        bullets: [String],
        supportingDrivers: [String],
        affectedDomains: [String],
        actionLine: String,
        primaryState: String?,
        primaryValue: String?
    ) -> ShareCaptionSet {
        let dataLine = sentenceJoin([
            "\(windowTitle) has \(primaryDriver) out front",
            titleMetricLine(title: primaryDriver, value: primaryValue, state: primaryState) ?? bullets.first
        ], maxCount: 1)
        let watchLine = commaList(affectedDomains, maxCount: 3)
        let supportLine = commaList(supportingDrivers, maxCount: 2)

        return ShareCaptionSet(
            scientific: scientificBulletCaption(
                hook: hook,
                lines: [
                    factLine("Window", windowTitle),
                    factLine("Leading", dataLine ?? insight),
                    factLine("Watch for", watchLine ?? supportLine ?? clippedSentence(actionLine, maxWords: 14) ?? feelingLine(category: category, bullets: bullets, style: .scientific, mode: mode)),
                ],
                cta: outlookCTA(style: .scientific, mode: mode)
            ),
            balanced: paragraphCaption([
                hook,
                dataLine ?? insight,
                supportLine.map { "\($0) is also in play" },
                watchLine.map { "Most likely to stand out: \($0)" },
                clippedSentence(actionLine, maxWords: 14) ?? feelingLine(category: category, bullets: bullets, style: .balanced, mode: mode),
            ], cta: outlookCTA(style: .balanced, mode: mode)),
            humorous: paragraphCaption([
                hook,
                "\(primaryDriver) looks ready to call the shots",
                watchLine.map { "If anything gets loud, it may be \($0.lowercased())" },
                clippedSentence(actionLine, maxWords: 14) ?? feelingLine(category: category, bullets: bullets, style: .humorous, mode: mode),
            ], cta: outlookCTA(style: .humorous, mode: mode))
        )
    }

    private enum CaptionTone {
        case scientific
        case balanced
        case humorous
    }

    private static func caption(_ lines: [String?]) -> String {
        let unique = uniqueLines(lines).prefix(4)
        return unique.map(sentence).joined(separator: " ")
    }

    private static func paragraphCaption(_ lines: [String?], cta: String?) -> String {
        caption(lines + [cta])
    }

    private static func scientificBulletCaption(hook: String, lines: [String?], cta: String?) -> String {
        let bulletLines = Array(uniqueLines(lines).prefix(3))
        var output: [String] = [sentence(hook)]
        output.append(contentsOf: bulletLines.map { "• " + sentence($0) })
        if let cta = cta {
            output.append("• " + sentence(cta))
        }
        return output.joined(separator: "\n")
    }

    private static func socialSignalLines(
        mode: ExperienceMode,
        category: ShareHookCategory,
        hook: String,
        title: String,
        insight: String,
        bullets: [String],
        value: String?,
        state: String?
    ) -> [String?] {
        let lower = title.lowercased()
        let metric = titleMetricLine(title: title, value: value, state: state)

        if lower.contains("cme") || lower.contains("solar wave") {
            return [
                hook,
                "CMEs can stir geomagnetic conditions that may overlap with sleep, sensitivity, or recovery shifts",
                "Sometimes what you feel is part of a bigger signal picture",
                "Decode the unseen in Gaia Eyes",
            ]
        }

        if lower.contains("schumann") || lower.contains("resonance") {
            return [
                hook,
                mode == .mystical
                    ? "Schumann shifts can make the field feel louder for some people"
                    : "Schumann shifts may overlap with restless energy or a less settled baseline",
                mode == .mystical
                    ? "Ground, breathe, and spend time outdoors if you can"
                    : "Grounding, breath work, and a steadier pace are good defaults today",
                "Decode the unseen in Gaia Eyes",
            ]
        }

        if lower.contains("temporary illness") || lower.contains("illness") || lower.contains("sick") {
            return [
                hook,
                "Temporary illness can turn symptoms up and make patterns harder to read",
                "Log it so Gaia can treat today as context instead of a false pattern",
                "Track the bigger picture in Gaia Eyes",
            ]
        }

        if lower.contains("symptom") {
            return [
                hook,
                "Your current symptoms are part of today's signal mix",
                "Log what is active so Gaia can learn what keeps showing up around it",
                "Track your own patterns in Gaia Eyes",
            ]
        }

        switch category {
        case .solar:
            return [
                hook,
                metric ?? insight,
                "Solar activity can stir the field and may overlap with sleep, energy, or sensitivity",
                "Decode the unseen in Gaia Eyes",
            ]
        case .geomagnetic:
            return [
                hook,
                metric ?? insight,
                "Field shifts may overlap with restlessness, sleep changes, or sensitivity",
                "Decode the unseen in Gaia Eyes",
            ]
        case .air:
            return [
                hook,
                metric ?? insight,
                "Air quality and irritants can overlap with sinus pressure, headaches, or fatigue",
                "Track the bigger picture in Gaia Eyes",
            ]
        case .pressure:
            return [
                hook,
                metric ?? insight,
                "Pressure swings can overlap with headaches, pain, or body sensitivity",
                "Track the bigger picture in Gaia Eyes",
            ]
        case .body:
            return [
                hook,
                "Your body context can change how today's signals should be read",
                feelingLine(category: category, bullets: bullets, style: .balanced, mode: mode),
                "Track the bigger picture in Gaia Eyes",
            ]
        case .earth, .pattern:
            return [
                hook,
                metric ?? insight,
                feelingLine(category: category, bullets: bullets, style: .balanced, mode: mode),
                groundingLine(category: category, style: .balanced, mode: mode),
            ]
        }
    }

    private static func shareCTA(style: CaptionTone, mode: ExperienceMode) -> String {
        switch style {
        case .scientific:
            return "Track your own signal mix in Gaia Eyes"
        case .balanced:
            return "Track your own patterns in Gaia Eyes"
        case .humorous:
            return mode == .mystical
                ? "Gaia Eyes keeps an eye on the weird days"
                : "Gaia Eyes keeps receipts on the weird days"
        }
    }

    private static func signalCTA(category: ShareHookCategory, style: CaptionTone, mode: ExperienceMode) -> String {
        switch (category, style) {
        case (.air, .scientific):
            return "Track local air shifts in Gaia Eyes"
        case (.pressure, .scientific):
            return "Track weather-sensitive shifts in Gaia Eyes"
        case (.solar, .scientific), (.geomagnetic, .scientific):
            return "Track space weather and body context in Gaia Eyes"
        case (.body, .scientific):
            return "Track symptoms and body context in Gaia Eyes"
        case (_, .balanced):
            return "See how your own signal mix trends in Gaia Eyes"
        case (_, .humorous):
            return mode == .mystical
                ? "Gaia Eyes keeps an eye on the louder days"
                : "Gaia Eyes keeps score when the day gets weird"
        default:
            return shareCTA(style: style, mode: mode)
        }
    }

    private static func patternCTA(style: CaptionTone, mode: ExperienceMode) -> String {
        switch style {
        case .scientific:
            return "Track recurring patterns in Gaia Eyes"
        case .balanced:
            return "See which patterns keep repeating in Gaia Eyes"
        case .humorous:
            return mode == .mystical
                ? "Gaia Eyes keeps track of the repeating themes"
                : "Gaia Eyes keeps receipts on repeat offenders"
        }
    }

    private static func dailyStateCTA(style: CaptionTone, mode: ExperienceMode) -> String {
        switch style {
        case .scientific:
            return "Track what is leading in Gaia Eyes"
        case .balanced:
            return "See what is shaping your mix in Gaia Eyes"
        case .humorous:
            return mode == .mystical
                ? "Gaia Eyes translates the louder days"
                : "Gaia Eyes translates the louder days"
        }
    }

    private static func eventCTA(category: ShareHookCategory, style: CaptionTone, mode: ExperienceMode) -> String {
        switch (category, style) {
        case (.solar, .scientific), (.geomagnetic, .scientific):
            return "Track live space weather in Gaia Eyes"
        case (_, .balanced):
            return "See how the wider signal picture shifts in Gaia Eyes"
        case (_, .humorous):
            return mode == .mystical
                ? "Gaia Eyes keeps an eye on the dramatic sky days"
                : "Gaia Eyes keeps an eye on the dramatic signal days"
        default:
            return shareCTA(style: style, mode: mode)
        }
    }

    private static func outlookCTA(style: CaptionTone, mode: ExperienceMode) -> String {
        switch style {
        case .scientific:
            return "Track the next shifts in Gaia Eyes"
        case .balanced:
            return "See what is lining up next in Gaia Eyes"
        case .humorous:
            return mode == .mystical
                ? "Gaia Eyes keeps tabs on what is lining up next"
                : "Gaia Eyes keeps tabs on what is lining up next"
        }
    }

    private static func titleMetricLine(title: String, value: String?, state: String?) -> String? {
        if let value = valueOrNil(value), let state = valueOrNil(state) {
            return "\(title) is \(state.lowercased()) at \(value)"
        }
        if let value = valueOrNil(value) {
            return "\(title) is at \(value)"
        }
        if let state = valueOrNil(state) {
            return "\(title) is \(state.lowercased()) right now"
        }
        return nil
    }

    private static func factLine(_ label: String, _ value: String?) -> String? {
        guard let value = valueOrNil(value) else { return nil }
        return "\(label): \(value)"
    }

    private static func commaList(_ values: [String], maxCount: Int) -> String? {
        let lines = uniqueLines(values.map(Optional.some))
        guard !lines.isEmpty else { return nil }
        return lines.prefix(maxCount).joined(separator: ", ")
    }

    private static func feelingLine(
        category: ShareHookCategory,
        bullets: [String],
        style: CaptionTone,
        mode: ExperienceMode
    ) -> String {
        if let bullet = preferredFeelingBullet(from: bullets) {
            switch style {
            case .scientific:
                return bullet
            case .balanced:
                return "You may notice \(lowercasedStart(bullet))"
            case .humorous:
                return bullet
            }
        }

        switch (category, style) {
        case (.pressure, .scientific):
            return "Rapid swings like this can line up with tension or headache days for some"
        case (.pressure, .balanced):
            return "You may notice a little more tension or body sensitivity"
        case (.pressure, .humorous):
            return "If your head feels dramatic, it may have a reason"
        case (.air, .scientific):
            return "Higher irritant load can line up with sinus, headache, or fatigue days"
        case (.air, .balanced):
            return "You may notice your sinuses, head, or energy a little more"
        case (.air, .humorous):
            return "If your sinuses are complaining, they may have a point"
        case (.solar, .scientific):
            return "Active solar windows can overlap with sleep or recovery shifts for some"
        case (.solar, .balanced):
            return "You may feel a little more wired, off rhythm, or extra sensitive"
        case (.solar, .humorous):
            return "If your system feels a little weird, space weather may be freelancing"
        case (.geomagnetic, .scientific):
            return "Some people notice sensitivity, restlessness, or sleep shifts during active field periods"
        case (.geomagnetic, .balanced):
            return "You may notice restless energy or a less settled baseline"
        case (.geomagnetic, .humorous):
            return mode == .mystical
                ? "If the vibes feel loud, you are not imagining the volume"
                : "If the background feels loud, it is not just your imagination"
        case (.pattern, .scientific):
            return "This is showing up consistently enough to keep on your radar"
        case (.pattern, .balanced):
            return "It may be worth trusting this pattern a little more"
        case (.pattern, .humorous):
            return "At this point the pattern might want a name tag"
        case (.body, .scientific):
            return "Body context can change how symptoms and signal overlap should be read"
        case (.body, .balanced):
            return "You may want to treat today as body-context first, pattern signal second"
        case (.body, .humorous):
            return "If your body is waving a flag, let it be loud enough to count"
        case (.earth, .scientific):
            return "The overall signal mix looks a little more loaded than usual"
        case (.earth, .balanced):
            return "You may feel a little less effortless than usual"
        case (.earth, .humorous):
            return "If the day feels slightly sideways, fair enough"
        }
    }

    private static func playfulLine(category: ShareHookCategory, title: String, mode: ExperienceMode) -> String {
        switch category {
        case .pressure:
            return "The weather picked a dramatic angle"
        case .air:
            return "The air quality did not choose subtlety"
        case .solar:
            return title.lowercased().contains("flare")
                ? "The sun chose a dramatic entrance"
                : "Space weather did not come to whisper"
        case .geomagnetic:
            return mode == .mystical ? "The field brought extra static" : "The background brought extra static"
        case .pattern:
            return "Your data keeps pulling this thread"
        case .body:
            return "Your body is sending a status update"
        case .earth:
            return "The day has opinions"
        }
    }

    private static func groundingLine(
        category: ShareHookCategory,
        style: CaptionTone,
        mode: ExperienceMode
    ) -> String {
        switch style {
        case .scientific:
            return "Worth watching without overcalling it"
        case .balanced:
            switch category {
            case .pressure, .air:
                return "Keep the pace a little gentler if you can"
            case .solar, .geomagnetic:
                return mode == .mystical ? "Stay a little softer with yourself today" : "Keep your baseline a little steadier today"
            case .pattern:
                return "Log it and see if it keeps holding"
            case .body:
                return "Use today as context, not a verdict"
            case .earth:
                return "Give yourself a little more margin today"
            }
        case .humorous:
            switch category {
            case .pressure, .air:
                return "Maybe let your body set the schedule"
            case .solar, .geomagnetic:
                return mode == .mystical ? "Decode the unseen" : "Maybe do not argue with physics today"
            case .pattern:
                return "Consider this your recurring reminder"
            case .body:
                return "Let the sick-day math be honest"
            case .earth:
                return "Let the day be weird without helping it"
            }
        }
    }

    private static func preferredFeelingBullet(from bullets: [String]) -> String? {
        let keywords = [
            "ache", "energy", "fatigue", "feel", "head", "headache", "mood", "notice",
            "pain", "restless", "sensitivity", "sinus", "sleep", "tension"
        ]
        return bullets
            .compactMap(valueOrNil)
            .first { line in
                let lower = line.lowercased()
                return keywords.contains { lower.contains($0) }
            }
    }

    private static func clippedSentence(_ raw: String?, maxWords: Int) -> String? {
        guard let value = valueOrNil(raw) else { return nil }
        let first = value
            .split(whereSeparator: { ".!?".contains($0) })
            .first
            .map(String.init)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? value
        let words = first.split(separator: " ")
        guard words.count > maxWords else { return first }
        return words.prefix(maxWords).joined(separator: " ") + "…"
    }

    private static func uniqueLines(_ values: [String?]) -> [String] {
        var result: [String] = []
        for value in values {
            guard let cleaned = valueOrNil(value) else { continue }
            guard !result.contains(where: { areSimilar(cleaned, $0) }) else { continue }
            result.append(cleaned)
        }
        return result
    }

    private static func sentenceJoin(_ values: [String?], maxCount: Int) -> String? {
        let lines = uniqueLines(values)
        guard !lines.isEmpty else { return nil }
        return lines.prefix(maxCount).map(sentence).joined(separator: " ")
    }

    private static func sentence(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return trimmed }
        if trimmed.hasSuffix(".") || trimmed.hasSuffix("!") || trimmed.hasSuffix("?") {
            return trimmed
        }
        return trimmed + "."
    }

    private static func lowercasedStart(_ raw: String) -> String {
        guard let first = raw.first else { return raw }
        return String(first).lowercased() + raw.dropFirst()
    }

    private static func valueOrNil(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let cleaned = raw
            .replacingOccurrences(of: "\n", with: " ")
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }

    private static func normalized(_ raw: String) -> String {
        let allowed = raw.lowercased().map { character -> Character in
            character.isLetter || character.isNumber ? character : " "
        }
        return String(allowed)
            .split(separator: " ")
            .joined(separator: " ")
    }

    private static func semanticTokens(_ raw: String) -> Set<String> {
        let stopWords: Set<String> = [
            "a", "an", "and", "are", "as", "at", "be", "for", "from", "in", "is", "it", "may",
            "more", "not", "of", "on", "or", "some", "than", "that", "the", "this", "today",
            "up", "with", "you", "your"
        ]
        return Set(
            normalized(raw)
                .split(separator: " ")
                .map(String.init)
                .filter { !stopWords.contains($0) }
        )
    }

    private static func areSimilar(_ lhs: String, _ rhs: String) -> Bool {
        let left = normalized(lhs)
        let right = normalized(rhs)
        if left == right || left.contains(right) || right.contains(left) {
            return true
        }

        let leftTokens = semanticTokens(lhs)
        let rightTokens = semanticTokens(rhs)
        guard !leftTokens.isEmpty, !rightTokens.isEmpty else { return false }

        let overlap = leftTokens.intersection(rightTokens).count
        let ratio = Double(overlap) / Double(max(leftTokens.count, rightTokens.count))
        return ratio >= 0.72
    }
}
