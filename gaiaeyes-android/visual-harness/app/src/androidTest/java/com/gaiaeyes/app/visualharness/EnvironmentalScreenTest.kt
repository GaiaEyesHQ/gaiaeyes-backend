package com.gaiaeyes.app.visualharness

import android.content.Intent
import android.graphics.Bitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import java.io.File
import org.junit.*
import org.junit.Assert.*

class EnvironmentalScreenTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private var scenario: ActivityScenario<IsolatedEnvironmentalActivity>? = null
    @After fun close() { scenario?.close() }
    private fun launch(detail: String, mode: String = "populated", large: Boolean = false) {
        val klass = if (large) IsolatedEnvironmentalLargeFontActivity::class.java else IsolatedEnvironmentalActivity::class.java
        scenario = ActivityScenario.launch(Intent(instrumentation.targetContext, klass).putExtra("detail", detail).putExtra("scenario", mode))
        compose.waitForIdle()
    }
    private fun scroll(text: String) { compose.onNodeWithText(text).performScrollTo().assertIsDisplayed() }
    private fun chart(title: String, name: String) {
        compose.onNode(hasContentDescription(title, substring = true)).performScrollTo().assertIsDisplayed()
        capture(name)
    }
    private fun capture(name: String) {
        compose.waitForIdle(); instrumentation.waitForIdleSync()
        val directory = File(instrumentation.targetContext.filesDir, "g035").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(directory, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
        File(directory, "$name-semantics.txt").writeText(compose.onRoot().printToString())
    }
    @Test fun schumannShowsSeparateStationsAndHistory() {
        launch("SCHUMANN")
        scroll("7.89 Hz"); capture("schumann-primary")
        scroll("Tomsk resonance"); capture("schumann-tomsk-stale")
        compose.onNodeWithText("Stale").assertExists()
        chart("Fundamental history", "schumann-history")
        scroll("Amplitude history · 0–20 Hz")
    }
    @Test fun ulfShowsRegionalAndStationMeasurementsAndProvisionalNote() {
        launch("ULF")
        scroll("Quiet"); capture("ulf-regional")
        compose.onNode(hasText("Baseline still building", substring = true)).performScrollTo().assertIsDisplayed()
        scroll("0.0054 nT/s"); capture("ulf-station")
        chart("Regional intensity · 48 hours", "ulf-history")
    }
    @Test fun spaceAndMagnetosphereHaveValuesAndChart() {
        launch("SPACE_WEATHER")
        scroll("442 km/s"); capture("space-weather")
        chart("Bz · north/south field · 24 hours", "space-weather-history")
        scenario!!.close(); scenario = null
        launch("MAGNETOSPHERE")
        scroll("10.40 Rₑ"); capture("magnetosphere")
        chart("Standoff history · 24 hours", "magnetosphere-history")
    }
    @Test fun emptyStateRefreshesWithoutFabricatedReading() {
        launch("SCHUMANN", "empty")
        compose.onNodeWithText("7.83 Hz").assertDoesNotExist()
        scroll("Cumiana resonance"); capture("empty")
        compose.onNodeWithText("Refresh readings").performScrollTo().performClick()
        scroll("7.89 Hz")
        scenario!!.onActivity { assertEquals(1, it.refreshes) }
    }
    @Test fun savedStaleAndLargeFontRemainReadable() {
        launch("ULF", "stale", large = true)
        scroll("Regional geomagnetic activity"); capture("ulf-large-font-stale")
        compose.onAllNodesWithText("Saved · Stale").onFirst().assertExists()
        compose.onNode(hasText("Baseline still building", substring = true)).performScrollTo().assertIsDisplayed()
        scroll("Refresh readings"); capture("large-font-refresh")
    }
}
