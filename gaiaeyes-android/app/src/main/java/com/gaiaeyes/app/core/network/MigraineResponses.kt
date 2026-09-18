package com.gaiaeyes.app.core.network

import java.math.BigDecimal
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.*

// The backend's Decimal is a JSON string (older replies may use a JSON number).
// Never pass either representation through Double, including during comparison.
object MigraineDecimalSerializer : KSerializer<BigDecimal> {
    override val descriptor = PrimitiveSerialDescriptor("MigraineDecimal", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): BigDecimal {
        val element = (decoder as JsonDecoder).decodeJsonElement()
        val text = (element as? JsonPrimitive)?.content
            ?: throw SerializationException("Invalid decimal dose")
        if (!DECIMAL.matches(text)) throw SerializationException("Invalid decimal dose")
        return text.toBigDecimalOrNull() ?: throw SerializationException("Invalid decimal dose")
    }

    override fun serialize(encoder: Encoder, value: BigDecimal) = encoder.encodeString(value.toString())

    private val DECIMAL = Regex("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
}

@Serializable
data class MigraineTimestamp(
    val utc: String,
    @SerialName("timezone_source") val timezoneSource: String,
    @SerialName("original_time") val originalTime: String? = null,
    @SerialName("timezone_name") val timezoneName: String? = null,
    @SerialName("utc_offset_minutes") val utcOffsetMinutes: Int? = null,
) {
    internal fun validate() {
        OffsetDateTime.parse(utc).toInstant()
        require(timezoneSource in setOf("user", "device", "provider", "imported_offset", "unknown"))
        require(utcOffsetMinutes == null || utcOffsetMinutes in -840..840)
        originalTime?.let { shortText(it) }
        timezoneName?.let { shortText(it) }
    }
}

@Serializable
data class MigraineEarlySign(
    val label: String,
    val code: String? = null,
    @SerialName("reported_at") val reportedAt: MigraineTimestamp? = null,
    val notes: String? = null,
) {
    internal fun validate() {
        shortText(label); code?.let { shortText(it) }; reportedAt?.validate(); notes?.let { longText(it) }
    }
}

@Serializable
data class MigraineContext(
    val kind: String,
    val label: String,
    val source: String,
    val code: String? = null,
    @SerialName("observed_at") val observedAt: MigraineTimestamp? = null,
    val notes: String? = null,
) {
    internal fun validate() {
        require(kind in setOf("exposure", "context"))
        require(source in setOf("user_reported", "device", "health_record", "environmental_service", "import"))
        shortText(label); code?.let { shortText(it) }; observedAt?.validate(); notes?.let { longText(it) }
    }
}

// The canonical API has an ordered array, not a medicine ID or a name-keyed map.
// Equal names/times remain separate entries, including their metadata.
@Serializable
data class MigraineMedicine(
    val name: String,
    @SerialName("taken_at") val takenAt: MigraineTimestamp,
    @SerialName("dose_amount") @Serializable(with = MigraineDecimalSerializer::class)
    val doseAmount: BigDecimal? = null,
    @SerialName("dose_unit") val doseUnit: String? = null,
    @SerialName("reported_relief") val reportedRelief: String? = null,
    @SerialName("relief_reported_at") val reliefReportedAt: MigraineTimestamp? = null,
    val notes: String? = null,
) {
    internal fun validate() {
        shortText(name); takenAt.validate()
        require((doseAmount == null) == (doseUnit == null))
        doseAmount?.let { require(it.signum() > 0) }
        doseUnit?.let { shortText(it) }
        require(reportedRelief == null || reportedRelief in setOf("none", "a_little", "some", "a_lot", "complete", "unknown"))
        require(reliefReportedAt == null || reportedRelief != null)
        reliefReportedAt?.validate(); notes?.let { longText(it) }
    }
}

@Serializable
data class MigraineProvenance(
    @SerialName("source_type") val sourceType: String,
    @SerialName("source_platform") val sourcePlatform: String,
    @SerialName("source_provider") val sourceProvider: String? = null,
    @SerialName("external_event_id") val externalEventId: String? = null,
    @SerialName("source_file_hash") val sourceFileHash: String? = null,
    @SerialName("import_run_id") val importRunId: String? = null,
    @SerialName("raw_row_ref") val rawRowRef: String? = null,
    @SerialName("mapping_version") val mappingVersion: String? = null,
)

@Serializable
data class MigraineLifecycle(
    val revision: Long,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("deleted_at") val deletedAt: String? = null,
    @SerialName("deletion_scope") val deletionScope: String? = null,
)

@Serializable
data class MigraineEpisode(
    @SerialName("schema_version") val schemaVersion: String,
    @SerialName("episode_id") val episodeId: String,
    @SerialName("symptom_code") val symptomCode: String,
    val state: String,
    val start: MigraineTimestamp,
    @SerialName("early_signs") val earlySigns: List<MigraineEarlySign>,
    val contexts: List<MigraineContext>,
    val medicines: List<MigraineMedicine>,
    val provenance: MigraineProvenance,
    val lifecycle: MigraineLifecycle,
    @SerialName("symptom_event_id") val symptomEventId: String? = null,
    val end: MigraineTimestamp? = null,
    val severity: Int? = null,
    val notes: String? = null,
)

@Serializable
data class MigraineDetail(
    val revision: Long,
    val episode: MigraineEpisode,
    val changed: Boolean = false,
) {
    internal fun validateFor(episodeId: String) {
        require(sameMigraineId(episode.episodeId, episodeId))
        require(episode.schemaVersion == "1.0" && episode.symptomCode == "MIGRAINE")
        require(episode.state in MIGRAINE_STATES)
        require(revision >= 0 && episode.lifecycle.revision >= 1)
        require((revision == 0L && episode.lifecycle.revision == 1L) ||
            (revision > 0 && revision == episode.lifecycle.revision))
        require(episode.severity == null || episode.severity in 0..10)
        episode.start.validate(); episode.end?.validate()
        require(episode.end == null || episode.state == "resolved")
        episode.end?.let { require(!OffsetDateTime.parse(it.utc).isBefore(OffsetDateTime.parse(episode.start.utc))) }
        episode.earlySigns.forEach { it.validate() }; episode.contexts.forEach { it.validate() }
        episode.medicines.forEach { it.validate() }; episode.notes?.let { longText(it) }
        val life = episode.lifecycle
        require(!OffsetDateTime.parse(life.updatedAt).isBefore(OffsetDateTime.parse(life.createdAt)))
        require(life.deletedAt == null && life.deletionScope == null)
        require(episode.provenance.sourceType in setOf("manual", "siri", "follow_up", "healthkit", "import"))
        shortText(episode.provenance.sourcePlatform)
        if (episode.provenance.sourceType != "import") require(episode.symptomEventId != null)
        episode.symptomEventId?.let { migraineId(it) }
    }
}

@Serializable
internal data class MigraineDetailEnvelope(val ok: Boolean = false, val data: MigraineDetail? = null)

sealed interface MigraineTextChange {
    data object Retain : MigraineTextChange
    data object Clear : MigraineTextChange
    data class Set(val value: String) : MigraineTextChange
}

data class MigraineStructuredEdit(
    val expectedRevision: Long,
    val earlySigns: List<MigraineEarlySign>? = null,
    val contexts: List<MigraineContext>? = null,
    val medicines: List<MigraineMedicine>? = null,
    val notes: MigraineTextChange = MigraineTextChange.Retain,
) {
    val hasChanges: Boolean
        get() = earlySigns != null || contexts != null || medicines != null || notes != MigraineTextChange.Retain

    fun toJson(): JsonObject {
        require(expectedRevision >= 0 && expectedRevision < Long.MAX_VALUE)
        earlySigns?.forEach { it.validate() }; contexts?.forEach { it.validate() }
        medicines?.forEach { it.validate() }
        return buildJsonObject {
            put("expected_revision", expectedRevision)
            earlySigns?.let { entries -> put("early_signs", migraineJson.encodeToJsonElement(entries.map {
                it.copy(reportedAt = it.reportedAt?.withMicrosecondPrecision())
            })) }
            contexts?.let { entries -> put("contexts", migraineJson.encodeToJsonElement(entries.map {
                it.copy(observedAt = it.observedAt?.withMicrosecondPrecision())
            })) }
            medicines?.let { entries -> put("medicines", migraineJson.encodeToJsonElement(entries.map {
                it.copy(takenAt = it.takenAt.withMicrosecondPrecision(),
                    reliefReportedAt = it.reliefReportedAt?.withMicrosecondPrecision())
            })) }
            when (val change = notes) {
                MigraineTextChange.Retain -> Unit
                MigraineTextChange.Clear -> put("notes", JsonNull)
                is MigraineTextChange.Set -> { longText(change.value); put("notes", change.value) }
            }
        }
    }
}

data class MigraineFollowUpRequest(
    val state: String,
    val timestampUtc: String,
    val migraine: MigraineStructuredEdit,
    val detailChoice: String? = null,
    val detailText: String? = null,
    val noteText: String? = null,
    val timeBucket: String? = null,
) {
    // Caller retains the original timestamp; the frozen request uses backend precision.
    // Serialization never reads the clock or changes the caller's metadata.
    fun toJson(): JsonObject {
        require(state in MIGRAINE_STATES)
        val canonicalTimestamp = migraineUtcMicroseconds(timestampUtc)
        return buildJsonObject {
            put("state", state); put("ts_utc", canonicalTimestamp); put("migraine", migraine.toJson())
            detailChoice?.let { put("detail_choice", it) }; detailText?.let { put("detail_text", it) }
            noteText?.let { put("note_text", it) }; timeBucket?.let { put("time_bucket", it) }
        }
    }
}

@Serializable
data class MigraineFollowUpPrompt(
    val id: String,
    @SerialName("episode_id") val episodeId: String,
    @SerialName("symptom_code") val symptomCode: String,
    val status: String,
)

@Serializable
data class MigraineFollowUpResult(
    val prompt: MigraineFollowUpPrompt,
    val episode: CurrentSymptomItem,
    @SerialName("migraine_detail") val migraineDetail: MigraineDetail,
)

@Serializable
internal data class MigraineFollowUpEnvelope(val ok: Boolean = false, val data: MigraineFollowUpResult? = null)

internal val migraineJson = Json { ignoreUnknownKeys = true }
internal val MIGRAINE_STATES = setOf("new", "ongoing", "improving", "worse", "resolved")
internal fun migraineId(value: String): String {
    val canonical = UUID.fromString(value).toString()
    require(canonical.equals(value, ignoreCase = true)) { "A canonical episode or prompt ID is required" }
    return canonical
}
internal fun sameMigraineId(left: String, right: String): Boolean = migraineId(left) == migraineId(right)
private fun shortText(value: String) { require(value.trim().codePointCount(0, value.trim().length) in 1..160) }
private fun longText(value: String) { require(value.trim().codePointCount(0, value.trim().length) in 1..4000) }

// Python's canonical datetime retains microseconds, truncating finer fractions.
// Normalize before freezing outbound JSON and use the same rule for acknowledgements.
// Copy only utc: original_time, zone/source/offset metadata and caller objects survive.
private fun migraineUtcMicroseconds(value: String): String =
    OffsetDateTime.parse(value).toInstant().truncatedTo(ChronoUnit.MICROS).toString()
private fun MigraineTimestamp.withMicrosecondPrecision(): MigraineTimestamp =
    copy(utc = migraineUtcMicroseconds(utc))

// Match only submitted fields, against a validated next-revision acknowledgement.
// Decimal scale and normalized UTC spelling may change on the backend; metadata
// and ordered duplicate entries must still match. A GET never calls this a save.
internal fun migraineEditAcknowledged(edit: JsonObject, saved: MigraineDetail): Boolean {
    if (saved.revision != edit.getValue("expected_revision").jsonPrimitive.long + 1) return false
    val actual = migraineJson.encodeToJsonElement(saved.episode).jsonObject
    return edit.filterKeys { it != "expected_revision" }.all { (key, value) ->
        normalizeMigraineValue(key, value) == normalizeMigraineValue(key, actual[key] ?: JsonNull)
    }
}

private fun normalizeMigraineValue(key: String, value: JsonElement): JsonElement = when (value) {
    JsonNull -> JsonNull
    is JsonObject -> JsonObject(value.mapValues { (name, item) -> normalizeMigraineValue(name, item) })
    is JsonArray -> JsonArray(value.map { normalizeMigraineValue(key, it) })
    is JsonPrimitive -> when (key) {
        "utc" -> JsonPrimitive(migraineUtcMicroseconds(value.content))
        "dose_amount" -> JsonPrimitive(BigDecimal(value.content).stripTrailingZeros().toString())
        else -> if (value.isString) JsonPrimitive(value.content.trim()) else value
    }
}

class MigraineConflictException : IllegalStateException("The saved migraine revision changed; review it before saving again")
class MigraineUnavailableException(cause: Throwable? = null) : IllegalStateException("Structured migraine details are unavailable", cause)
class MigraineEpisodeNotFoundException : IllegalStateException("The migraine episode was not found")
class MigraineRejectedException(val statusCode: Int) : IllegalStateException("The migraine request was rejected ($statusCode)")
class MigraineInvalidResponseException(cause: Throwable? = null) : IllegalStateException("The server returned invalid migraine details", cause)
class MigraineUnconfirmedWriteException(cause: Throwable? = null) : IllegalStateException("The migraine write is unconfirmed; retain the original request for review", cause)
