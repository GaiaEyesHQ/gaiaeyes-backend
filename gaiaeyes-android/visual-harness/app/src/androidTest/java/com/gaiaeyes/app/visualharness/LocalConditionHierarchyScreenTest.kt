package com.gaiaeyes.app.visualharness

import android.content.Intent
import android.graphics.Bitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.TextLayoutResult
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

class LocalConditionHierarchyScreenTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private var scenario: ActivityScenario<IsolatedMainAppActivity>? = null
    @After fun close() { scenario?.close() }
    private fun click(text: String) { compose.onAllNodesWithText(text).onLast().performClick(); compose.waitForIdle() }
    private fun frame(text: String) {
        val node = compose.onAllNodesWithText(text).onFirst(); node.performScrollTo()
        val top = node.fetchSemanticsNode().boundsInRoot.top
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange)).onFirst()
            .performSemanticsAction(SemanticsActions.ScrollBy) { it(0f, top - 80f) }
        compose.waitForIdle()
    }
    private fun base(): JSONObject = JSONObject(instrumentation.targetContext.assets.open("g037-local.json").bufferedReader().readText()).apply {
        put("asof", Instant.now().toString())
        getJSONObject("weather").put("obs_time", Instant.now().minusSeconds(120).toString())
        getJSONObject("allergens").put("forecast_day", LocalDate.now(ZoneOffset.UTC).toString())
            .put("updated_at", Instant.now().minusSeconds(3600).toString()).put("weed_index", 0)
    }
    private fun replace(body: JSONObject) {
        val marker = Instant.now().toString(); body.put("asof", marker)
        scenario!!.onActivity { it.fixture.server.readOverrides["/v1/local/check"] = Reply(body = body.toString()); it.fixture.viewModel.refreshLocalWeather() }
        compose.waitUntil(10000) {
            var ready = false
            scenario!!.onActivity { ready = it.fixture.viewModel.uiState.value.localWeather?.local?.asof == marker && !it.fixture.viewModel.uiState.value.isLoadingLocalWeather }
            ready
        }
    }
    private fun launch(body: JSONObject, large: Boolean = false) {
        val klass = if (large) IsolatedMainAppLargeFontActivity::class.java else IsolatedMainAppActivity::class.java
        scenario = ActivityScenario.launch(Intent(instrumentation.targetContext, klass).putExtra("g037", true))
        compose.waitUntil(20000) { var ready = false; scenario!!.onActivity { ready = it.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size == 5 }; ready }
        click("Explore")
        compose.waitUntil(20000) { var ready = false; scenario!!.onActivity { ready = it.fixture.viewModel.uiState.value.localWeather?.local != null && !it.fixture.viewModel.uiState.value.isLoadingExplore }; ready }
        replace(body); compose.onAllNodesWithText("Local Conditions").onFirst().performScrollTo(); click("Local Conditions")
    }
    private fun readable(text: String) {
        val layouts = mutableListOf<TextLayoutResult>()
        compose.onAllNodesWithText(text, useUnmergedTree = true).onFirst()
            .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
        assertTrue("Expected measured text for $text", layouts.isNotEmpty())
        if (layouts.any { it.hasVisualOverflow }) {
            val name = "layout-overflow-" + text.replace(Regex("[^A-Za-z0-9]"), "_")
            capture(name)
            File(instrumentation.targetContext.filesDir, "g051/$name-layout.txt").writeText(layouts.joinToString("\n") {
                "text=$text size=${it.size} lines=${it.lineCount} widthOverflow=${it.didOverflowWidth} heightOverflow=${it.didOverflowHeight} firstBottom=${it.getLineBottom(0)} style=${it.layoutInput.style}"
            })
        }
        assertTrue("Text must wrap without clipping: $text", layouts.none { it.hasVisualOverflow })
    }
    private fun contains(text: String) = compose.onAllNodes(hasText(text, substring = true)).onFirst().assertExists()
    private fun capture(name: String) {
        compose.waitForIdle(); instrumentation.waitForIdleSync(); android.os.SystemClock.sleep(250)
        val dir = File(instrumentation.targetContext.filesDir, "g051").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        File(dir, "$name-semantics.txt").writeText(compose.onRoot().printToString())
        scenario!!.onActivity { assertEquals(0, it.fixture.server.mutations); File(dir, "$name-ledger.json").writeText(it.fixture.ledger().toString()) }
    }
    private fun populated(large: Boolean) {
        launch(base(), large); val prefix = if (large) "large" else "normal"
        frame("Weather"); readable("96.8°F"); readable("37%"); readable("0%"); contains("+1.8°F in 24h")
        compose.onNodeWithText("Weather").assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading))
        capture("$prefix-weather-pressure")
        if (large) {
            frame("Barometric pressure"); readable("1011.5 hPa"); contains("-2.4 hPa in 24h • falling")
            capture("large-pressure")
        }
        frame("Air quality"); readable("52 AQI"); contains("Moderate • PM2.5")
        contains("Observation time and source not supplied"); capture("$prefix-air-quality")
        frame("Allergens"); readable("3 / 5"); readable("Moderate"); readable("0 / 5")
        contains("Main contributor: Grass pollen"); contains("Forecast, not a direct observation.")
        contains("Source: google-pollen:forecast"); compose.onNodeWithText("Mold").assertDoesNotExist()
        capture("$prefix-allergen-types")
        frame("Daily forecast"); compose.onNodeWithText("Show all 7 days").assertExists()
        frame("Moon"); compose.onNodeWithText("66.7%").assertExists()
        frame("Close"); click("Close"); compose.onAllNodesWithText("Explore").onFirst().assertExists()
    }
    @Test fun normalHierarchyPreservesReadingsAndNavigation() { populated(false) }
    @Test fun largeHierarchyWrapsTypesAndCategories() { populated(true) }
    @Test fun missingReadingsStaySeparateFromRealZero() {
        val body = base().put("weather", JSONObject().put("humidity_pct", 0)).put("allergens", JSONObject())
        body.put("air", JSONObject().put("aqi", 0).put("category", "Good"))
        launch(body); frame("Weather"); readable("Unavailable"); readable("0%")
        contains("Observation time unavailable"); capture("missing-weather-zero-humidity")
        frame("Air quality"); readable("0 AQI"); contains("Good"); capture("zero-aqi-empty-pollen")
        frame("Allergens"); compose.onNodeWithText("No pollen readings are available for this location in this update. Missing data does not mean a low pollen level.").assertIsDisplayed()
        capture("empty-pollen")
    }
    @Test fun largePollenKeepsHistoricalFutureAndUnknownWarningsVisible() {
        val old = base(); old.getJSONObject("allergens").put("forecast_day", "2026-01-01").put("updated_at", "2026-01-01T01:00:00Z")
        launch(old, true); frame("Allergens"); contains("Last reported"); contains("Stale"); contains("Not today's pollen forecast.")
        capture("large-historical-pollen")
        frame("Pollen index", substring = true); capture("large-historical-provenance")
        val future = base(); future.getJSONObject("allergens").put("forecast_day", LocalDate.now(ZoneOffset.UTC).plusDays(1).toString())
            .put("updated_at", Instant.now().plusSeconds(86400).toString())
        replace(future); frame("Allergens"); contains("Forecast"); contains("Update time is in the future; freshness unverified")
        capture("large-future-pollen")
        frame("Pollen index", substring = true); capture("large-future-provenance")
        val unknown = base().put("allergens", JSONObject().put("overall_level", "high").put("grass_level", "moderate")
            .put("source", "google-pollen:forecast").put("updated_at", "invalid").put("forecast_day", "invalid"))
        replace(unknown); frame("Allergens"); readable("High"); readable("Moderate")
        contains("Update time unavailable; freshness unverified"); contains("Forecast date could not be verified.")
        capture("large-category-unverified-date")
    }
    private fun frame(text: String, substring: Boolean) {
        val node = compose.onNode(hasText(text, substring = substring)); node.performScrollTo()
        compose.waitForIdle()
    }
}
