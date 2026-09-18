package com.gaiaeyes.app.visualharness

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModelProvider
import com.gaiaeyes.app.core.auth.*
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.core.notifications.NotificationNavigationCoordinator
import com.gaiaeyes.app.core.quicklog.QuickLogCoordinator
import com.gaiaeyes.app.data.*
import com.gaiaeyes.app.ui.*
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme
import com.google.firebase.FirebaseApp
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
import java.util.Collections
import java.util.UUID
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.serialization.json.*

/** Actual app composable, HomeViewModel.Factory, account collector and repositories. */
class IsolatedMainAppActivity : ComponentActivity() {
    internal lateinit var fixture: MainAppFixture
        private set
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        fixture = MainAppFixture(this)
        setContent { GaiaEyesTheme {
            with(fixture) {
                GaiaEyesApp(auth, body, dashboard, location, health, healthConnect, home, explore, journal,
                    notifications, navigation, outlook, patterns, profile, quickLog)
            }
        } }
    }
    override fun onDestroy() {
        super.onDestroy()
        if (!isChangingConfigurations) fixture.close()
    }
}

internal class MainAppFixture(activity: ComponentActivity) {
    private val context = activity.applicationContext
    val auth = SyntheticMainAuth(context)
    val server = MainAppServer(context.assets.open("migraine-detail.json").bufferedReader().use { it.readText() })
    val engine = SyntheticEngine(server::handle)
    val client = HttpClient(engine) {
        expectSuccess = false; followRedirects = false
        install(HttpTimeout); install(ContentNegotiation) { json(migraineJson) }
        defaultRequest { url("https://example.invalid") }
    }
    val api = GaiaApiClient("https://example.invalid", client, client)
    val quickLog = QuickLogCoordinator()
    val navigation = NotificationNavigationCoordinator()
    val body = BodyRepository(auth, api, BodyCache(context))
    val dashboard = DashboardRepository(auth, api, DashboardCache(context))
    val location = DeviceLocationRepository(context)
    val health = HealthRepository(api)
    val healthConnect = HealthConnectRepository(context, auth, api, HealthSampleQueue(context), { error("No background work in synthetic medicine checks") })
    val home = HomeContextRepository(auth, api, HomeContextCache(context))
    val explore = ExploreRepository(api, ExploreCache(context))
    val journal = JournalRepository(auth, api, JournalWriteQueue(context), { error("No background work in synthetic medicine checks") })
    val notifications = NotificationRepository(context, auth, api)
    val outlook = OutlookRepository(auth, api, OutlookCache(context))
    val patterns = PatternsRepository(auth, api, PatternsCache(context))
    val profile = ProfileRepository(auth, api)
    // Same default store/key and production factory used by GaiaEyesApp's viewModel().
    val viewModel = ViewModelProvider(activity, HomeViewModel.Factory(auth, body, dashboard, location, health,
        healthConnect, home, explore, journal, notifications, outlook, patterns, profile, quickLog))[HomeViewModel::class.java]
    init { check(!auth.isConfigured); check(FirebaseApp.getApps(context).isEmpty()) }
    fun route(family: String = "symptom_followups") {
        check(navigation.handleIntent(Intent(Intent.ACTION_VIEW, Uri.parse("gaiaeyes://mission-control?family=$family"))))
    }
    fun ledger() = buildJsonObject {
        val ui = viewModel.uiState.value; val medicine = viewModel.migraineMedicine.state.value
        put("data", "synthetic only"); put("actual_home_view_model", viewModel.javaClass.name)
        put("auth_event", auth.authState.value.toString()); put("observed_auth", ui.authState.toString())
        put("current_account", auth.currentAccountId()); put("account_a", auth.accountA); put("account_b", auth.accountB)
        put("is_signing_out", ui.isSigningOut); put("onboarding", ui.onboardingStatus.name); put("selected_page", ui.selectedPage.name)
        put("medicine_phase", medicine.phase.name); put("medicine_session", medicine.sessionId)
        put("summary_account", viewModel.savedMigraineSummary.value.accountId)
        put("current_symptoms_account", ui.currentSymptoms?.accountId)
        put("summary_detail", viewModel.savedMigraineSummary.value.detail?.let { migraineJson.encodeToJsonElement(it) } ?: JsonNull)
        put("saved_receipt_present", medicine.saved != null)
        put("pending_medicine_request", medicine.pendingRequest?.toJson() ?: JsonNull)
        put("pending_navigation", navigation.pending.value?.destination?.name)
        put("pending_navigation_id", navigation.pending.value?.id)
        put("sign_out_gate_completed", auth.signOutGate?.isCompleted)
        put("sign_out_returned", auth.signOutReturned); put("sign_out_failed", auth.failSignOut)
        put("auth_message", ui.authMessage)
        put("token_reads", auth.tokenReads); put("sign_outs", auth.signOuts)
        put("requests", JsonArray(server.requests.toList().map(::JsonPrimitive)))
        put("patches", JsonArray(server.patches.toList()))
        put("mutations", server.mutations); put("released_late_responses", server.lateResponses)
        put("server_details", JsonObject(server.details.mapValues { migraineJson.encodeToJsonElement(it.value) }))
        put("supabase_client_absent", !auth.isConfigured); put("firebase_apps", FirebaseApp.getApps(context).size)
    }
    fun close() { auth.releaseAll(); server.releaseAll(); client.close(); engine.close() }
}

/** Blank base configuration creates no Supabase client, storage or SDK session. */
internal class SyntheticMainAuth(context: Context) : AuthRepository(context, "", "") {
    val accountA = "synthetic-a-${UUID.randomUUID()}"
    val accountB = "synthetic-b-${UUID.randomUUID()}"
    private var account: String? = accountA
    override val authState = MutableStateFlow<AuthState>(signedIn(accountA))
    var tokenReads = 0; var signOuts = 0
    var nextTokenGate: CompletableDeferred<Unit>? = null
    var signOutGate: CompletableDeferred<Unit>? = null
    var failSignOut = false
    var emitSignedOut = true
    @Volatile var signOutReturned = false
    @Volatile var tokenHeld = false
    @Volatile var signOutHeld = false
    private val gates = mutableListOf<CompletableDeferred<Unit>>()
    fun signedIn(id: String) = AuthState.SignedIn(id, "synthetic@example.invalid", false)
    fun replace(id: String?) { account = id; authState.value = id?.let(::signedIn) ?: AuthState.SignedOut }
    fun transient(value: AuthState) { authState.value = value }
    override fun currentAccountId(): String? = account
    override suspend fun accessToken(): String {
        tokenReads++; val captured = requireNotNull(account)
        nextTokenGate?.let { gate ->
            nextTokenGate = null; gates += gate; tokenHeld = true
            withContext(NonCancellable) { gate.await() }
        }
        return "synthetic-token:$captured"
    }
    override suspend fun refreshAccessToken() = accessToken()
    override suspend fun signOut() {
        signOuts++
        signOutGate?.let { gate -> gates += gate; signOutHeld = true; withContext(NonCancellable) { gate.await() } }
        if (failSignOut) error("Synthetic sign-out failure")
        if (emitSignedOut) replace(null)
        signOutReturned = true
    }
    fun releaseAll() { gates.forEach { it.complete(Unit) }; nextTokenGate?.complete(Unit); signOutGate?.complete(Unit) }
}

internal class MainAppServer(raw: String) {
    val original = migraineJson.decodeFromJsonElement<MigraineDetail>(migraineJson.parseToJsonElement(raw).jsonObject.getValue("data"))
    val details = Collections.synchronizedMap(mutableMapOf<String, MigraineDetail>())
    val requests = Collections.synchronizedList(mutableListOf<String>())
    val patches = Collections.synchronizedList(mutableListOf<JsonObject>())
    private val committed = mutableMapOf<String, JsonObject>()
    @Volatile var mutations = 0
    @Volatile var lateResponses = 0
    @Volatile var patchHeld = false
    @Volatile var readHeld = false
    @Volatile var currentSymptomsHeld = false
    var patchGate: CompletableDeferred<Unit>? = null
    var readGate: CompletableDeferred<Unit>? = null
    var currentSymptomsGate: CompletableDeferred<Unit>? = null
    var replyAfterGate: Reply? = null
    var badReceipt = false
    var loseReceipt = false
    private val gates = Collections.synchronizedList(mutableListOf<CompletableDeferred<Unit>>())
    fun detail(account: String) = details.getOrPut(account) { original }
    suspend fun handle(data: HttpRequestData): Reply {
        check(data.url.host == "example.invalid")
        val path = data.url.encodedPath
        val account = data.headers[HttpHeaders.Authorization]?.removePrefix("Bearer synthetic-token:")
        requests += "${data.method.value} $path ${account ?: "public"}"
        if (path == "/health") return Reply(body = """{"ok":true,"db":true,"time":"$SYNTHETIC_NOW"}""")
        if (path.endsWith("/migraine-detail")) {
            check(path == "/v1/symptoms/current/$SYNTHETIC_EPISODE/migraine-detail")
            val owner = requireNotNull(account).also { check(it.startsWith("synthetic-")) }
            val before = detail(owner)
            if (data.method == HttpMethod.Get) {
                val reply = envelope(before)
                readGate?.let { gate -> gates += gate; readHeld = true; withContext(NonCancellable) { gate.await() }; lateResponses++ }
                return reply
            }
            check(data.method == HttpMethod.Patch)
            val text = when (val body = data.body) {
                is OutgoingContent.ByteArrayContent -> body.bytes().decodeToString()
                is OutgoingContent.ReadChannelContent -> body.readFrom().readRemaining().readText()
                else -> error("Unexpected synthetic request body")
            }
            val request = migraineJson.parseToJsonElement(text).jsonObject
            check(request.keys == setOf("expected_revision", "medicines"))
            patches += buildJsonObject { put("account", owner); put("body", text) }
            val revision = request.getValue("expected_revision").jsonPrimitive.long
            if (before.revision == revision) {
                details[owner] = before.copy(revision = revision + 1, episode = before.episode.copy(
                    medicines = migraineJson.decodeFromJsonElement(request.getValue("medicines")), lifecycle = before.episode.lifecycle.copy(revision = revision + 1)))
                mutations++; committed[owner] = request
            } else if (committed[owner] != request || before.revision != revision + 1) return Reply(409, "{}")
            val saved = detail(owner)
            val response = envelope(if (badReceipt) saved.copy(episode = saved.episode.copy(medicines = emptyList())) else saved)
            patchGate?.let { gate -> gates += gate; patchHeld = true; withContext(NonCancellable) { gate.await() }; lateResponses++ }
            replyAfterGate?.let { return it }
            if (loseReceipt) { loseReceipt = false; throw IOException("Synthetic receipt lost") }
            return response
        }
        check(data.method == HttpMethod.Get) { "Unexpected write $path" }
        if (path == "/v1/symptoms/current") currentSymptomsGate?.let { gate ->
            gates += gate; currentSymptomsHeld = true; withContext(NonCancellable) { gate.await() }
        }
        return when (path) {
            "/v1/profile/preferences" -> Reply(body = """{"ok":true,"preferences":{"onboarding_completed":true}}""")
            "/v1/profile/location" -> Reply(body = """{"ok":true,"location":null}""")
            "/v1/profile/notifications" -> Reply(body = """{"ok":true,"preferences":{"enabled":false}}""")
            "/v1/dashboard/gauges" -> Reply(body = """{"day":"2026-09-17","gauges":{}}""")
            "/v1/users/me/drivers" -> Reply(body = """{"ok":true,"drivers":[]}""")
            "/v1/symptoms/current" -> Reply(body = migraineJson.encodeToString(CurrentSymptomsEnvelope(true,
                CurrentSymptomsResponse(items = listOf(CurrentSymptomItem(SYNTHETIC_EPISODE, "MIGRAINE", "Synthetic migraine", 0,
                    loggedAt = "2026-09-17T12:00:00Z", currentState = "ongoing"))))))
            else -> Reply(503, """{"detail":"Unrelated synthetic surface unavailable"}""")
        }
    }
    private fun envelope(value: MigraineDetail) = Reply(body = buildJsonObject { put("ok", true); put("data", migraineJson.encodeToJsonElement(value)) }.toString())
    fun releaseAll() { gates.toList().forEach { it.complete(Unit) }; patchGate?.complete(Unit); readGate?.complete(Unit); currentSymptomsGate?.complete(Unit) }
}
