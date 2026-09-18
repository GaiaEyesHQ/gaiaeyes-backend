package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.network.*
import java.time.ZoneId
import java.util.Locale
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class MigraineSummaryPresentationTest {
    private fun present(detail: MigraineDetail = fixtureDetail(), prompt: CurrentSymptomPendingFollowUp? = null) =
        savedMigraineSummary(detail, EPISODE_ID, prompt, ZoneId.of("America/Chicago"), Locale.US)

    private fun SavedMigraineSummary.section(title: String) = sections.single { it.title == title }
    private fun SavedMigraineSummary.lines() = sections.flatMap { it.entries }.flatMap { it.lines }

    @Test fun repeatedMedicinesKeepOrderExactDecimalAndDistinctRelief() {
        val entries = present().section("Medicines").entries
        assertEquals(listOf("1. Example medicine", "2. Example medicine", "3. Example medicine"), entries.map { it.title })
        assertTrue(entries[0].lines.contains("Dose: 0.1000000000000000000001 mg"))
        assertTrue(entries[0].lines.contains("Reported relief: Unknown"))
        assertTrue(entries[1].lines.contains("Reported relief: No relief"))
        assertTrue(entries[2].lines.contains("Reported relief: Not recorded"))
        assertTrue(entries[1].lines.contains("Dose: Not recorded"))
        assertTrue(entries[0].lines.contains("Note: First distinct entry"))
        assertTrue(entries[1].lines.contains("Note: Second distinct entry"))
    }

    @Test fun showsDisplayTimeAndEverySavedTimeMetadataField() {
        val summary = present()
        val onset = summary.section("Episode").entries.first().lines
        assertEquals("America/Chicago", summary.displayTimezone)
        assertTrue(onset.contains("Started: Sep 15, 2026 at 8:05:06 AM CDT"))
        assertTrue(onset.contains("Started — saved UTC: 2026-09-15T13:05:06.123456Z"))
        assertTrue(onset.contains("Original time: 2026-09-15 08:05:06.123456"))
        assertTrue(onset.contains("Recorded timezone: America/Chicago"))
        assertTrue(onset.contains("Recorded UTC offset (minutes): -300"))
        assertTrue(onset.contains("Timezone source: device"))
        assertFalse(summary.lines().any { "14:00:00" in it }) // lifecycle update is not episode activity
    }

    @Test fun zeroSeverityIsNotMissingAndAbsentEndDoesNotInventDuration() {
        val original = fixtureDetail()
        assertEquals(listOf("0/10"), present().section("Episode").entries.single { it.title == "Severity" }.lines)
        val missing = present(original.copy(episode = original.episode.copy(severity = null)))
        assertEquals(listOf("Not recorded"), missing.section("Episode").entries.single { it.title == "Severity" }.lines)
        assertTrue(missing.lines().contains("Ended: Not recorded"))
        assertTrue(missing.lines().contains("Not available without a recorded end time"))
    }

    @Test fun recordedEndSuppliesDurationWithoutLosingEndMetadata() {
        val original = fixtureDetail()
        val end = original.episode.start.copy(utc = "2026-09-15T14:35:06.123456Z", originalTime = "2026-09-15 09:35:06.123456")
        val summary = present(original.copy(episode = original.episode.copy(state = "resolved", end = end)))
        assertTrue(summary.lines().contains("1 hour, 30 minutes"))
        assertTrue(summary.lines().contains("Ended — saved UTC: 2026-09-15T14:35:06.123456Z"))
    }

    @Test fun earlySignsAndContextRetainSeparateOrderAndNotes() {
        val summary = present()
        assertEquals(listOf("Visual changes", "Sensitivity"), summary.section("Recorded early signs").entries.map { it.title })
        assertTrue(summary.section("Recorded early signs").entries[1].lines.contains("Recorded: Not recorded"))
        val context = summary.section("Recorded context").entries.single()
        assertEquals("Synthetic context", context.title)
        assertTrue(context.lines.contains("Source: user reported"))
        assertTrue(context.lines.contains("Note: Keep context metadata"))
    }

    @Test fun missingStructuredFieldsStayExplicitForLegacyZeroRevision() {
        val original = fixtureDetail()
        val legacy = original.copy(revision = 0, episode = original.episode.copy(
            medicines = emptyList(), contexts = emptyList(), earlySigns = emptyList(), notes = null,
            lifecycle = original.episode.lifecycle.copy(revision = 1)))
        val summary = present(legacy)
        assertFalse(summary.hasStructuredDetails)
        assertEquals("No medicine entries recorded", summary.section("Medicines").emptyMessage)
        assertTrue(summary.section("Medicines").entries.isEmpty())
        assertEquals(listOf("Not recorded"), summary.section("Episode notes").entries.single().lines)
    }

    @Test fun absentFollowUpDoesNotInferCompletionFromProvenance() {
        val lines = present().section("Follow-up").entries.single().lines
        assertEquals(listOf("Follow-up status was not provided in the Current Symptoms list."), lines)
        assertFalse(lines.any { "complete" in it || "answered" in it })
    }

    @Test fun decodesOnlyActualPendingFollowUpAndDisplaysProvidedState() {
        val json = Json { ignoreUnknownKeys = true }
        val item = json.decodeFromString<CurrentSymptomItem>("""{
            "id":"$EPISODE_ID","symptom_code":"MIGRAINE","pending_follow_up":{
              "id":"synthetic-prompt","episode_id":"$EPISODE_ID","symptom_code":"MIGRAINE",
              "question_text":"How is it now?","status":"pending","scheduled_for":"2026-09-15T14:00:00Z",
              "delivered_at":null,"detail_focus":"state","push_delivery_enabled":false}}
        """)
        val lines = present(prompt = item.pendingFollowUp).section("Follow-up").entries.single().lines
        assertTrue(lines.contains("Status: pending"))
        assertTrue(lines.contains("Question: How is it now?"))
        assertTrue(lines.contains("Scheduled: Sep 15, 2026 at 9:00:00 AM CDT"))
        assertTrue(lines.contains("Delivered: Not recorded"))
        assertTrue(lines.contains("From the last Current Symptoms refresh."))
        assertNull(json.decodeFromString<CurrentSymptomItem>("""{"id":"legacy"}""").pendingFollowUp)
    }

    @Test fun rejectsForeignFollowUpAndWrongEpisodeResponse() {
        val prompt = CurrentSymptomPendingFollowUp(episodeId = "99999999-9999-4999-8999-999999999999",
            symptomCode = "MIGRAINE", questionText = "Foreign prompt")
        assertEquals(listOf("Follow-up information is unavailable for this episode."),
            present(prompt = prompt).section("Follow-up").entries.single().lines)
        val detail = fixtureDetail()
        assertThrows(IllegalArgumentException::class.java) {
            present(detail.copy(episode = detail.episode.copy(episodeId = prompt.episodeId)))
        }
    }
}
