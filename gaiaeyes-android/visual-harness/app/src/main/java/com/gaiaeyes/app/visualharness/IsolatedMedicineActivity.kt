package com.gaiaeyes.app.visualharness

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.MigraineMedicineRepository
import com.gaiaeyes.app.ui.*
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestData
import io.ktor.http.*
import io.ktor.http.content.OutgoingContent
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.*
import java.io.IOException
import java.time.ZoneId
import java.util.Collections
import kotlinx.coroutines.*
import kotlinx.serialization.json.*

/** Actual production summary -> medicine editor -> summary; no HomeViewModel/startup. */
class IsolatedMedicineActivity : ComponentActivity() {
    internal lateinit var fixture: MedicineFixture
        private set
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        fixture = MedicineFixture(assets.open("migraine-detail.json").bufferedReader().use { it.readText() })
        setContent { GaiaEyesTheme {
            val state by fixture.summary.state.collectAsState()
            SavedMigraineSummaryScreen(state, fixture.summary::close, fixture.summary::retry, medicineEditor = fixture.controller)
        } }
        fixture.summary.open("synthetic-account", CurrentSymptomItem(SYNTHETIC_EPISODE, "MIGRAINE"))
    }
    override fun onDestroy() { fixture.close(); super.onDestroy() }
}

internal class MedicineFixture(raw: String) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    var account: String? = "synthetic-account"
    val server = MedicineServer(raw)
    val original = server.detail
    val engine = SyntheticEngine(server::handle)
    val client = HttpClient(engine) {
        expectSuccess = false; followRedirects = false
        install(HttpTimeout); install(ContentNegotiation) { json(migraineJson) }
        defaultRequest { url("https://example.invalid") }
    }
    val api = GaiaApiClient("https://example.invalid", client, client)
    var tokenReads = 0; var refreshes = 0
    val summary = MigraineSummaryStore(scope, { account }, { _, id -> api.migraineDetail("synthetic-token", id) })
    val repository = MigraineMedicineRepository({ account }, { tokenReads++; "synthetic-token" }, api::migraineDetail, api::updateMigraineDetail, { account = null })
    val controller = MigraineMedicineController(scope, { account }, summary.state, repository,
        { selection, request, saved -> summary.acceptMedicineEdit(selection, request, saved).also { if (it) refreshes++ } },
        { SYNTHETIC_NOW }, { ZoneId.of("America/Chicago") })
    fun ledger() = buildJsonObject {
        put("data", "synthetic only"); put("phase", controller.state.value.phase.name)
        put("pending_prompt", JsonNull); put("gets", server.gets); put("patches", server.bodies.size)
        put("mutations", server.mutations); put("refreshes", refreshes); put("token_reads", tokenReads)
        put("original_detail", migraineJson.encodeToJsonElement(original))
        put("server_detail", migraineJson.encodeToJsonElement(server.detail))
        put("summary_detail", summary.state.value.detail?.let { migraineJson.encodeToJsonElement(it) } ?: JsonNull)
        put("request_bodies", JsonArray(server.bodies.map(::JsonPrimitive)))
        put("draft_medicines", migraineJson.encodeToJsonElement(controller.state.value.medicines.map { it.value }))
        put("saved_receipt_present", controller.state.value.saved != null)
        put("reviewed_detail", controller.state.value.reviewed?.let { migraineJson.encodeToJsonElement(it) } ?: JsonNull)
        put("pending_request", controller.state.value.pendingRequest?.toJson() ?: JsonNull)
    }
    fun close() { controller.clear(); summary.close(); scope.cancel(); client.close(); engine.close() }
}

internal class MedicineServer(raw: String) {
    @Volatile var detail = migraineJson.decodeFromJsonElement<MigraineDetail>(migraineJson.parseToJsonElement(raw).jsonObject.getValue("data"))
    @Volatile var reply: Reply? = null
    @Volatile var loseReceipt = false
    @Volatile var gets = 0
    @Volatile var mutations = 0
    val bodies = Collections.synchronizedList(mutableListOf<String>())
    private var committed: JsonObject? = null
    suspend fun handle(data: HttpRequestData): Reply {
        check(data.url.host == "example.invalid")
        check(data.headers[HttpHeaders.Authorization] == "Bearer synthetic-token")
        check(data.url.encodedPath == "/v1/symptoms/current/$SYNTHETIC_EPISODE/migraine-detail")
        if (data.method == HttpMethod.Get) { gets++; return Reply(body = envelope()) }
        check(data.method == HttpMethod.Patch)
        val text = when (val body = data.body) {
            is OutgoingContent.ByteArrayContent -> body.bytes().decodeToString()
            is OutgoingContent.ReadChannelContent -> body.readFrom().readRemaining().readText()
            else -> error("Unexpected synthetic body")
        }
        val request = migraineJson.parseToJsonElement(text).jsonObject
        check(request.keys == setOf("expected_revision", "medicines"))
        bodies += text; reply?.let { return it }
        val revision = request.getValue("expected_revision").jsonPrimitive.long
        if (revision == detail.revision) {
            detail = detail.copy(revision = revision + 1, episode = detail.episode.copy(
                medicines = migraineJson.decodeFromJsonElement(request.getValue("medicines")), lifecycle = detail.episode.lifecycle.copy(revision = revision + 1)))
            mutations++; committed = request
        } else if (committed != request || detail.revision != revision + 1) return Reply(409, "{}")
        if (loseReceipt) { loseReceipt = false; throw IOException("Synthetic lost receipt") }
        return Reply(body = envelope())
    }
    private fun envelope() = buildJsonObject { put("ok", true); put("data", migraineJson.encodeToJsonElement(detail)) }.toString()
}
