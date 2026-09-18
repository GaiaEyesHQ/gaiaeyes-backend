package com.gaiaeyes.app.visualharness

import android.content.Context
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import com.gaiaeyes.app.ui.*
import io.ktor.client.HttpClient
import io.ktor.client.engine.*
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.HttpTimeoutCapability
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.http.content.OutgoingContent
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.date.GMTDate
import io.ktor.utils.io.*
import java.io.IOException
import java.time.ZoneId
import java.util.Collections
import kotlinx.coroutines.*
import kotlinx.serialization.json.*

internal const val SYNTHETIC_EPISODE = "11111111-1111-4111-8111-111111111111"
internal const val SYNTHETIC_PROMPT = "33333333-3333-4333-8333-333333333333"
internal const val SYNTHETIC_NOW = "2026-09-17T12:00:00.123456Z"

internal class SyntheticFixture(context: Context, scenario: String) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    var account: String? = "synthetic-account"
    val server = SyntheticServer(context.assets.open("migraine-detail.json").bufferedReader().use { it.readText() })
    val original = server.detail
    val engine = SyntheticEngine(server::handle)
    val client = HttpClient(engine) {
        expectSuccess = false; followRedirects = false
        install(HttpTimeout)
        install(ContentNegotiation) { json(migraineJson) }
        defaultRequest { url("https://example.invalid") }
    }
    // Both clients are injected. No default OkHttp transport can be selected here.
    val api = GaiaApiClient("https://example.invalid", client, client)
    var tokenReads = 0
    var signOuts = 0
    var clockReads = 0
    val refreshes = mutableListOf<String>()
    var writeGate: CompletableDeferred<Unit>? = null
    @Volatile var writeReached = false
    val repository = MigraineFollowUpRepository(
        currentAccountId = { account },
        accessToken = { tokenReads++; "synthetic-token" },
        read = { token, id -> api.migraineDetail(token, id) },
        respond = { token, id, prompt, request ->
            val result = api.respondMigraineFollowUp(token, id, prompt, request)
            writeReached = true
            writeGate?.let { withContext(NonCancellable) { it.await() } }
            result
        },
        signOut = { signOuts++; account = null },
    )
    var item = CurrentSymptomItem(id = SYNTHETIC_EPISODE, symptomCode = "MIGRAINE", currentState = "ongoing",
        pendingFollowUp = CurrentSymptomPendingFollowUp(SYNTHETIC_PROMPT, SYNTHETIC_EPISODE, "MIGRAINE", "How is your migraine now?", "pending"))
    var snapshot = makeSnapshot()
    val controller = MigraineFollowUpFormController(scope, { account }, { snapshot }, repository,
        { refreshes += it }, { clockReads++; SYNTHETIC_NOW }, { ZoneId.of("America/Chicago") })

    init {
        if (scenario == "initial_unavailable") server.getReply = Reply(503, """{"detail":"structured migraine detail storage is not installed"}""")
        if (scenario == "missing_severity") server.detail = server.detail.copy(episode = server.detail.episode.copy(severity = null))
    }
    private fun makeSnapshot() = CurrentSymptomsSnapshot(requireNotNull(account),
        CurrentSymptomsResponse(items = listOf(item)), HomeContextSource.NETWORK, 0)
    fun replaceAccount(value: String?) {
        account = value
        controller.accountChanged(value)
        if (value != null) snapshot = makeSnapshot()
    }
    fun actions() = controller.actions(controller.ui.value.sessionId)
    fun ledger(): JsonObject = buildJsonObject {
        val state = controller.state.value
        put("data", "synthetic only")
        put("phase", state.phase.name)
        put("account", account)
        put("token_reads", tokenReads); put("clock_reads", clockReads); put("sign_outs", signOuts)
        put("gets", server.getCount); put("posts", server.postBodies.size); put("mutations", server.mutations)
        put("refreshes", JsonArray(refreshes.map(::JsonPrimitive)))
        put("original_detail", migraineJson.encodeToJsonElement(original))
        put("server_detail", migraineJson.encodeToJsonElement(server.detail))
        put("request_bodies", JsonArray(server.postBodies.map(::JsonPrimitive)))
        state.draft?.let {
            put("draft_response_timestamp", it.responseTimestampUtc)
            put("draft_medicines", migraineJson.encodeToJsonElement(it.medicines.map { row -> row.value }))
            put("draft_state", it.answers.state)
        }
        state.reviewed?.let { put("reviewed_detail", migraineJson.encodeToJsonElement(it)) }
        state.saved?.let { put("saved_detail", migraineJson.encodeToJsonElement(it.migraineDetail)) }
        put("pending_request", state.pendingRequest?.toJson() ?: JsonNull)
        put("saved_receipt_present", state.saved != null)
        put("editor_present", controller.ui.value.medicine != null)
    }
    fun close() {
        controller.clear(); writeGate?.complete(Unit); scope.cancel(); client.close(); engine.close()
    }
}

internal data class Reply(val status: Int = 200, val body: String)

/** In-process deterministic protocol fixture, never a socket server. */
internal class SyntheticServer(fixture: String) {
    @Volatile var detail = migraineJson.decodeFromJsonElement<MigraineDetail>(migraineJson.parseToJsonElement(fixture).jsonObject.getValue("data"))
    @Volatile var getReply: Reply? = null
    @Volatile var postReply: Reply? = null
    @Volatile var getCount = 0
    @Volatile var mutations = 0
    @Volatile var loseNextReceipt = false
    val postBodies = Collections.synchronizedList(mutableListOf<String>())
    private var committedRequest: JsonObject? = null

    suspend fun handle(data: HttpRequestData): Reply {
        check(data.url.host == "example.invalid")
        check(data.headers[HttpHeaders.Authorization] == "Bearer synthetic-token")
        if (data.method == HttpMethod.Get) {
            check(data.url.encodedPath == "/v1/symptoms/current/$SYNTHETIC_EPISODE/migraine-detail")
            getCount++
            return getReply ?: Reply(body = buildJsonObject {
                put("ok", true); put("data", migraineJson.encodeToJsonElement(detail))
            }.toString())
        }
        check(data.method == HttpMethod.Post)
        check(data.url.encodedPath == "/v1/symptoms/follow-ups/$SYNTHETIC_PROMPT/respond")
        val body = when (val outgoing = data.body) {
            is OutgoingContent.ByteArrayContent -> outgoing.bytes().decodeToString()
            is OutgoingContent.ReadChannelContent -> outgoing.readFrom().readRemaining().readText()
            else -> error("Unexpected in-process body type")
        }
        postBodies += body
        postReply?.let { return it }
        val request = migraineJson.parseToJsonElement(body).jsonObject
        val edit = request.getValue("migraine").jsonObject
        val revision = edit.getValue("expected_revision").jsonPrimitive.long
        if (detail.revision == revision) {
            val previous = detail.episode
            detail = detail.copy(revision = revision + 1, episode = previous.copy(
                state = request.getValue("state").jsonPrimitive.content,
                medicines = edit["medicines"]?.let { migraineJson.decodeFromJsonElement<List<MigraineMedicine>>(it) } ?: previous.medicines,
                earlySigns = edit["early_signs"]?.let { migraineJson.decodeFromJsonElement<List<MigraineEarlySign>>(it) } ?: previous.earlySigns,
                contexts = edit["contexts"]?.let { migraineJson.decodeFromJsonElement<List<MigraineContext>>(it) } ?: previous.contexts,
                notes = if (edit.containsKey("notes")) edit["notes"]?.jsonPrimitive?.contentOrNull else previous.notes,
                lifecycle = previous.lifecycle.copy(revision = revision + 1),
            ))
            mutations++; committedRequest = request
        } else if (committedRequest != request || detail.revision != revision + 1) return Reply(409, "{}")
        if (loseNextReceipt) { loseNextReceipt = false; throw IOException("Synthetic lost acknowledgement after in-process commit") }
        return Reply(body = """{"ok":true,"data":{"prompt":{"id":"$SYNTHETIC_PROMPT","episode_id":"$SYNTHETIC_EPISODE","symptom_code":"MIGRAINE","status":"answered"},"episode":{"id":"$SYNTHETIC_EPISODE","symptom_code":"MIGRAINE","current_state":"${detail.episode.state}","pending_follow_up":null},"migraine_detail":${migraineJson.encodeToJsonElement(detail)}}}""")
    }
}

internal class SyntheticEngine(private val handle: suspend (HttpRequestData) -> Reply) : HttpClientEngineBase("g026-in-process-only") {
    override val config = HttpClientEngineConfig()
    override val supportedCapabilities = setOf(HttpTimeoutCapability)
    @OptIn(InternalAPI::class)
    override suspend fun execute(data: HttpRequestData): HttpResponseData {
        val reply = handle(data)
        return HttpResponseData(HttpStatusCode.fromValue(reply.status), GMTDate(),
            Headers.build { append(HttpHeaders.ContentType, "application/json") },
            HttpProtocolVersion.HTTP_1_1, ByteReadChannel(reply.body), callContext())
    }
}
