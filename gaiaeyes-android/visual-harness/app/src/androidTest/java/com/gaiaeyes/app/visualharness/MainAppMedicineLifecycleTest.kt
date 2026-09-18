package com.gaiaeyes.app.visualharness

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gaiaeyes.app.core.auth.AuthState
import com.gaiaeyes.app.ui.*
import java.io.File
import kotlinx.coroutines.CompletableDeferred
import kotlinx.serialization.json.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainAppMedicineLifecycleTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: IsolatedMainAppActivity
    private var scenario: ActivityScenario<IsolatedMainAppActivity>? = null
    private val f get() = activity.fixture
    private val vm get() = f.viewModel
    private val medicine get() = vm.migraineMedicine.state.value
    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun await(block: () -> Boolean) { compose.waitUntil(10000, block); compose.waitForIdle() }
    private fun phase(value: MigraineMedicinePhase) = await { medicine.phase == value }
    private fun tap(text: String) = compose.onNodeWithText(text).performScrollTo().performClick()
    private fun button(text: String) = compose.onNodeWithText(text).performClick()
    private fun launch() {
        scenario = ActivityScenario.launch(Intent(instrumentation.targetContext, IsolatedMainAppActivity::class.java))
        scenario!!.onActivity { activity = it }
        ready(f.auth.accountA)
    }
    private fun ready(account: String) = await {
        val state = vm.uiState.value
        (state.authState as? AuthState.SignedIn)?.accountId == account &&
            state.onboardingStatus == OnboardingStatus.COMPLETE && state.currentSymptoms?.accountId == account &&
            !state.isLoadingHomeContext && !state.isLoadingDashboard && !state.isLoadingNotificationPreferences && state.locationSettingsLoaded
    }
    private fun openSummary() {
        main { f.route() }; await { f.navigation.pending.value == null }
        compose.onNodeWithText("Current Symptoms").assertExists()
        tap("View saved migraine summary"); await { vm.savedMigraineSummary.value.detail != null }
        compose.onNodeWithText("Saved migraine summary").assertExists()
    }
    private fun openEditor() { openSummary(); tap("Edit medicines"); phase(MigraineMedicinePhase.EDITING) }
    private fun change() { compose.onAllNodesWithText("Remove")[0].performScrollTo().performClick() }
    private fun capture(name: String) {
        compose.waitForIdle(); instrumentation.waitForIdleSync(); SystemClock.sleep(200)
        val dir = File(instrumentation.targetContext.filesDir, "g029").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        main { File(dir, "$name.json").writeText(buildJsonObject {
            put("label", name); put("package", activity.packageName)
            put("application", activity.application.javaClass.name)
            put("internet_permission_denied", activity.checkSelfPermission(Manifest.permission.INTERNET) == PackageManager.PERMISSION_DENIED)
            put("fixture", f.ledger())
        }.toString()) }
        val roots = compose.onAllNodes(isRoot())
        File(dir, "$name-semantics.txt").writeText(roots.fetchSemanticsNodes().indices.joinToString("\n\n") { roots[it].printToString() })
    }
    @After fun close() { if (::activity.isInitialized) main { f.auth.releaseAll(); f.server.releaseAll() }; scenario?.close() }

    @Test fun actualMainAppEntryMatchingSaveAndDeliberateSummaryReturn() {
        launch(); openEditor(); val original = vm.savedMigraineSummary.value.detail!!
        capture("01-main-app-editor")
        change(); button("Save medicines"); phase(MigraineMedicinePhase.SAVED)
        assertEquals(4L, vm.savedMigraineSummary.value.detail!!.revision)
        assertEquals(original.episode.medicines.drop(1), vm.savedMigraineSummary.value.detail!!.episode.medicines)
        assertEquals(f.server.detail(f.auth.accountA), vm.savedMigraineSummary.value.detail)
        assertEquals(1, f.server.mutations); assertEquals(1, f.server.patches.size)
        capture("02-main-app-acknowledged")
        button("Done"); phase(MigraineMedicinePhase.CLOSED)
        compose.onNodeWithText("Saved migraine summary").assertExists(); capture("03-deliberate-summary-return")
        button("Close"); await { vm.savedMigraineSummary.value.episodeId == null }
        compose.onNodeWithText("Current Symptoms").assertExists()
    }

    @Test fun pendingSymptomRouteDefersThroughSaveUntilDoneThenOpensList() {
        launch(); openEditor(); change()
        main { f.route() }; val request = f.navigation.pending.value!!
        compose.waitForIdle(); assertEquals(request, f.navigation.pending.value)
        button("Save medicines"); phase(MigraineMedicinePhase.SAVED)
        assertEquals(request, f.navigation.pending.value); capture("04-route-deferred-after-save")
        button("Done"); phase(MigraineMedicinePhase.CLOSED); await { f.navigation.pending.value == null }
        capture("05-symptom-route-after-done")
        compose.onNodeWithText("Current Symptoms").assertExists()
        assertNull(vm.savedMigraineSummary.value.episodeId)
    }

    @Test fun homeRouteDefersDuringDiscardDecisionThenRunsAfterExplicitDiscard() {
        launch(); openEditor(); change()
        main { f.route("home") }; val request = f.navigation.pending.value!!
        button("Close"); compose.onNodeWithText("Discard medicine changes?").assertExists()
        assertEquals(request, f.navigation.pending.value)
        button("Keep editing"); assertEquals(request, f.navigation.pending.value)
        button("Close"); button("Discard changes and close")
        phase(MigraineMedicinePhase.CLOSED); await { f.navigation.pending.value == null && vm.uiState.value.selectedPage == SignedInPage.HOME }
        assertNull(vm.savedMigraineSummary.value.episodeId); assertTrue(f.server.patches.isEmpty())
        capture("06-home-route-after-discard")
    }

    @Test fun replacementAccountDuringTokenWaitRejectsLateAuthAndOldUiCallbacks() {
        launch(); openEditor(); change()
        val old = vm.migraineMedicine.actions(medicine.sessionId)
        val gate = CompletableDeferred<Unit>()
        main { f.auth.nextTokenGate = gate; old.save() }
        await { f.auth.tokenHeld }; phase(MigraineMedicinePhase.SAVING)
        main { f.auth.replace(f.auth.accountB) }; ready(f.auth.accountB)
        phase(MigraineMedicinePhase.CLOSED); assertNull(vm.savedMigraineSummary.value.episodeId)
        openEditor(); val replacement = medicine.sessionId
        main { gate.complete(Unit); old.close(); old.discard(); old.save(); old.edit(null) }
        compose.waitForIdle(); SystemClock.sleep(200)
        assertEquals(replacement, medicine.sessionId); assertEquals(f.auth.accountB, medicine.accountId)
        assertTrue(f.server.patches.isEmpty()); assertEquals(0, f.auth.signOuts)
        capture("07-replacement-rejects-late-auth")
    }

    @Test fun replacementAccountCannotShowPreviousSymptomsWhileNewReadIsPending() {
        launch(); openEditor(); change(); val gate = CompletableDeferred<Unit>()
        main { f.server.currentSymptomsGate = gate; f.auth.replace(f.auth.accountB) }
        await { f.server.currentSymptomsHeld && vm.uiState.value.onboardingStatus == OnboardingStatus.COMPLETE }
        capture("20-replacement-before-new-symptoms")
        assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase)
        assertNull(vm.savedMigraineSummary.value.episodeId)
        assertNull(vm.uiState.value.currentSymptoms)
        compose.onNodeWithText("Synthetic migraine").assertDoesNotExist()
        main { gate.complete(Unit) }; ready(f.auth.accountB)
        capture("21-replacement-after-new-symptoms")
    }

    @Test fun actualSignOutDuringTokenWaitCancelsMedicineBeforeLateAuth() {
        launch(); openEditor(); change(); val gate = CompletableDeferred<Unit>()
        main { f.auth.nextTokenGate = gate; vm.migraineMedicine.actions(medicine.sessionId).save() }
        await { f.auth.tokenHeld }
        main { vm.signOut() }; await { vm.uiState.value.authState == AuthState.SignedOut }
        main { gate.complete(Unit) }; compose.waitForIdle(); SystemClock.sleep(200)
        assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase); assertNull(vm.savedMigraineSummary.value.episodeId)
        assertTrue(f.server.patches.isEmpty()); assertEquals(1, f.auth.signOuts)
        capture("08-signed-out-late-auth-ignored")
    }

    @Test fun replacementAccountDuringPatchRejectsLateReceiptAndLateUnauthorized() {
        for (unauthorized in listOf(false, true)) {
            launch(); openEditor(); change(); val gate = CompletableDeferred<Unit>()
            main { f.server.patchGate = gate; if (unauthorized) f.server.replyAfterGate = Reply(401, "{}") }
            button("Save medicines"); await { f.server.patchHeld }
            main { f.auth.replace(f.auth.accountB) }; ready(f.auth.accountB)
            openEditor(); val replacement = medicine.sessionId
            main { gate.complete(Unit) }; await { f.server.lateResponses == 1 }
            assertEquals(replacement, medicine.sessionId); assertEquals(f.auth.accountB, medicine.accountId)
            assertEquals(3L, vm.savedMigraineSummary.value.detail!!.revision); assertNull(medicine.saved)
            assertEquals(0, f.auth.signOuts); assertEquals(4L, f.server.detail(f.auth.accountA).revision)
            capture(if (unauthorized) "10-replacement-rejects-late-401" else "09-replacement-rejects-late-ack")
            scenario!!.close(); scenario = null
        }
    }

    @Test fun actualSignOutDuringPatchClearsSummaryAndLateReceiptCannotRestoreIt() {
        launch(); openEditor(); change(); val gate = CompletableDeferred<Unit>()
        main { f.server.patchGate = gate }; button("Save medicines"); await { f.server.patchHeld }
        main { vm.signOut() }; await { vm.uiState.value.authState == AuthState.SignedOut }
        main { gate.complete(Unit) }; await { f.server.lateResponses == 1 }
        assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase); assertNull(vm.savedMigraineSummary.value.episodeId)
        assertEquals(4L, f.server.detail(f.auth.accountA).revision); assertEquals(1, f.auth.signOuts)
        capture("11-signed-out-late-ack-ignored")
    }

    @Test fun transientSameAccountEventsKeepDraftAndMatchingSaveStillReturns() {
        launch(); openEditor(); change(); val selection = vm.savedMigraineSummary.value.selectionId; val session = medicine.sessionId
        for (event in listOf(AuthState.Initializing, AuthState.SessionProblem("Synthetic refresh problem"), f.auth.signedIn(f.auth.accountA))) {
            main { f.auth.transient(event) }; compose.waitForIdle(); SystemClock.sleep(100)
            assertEquals(session, medicine.sessionId); assertEquals(selection, vm.savedMigraineSummary.value.selectionId)
            assertEquals(MigraineMedicinePhase.EDITING, medicine.phase)
            assertEquals(f.auth.accountA, (vm.uiState.value.authState as AuthState.SignedIn).accountId)
        }
        button("Save medicines"); phase(MigraineMedicinePhase.SAVED); capture("12-transient-auth-kept-draft")
        assertEquals(4L, vm.savedMigraineSummary.value.detail!!.revision)
    }

    @Test fun unconfirmedGetReviewDoesNotRefreshActualViewModelSummary() {
        launch(); openEditor(); change()
        main { f.server.loseReceipt = true }; button("Save medicines"); phase(MigraineMedicinePhase.UNCERTAIN)
        button("Review saved medicines"); phase(MigraineMedicinePhase.REVIEW)
        assertEquals(3L, vm.savedMigraineSummary.value.detail!!.revision); assertEquals(4L, medicine.reviewed!!.revision); assertNull(medicine.saved)
        capture("13-main-app-get-is-not-receipt")
        button("Use reviewed version"); button("Done"); phase(MigraineMedicinePhase.CLOSED)
        assertEquals(3L, vm.savedMigraineSummary.value.detail!!.revision)
        tap("Refresh saved summary"); await { vm.savedMigraineSummary.value.detail?.revision == 4L && !vm.savedMigraineSummary.value.isLoading }
        capture("14-deliberate-summary-refresh")
    }

    @Test fun pendingNotificationIsNotConsumedBySignOutClosingTheEditor() {
        launch(); openEditor(); change()
        main { f.route("home") }; val request = f.navigation.pending.value!!; val gate = CompletableDeferred<Unit>()
        main { f.auth.signOutGate = gate; vm.signOut() }; await { f.auth.signOutHeld }
        capture("15-notification-during-sign-out")
        assertTrue(vm.uiState.value.isSigningOut)
        assertEquals(request, f.navigation.pending.value)
        main { gate.complete(Unit) }; await { vm.uiState.value.authState == AuthState.SignedOut }
        assertEquals(request, f.navigation.pending.value); assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase)
        capture("16-notification-retained-while-signed-out")
    }

    private fun heldSignOutRetainsRoute(eventName: String, fail: Boolean = false, emitSignedOut: Boolean = true) {
        launch(); openEditor(); change()
        main { f.route("home") }; val request = f.navigation.pending.value!!
        val gate = CompletableDeferred<Unit>()
        main {
            f.auth.signOutGate = gate; f.auth.failSignOut = fail; f.auth.emitSignedOut = emitSignedOut
            vm.signOut()
        }
        await { f.auth.signOutHeld }
        capture("r1-$eventName-started")
        val event = when (eventName) {
            "initializing" -> AuthState.Initializing
            "session-problem" -> AuthState.SessionProblem("Synthetic refresh problem during sign-out")
            // Change the email so StateFlow emits a real same-account update.
            "same-account" -> f.auth.signedIn(f.auth.accountA).copy(email = "updated@example.invalid")
            else -> null
        }
        if (event != null) main { f.auth.transient(event) }
        compose.waitForIdle(); instrumentation.waitForIdleSync()
        capture("r1-$eventName-held")
        assertFalse(gate.isCompleted)
        assertTrue("Auth update must retain the in-flight sign-out flag", vm.uiState.value.isSigningOut)
        assertEquals("The identical pending route must remain held", request, f.navigation.pending.value)
        assertEquals(f.auth.accountA, (vm.uiState.value.authState as AuthState.SignedIn).accountId)
        if (event is AuthState.SignedIn) assertEquals(event, vm.uiState.value.authState)
        if (event is AuthState.SessionProblem) assertNotNull(vm.uiState.value.authMessage)
        assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase)
        assertNull(vm.savedMigraineSummary.value.episodeId)
        main { vm.signOut() }; compose.waitForIdle(); assertEquals(1, f.auth.signOuts)
        main { gate.complete(Unit) }
        if (fail || !emitSignedOut) {
            await { !vm.uiState.value.isSigningOut && f.navigation.pending.value == null }
            assertEquals(f.auth.accountA, (vm.uiState.value.authState as AuthState.SignedIn).accountId)
            assertEquals(SignedInPage.HOME, vm.uiState.value.selectedPage)
            if (fail) assertEquals("We couldn't sign you out. Check your connection and try again.", vm.uiState.value.authMessage)
            else assertTrue(f.auth.signOutReturned)
        } else {
            await { vm.uiState.value.authState == AuthState.SignedOut && !vm.uiState.value.isSigningOut }
            assertEquals(request, f.navigation.pending.value)
            assertNull(vm.uiState.value.currentSymptoms)
        }
        capture("r1-$eventName-terminal")
        assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase)
        assertNull(vm.savedMigraineSummary.value.episodeId)
        assertTrue(f.server.patches.isEmpty()); assertEquals(1, f.auth.signOuts)
    }

    @Test fun heldSignOutSurvivesInitializing() = heldSignOutRetainsRoute("initializing")
    @Test fun heldSignOutSurvivesSessionProblem() = heldSignOutRetainsRoute("session-problem")
    @Test fun heldSignOutSurvivesSameAccountUpdate() = heldSignOutRetainsRoute("same-account")
    @Test fun failedSignOutReleasesRouteGuard() = heldSignOutRetainsRoute("failure", fail = true)
    @Test fun completedSignOutReleasesRouteGuardWithoutAnotherAuthEvent() =
        heldSignOutRetainsRoute("completion", emitSignedOut = false)

    @Test fun accountReplacementDuringSummaryReadIgnoresLateDetail() {
        launch(); main { f.route() }; await { f.navigation.pending.value == null }
        val gate = CompletableDeferred<Unit>(); main { f.server.readGate = gate }
        tap("View saved migraine summary"); await { f.server.readHeld }
        main { f.auth.replace(f.auth.accountB); f.server.readGate = null }; ready(f.auth.accountB)
        main { gate.complete(Unit) }; await { f.server.lateResponses == 1 }
        assertNull(vm.savedMigraineSummary.value.detail); assertEquals(MigraineMedicinePhase.CLOSED, medicine.phase)
        capture("17-late-summary-read-rejected")
    }

    @Test fun finishingActualActivityClearsViewModelAndPendingMedicine() {
        launch(); openEditor(); change(); val gate = CompletableDeferred<Unit>()
        main { f.server.patchGate = gate }; button("Save medicines"); await { f.server.patchHeld }
        val held = f; val ownedModel = vm
        capture("18-finishing-with-pending-patch")
        scenario!!.close(); scenario = null
        assertEquals(MigraineMedicinePhase.CLOSED, ownedModel.migraineMedicine.state.value.phase)
        assertNull(ownedModel.savedMigraineSummary.value.episodeId)
        assertTrue(gate.isCompleted)
        File(instrumentation.targetContext.filesDir, "g029/19-finished-viewmodel.json").writeText(held.ledger().toString())
    }
}
