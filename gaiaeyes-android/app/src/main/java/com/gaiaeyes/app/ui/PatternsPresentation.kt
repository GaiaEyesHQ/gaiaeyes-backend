package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.PatternCard
import com.gaiaeyes.app.core.network.PatternsResponse
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

data class PatternSectionModel(
    val title: String,
    val subtitle: String,
    val emptyMessage: String,
    val cards: List<PatternCard>,
)

fun visiblePatternCards(
    cards: List<PatternCard>,
    showsAll: Boolean,
    collapsedLimit: Int = 3,
): List<PatternCard> {
    return if (showsAll) cards else cards.take(collapsedLimit.coerceAtLeast(0))
}

fun patternOverviewText(patterns: PatternsResponse): String {
    return patterns.voiceSemantics
        ?.overview
        ?.interpretation
        ?.headerSummary
        .cleanOrNull()
        ?: "Patterns compare your logs and health stats with repeating signals in your history."
}

fun patternSections(patterns: PatternsResponse): List<PatternSectionModel> {
    val semantic = patterns.voiceSemantics?.overview?.interpretation
    return listOf(
        PatternSectionModel(
            title = "Clearest Patterns",
            subtitle = semantic?.strongestSubtitle.cleanOrNull()
                ?: "The clearest repeats in your history so far.",
            emptyMessage = semantic?.strongestEmpty.cleanOrNull()
                ?: "No clear patterns yet. Keep logging to help this section fill in.",
            cards = patterns.strongestPatterns,
        ),
        PatternSectionModel(
            title = "Body Signals",
            subtitle = semantic?.bodySubtitle.cleanOrNull()
                ?: "Wearable-based patterns appear here when the overlap is strong enough.",
            emptyMessage = semantic?.bodyEmpty.cleanOrNull()
                ?: "No body-signal patterns are standing out yet.",
            cards = patterns.bodySignalsPatterns,
        ),
        PatternSectionModel(
            title = "Still Taking Shape",
            subtitle = semantic?.emergingSubtitle.cleanOrNull()
                ?: "Possible repeats that still need more overlap before they feel reliable.",
            emptyMessage = semantic?.emergingEmpty.cleanOrNull()
                ?: "Nothing is clearly emerging yet. More overlap will help this section fill in.",
            cards = patterns.emergingPatterns,
        ),
    )
}

fun patternExplanation(card: PatternCard): String {
    return card.voiceSemantic
        ?.interpretation
        ?.headerSummary
        .cleanOrNull()
        ?: card.explanation.cleanOrNull()
        ?: "This repeat is still being compared with your history."
}

fun patternEvidence(card: PatternCard): String {
    card.voiceSemantic
        ?.interpretation
        ?.evidenceSummary
        .cleanOrNull()
        ?.let { return it }

    val lag = card.lagLabel.cleanOrNull() ?: "same day"
    val sample = card.sampleSize ?: card.exposedDays ?: 0
    val lift = card.relativeLift ?: 0.0
    return when {
        lift > 0.0 && sample > 0 ->
            "${String.format(Locale.US, "%.1fx", lift)} more common when exposed • $sample exposed days • Lag $lag"
        sample > 0 -> "$sample exposed days • Lag $lag"
        else -> "Lag $lag"
    }
}

fun patternBaseline(card: PatternCard): String {
    card.voiceSemantic
        ?.interpretation
        ?.baselineSummary
        .cleanOrNull()
        ?.let { return it }

    val exposed = ((card.exposedRate ?: 0.0) * 100).roundToInt()
    val baseline = ((card.unexposedRate ?: 0.0) * 100).roundToInt()
    val lastSeen = formatPatternDate(card.lastSeenAt)
    return buildList {
        add("When exposed: $exposed%")
        add("When not exposed: $baseline%")
        if (lastSeen != null) add("Last seen: $lastSeen")
    }.joinToString(" • ")
}

private fun formatPatternDate(raw: String?): String? {
    val value = raw.cleanOrNull() ?: return null
    return runCatching {
        OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("MMM d, yyyy"))
    }.getOrNull() ?: value
}

private fun String?.cleanOrNull(): String? = this?.trim()?.takeIf(String::isNotEmpty)
