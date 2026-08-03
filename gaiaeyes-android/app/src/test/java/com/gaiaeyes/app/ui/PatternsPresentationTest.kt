package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.PatternCard
import com.gaiaeyes.app.core.network.PatternCardInterpretation
import com.gaiaeyes.app.core.network.PatternCardVoiceSemantic
import com.gaiaeyes.app.core.network.PatternsOverviewInterpretation
import com.gaiaeyes.app.core.network.PatternsOverviewSemantic
import com.gaiaeyes.app.core.network.PatternsResponse
import com.gaiaeyes.app.core.network.PatternsVoiceSemantics
import org.junit.Assert.assertEquals
import org.junit.Test

class PatternsPresentationTest {
    @Test
    fun prefersServerSuppliedPatternLanguage() {
        val card = PatternCard(
            explanation = "Fallback explanation",
            relativeLift = 2.0,
            sampleSize = 20,
            lagLabel = "next day",
            voiceSemantic = PatternCardVoiceSemantic(
                interpretation = PatternCardInterpretation(
                    headerSummary = "Personal pattern summary",
                    evidenceSummary = "Personal evidence summary",
                    baselineSummary = "Personal baseline summary",
                ),
            ),
        )

        assertEquals("Personal pattern summary", patternExplanation(card))
        assertEquals("Personal evidence summary", patternEvidence(card))
        assertEquals("Personal baseline summary", patternBaseline(card))
    }

    @Test
    fun buildsTheThreeSharedPatternSections() {
        val response = PatternsResponse(
            ok = true,
            strongestPatterns = listOf(PatternCard(outcome = "Migraine")),
            voiceSemantics = PatternsVoiceSemantics(
                overview = PatternsOverviewSemantic(
                    interpretation = PatternsOverviewInterpretation(
                        bodySubtitle = "Wearable repeats",
                    ),
                ),
            ),
        )

        val sections = patternSections(response)

        assertEquals(
            listOf("Clearest Patterns", "Body Signals", "Still Taking Shape"),
            sections.map { it.title },
        )
        assertEquals("Wearable repeats", sections[1].subtitle)
        assertEquals("Migraine", sections[0].cards.single().outcome)
    }

    @Test
    fun fallsBackToEvidenceAndBaselineValues() {
        val card = PatternCard(
            relativeLift = 1.8,
            sampleSize = 15,
            lagLabel = "same day",
            exposedRate = 0.42,
            unexposedRate = 0.21,
            lastSeenAt = "2026-07-29T13:00:00Z",
        )

        assertEquals(
            "1.8x more common when exposed • 15 exposed days • Lag same day",
            patternEvidence(card),
        )
        assertEquals(
            "When exposed: 42% • When not exposed: 21% • Last seen: Jul 29, 2026",
            patternBaseline(card),
        )
    }

    @Test
    fun collapsesEachPatternSectionToThreeCardsUntilExpanded() {
        val cards = (1..5).map { PatternCard(outcome = "Pattern $it") }

        assertEquals(
            listOf("Pattern 1", "Pattern 2", "Pattern 3"),
            visiblePatternCards(cards, showsAll = false).map { it.outcome },
        )
        assertEquals(cards, visiblePatternCards(cards, showsAll = true))
    }
}
