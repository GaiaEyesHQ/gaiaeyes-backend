package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.CurrentSymptomItem
import com.gaiaeyes.app.core.network.DriverItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GuidePresentationTest {
    @Test
    fun deduplicatesSimilarLowStimulationSuggestions() {
        val model = guideSupportModel(
            symptoms = listOf(
                CurrentSymptomItem(label = "Migraine"),
                CurrentSymptomItem(label = "Light sensitivity"),
                CurrentSymptomItem(label = "Headache"),
            ),
            drivers = emptyList(),
        )

        assertEquals(1, model.suggestions.count { it.contains("Lower light") })
        assertEquals("Make the day a little easier", model.title)
        assertTrue(model.introduction.contains("Migraine and Light sensitivity"))
    }

    @Test
    fun limitsSuggestionsAndKeepsDistinctThemes() {
        val model = guideSupportModel(
            symptoms = listOf(
                CurrentSymptomItem(label = "Migraine"),
                CurrentSymptomItem(label = "Brain fog"),
                CurrentSymptomItem(label = "Joint pain"),
                CurrentSymptomItem(label = "Anxious"),
            ),
            drivers = listOf(DriverItem(label = "Pressure swing")),
        )

        assertEquals(3, model.suggestions.size)
        assertEquals(model.suggestions.size, model.suggestions.distinct().size)
    }

    @Test
    fun pollUsesCurrentSymptomWhenAvailable() {
        val symptoms = listOf(CurrentSymptomItem(label = "Migraine"))

        assertEquals("Did migraine stand out today?", guidePollPrompt(symptoms))
        assertEquals(listOf("Yes", "A little", "Not really"), guidePollChoices(symptoms))
        assertFalse(guidePollPrompt(emptyList()).contains("migraine"))
    }
}
