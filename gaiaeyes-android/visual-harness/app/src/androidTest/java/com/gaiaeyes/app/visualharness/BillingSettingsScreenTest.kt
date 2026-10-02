package com.gaiaeyes.app.visualharness

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import com.gaiaeyes.app.data.BillingProduct
import com.gaiaeyes.app.data.BillingState
import com.gaiaeyes.app.data.PlusPlan
import com.gaiaeyes.app.ui.BillingSettingsContent
import com.gaiaeyes.app.ui.theme.GaiaEyesTheme
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual production UI; fake callbacks only, no SDK configuration or store/network permission. */
class BillingSettingsScreenTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<IsolatedFormActivity>? = null
    private val state = mutableStateOf(BillingState())
    private var purchases = mutableListOf<String>()
    private var restores = 0
    private var refreshes = 0

    @After fun close() { scenario?.close() }

    private fun launch(initial: BillingState, large: Boolean = false) {
        state.value = initial
        scenario = ActivityScenario.launch(IsolatedFormActivity::class.java).also { scenario ->
            scenario.onActivity { activity ->
                activity.setContent {
                    GaiaEyesTheme {
                        val density = LocalDensity.current
                        CompositionLocalProvider(LocalDensity provides Density(density.density, if (large) 1.5f else 1f)) {
                            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp)) {
                                BillingSettingsContent(state.value, true,
                                    onPurchase = { purchases += it; state.value = state.value.copy(busy = true) },
                                    onRestore = { restores++ }, onRefresh = { refreshes++ })
                            }
                        }
                    }
                }
            }
        }
    }

    @Test fun unavailableBillingKeepsRestoreDisabledAndOffersRefresh() {
        launch(BillingState(accountId = "synthetic", backendPlus = false,
            message = "Purchases and restore are unavailable in this build."))
        compose.onNodeWithText("Purchases and restore are unavailable in this build.").assertExists()
        compose.onNodeWithText("Restore purchases").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithText("Refresh membership").performScrollTo().performClick()
        assertEquals(1, refreshes); assertTrue(purchases.isEmpty()); assertEquals(0, restores)
        capture("unavailable")
    }

    @Test fun localizedPriceAndSelectedPlanReachOnlyPurchaseCallback() {
        launch(available())
        compose.onNodeWithText("Monthly · regular price 4,99 € / month").assertExists()
        compose.onNodeWithText("Continue with yearly Plus").performScrollTo().performClick()
        assertEquals(listOf("synthetic:year"), purchases)
        compose.onNodeWithText("Continue with monthly Plus").assertIsNotEnabled()
        compose.onNodeWithText("Restore purchases").performScrollTo().assertIsNotEnabled()
        assertEquals(0, restores); assertEquals(0, refreshes)
    }

    @Test fun confirmedStorePurchaseShowsSyncingWithoutAnotherPurchaseButton() {
        launch(available().copy(storePlus = true, backendPlus = false))
        compose.onNodeWithText("Your purchase is active. Account membership is syncing.").assertExists()
        compose.onNodeWithText("Continue with monthly Plus").assertDoesNotExist()
        compose.onNodeWithText("Restore purchases").performScrollTo().performClick()
        assertEquals(1, restores); assertTrue(purchases.isEmpty())
        capture("account-syncing")
    }

    @Test fun largeTextWrapsMembershipAndBothPlanControlsRemainReachable() {
        launch(available(), large = true)
        for (text in listOf("Gaia Eyes Plus", "Monthly · regular price 4,99 € / month",
            "Yearly · regular price 49,99 € / year", "Continue with monthly Plus", "Continue with yearly Plus")) {
            val node = compose.onNodeWithText(text, useUnmergedTree = true)
            node.performScrollTo()
            val layouts = mutableListOf<TextLayoutResult>()
            node.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            assertTrue(layouts.isNotEmpty())
            if (layouts.any { it.hasVisualOverflow }) {
                capture("large-overflow")
                val context = InstrumentationRegistry.getInstrumentation().targetContext
                File(context.filesDir, "billing-20261001/layout.txt").writeText(layouts.joinToString("\n") {
                    "text=$text size=${it.size} lines=${it.lineCount} width=${it.didOverflowWidth} height=${it.didOverflowHeight} bottom=${it.getLineBottom(0)} style=${it.layoutInput.style}"
                })
            }
            assertTrue("Clipped text: $text", layouts.none { it.hasVisualOverflow })
        }
        capture("large-plans")
        compose.onNodeWithText("Restore purchases").performScrollTo().assertIsEnabled()
        compose.onNodeWithText("Refresh membership").performScrollTo().assertIsEnabled()
    }

    private fun available() = BillingState(accountId = "synthetic", storeAvailable = true,
        backendPlus = false, storePlus = false, products = listOf(
            BillingProduct("synthetic:month", PlusPlan.MONTHLY, "4,99 €"),
            BillingProduct("synthetic:year", PlusPlan.YEARLY, "49,99 €")))

    private fun capture(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val dir = File(instrumentation.targetContext.filesDir, "billing-20261001").apply { mkdirs() }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
        File(dir, "$name-semantics.txt").writeText(compose.onRoot().printToString())
    }
}
