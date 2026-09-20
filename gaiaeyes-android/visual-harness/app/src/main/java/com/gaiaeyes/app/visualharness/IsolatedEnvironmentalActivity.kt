package com.gaiaeyes.app.visualharness

import android.content.Context
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import com.gaiaeyes.app.ui.*
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme
import java.time.Instant
import kotlinx.serialization.json.JsonPrimitive

/** Synthetic measurements only, using the exact production detail destination. No real services. */
open class IsolatedEnvironmentalActivity : ComponentActivity() {
    protected open val fontScale = 1f
    internal var refreshes = 0
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base.createConfigurationContext(Configuration(base.resources.configuration).apply { fontScale = this@IsolatedEnvironmentalActivity.fontScale }))
    }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val detail = ExploreDetail.valueOf(intent.getStringExtra("detail") ?: "SCHUMANN")
        val mode = intent.getStringExtra("scenario") ?: "populated"
        setContent {
            var scenario by remember { mutableStateOf(mode) }
            GaiaEyesTheme { ExploreDetailScreen(detail, environmentFixture(scenario), false, null,
                onBack = { finish() }, onRefresh = { refreshes++; scenario = "populated" }) }
        }
    }
}
class IsolatedEnvironmentalLargeFontActivity : IsolatedEnvironmentalActivity() { override val fontScale = 1.6f }

internal fun environmentFixture(mode: String): ExploreSnapshot {
    val now = Instant.now()
    val ts = now.minusSeconds(if (mode == "stale") 172800 else 300).toString()
    val old = now.minusSeconds(10800).toString()
    val history = (0..24).map { i -> EnvironmentPoint(now.minusSeconds((24 - i) * 900L + 300).toString(), 7.75 + (i % 5) * .03) }
    val payload = if (mode == "empty") ExplorePayload() else ExplorePayload(
        schumann = SchumannLatestResponse(true, ts, SchumannHarmonics(f0 = 7.89), SchumannAmplitude(.116, .016, .314, .017), SchumannQuality("cumiana", true, 1.0)),
        tomsk = TomskLatestResponse(true, old, "tomsk", true, 1.0, mapOf("F1" to 7.75, "F2" to 13.77, "F3" to 19.19, "F4" to 24.31)),
        schumannSeries = SchumannSeriesResponse(true, history.map { SchumannSeriesRow(it.t, SchumannHarmonics(f0 = it.v), SchumannAmplitude(total0To20 = it.v!! / 50)) }),
        ulf = UlfLatestResponse(UlfContext(ts, listOf("BOU", "CMO"), 20.22, .753, 24.41, "Quiet", .753, listOf("low_history")), listOf(
            UlfStation("BOU", ts, "H", .0054, index = 18.5), UlfStation("CMO", ts, "H", .0149, index = 21.9))),
        ulfSeries = UlfSeriesResponse(history.mapIndexed { i, point -> UlfContext(timestamp = point.t, intensity = 10.0 + i) }),
        magnetosphere = MagnetosphereResponse(true, MagnetosphereData(ts, MagnetosphereKpis(10.4, "quiet", "quiet", "low", 5.2, 2.7),
            MagnetosphereSolarWind(6.8, 442.0, -3.1), MagnetosphereSeries(history.mapIndexed { i, point -> EnvironmentPoint(point.t, 9.5 + i * .04) }))),
        spaceHistory = SpaceHistoryResponse(true, SpaceHistoryData(mapOf(
            "kp" to history.map { listOf(JsonPrimitive(it.t), JsonPrimitive(2.7)) },
            "sw" to history.map { listOf(JsonPrimitive(it.t), JsonPrimitive(442.0)) },
            "bz" to history.map { listOf(JsonPrimitive(it.t), JsonPrimitive(-3.1)) },
        ))),
        sourceErrors = if (mode == "stale") mapOf("Schumann Resonance" to "request_failed", "ULF" to "request_failed", "Magnetosphere" to "sign_in_required") else emptyMap(),
    )
    return ExploreSnapshot(payload, if (mode == "stale") ExploreSource.CACHE else ExploreSource.NETWORK, now.toEpochMilli())
}
