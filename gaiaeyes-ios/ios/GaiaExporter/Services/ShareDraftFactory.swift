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
        let card = ShareCardModel(
            shareType: .signalSnapshot,
            layout: .signalSnapshot,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Signal Snapshot",
            title: title,
            subtitle: interpretation,
            primaryText: nil,
            valueText: value,
            stateText: state,
            bullets: Array(bullets.prefix(3)),
            highlights: [],
            note: nil,
            footer: footer(updatedAt),
            sourceLine: sourceLine,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.signalSnapshot(
            mode: mode,
            tone: tone,
            title: title,
            state: state,
            value: value,
            interpretation: interpretation,
            bullets: bullets
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
        let chips = [
            evidenceCount.map {
                ShareCardChip(id: "evidence", label: "Evidence", value: "\($0) events")
            },
            lagText.map {
                ShareCardChip(id: "lag", label: "Lag", value: $0)
            },
            confidence.map {
                ShareCardChip(id: "confidence", label: "Confidence", value: $0)
            }
        ].compactMap { $0 }

        let card = ShareCardModel(
            shareType: .personalPattern,
            layout: .personalPattern,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Pattern observed",
            title: relationship,
            subtitle: explanation,
            primaryText: explanation,
            valueText: nil,
            stateText: nil,
            bullets: [],
            highlights: chips,
            note: nil,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.personalPattern(
            mode: mode,
            relationship: relationship,
            evidenceCount: evidenceCount,
            lagText: lagText,
            confidence: confidence,
            explanation: explanation
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
        let chips = [
            ShareCardChip(id: "leading", label: "Leading", value: leading)
        ] + supporting.prefix(2).enumerated().map { index, value in
            ShareCardChip(id: "supporting_\(index)", label: "Also in play", value: value)
        }

        let card = ShareCardModel(
            shareType: .dailyState,
            layout: .dailyState,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: title,
            title: leading,
            subtitle: supporting.first,
            primaryText: interpretation,
            valueText: nil,
            stateText: nil,
            bullets: Array(supporting.dropFirst().prefix(2)),
            highlights: chips,
            note: interpretation,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.dailyState(
            mode: mode,
            title: title,
            leading: leading,
            supporting: supporting,
            interpretation: interpretation
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
        let chips = [
            severity.map { ShareCardChip(id: "severity", label: "Severity", value: $0) },
            earthDirectedNote.map { ShareCardChip(id: "direction", label: "Context", value: $0) }
        ].compactMap { $0 }

        let card = ShareCardModel(
            shareType: .event,
            layout: .event,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: "Event Update",
            title: title,
            subtitle: context,
            primaryText: context,
            valueText: nil,
            stateText: severity,
            bullets: Array(bullets.prefix(3)),
            highlights: chips,
            note: earthDirectedNote,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.event(
            mode: mode,
            title: title,
            severity: severity,
            context: context,
            bullets: bullets,
            earthDirectedNote: earthDirectedNote
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
        let chips = [
            ShareCardChip(id: "primary", label: "Primary", value: primaryDriver)
        ] + supportingDrivers.prefix(2).enumerated().map { index, driver in
            ShareCardChip(id: "support_\(index)", label: "Supporting", value: driver)
        }

        let card = ShareCardModel(
            shareType: .outlook,
            layout: .outlook,
            format: .square,
            background: background,
            accentLevel: accent,
            eyebrow: windowTitle,
            title: primaryDriver,
            subtitle: supportingDrivers.first,
            primaryText: actionLine,
            valueText: nil,
            stateText: nil,
            bullets: Array(affectedDomains.prefix(3)),
            highlights: chips,
            note: actionLine,
            footer: footer(updatedAt),
            sourceLine: nil,
            branding: .gaiaEyes
        )
        let captions = ShareCaptionEngine.outlook(
            mode: mode,
            windowTitle: windowTitle,
            primaryDriver: primaryDriver,
            supportingDrivers: supportingDrivers,
            affectedDomains: affectedDomains,
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

    private static func footer(_ updatedAt: String?) -> String {
        guard let updatedAt, !updatedAt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return "Gaia Eyes • gaiaeyes.app"
        }
        return "Gaia Eyes • \(updatedAt)"
    }
}
