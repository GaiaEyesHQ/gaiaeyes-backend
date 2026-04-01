import Foundation

enum ShareDraftFactory {
    static func signalSnapshot(
        surface: String,
        analyticsKey: String?,
        mode: ExperienceMode,
        tone: ToneStyle,
        title: String,
        value: String?,
        state: String?,
        interpretation: String,
        bullets: [String],
        accent: ShareAccentLevel,
        background: ShareCardBackground,
        sourceLine: String? = nil,
        updatedAt: String? = nil,
        promptText: String? = nil
    ) -> ShareDraft {
        let category = ShareHookBank.category(
            for: .signalSnapshot,
            analyticsKey: analyticsKey,
            title: title,
            backgroundStyle: background.style
        )
        let hook = ShareHookBank.hook(for: category, mode: mode)
        let insight = signalInsight(
            category: category,
            title: title,
            value: value,
            state: state,
            interpretation: interpretation
        )
        let support = uniqueLines(
            [condensedSentence(interpretation, maxWords: 8)] + bullets,
            excluding: [hook, title, insight, state, value],
            maxCount: 2
        )
        let signText = signalSignText(category: category, title: title, value: value, state: state)

        let card = ShareCardModel(
            shareType: .signalSnapshot,
            layout: .signalSnapshot,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: title,
            title: hook,
            subtitle: insight,
            signText: signText,
            primaryText: nil,
            valueText: nil,
            stateText: state,
            bullets: support,
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: sourceLine,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.signalSnapshot(
            mode: mode,
            tone: tone,
            category: category,
            hook: hook,
            title: title,
            insight: insight,
            signText: signText,
            bullets: support,
            value: value,
            state: state
        )
        return ShareDraft(
            shareType: .signalSnapshot,
            surface: surface,
            analyticsKey: analyticsKey,
            promptText: promptText,
            card: card,
            captions: captions
        )
    }

    static func personalPattern(
        surface: String,
        analyticsKey: String?,
        mode: ExperienceMode,
        relationship: String,
        explanation: String,
        evidenceCount: Int?,
        lagText: String?,
        confidence: String?,
        accent: ShareAccentLevel,
        background: ShareCardBackground,
        updatedAt: String? = nil,
        promptText: String? = nil
    ) -> ShareDraft {
        let hook = ShareHookBank.hook(for: .pattern, mode: mode)
        let insight = joinSentences(
            [
                relationship,
                condensedSentence(explanation, maxWords: 10),
            ],
            maxCount: 2
        ) ?? relationship
        let support = uniqueLines(
            [
                evidenceCount.map { "Seen \($0) times" },
                lagText.map { "Lag \($0)" },
                confidence.map { "Confidence \($0)" },
            ],
            excluding: [hook, relationship, insight],
            maxCount: 2
        )
        let signText = patternSignText(evidenceCount: evidenceCount, confidence: confidence)

        let card = ShareCardModel(
            shareType: .personalPattern,
            layout: .personalPattern,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Pattern",
            title: hook,
            subtitle: insight,
            signText: signText,
            primaryText: nil,
            valueText: nil,
            stateText: confidence,
            bullets: support,
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.personalPattern(
            mode: mode,
            hook: hook,
            relationship: relationship,
            insight: insight,
            bullets: support,
            evidenceCount: evidenceCount,
            lagText: lagText,
            confidence: confidence
        )
        return ShareDraft(
            shareType: .personalPattern,
            surface: surface,
            analyticsKey: analyticsKey,
            promptText: promptText,
            card: card,
            captions: captions
        )
    }

    static func dailyState(
        surface: String,
        analyticsKey: String?,
        mode: ExperienceMode,
        title: String,
        leading: String,
        supporting: [String],
        interpretation: String,
        accent: ShareAccentLevel,
        background: ShareCardBackground,
        updatedAt: String? = nil,
        promptText: String? = nil
    ) -> ShareDraft {
        let category = ShareHookBank.category(
            for: .dailyState,
            analyticsKey: analyticsKey,
            title: leading,
            backgroundStyle: background.style
        )
        let hook = ShareHookBank.hook(for: category, mode: mode)
        let supportDrivers = uniqueLines(supporting, excluding: [leading], maxCount: 2)
        let insight = joinSentences(
            [
                "\(leading) is leading today",
                supportDrivers.first.map { "\($0) is also in the mix" },
            ],
            maxCount: 2
        ) ?? "\(leading) is leading today."
        let support = uniqueLines(
            [condensedSentence(interpretation, maxWords: 10)] + Array(supportDrivers.dropFirst()),
            excluding: [hook, title, leading, insight],
            maxCount: 2
        )
        let signText = linePair("Today", clippedText(leading, maxWords: 3))

        let card = ShareCardModel(
            shareType: .dailyState,
            layout: .dailyState,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: title,
            title: hook,
            subtitle: insight,
            signText: signText,
            primaryText: nil,
            valueText: nil,
            stateText: accent.pillTitle,
            bullets: support,
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.dailyState(
            mode: mode,
            category: category,
            hook: hook,
            title: title,
            insight: insight,
            bullets: support,
            leading: leading,
            supporting: supportDrivers
        )
        return ShareDraft(
            shareType: .dailyState,
            surface: surface,
            analyticsKey: analyticsKey,
            promptText: promptText,
            card: card,
            captions: captions
        )
    }

    static func event(
        surface: String,
        analyticsKey: String?,
        mode: ExperienceMode,
        title: String,
        severity: String?,
        context: String,
        bullets: [String],
        earthDirectedNote: String?,
        accent: ShareAccentLevel,
        background: ShareCardBackground,
        updatedAt: String? = nil,
        promptText: String? = nil
    ) -> ShareDraft {
        let category = ShareHookBank.category(
            for: .event,
            analyticsKey: analyticsKey,
            title: title,
            backgroundStyle: background.style
        )
        let hook = ShareHookBank.hook(for: category, mode: mode)
        let insight = eventInsight(title: title, severity: severity, context: context)
        let support = uniqueLines(
            [earthDirectedNote, condensedSentence(context, maxWords: 8)] + bullets,
            excluding: [hook, title, severity, insight],
            maxCount: 2
        )
        let signText = eventSignText(title: title, severity: severity, category: category)

        let card = ShareCardModel(
            shareType: .event,
            layout: .event,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Event",
            title: hook,
            subtitle: insight,
            signText: signText,
            primaryText: nil,
            valueText: nil,
            stateText: severity ?? accent.pillTitle,
            bullets: support,
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.event(
            mode: mode,
            category: category,
            hook: hook,
            title: title,
            severity: severity,
            insight: insight,
            bullets: support
        )
        return ShareDraft(
            shareType: .event,
            surface: surface,
            analyticsKey: analyticsKey,
            promptText: promptText,
            card: card,
            captions: captions
        )
    }

    static func outlook(
        surface: String,
        analyticsKey: String?,
        mode: ExperienceMode,
        windowTitle: String,
        primaryDriver: String,
        supportingDrivers: [String],
        affectedDomains: [String],
        actionLine: String,
        accent: ShareAccentLevel,
        background: ShareCardBackground,
        updatedAt: String? = nil,
        promptText: String? = nil
    ) -> ShareDraft {
        let category = ShareHookBank.category(
            for: .outlook,
            analyticsKey: analyticsKey,
            title: primaryDriver,
            backgroundStyle: background.style
        )
        let hook = ShareHookBank.hook(for: category, mode: mode)
        let supportDrivers = uniqueLines(supportingDrivers, excluding: [primaryDriver], maxCount: 2)
        let insight = joinSentences(
            [
                "\(windowTitle) points to \(primaryDriver) first",
                supportDrivers.first.map { "\($0) may add to it" },
            ],
            maxCount: 2
        ) ?? "\(windowTitle) points to \(primaryDriver) first."
        let support = uniqueLines(
            affectedDomains + [condensedSentence(actionLine, maxWords: 8)] + Array(supportDrivers.dropFirst()),
            excluding: [hook, windowTitle, primaryDriver, insight],
            maxCount: 2
        )
        let signText = linePair(clippedText(windowTitle, maxWords: 3), clippedText(primaryDriver, maxWords: 3))

        let card = ShareCardModel(
            shareType: .outlook,
            layout: .outlook,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Outlook",
            title: hook,
            subtitle: insight,
            signText: signText,
            primaryText: nil,
            valueText: nil,
            stateText: accent.pillTitle,
            bullets: support,
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.outlook(
            mode: mode,
            category: category,
            hook: hook,
            windowTitle: windowTitle,
            primaryDriver: primaryDriver,
            insight: insight,
            bullets: support,
            actionLine: actionLine
        )
        return ShareDraft(
            shareType: .outlook,
            surface: surface,
            analyticsKey: analyticsKey,
            promptText: promptText,
            card: card,
            captions: captions
        )
    }

    private static func signalInsight(
        category: ShareHookCategory,
        title: String,
        value: String?,
        state: String?,
        interpretation: String
    ) -> String {
        let metricLine: String?
        switch category {
        case .pressure:
            metricLine = valueOrNil(value).map { "\(title) moved \($0)" }
                ?? valueOrNil(state).map { "\(title) is \($0.lowercased()) right now" }
        case .air:
            metricLine = valueOrNil(value).map { "\(title) is at \($0) right now" }
                ?? valueOrNil(state).map { "\(title) is \($0.lowercased()) today" }
        case .solar:
            metricLine = valueOrNil(value).map { "\(title) is reading \($0)" }
                ?? valueOrNil(state).map { "\(title) is \($0.lowercased()) right now" }
        case .geomagnetic:
            metricLine = valueOrNil(value).map { "\(title) is running at \($0)" }
                ?? valueOrNil(state).map { "\(title) is \($0.lowercased()) right now" }
        case .earth, .pattern:
            metricLine = valueOrNil(state).map { "\(title) is \($0.lowercased()) today" }
                ?? valueOrNil(value).map { "\(title) is at \($0)" }
        }

        return joinSentences(
            [
                metricLine,
                condensedSentence(interpretation, maxWords: 10),
            ],
            maxCount: 2
        ) ?? clippedText(interpretation, maxWords: 14) ?? title
    }

    private static func eventInsight(title: String, severity: String?, context: String) -> String {
        let lower = title.lowercased()
        let lead: String?
        if lower.contains("flare"), let severity = valueOrNil(severity) {
            lead = "A \(severity) flare just fired off"
        } else if lower.contains("cme"), let severity = valueOrNil(severity) {
            lead = "A CME is in play at \(severity)"
        } else if lower.contains("geomagnetic"), let severity = valueOrNil(severity) {
            lead = "Geomagnetic conditions are \(severity.lowercased())"
        } else {
            lead = [title, valueOrNil(severity)].compactMap { $0 }.joined(separator: " ")
        }

        return joinSentences(
            [
                lead,
                condensedSentence(context, maxWords: 10),
            ],
            maxCount: 2
        ) ?? clippedText(context, maxWords: 14) ?? title
    }

    private static func signalSignText(
        category: ShareHookCategory,
        title: String,
        value: String?,
        state: String?
    ) -> String? {
        let lower = title.lowercased()
        switch category {
        case .pressure:
            return linePair("Headache watch", cleanSignValue(value) ?? cleanSignValue(state) ?? "Pressure rising")
        case .air:
            return linePair("Sinus watch", cleanSignValue(state) ?? cleanSignValue(value) ?? "Air load up")
        case .solar:
            if lower.contains("flare") {
                return linePair("Solar flare", cleanSignValue(state) ?? cleanSignValue(value) ?? "Sun active")
            }
            return linePair("Solar watch", cleanSignValue(state) ?? cleanSignValue(value) ?? clippedText(title, maxWords: 2))
        case .geomagnetic:
            return linePair("Field watch", cleanSignValue(state) ?? cleanSignValue(value) ?? "Background up")
        case .earth:
            return linePair(clippedText(title, maxWords: 2), cleanSignValue(state) ?? cleanSignValue(value))
        case .pattern:
            return nil
        }
    }

    private static func patternSignText(evidenceCount: Int?, confidence: String?) -> String? {
        if let evidenceCount {
            return linePair("Pattern seen", "\(evidenceCount) matches")
        }
        if let confidence = cleanSignValue(confidence) {
            return linePair("Pattern", confidence)
        }
        return linePair("Pattern", "Repeat signal")
    }

    private static func eventSignText(
        title: String,
        severity: String?,
        category: ShareHookCategory
    ) -> String? {
        let lower = title.lowercased()
        switch category {
        case .solar:
            if lower.contains("flare") {
                return linePair("Solar flare", cleanSignValue(severity) ?? "Active now")
            }
            if lower.contains("cme") {
                return linePair("CME watch", cleanSignValue(severity) ?? "In motion")
            }
            return linePair("Solar watch", cleanSignValue(severity) ?? clippedText(title, maxWords: 2))
        case .geomagnetic:
            return linePair("Field watch", cleanSignValue(severity) ?? "Active now")
        case .pressure, .air, .earth, .pattern:
            return linePair(clippedText(title, maxWords: 2), cleanSignValue(severity))
        }
    }

    private static func footer(_ updatedAt: String?) -> String {
        guard let updatedAt = valueOrNil(updatedAt) else {
            return "gaiaeyes.app"
        }
        return updatedAt
    }

    private static func uniqueLines(
        _ values: [String?],
        excluding: [String?] = [],
        maxCount: Int
    ) -> [String] {
        let blocked = excluding.compactMap(cleanedLine)
        var result: [String] = []

        for value in values {
            guard let cleaned = cleanedLine(value) else { continue }
            guard !blocked.contains(where: { areSimilar(cleaned, $0) }) else { continue }
            guard !result.contains(where: { areSimilar(cleaned, $0) }) else { continue }
            result.append(cleaned)
            if result.count == maxCount {
                break
            }
        }

        return result
    }

    private static func joinSentences(_ values: [String?], maxCount: Int) -> String? {
        let lines = uniqueLines(values, maxCount: maxCount)
        guard !lines.isEmpty else { return nil }
        return lines
            .prefix(maxCount)
            .map(sentence)
            .joined(separator: " ")
    }

    private static func sentence(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return trimmed }
        if trimmed.hasSuffix(".") || trimmed.hasSuffix("!") || trimmed.hasSuffix("?") {
            return trimmed
        }
        return trimmed + "."
    }

    private static func condensedSentence(_ raw: String?, maxWords: Int) -> String? {
        guard let cleaned = cleanedLine(raw) else { return nil }
        let sentence = firstSentence(from: cleaned) ?? cleaned
        let words = sentence.split(separator: " ")
        guard words.count > maxWords else { return sentence }
        return words.prefix(maxWords).joined(separator: " ") + "…"
    }

    private static func clippedText(_ raw: String?, maxWords: Int) -> String? {
        guard let cleaned = cleanedLine(raw) else { return nil }
        let words = cleaned.split(separator: " ")
        guard words.count > maxWords else { return cleaned }
        return words.prefix(maxWords).joined(separator: " ")
    }

    private static func firstSentence(from raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard let range = trimmed.range(of: #"[.!?](\s|$)"#, options: .regularExpression) else {
            return trimmed
        }
        return String(trimmed[..<range.upperBound]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func linePair(_ first: String?, _ second: String?) -> String? {
        let lines = [first, second].compactMap(cleanedLine)
        guard !lines.isEmpty else { return nil }
        return lines.prefix(2).joined(separator: "\n")
    }

    private static func cleanSignValue(_ raw: String?) -> String? {
        guard let clipped = clippedText(raw, maxWords: 4) else { return nil }
        return clipped
            .replacingOccurrences(of: ".", with: "")
            .replacingOccurrences(of: "!", with: "")
            .replacingOccurrences(of: "?", with: "")
    }

    private static func cleanedLine(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let refined = CopyRefiner.refine(raw) ?? raw
        let collapsed = refined
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "•", with: " ")
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return collapsed.isEmpty ? nil : collapsed
    }

    private static func valueOrNil(_ raw: String?) -> String? {
        cleanedLine(raw)
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
            "a", "an", "and", "are", "as", "at", "be", "can", "could", "day", "days", "for",
            "from", "in", "into", "is", "it", "its", "just", "may", "might", "more", "most",
            "not", "now", "of", "on", "or", "right", "some", "than", "that", "the", "their",
            "there", "these", "this", "those", "today", "up", "with", "your"
        ]
        let synonyms: [String: String] = [
            "allergens": "allergen",
            "allergies": "allergen",
            "aqi": "air",
            "fatigue": "fatigue",
            "headaches": "headache",
            "irritants": "allergen",
            "pollen": "allergen",
            "pressure": "pressure",
            "shift": "shift",
            "shifts": "shift",
            "swing": "shift",
            "swings": "shift",
            "solar": "solar",
            "storminess": "storm",
            "symptoms": "symptom",
            "temperature": "temperature",
        ]

        return Set(
            normalized(raw)
                .split(separator: " ")
                .map(String.init)
                .map { token in
                    if let mapped = synonyms[token] {
                        return mapped
                    }
                    if token.count > 4, token.hasSuffix("s") {
                        return String(token.dropLast())
                    }
                    return token
                }
                .filter { !stopWords.contains($0) }
        )
    }

    private static func areSimilar(_ lhs: String, _ rhs: String) -> Bool {
        let left = normalized(lhs)
        let right = normalized(rhs)
        if left == right {
            return true
        }
        if left.contains(right) || right.contains(left) {
            return true
        }

        let leftTokens = semanticTokens(lhs)
        let rightTokens = semanticTokens(rhs)
        guard !leftTokens.isEmpty, !rightTokens.isEmpty else {
            return false
        }

        let overlap = leftTokens.intersection(rightTokens).count
        let ratio = Double(overlap) / Double(max(leftTokens.count, rightTokens.count))
        if ratio >= 0.72 {
            return true
        }

        let smallerCount = min(leftTokens.count, rightTokens.count)
        return smallerCount > 1 && overlap == smallerCount
    }
}
