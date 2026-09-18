package com.gaiaeyes.app.visualharness

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.SystemClock
import android.view.View
import android.widget.DatePicker
import android.widget.TimePicker
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.UiController
import androidx.test.espresso.ViewAction
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import com.gaiaeyes.app.ui.*
import java.io.File
import java.math.BigDecimal
import java.time.LocalDateTime
import kotlinx.coroutines.CompletableDeferred
import kotlinx.serialization.json.*
import org.hamcrest.Matcher
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ActualFormInteractionTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: IsolatedFormActivity
    private var scenario: ActivityScenario<out IsolatedFormActivity>? = null
    private val f get() = activity.fixture

    private fun launch(name: String = "editable", largeFont: Boolean = false) {
        val klass = if (largeFont) IsolatedLargeFontActivity::class.java else IsolatedFormActivity::class.java
        scenario = ActivityScenario.launch<IsolatedFormActivity>(Intent(instrumentation.targetContext, klass).putExtra("scenario", name))
        scenario!!.onActivity { activity = it }
        await(if (name == "initial_unavailable") MigraineFollowUpPhase.UNAVAILABLE else MigraineFollowUpPhase.EDITING)
    }
    private fun await(phase: MigraineFollowUpPhase) {
        compose.waitUntil(10000) { f.controller.state.value.phase == phase }
        compose.waitForIdle()
    }
    private fun tap(text: String) { compose.onNodeWithText(text).performScrollTo().performClick() }
    private fun button(text: String) { compose.onNodeWithText(text).performClick() }
    private fun field(label: String, value: String) {
        compose.onNodeWithText(label).performScrollTo().performClick().performTextReplacement(value)
    }
    private fun edit(index: Int) { compose.onAllNodesWithText("Edit")[index].performScrollTo().performClick() }
    private fun hideKeyboard() {
        var visible = false
        instrumentation.runOnMainSync { visible = ViewCompat.getRootWindowInsets(activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true }
        if (visible) pressBack()
        compose.waitForIdle()
    }
    private fun capture(name: String, nativeDialog: Boolean = false) {
        compose.waitForIdle(); instrumentation.waitForIdleSync(); SystemClock.sleep(200)
        val directory = File(instrumentation.targetContext.filesDir, "g026").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(directory, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
        var evidence = JsonObject(emptyMap())
        instrumentation.runOnMainSync {
            evidence = buildJsonObject {
                put("label", name); put("native_dialog", nativeDialog)
                put("package", activity.packageName)
                put("application", activity.application.javaClass.name)
                put("internet_permission_denied", activity.checkSelfPermission(Manifest.permission.INTERNET) == PackageManager.PERMISSION_DENIED)
                put("width_dp", activity.resources.configuration.screenWidthDp)
                put("height_dp", activity.resources.configuration.screenHeightDp)
                put("font_scale", activity.resources.configuration.fontScale)
                put("ime_visible", ViewCompat.getRootWindowInsets(activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true)
                put("fixture", f.ledger())
            }
        }
        File(directory, "$name.json").writeText(evidence.toString())
        if (!nativeDialog) {
            val roots = compose.onAllNodes(androidx.compose.ui.test.isRoot())
            File(directory, "$name-semantics.txt").writeText(roots.fetchSemanticsNodes().indices.joinToString("\n\n") { roots[it].printToString() })
        }
    }
    private fun nativeDate(year: Int, month: Int, day: Int) {
        onView(isAssignableFrom(DatePicker::class.java)).perform(object : ViewAction {
            override fun getConstraints(): Matcher<View> = isAssignableFrom(DatePicker::class.java)
            override fun getDescription() = "Choose a synthetic date in the actual native picker"
            override fun perform(ui: UiController, view: View) { (view as DatePicker).updateDate(year, month - 1, day); ui.loopMainThreadUntilIdle() }
        })
    }
    private fun nativeTime(hour: Int, minute: Int) {
        onView(isAssignableFrom(TimePicker::class.java)).perform(object : ViewAction {
            override fun getConstraints(): Matcher<View> = isAssignableFrom(TimePicker::class.java)
            override fun getDescription() = "Choose a synthetic time in the actual native picker"
            override fun perform(ui: UiController, view: View) { (view as TimePicker).hour = hour; view.minute = minute; ui.loopMainThreadUntilIdle() }
        })
    }
    private fun nativeOK() { onView(withId(android.R.id.button1)).perform(click()); compose.waitForIdle() }

    @After fun close() { scenario?.close() }

    @Test fun ordinaryFormPreservesAllMedicineMetadataAndRefreshesOnlyAfterSave() {
        launch()
        compose.onNodeWithText("Severity 0/10", substring = true).assertExists()
        capture("01-editable-severity-zero")
        compose.onNodeWithText("0.1000000000000000000001 mg", substring = true).performScrollTo().assertIsDisplayed()
        capture("02-exact-dose")
        compose.onAllNodesWithText("Dose not recorded", substring = true)[0].performScrollTo().assertIsDisplayed()
        capture("03-missing-dose-relief")
        for (index in 0..2) { edit(index); tap("Apply entry") }
        compose.runOnIdle {
            assertEquals(f.original.episode.medicines, f.controller.state.value.draft!!.medicines.map { it.value })
            assertEquals(0, f.server.postBodies.size); assertEquals(0, f.refreshes.size)
        }
        button("Save follow-up"); await(MigraineFollowUpPhase.SAVED)
        compose.runOnIdle {
            assertEquals(f.original.episode.medicines, f.controller.state.value.saved!!.migraineDetail.episode.medicines)
            assertEquals(listOf("synthetic-account"), f.refreshes)
            assertEquals(1, f.server.mutations)
        }
        compose.onNodeWithText("Response").performScrollTo()
        capture("04-acknowledged-save")
        button("Done"); await(MigraineFollowUpPhase.CLOSED)
        compose.onNodeWithText("Synthetic session closed").assertExists()
    }

    @Test fun nativePickersKeyboardAndOrderedMedicineEditingOnSmallPhone() {
        launch()
        tap("Add medicine")
        field("Medicine name", "Example medicine")
        compose.waitUntil(5000) {
            var shown = false
            instrumentation.runOnMainSync { shown = ViewCompat.getRootWindowInsets(activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true }
            shown
        }
        capture("05-small-phone-keyboard")
        field("Dose (optional)", "0.1000000000000000000001")
        field("Unit, such as mg (optional)", "mg")
        hideKeyboard()
        tap("Sep 17, 2026"); nativeDate(2026, 9, 16); capture("06-native-date-picker", true); nativeOK()
        tap("7:00 AM"); nativeTime(9, 45); capture("07-native-time-picker", true); nativeOK()
        tap("Some")
        field("Medicine note (optional)", "New synthetic ordered entry")
        hideKeyboard(); tap("Apply entry")
        compose.onAllNodesWithText("Move up")[3].performScrollTo().performClick()
        compose.runOnIdle {
            val rows = f.controller.state.value.draft!!.medicines
            assertEquals(f.original.episode.medicines[0], rows[0].value)
            assertEquals(f.original.episode.medicines[1], rows[1].value)
            assertEquals(f.original.episode.medicines[2], rows[3].value)
            val added = rows[2].value
            assertEquals(BigDecimal("0.1000000000000000000001"), added.doseAmount)
            assertEquals("2026-09-16T14:45:00Z", added.takenAt.utc)
            assertEquals("America/Chicago", added.takenAt.timezoneName)
            assertEquals(-300, added.takenAt.utcOffsetMinutes)
            assertEquals("some", added.reportedRelief)
            assertEquals(SYNTHETIC_NOW, added.reliefReportedAt!!.utc)
        }
        capture("08-ordered-new-medicine")
        edit(2); field("Medicine note (optional)", "Edited synthetic ordered entry"); hideKeyboard(); tap("Apply entry")
        val expected = f.controller.state.value.draft!!.medicines.map { it.value }
        button("Save follow-up"); await(MigraineFollowUpPhase.SAVED)
        compose.runOnIdle { assertEquals(expected, f.server.detail.episode.medicines); assertEquals(1, f.refreshes.size) }
        capture("09-ordered-array-saved")
    }

    @Test fun largeFontMissingSeverityAndZeroDoseValidationRemainUsable() {
        launch("missing_severity", largeFont = true)
        compose.onNodeWithText("Severity not recorded", substring = true).performScrollTo().assertIsDisplayed()
        capture("10-large-font-missing-severity")
        edit(1)
        compose.runOnIdle { assertEquals("", f.controller.ui.value.medicine!!.amount) }
        field("Dose (optional)", "0"); field("Unit, such as mg (optional)", "mg"); hideKeyboard()
        tap("Apply entry")
        compose.runOnIdle {
            assertNotNull(f.controller.ui.value.medicine); assertNotNull(f.controller.ui.value.message)
            assertNull(f.controller.state.value.draft!!.medicines[1].value.doseAmount)
            assertEquals(0, f.server.postBodies.size)
        }
        compose.onNodeWithText("Save follow-up").assertIsNotEnabled()
        capture("11-large-font-zero-dose-rejected")
        field("Dose (optional)", ""); field("Unit, such as mg (optional)", ""); hideKeyboard(); tap("Apply entry")
        button("Save follow-up"); await(MigraineFollowUpPhase.SAVED)
        compose.runOnIdle { assertNull(f.server.detail.episode.severity); assertEquals(f.original.episode.medicines, f.server.detail.episode.medicines) }
        compose.onNodeWithText("Response").performScrollTo(); capture("12-large-font-saved")
    }

    @Test fun initialUnavailableLoadHasOnlyExplicitReload() {
        launch("initial_unavailable")
        compose.onNodeWithText("Retry loading").assertIsDisplayed()
        compose.onNodeWithText("Retry same response").assertDoesNotExist()
        compose.runOnIdle { assertNull(f.controller.state.value.draft); assertEquals(0, f.clockReads) }
        capture("13-initial-unavailable")
        compose.runOnIdle { f.server.getReply = null }
        button("Retry loading"); await(MigraineFollowUpPhase.EDITING)
        compose.runOnIdle { assertEquals(2, f.server.getCount); assertEquals(1, f.clockReads); assertEquals(0, f.server.postBodies.size) }
        capture("14-explicit-load-recovered")
    }

    @Test fun loadedUnavailableRetriesExactResponseWithoutDiscardingEdits() {
        launch()
        tap("Improving")
        compose.runOnIdle { f.server.postReply = Reply(503, """{"detail":"structured migraine detail storage is not installed"}""") }
        button("Save follow-up"); await(MigraineFollowUpPhase.UNAVAILABLE)
        compose.onNodeWithText("Retry loading").assertDoesNotExist()
        capture("15-loaded-unavailable-kept-response")
        compose.runOnIdle { assertEquals(0, f.refreshes.size); f.server.postReply = null }
        button("Retry same response"); await(MigraineFollowUpPhase.SAVED)
        compose.runOnIdle {
            assertEquals(2, f.server.postBodies.size); assertEquals(f.server.postBodies[0], f.server.postBodies[1])
            assertEquals(1, f.clockReads); assertEquals(1, f.server.getCount); assertEquals(1, f.server.mutations); assertEquals(1, f.refreshes.size)
        }
        capture("16-same-response-recovered")
    }

    @Test fun uncertaintyGetReviewDoesNotBecomeSaveOrAutomaticMerge() {
        launch()
        tap("Improving")
        compose.runOnIdle { f.server.loseNextReceipt = true }
        button("Save follow-up"); await(MigraineFollowUpPhase.UNCERTAIN)
        capture("17-unconfirmed-save")
        button("Review saved version"); await(MigraineFollowUpPhase.REVIEW)
        compose.onNodeWithText("This check does not confirm your earlier save.", substring = true).assertExists()
        compose.onNodeWithText("Follow-up saved.").assertDoesNotExist()
        compose.runOnIdle {
            assertNull(f.controller.state.value.saved); assertNotNull(f.controller.state.value.draft)
            assertEquals(1, f.server.postBodies.size); assertEquals(2, f.server.getCount); assertEquals(0, f.refreshes.size)
        }
        capture("18-get-review-not-save")
        button("Use reviewed version"); await(MigraineFollowUpPhase.REVIEWED)
        capture("19-explicit-set-aside-not-save")
        compose.runOnIdle { assertEquals(0, f.refreshes.size); assertEquals(1, f.server.mutations); assertNull(f.controller.state.value.saved) }
    }

    @Test fun conflictReviewKeepsBothVersionsWithoutMutation() {
        launch()
        tap("Worse")
        compose.runOnIdle {
            val old = f.server.detail
            f.server.detail = old.copy(revision = old.revision + 1, episode = old.episode.copy(state = "improving", lifecycle = old.episode.lifecycle.copy(revision = old.revision + 1)))
        }
        button("Save follow-up"); await(MigraineFollowUpPhase.CONFLICT)
        capture("20-conflict")
        button("Review saved version"); await(MigraineFollowUpPhase.REVIEW)
        compose.runOnIdle {
            assertEquals("worse", f.controller.state.value.draft!!.answers.state)
            assertEquals("improving", f.controller.state.value.reviewed!!.episode.state)
            assertEquals(0, f.server.mutations); assertEquals(0, f.refreshes.size); assertEquals(1, f.server.postBodies.size)
        }
        capture("21-conflict-kept-and-reviewed")
    }

    @Test fun closeRequiresExplicitDiscardAndNativeStaleCallbackCannotEditReplacementAccount() {
        launch()
        button("Close")
        compose.onNodeWithText("Close this response?").assertIsDisplayed(); capture("22-discard-confirmation")
        button("Keep response"); await(MigraineFollowUpPhase.EDITING)
        edit(0); tap("Sep 15, 2026")
        nativeDate(2026, 9, 14)
        // Account replacement while an actual native picker owns an old production callback.
        instrumentation.runOnMainSync { f.replaceAccount("replacement-synthetic-account"); f.controller.open(f.item) }
        await(MigraineFollowUpPhase.EDITING)
        nativeOK()
        compose.runOnIdle {
            assertNull(f.controller.ui.value.medicine)
            assertEquals("replacement-synthetic-account", f.controller.state.value.accountId)
            assertEquals(f.original.episode.medicines, f.controller.state.value.draft!!.medicines.map { it.value })
            assertEquals(0, f.server.postBodies.size)
        }
        capture("23-old-native-callback-ignored")
        pressBack()
        compose.onNodeWithText("Close this response?").assertIsDisplayed()
        button("Discard draft and close"); await(MigraineFollowUpPhase.CLOSED)
        compose.runOnIdle { assertNull(f.controller.state.value.draft); assertNull(f.controller.ui.value.medicine) }
        capture("24-explicit-discard-closed")
    }

    @Test fun lateAcknowledgementAfterAccountReplacementCannotRefreshNewAccount() {
        launch()
        val gate = CompletableDeferred<Unit>()
        compose.runOnIdle { f.writeGate = gate }
        button("Save follow-up")
        compose.waitUntil(10000) { f.writeReached }
        capture("25-save-awaiting-acknowledgement")
        compose.runOnIdle { f.replaceAccount("replacement-synthetic-account"); gate.complete(Unit) }
        await(MigraineFollowUpPhase.CLOSED)
        compose.runOnIdle { assertEquals(0, f.refreshes.size); assertEquals(0, f.signOuts); assertEquals(1, f.server.mutations) }
        capture("26-account-replacement-no-refresh")
    }

    @Test fun largeFontNativePickersAndKeyboardPreserveUntouchedTimestampPrecision() {
        launch(largeFont = true)
        edit(0)
        field("Medicine name", "Example medicine")
        compose.onNodeWithText("Medicine name").assertIsDisplayed()
        capture("27-large-font-keyboard")
        hideKeyboard()
        tap("Sep 15, 2026"); nativeDate(2026, 9, 15)
        capture("28-large-font-native-date", true); nativeOK()
        tap("8:05 AM"); nativeTime(8, 5)
        capture("29-large-font-native-time", true); nativeOK()
        tap("Apply entry")
        compose.runOnIdle {
            assertEquals(f.original.episode.medicines, f.controller.state.value.draft!!.medicines.map { it.value })
            assertEquals("2026-09-15T13:05:06.123456Z", f.controller.state.value.draft!!.medicines[0].value.takenAt.utc)
        }
        button("Save follow-up"); await(MigraineFollowUpPhase.SAVED)
        compose.runOnIdle { assertEquals(f.original.episode.medicines, f.server.detail.episode.medicines); assertEquals(1, f.refreshes.size) }
        capture("30-large-font-native-round-trip-saved")
    }
}
