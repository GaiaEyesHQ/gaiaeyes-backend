package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.DriverItem

internal data class GuideSupportModel(
    val title: String,
    val introduction: String,
    val suggestions: List<String>,
)

internal fun guideSupportModel(
    symptoms: List<CurrentSymptomItem>,
    drivers: List<DriverItem>,
): GuideSupportModel {
    val activeLabels = symptoms
        .map { it.label.trim() }
        .filter(String::isNotEmpty)
        .distinctBy { it.lowercase() }

    val suggestions = linkedMapOf<String, String>()
    activeLabels.forEach { label ->
        val normalized = label.lowercase()
        when {
            normalized.containsAny("migraine", "headache", "light sensitivity", "sinus") ->
                suggestions.putIfAbsent(
                    "low-stimulation",
                    "Lower light, sound, and extra stimulation where you can.",
                )
            normalized.containsAny(
                "fatigue",
                "drained",
                "brain fog",
                "poor sleep",
                "restless sleep",
                "insomnia",
                "low energy",
            ) -> suggestions.putIfAbsent(
                "pacing",
                "Break tasks into smaller blocks and leave more room for recovery.",
            )
            normalized.containsAny("pain", "stiff", "joint", "ache") ->
                suggestions.putIfAbsent(
                    "gentle-movement",
                    "Choose gentler movement and a lighter task load if that feels better.",
                )
            normalized.containsAny("anxious", "wired", "palpitation", "restless") ->
                suggestions.putIfAbsent(
                    "slower-reset",
                    "Try a slower pace or a brief breathing reset before adding more input.",
                )
        }
    }

    if (suggestions.isEmpty()) {
        suggestions["steady-basics"] = "Keep hydration, meals, and effort steady today."
    }
    if (drivers.isNotEmpty() && suggestions.size < 3) {
        suggestions["compare-context"] =
            "Keep ${drivers.first().label.trim().ifEmpty { "today’s signals" }} in view as you compare how today feels."
    }

    return GuideSupportModel(
        title = when {
            activeLabels.isNotEmpty() -> "Make the day a little easier"
            drivers.isNotEmpty() -> "Keep your pace steady"
            else -> "A steady starting point"
        },
        introduction = when {
            activeLabels.isNotEmpty() ->
                "You logged ${naturalLanguageList(activeLabels.take(2))}. Here are a few low-effort ways to support the day."
            drivers.isNotEmpty() ->
                "Current signals can add context, but how you feel comes first."
            else ->
                "Nothing urgent stands out. A few steady basics can still help."
        },
        suggestions = suggestions.values.take(3),
    )
}

internal fun guidePollPrompt(symptoms: List<CurrentSymptomItem>): String {
    val label = symptoms.firstOrNull()?.label?.trim().orEmpty()
    return if (label.isNotEmpty()) {
        "Did ${label.lowercase()} stand out today?"
    } else {
        "Did today feel better or worse than yesterday?"
    }
}

internal fun guidePollChoices(symptoms: List<CurrentSymptomItem>): List<String> {
    return if (symptoms.isNotEmpty()) {
        listOf("Yes", "A little", "Not really")
    } else {
        listOf("Better", "About the same", "Worse")
    }
}

private fun String.containsAny(vararg needles: String): Boolean {
    return needles.any(::contains)
}

private fun naturalLanguageList(items: List<String>): String {
    return when (items.size) {
        0 -> "today’s symptoms"
        1 -> items.first()
        else -> "${items.first()} and ${items.last()}"
    }
}
