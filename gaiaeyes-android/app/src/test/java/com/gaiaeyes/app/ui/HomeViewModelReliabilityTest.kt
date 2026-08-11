package com.gaiaeyes.app.ui

import com.gaiaeyes.app.core.auth.AuthState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeViewModelReliabilityTest {
    private val signedIn = AuthState.SignedIn(
        accountId = "account-1",
        email = "person@example.com",
    )

    @Test
    fun preservesSignedInSurfaceDuringTransientSessionTransitions() {
        assertTrue(
            shouldPreserveSignedInSurface(
                currentAuthState = signedIn,
                nextAuthState = AuthState.Initializing,
                loadedAccountId = "account-1",
            ),
        )
        assertTrue(
            shouldPreserveSignedInSurface(
                currentAuthState = signedIn,
                nextAuthState = AuthState.SessionProblem("offline"),
                loadedAccountId = "account-1",
            ),
        )
    }

    @Test
    fun clearsSignedInSurfaceForRealSignOutOrDifferentAccount() {
        assertFalse(
            shouldPreserveSignedInSurface(
                currentAuthState = signedIn,
                nextAuthState = AuthState.SignedOut,
                loadedAccountId = "account-1",
            ),
        )
        assertFalse(
            shouldPreserveSignedInSurface(
                currentAuthState = signedIn,
                nextAuthState = AuthState.SessionProblem("offline"),
                loadedAccountId = "account-2",
            ),
        )
    }

    @Test
    fun rateLimitsForegroundHealthImports() {
        val now = 2_000_000L

        assertTrue(shouldRunForegroundHealthImport(lastImportAt = 0L, now = now))
        assertFalse(
            shouldRunForegroundHealthImport(
                lastImportAt = now - 14 * 60 * 1_000L,
                now = now,
            ),
        )
        assertTrue(
            shouldRunForegroundHealthImport(
                lastImportAt = now - 15 * 60 * 1_000L,
                now = now,
            ),
        )
    }
}
