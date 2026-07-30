package com.gaiaeyes.app.core.network

import kotlinx.serialization.Serializable

@Serializable
data class PatternsResponse(
    val ok: Boolean = false,
    val partial: Boolean = false,
    val generatedAt: String? = null,
    val disclaimer: String? = null,
    val strongestPatterns: List<PatternCard> = emptyList(),
    val emergingPatterns: List<PatternCard> = emptyList(),
    val bodySignalsPatterns: List<PatternCard> = emptyList(),
    val voiceSemantics: PatternsVoiceSemantics? = null,
)

@Serializable
data class PatternCard(
    val signalKey: String = "",
    val signal: String = "",
    val outcomeKey: String = "",
    val outcome: String = "",
    val explanation: String = "",
    val confidence: String? = null,
    val sampleSize: Int? = null,
    val lagHours: Int? = null,
    val lagLabel: String? = null,
    val lastSeenAt: String? = null,
    val relativeLift: Double? = null,
    val exposedRate: Double? = null,
    val unexposedRate: Double? = null,
    val exposedDays: Int? = null,
    val usedToday: Boolean = false,
    val usedTodayLabel: String? = null,
    val voiceSemantic: PatternCardVoiceSemantic? = null,
)

@Serializable
data class PatternsVoiceSemantics(
    val overview: PatternsOverviewSemantic? = null,
)

@Serializable
data class PatternsOverviewSemantic(
    val interpretation: PatternsOverviewInterpretation? = null,
)

@Serializable
data class PatternsOverviewInterpretation(
    val headerSummary: String? = null,
    val strongestSubtitle: String? = null,
    val strongestEmpty: String? = null,
    val emergingSubtitle: String? = null,
    val emergingEmpty: String? = null,
    val emergingPending: String? = null,
    val bodySubtitle: String? = null,
    val bodyEmpty: String? = null,
    val bodyPending: String? = null,
)

@Serializable
data class PatternCardVoiceSemantic(
    val interpretation: PatternCardInterpretation? = null,
)

@Serializable
data class PatternCardInterpretation(
    val headerSummary: String? = null,
    val evidenceSummary: String? = null,
    val baselineSummary: String? = null,
    val activeTodaySummary: String? = null,
)
