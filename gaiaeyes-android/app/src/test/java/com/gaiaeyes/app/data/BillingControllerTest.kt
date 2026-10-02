package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthState
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class BillingControllerTest {
    @Test fun missingConfigurationNeverCallsStoreOrFabricatesAccess() = runBlocking {
        val f = Fixture(BillingConfig("", emptyMap()))
        f.connect()
        assertEquals(false, f.controller.state.value.backendPlus)
        assertNull(f.controller.state.value.storePlus)
        assertFalse(f.controller.state.value.canPurchase)
        assertNull(f.controller.restore())
        assertEquals(emptyList<String>(), f.store.events)
    }

    @Test fun unconfiguredStoreStillShowsExistingBackendMembership() = runBlocking {
        val f = Fixture(BillingConfig("", emptyMap()))
        f.backend = { true }; f.connect()
        assertEquals(true, f.controller.state.value.backendPlus)
        assertFalse(f.controller.state.value.canPurchase)
    }

    @Test fun purchaseUsesCurrentAccountAndSeparatesWebhookLag() = runBlocking {
        val f = Fixture(); f.connect()
        f.controller.purchase("monthly") {
            assertEquals("a", f.store.account)
            true
        }!!.join()
        assertEquals(true, f.controller.state.value.storePlus)
        assertEquals(false, f.controller.state.value.backendPlus)
        assertFalse(f.controller.state.value.canPurchase)
        assertTrue(f.controller.state.value.message!!.contains("syncing"))
        f.backend = { true }; f.store.active = true
        f.controller.refresh()!!.join()
        assertEquals(true, f.controller.state.value.backendPlus)
    }

    @Test fun inactivePurchaseDoesNotReportSuccessOrAllowImmediateRepurchase() = runBlocking {
        val f = Fixture(); f.connect()
        f.controller.purchase("monthly") { false }!!.join()
        assertNull(f.controller.state.value.storePlus)
        assertFalse(f.controller.state.value.canPurchase)
        assertTrue(f.controller.state.value.message!!.contains("not active"))
    }

    @Test fun cancelledPurchaseRemainsFreeAndCanBeRetried() = runBlocking {
        val f = Fixture(); f.connect()
        f.controller.purchase("monthly") { throw BillingStoreException(BillingFailure.CANCELLED) }!!.join()
        assertEquals("Purchase cancelled.", f.controller.state.value.message)
        assertEquals(false, f.controller.state.value.storePlus)
        assertTrue(f.controller.state.value.canPurchase)
    }

    @Test fun pendingAndFailureNeverGrantMembershipAndRequireRefreshBeforeRetry() = runBlocking {
        for (reason in listOf(BillingFailure.PENDING, BillingFailure.FAILED, BillingFailure.UNAVAILABLE)) {
            val f = Fixture(); f.connect()
            f.controller.purchase("monthly") { throw BillingStoreException(reason) }!!.join()
            assertEquals(false, f.controller.state.value.backendPlus)
            assertNull(f.controller.state.value.storePlus)
            assertFalse(f.controller.state.value.canPurchase)
            assertNull(f.controller.purchase("monthly") { error("must not repurchase") })
        }
    }

    @Test fun restoreIsExplicitAndEmptyRestoreDoesNotActivatePlus() = runBlocking {
        val f = Fixture(); f.connect()
        assertFalse(f.store.events.contains("restore"))
        f.controller.restore()!!.join()
        assertEquals(false, f.controller.state.value.storePlus)
        assertTrue(f.controller.state.value.message!!.contains("No active"))
        f.store.active = true; f.backend = { true }
        f.controller.restore()!!.join()
        assertEquals(true, f.controller.state.value.backendPlus)
    }

    @Test fun repeatedClicksAndUnknownProductNeverStartTransactions() = runBlocking {
        val f = Fixture(); f.connect()
        assertNull(f.controller.purchase("invented") { error("unexpected") })
        val done = CompletableDeferred<Boolean>()
        val purchase = f.controller.purchase("monthly") { done.await() }!!
        assertTrue(f.controller.state.value.busy)
        assertNull(f.controller.purchase("monthly") { error("duplicate") })
        assertNull(f.controller.restore())
        done.complete(true); purchase.join()
    }

    @Test fun accountSwitchWaitsForPurchaseAndRejectsItsLateResult() = runBlocking {
        val f = Fixture(); f.connect()
        val done = CompletableDeferred<Boolean>()
        val purchase = f.controller.purchase("monthly") { done.await() }!!
        f.connect("b")
        assertEquals("b", f.controller.state.value.accountId)
        assertNull(f.controller.state.value.backendPlus)
        assertEquals("a", f.store.account)
        done.complete(true); purchase.join(); yield()
        assertEquals("b", f.store.account)
        assertEquals(false, f.controller.state.value.storePlus)
        assertEquals(false, f.controller.state.value.backendPlus)
    }

    @Test fun signOutClearsImmediatelyAndSerializesLogoutBeforeNextAccount() = runBlocking {
        val f = Fixture(); f.connect()
        val done = CompletableDeferred<Boolean>()
        val purchase = f.controller.purchase("monthly") { done.await() }!!
        f.currentAccount = null; f.controller.authChanged(AuthState.SignedOut)
        assertNull(f.controller.state.value.accountId)
        assertTrue(f.controller.state.value.products.isEmpty())
        assertNull(f.controller.state.value.storePlus)
        f.connect("b")
        done.complete(true); purchase.join(); yield()
        assertTrue(f.store.events.indexOf("logout") < f.store.events.indexOf("identify:b"))
        assertEquals(false, f.controller.state.value.storePlus)
    }

    @Test fun returningToSameAccountDoesNotAcceptAnEarlierSessionsCallback() = runBlocking {
        val f = Fixture(); f.connect()
        val done = CompletableDeferred<Boolean>()
        val purchase = f.controller.purchase("monthly") { done.await() }!!
        f.connect("b"); f.connect("a")
        done.complete(true); purchase.join(); yield()
        assertEquals("a", f.controller.state.value.accountId)
        assertEquals(false, f.controller.state.value.storePlus)
        assertEquals(false, f.controller.state.value.backendPlus)
        assertFalse(f.controller.state.value.busy)
        assertFalse(f.store.events.contains("identify:b"))
    }

    @Test fun logoutFailureCannotReuseOldIdentityForNextAccountPurchase() = runBlocking {
        val f = Fixture(); f.connect()
        f.store.failLogout = true
        f.currentAccount = null; f.controller.authChanged(AuthState.SignedOut)
        f.connect("b")
        f.controller.purchase("monthly") { assertEquals("b", f.store.account); true }!!.join()
    }

    @Test fun failedIdentitySwitchCannotPurchaseOrShowPreviousMembership() = runBlocking {
        val f = Fixture(); f.store.active = true; f.connect()
        f.store.failIdentity = true
        f.connect("b")
        assertNull(f.controller.state.value.storePlus)
        assertTrue(f.controller.state.value.products.isEmpty())
        assertNull(f.controller.purchase("monthly") { error("must not purchase") })
        f.controller.restore()!!.join()
        assertFalse(f.store.events.contains("restore"))
    }

    @Test fun transientAuthKeepsSameIdentityButCannotPreserveReplacementAccount() = runBlocking {
        val f = Fixture(); f.connect()
        f.controller.authChanged(AuthState.SessionProblem("synthetic"))
        f.controller.authChanged(AuthState.Initializing)
        assertEquals("a", f.controller.state.value.accountId)
        assertFalse(f.store.events.contains("logout"))
        f.currentAccount = "b"
        f.controller.authChanged(AuthState.SessionProblem("synthetic"))
        assertNull(f.controller.state.value.accountId)
    }

    @Test fun membershipActivatedElsewherePreventsSecondPurchase() = runBlocking {
        val f = Fixture(); f.connect()
        f.backend = { true }
        f.controller.purchase("monthly") { error("already has Plus") }!!.join()
        assertEquals(true, f.controller.state.value.backendPlus)
        assertFalse(f.controller.state.value.canPurchase)
    }

    @Test fun backendFailureAndAccountChangeDuringIdentityPreventStorePurchase() = runBlocking {
        val f = Fixture(); f.connect()
        f.backend = { error("synthetic failure") }
        f.controller.purchase("monthly") { error("must not purchase") }!!.join()
        assertFalse(f.controller.state.value.canPurchase)
        f.backend = { false }; f.controller.refresh()!!.join()
        f.store.afterIdentify = { f.currentAccount = "b" }
        f.controller.purchase("monthly") { error("wrong account") }!!.join()
    }

    private class Fixture(config: BillingConfig = BillingConfig("synthetic-key", mapOf(PlusPlan.MONTHLY to "monthly"))) {
        var currentAccount: String? = "a"
        var backend: suspend (String) -> Boolean = { false }
        val store = FakeStore()
        val controller = BillingController(config, store,
            CoroutineScope(SupervisorJob() + Dispatchers.Unconfined), { currentAccount }, { backend(it) })
        fun connect(account: String = "a") {
            currentAccount = account
            controller.authChanged(AuthState.SignedIn(account, null))
        }
    }

    private class FakeStore : BillingStore {
        val events = mutableListOf<String>()
        var account: String? = null
        var active = false
        var failLogout = false
        var failIdentity = false
        var afterIdentify: () -> Unit = {}
        override suspend fun identify(accountId: String) {
            events += "identify:$accountId"
            if (failIdentity) error("synthetic identity error")
            account = accountId; afterIdentify()
        }
        override suspend fun signOut() {
            events += "logout"
            if (failLogout) error("synthetic logout error")
            account = null
        }
        override suspend fun products() = listOf(BillingProduct("monthly", PlusPlan.MONTHLY, "synthetic price"))
        override suspend fun hasPlus() = active
        override suspend fun restore(): Boolean { events += "restore"; return active }
    }
}
