package com.gaiaeyes.app.visualharness

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.pressBack
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gaiaeyes.app.ui.MigraineMedicinePhase
import java.io.File
import kotlinx.serialization.json.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SavedMedicineInteractionTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: IsolatedMedicineActivity
    private var scenario: ActivityScenario<IsolatedMedicineActivity>? = null
    private val f get() = activity.fixture
    private fun launch() {
        scenario = ActivityScenario.launch(Intent(instrumentation.targetContext, IsolatedMedicineActivity::class.java))
        scenario!!.onActivity { activity = it }
        compose.waitUntil(10000) { f.summary.state.value.summary != null }; compose.waitForIdle()
    }
    private fun phase(value: MigraineMedicinePhase) { compose.waitUntil(10000) { f.controller.state.value.phase == value }; compose.waitForIdle() }
    private fun tap(text: String) = compose.onNodeWithText(text).performScrollTo().performClick()
    private fun button(text: String) = compose.onNodeWithText(text).performClick()
    private fun capture(name: String) {
        compose.waitForIdle(); instrumentation.waitForIdleSync(); SystemClock.sleep(200)
        val directory = File(instrumentation.targetContext.filesDir, "g028").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(directory, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        instrumentation.runOnMainSync {
            File(directory, "$name.json").writeText(buildJsonObject {
                put("label", name); put("package", activity.packageName); put("application", activity.application.javaClass.name)
                put("internet_permission_denied", activity.checkSelfPermission(Manifest.permission.INTERNET) == PackageManager.PERMISSION_DENIED)
                put("fixture", f.ledger())
            }.toString())
        }
        val roots = compose.onAllNodes(isRoot())
        File(directory, "$name-semantics.txt").writeText(roots.fetchSemanticsNodes().indices.joinToString("\n\n") { roots[it].printToString() })
    }
    @After fun close() { scenario?.close() }

    @Test fun loadedSummaryOpensWithoutPromptAndUnchangedSaveReturnsWithoutWrite() {
        launch(); capture("01-summary-entry")
        tap("Edit medicines"); phase(MigraineMedicinePhase.EDITING)
        compose.onNodeWithText("Save medicines").assertIsDisplayed(); capture("02-editor")
        button("Save medicines")
        compose.onNodeWithText("Medicine entries are unchanged. Nothing was saved.").assertExists()
        assertEquals(0, f.tokenReads); assertEquals(0, f.server.bodies.size)
        button("Close"); phase(MigraineMedicinePhase.CLOSED)
        compose.onNodeWithText("Saved migraine summary").assertExists(); capture("03-unchanged-return")
    }

    @Test fun actualSharedEditorAppliesThenUnavailableRetryRefreshesAndReturns() {
        launch(); tap("Edit medicines")
        compose.onAllNodesWithText("Edit")[1].performScrollTo().performClick()
        compose.onNodeWithText("Medicine note (optional)").performScrollTo().performClick().performTextReplacement("G028 synthetic edited duplicate")
        pressBack(); compose.waitForIdle()
        capture("04-medicine-editor")
        tap("Apply entry")
        instrumentation.runOnMainSync { f.server.reply = Reply(503, """{"detail":"structured migraine detail storage is not installed"}""") }
        button("Save medicines"); phase(MigraineMedicinePhase.UNAVAILABLE)
        compose.onNodeWithText("Saving medicines is unavailable.", substring = true).assertIsDisplayed(); capture("05-unavailable-kept")
        assertEquals(0, f.refreshes); assertEquals(3L, f.summary.state.value.detail!!.revision)
        instrumentation.runOnMainSync { f.server.reply = null }
        button("Retry same changes"); phase(MigraineMedicinePhase.SAVED)
        compose.onNodeWithText("Medicines saved.").assertIsDisplayed(); capture("06-saved")
        assertEquals(2, f.server.bodies.size); assertEquals(1, f.server.bodies.toSet().size); assertEquals(1, f.server.mutations)
        assertEquals(1, f.refreshes)
        assertEquals(f.original.episode.medicines[0], f.server.detail.episode.medicines[0])
        assertEquals(f.original.episode.medicines[1].copy(notes = "G028 synthetic edited duplicate"), f.server.detail.episode.medicines[1])
        button("Done"); phase(MigraineMedicinePhase.CLOSED)
        compose.onNodeWithText("Saved migraine summary").assertExists()
        compose.onNodeWithText("Note: G028 synthetic edited duplicate").performScrollTo().assertIsDisplayed()
        capture("07-updated-summary-return")
    }

    @Test fun explicitDiscardAndUncertainReadNeverClaimSaved() {
        launch(); tap("Edit medicines")
        compose.onAllNodesWithText("Remove")[0].performScrollTo().performClick()
        button("Close"); compose.onNodeWithText("Discard medicine changes?").assertExists(); capture("08-discard-decision")
        button("Keep editing"); phase(MigraineMedicinePhase.EDITING)
        instrumentation.runOnMainSync { f.server.loseReceipt = true }
        button("Save medicines"); phase(MigraineMedicinePhase.UNCERTAIN); capture("09-unconfirmed")
        button("Review saved medicines"); phase(MigraineMedicinePhase.REVIEW); capture("10-get-comparison")
        assertEquals(0, f.refreshes); assertNull(f.controller.state.value.saved); assertEquals(3L, f.summary.state.value.detail!!.revision)
        button("Use reviewed version"); phase(MigraineMedicinePhase.REVIEWED)
        button("Done"); phase(MigraineMedicinePhase.CLOSED); capture("11-reviewed-return-not-receipt")
        assertEquals(1, f.server.bodies.size); assertEquals(2, f.server.gets)
    }
}
