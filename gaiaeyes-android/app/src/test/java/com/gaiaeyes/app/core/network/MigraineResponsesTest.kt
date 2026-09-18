package com.gaiaeyes.app.core.network

import java.math.BigDecimal
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class MigraineResponsesTest {
    @Test
    fun readsBackendDecimalStringWithoutRoundingAndKeepsDistinctEntries() {
        val detail = fixtureDetail()
        detail.validateFor(EPISODE_ID)
        assertEquals(0, detail.episode.severity)
        assertEquals(3, detail.episode.medicines.size)
        assertEquals(BigDecimal("0.1000000000000000000001"), detail.episode.medicines[0].doseAmount)
        assertEquals(listOf("unknown", "none", null), detail.episode.medicines.map { it.reportedRelief })
        assertNull(detail.episode.medicines[1].doseAmount)
        assertNull(detail.episode.medicines[1].doseUnit)
        assertEquals(-300, detail.episode.start.utcOffsetMinutes)
        assertEquals("America/Chicago", detail.episode.start.timezoneName)
        assertEquals("2026-09-15 08:05:06.123456", detail.episode.start.originalTime)
    }

    @Test
    fun acceptsLegacyNumericDecimalAndMissingSeverityWithoutConvertingToZero() {
        val raw = fixtureText().replace("\"0.1000000000000000000001\"", "0.1000000000000000000001")
            .replace("\"severity\": 0", "\"severity\": null")
        val detail = requireNotNull(migraineJson.decodeFromString<MigraineDetailEnvelope>(raw).data)
        detail.validateFor(EPISODE_ID)
        assertEquals(BigDecimal("0.1000000000000000000001"), detail.episode.medicines[0].doseAmount)
        assertNull(detail.episode.severity)
    }

    @Test
    fun retainClearAndSetRemainDifferentWireOperations() {
        assertEquals("{\"expected_revision\":0}", MigraineStructuredEdit(0).toJson().toString())
        val clear = MigraineStructuredEdit(3, earlySigns = emptyList(), contexts = emptyList(),
            medicines = emptyList(), notes = MigraineTextChange.Clear).toJson()
        assertEquals(migraineJson.parseToJsonElement(
            """{"expected_revision":3,"early_signs":[],"contexts":[],"medicines":[],"notes":null}"""), clear)
        assertEquals("Keep this", MigraineStructuredEdit(3, notes = MigraineTextChange.Set("Keep this"))
            .toJson().getValue("notes").jsonPrimitive.content)
    }

    @Test
    fun serializesExactDoseAndAllEntryMetadataWithoutInventingMedicineIds() {
        val original = fixtureDetail().episode
        val edit = MigraineStructuredEdit(2, original.earlySigns, original.contexts, original.medicines)
        val wire = edit.toJson()
        val medicines = wire.getValue("medicines").jsonArray
        assertEquals(3, medicines.size)
        assertEquals("0.1000000000000000000001", medicines[0].jsonObject.getValue("dose_amount").jsonPrimitive.content)
        assertTrue(medicines[0].jsonObject.getValue("dose_amount").jsonPrimitive.isString)
        assertFalse(medicines[1].jsonObject.containsKey("dose_amount"))
        assertFalse(medicines[2].jsonObject.containsKey("reported_relief"))
        assertTrue(medicines.none { it.jsonObject.containsKey("id") })
        assertEquals(migraineJson.encodeToJsonElement(original.contexts), wire["contexts"])
        assertEquals(migraineJson.encodeToJsonElement(original.earlySigns), wire["early_signs"])
    }

    @Test
    fun followUpUsesCanonicalFieldsAndStableCallerSuppliedTime() {
        val request = MigraineFollowUpRequest("improving", "2026-09-15T14:30:00.123456Z",
            MigraineStructuredEdit(3, medicines = emptyList(), notes = MigraineTextChange.Clear),
            "some", "Synthetic detail", "Synthetic note", "later")
        val expected = migraineJson.parseToJsonElement("""{"state":"improving","ts_utc":"2026-09-15T14:30:00.123456Z","migraine":{"expected_revision":3,"medicines":[],"notes":null},"detail_choice":"some","detail_text":"Synthetic detail","note_text":"Synthetic note","time_bucket":"later"}""")
        assertEquals(expected, request.toJson())
        assertEquals(request.toJson(), request.toJson())
    }

    @Test
    fun truncatesAllStructuredUtcFieldsBeforeSnapshotAndPreservesOriginalMetadata() {
        val nanoUtc = "2026-09-15T13:05:06.123456789Z"
        val originalTime = "2026-09-15 08:05:06.123456789"
        val metadataText = fixtureText().replace("2026-09-15 08:05:06.123456", originalTime)
        val original = requireNotNull(migraineJson.decodeFromString<MigraineDetailEnvelope>(
            metadataText.replace("2026-09-15T13:05:06.123456Z", nanoUtc)).data).episode
        val canonical = requireNotNull(migraineJson.decodeFromString<MigraineDetailEnvelope>(metadataText).data).episode
        val request = MigraineStructuredEdit(2, original.earlySigns, original.contexts, original.medicines)

        val frozen = request.toJson()

        assertEquals(migraineJson.encodeToJsonElement(canonical.earlySigns), frozen["early_signs"])
        assertEquals(migraineJson.encodeToJsonElement(canonical.contexts), frozen["contexts"])
        assertEquals(migraineJson.encodeToJsonElement(canonical.medicines), frozen["medicines"])
        assertEquals(3, frozen.getValue("medicines").jsonArray.size)
        assertEquals("0.1000000000000000000001", frozen.getValue("medicines").jsonArray[0]
            .jsonObject.getValue("dose_amount").jsonPrimitive.content)
        assertEquals(nanoUtc, original.medicines[0].takenAt.utc)
        assertEquals(originalTime, original.medicines[0].takenAt.originalTime)
        assertEquals(frozen, request.toJson())
    }

    @Test
    fun followUpTimestampTruncatesWithoutRoundingAndCanonicalizesEquivalentOffsets() {
        val cases = listOf(
            "2026-09-15T13:05:06.123456789Z" to "2026-09-15T13:05:06.123456Z",
            "2026-09-15T08:05:06.123456789-05:00" to "2026-09-15T13:05:06.123456Z",
            "2026-09-15T13:05:06.123456Z" to "2026-09-15T13:05:06.123456Z",
            "2026-09-15T13:05:06.123456000Z" to "2026-09-15T13:05:06.123456Z",
            "2026-09-15T13:05:06.000000999Z" to "2026-09-15T13:05:06Z",
            "2026-09-15T13:05:06.999999999Z" to "2026-09-15T13:05:06.999999Z",
            "1969-12-31T23:59:59.999999999Z" to "1969-12-31T23:59:59.999999Z",
        )
        for ((original, expected) in cases) {
            val request = MigraineFollowUpRequest("ongoing", original, MigraineStructuredEdit(2))
            val frozen = request.toJson()
            assertEquals(expected, frozen.getValue("ts_utc").jsonPrimitive.content)
            assertEquals(original, request.timestampUtc)
            assertEquals(frozen, request.toJson())
        }
    }

    @Test
    fun microsecondAcknowledgementStillRejectsChangedInstantOrAnyTimestampMetadata() {
        val detail = fixtureDetail()
        val nano = detail.episode.medicines.map { it.copy(
            takenAt = it.takenAt.copy(utc = "2026-09-15T08:05:06.123456789-05:00")) }
        val edit = MigraineStructuredEdit(2, medicines = nano).toJson()
        assertTrue(migraineEditAcknowledged(edit, detail))
        val time = detail.episode.medicines[0].takenAt
        val changedTimes = listOf(
            time.copy(utc = "2026-09-15T13:05:06.123457Z"),
            time.copy(originalTime = "different original time"),
            time.copy(timezoneName = "America/New_York"),
            time.copy(utcOffsetMinutes = -240),
            time.copy(timezoneSource = "user"),
        )
        for (changedTime in changedTimes) {
            val changed = detail.episode.medicines.toMutableList()
            changed[0] = changed[0].copy(takenAt = changedTime)
            assertFalse(migraineEditAcknowledged(edit, detail.copy(episode = detail.episode.copy(medicines = changed))))
        }
    }

    @Test
    fun zeroSeverityIsValidButZeroDoseAndIncompleteDoseAreRejected() {
        fixtureDetail().validateFor(EPISODE_ID)
        val medicine = fixtureDetail().episode.medicines.first()
        listOf(medicine.copy(doseAmount = BigDecimal.ZERO), medicine.copy(doseAmount = BigDecimal("-1")),
            medicine.copy(doseAmount = null), medicine.copy(doseUnit = null),
            medicine.copy(reportedRelief = null, reliefReportedAt = medicine.takenAt)).forEach {
            assertThrows(IllegalArgumentException::class.java) { MigraineStructuredEdit(3, medicines = listOf(it)).toJson() }
        }
    }

    @Test
    fun rejectsNonfiniteMalformedOrBooleanDecimalValues() {
        listOf("\"NaN\"", "\"Infinity\"", "true", "{}", "\"1 mg\"").forEach { value ->
            assertThrows(Exception::class.java) {
                migraineJson.decodeFromString<MigraineDetailEnvelope>(
                    fixtureText().replace("\"0.1000000000000000000001\"", value))
            }
        }
    }

    @Test
    fun revisionZeroAllowsOnlyUnstoredLifecycleOneAndWrongIdentityFails() {
        val detail = fixtureDetail()
        detail.copy(revision = 0, episode = detail.episode.copy(lifecycle = detail.episode.lifecycle.copy(revision = 1)))
            .validateFor(EPISODE_ID)
        assertThrows(IllegalArgumentException::class.java) { detail.copy(revision = 0).validateFor(EPISODE_ID) }
        assertThrows(IllegalArgumentException::class.java) { detail.copy(revision = 2).validateFor(EPISODE_ID) }
        assertThrows(IllegalArgumentException::class.java) { detail.validateFor(PROMPT_ID) }
    }

    @Test
    fun acknowledgmentAllowsOnlySemanticTimestampAndDecimalNormalization() {
        val detail = fixtureDetail()
        val medicines = detail.episode.medicines.map { it.copy(
            takenAt = it.takenAt.copy(utc = "2026-09-15T08:05:06.123456-05:00"),
            doseAmount = it.doseAmount?.setScale(25),
        ) }
        val edit = MigraineStructuredEdit(2, medicines = medicines).toJson()
        assertTrue(migraineEditAcknowledged(edit, detail))
        val changed = detail.episode.medicines.toMutableList()
        changed[0] = changed[0].copy(takenAt = changed[0].takenAt.copy(timezoneSource = "unknown"))
        assertFalse(migraineEditAcknowledged(edit, detail.copy(episode = detail.episode.copy(medicines = changed))))
        assertFalse(migraineEditAcknowledged(edit, detail.copy(episode = detail.episode.copy(medicines = detail.episode.medicines.reversed()))))
        assertFalse(migraineEditAcknowledged(edit, detail.copy(revision = 4)))
    }

    @Test
    fun legacyCurrentSymptomPayloadRemainsUnchangedIncludingSeverityZero() {
        val request = CurrentSymptomUpdateRequest(state = "ongoing", severity = 0,
            noteText = "Synthetic legacy note", timestampUtc = "2026-09-15T14:00:00Z")
        assertEquals(migraineJson.parseToJsonElement("""{"state":"ongoing","severity":0,"note_text":"Synthetic legacy note","ts_utc":"2026-09-15T14:00:00Z"}"""),
            migraineJson.parseToJsonElement(migraineJson.encodeToString(request)))
        assertEquals("{}", migraineJson.encodeToString(CurrentSymptomUpdateRequest()))
    }
}

internal const val EPISODE_ID = "11111111-1111-4111-8111-111111111111"
internal const val PROMPT_ID = "33333333-3333-4333-8333-333333333333"
internal fun fixtureText(): String = requireNotNull(MigraineResponsesTest::class.java.getResource("/migraine-detail.json")).readText()
internal fun fixtureDetail(): MigraineDetail = requireNotNull(migraineJson.decodeFromString<MigraineDetailEnvelope>(fixtureText()).data)
