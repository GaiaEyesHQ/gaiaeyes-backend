package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.*
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class BillingAccountReadTest {
    @Test fun retriesUnauthorizedOnceWithSameAccountRefreshedToken() = runBlocking {
        val tokens = mutableListOf<String>()
        val result = readBillingForAccount("a", { "a" }, { "old" }, { "new" }, { token ->
            tokens += token
            if (token == "old") throw ApiUnauthorizedException()
            BillingEntitlementsResponse(true, "a", listOf(BillingEntitlement("plus", true)))
        })
        assertTrue(result); assertEquals(listOf("old", "new"), tokens)
    }

    @Test fun accountChangeDuringTokenRefreshDoesNotReadReplacementAccount() = runBlocking {
        var account = "a"; var calls = 0
        val error = runCatching { readBillingForAccount("a", { account }, { "old" }, { account = "b"; "new" }, {
            calls++; throw ApiUnauthorizedException()
        }) }.exceptionOrNull()
        assertTrue(error is CancellationException); assertEquals(1, calls)
    }

    @Test fun lateResponseOrMismatchedUserCannotGrantEntitlement() = runBlocking {
        for (changeAccount in listOf(false, true)) {
            var account = "a"
            val result = runCatching { readBillingForAccount("a", { account }, { "token" }, { error("no retry") }, {
                if (changeAccount) account = "b"
                BillingEntitlementsResponse(true, if (changeAccount) "a" else "b", listOf(BillingEntitlement("plus", true)))
            }) }
            assertTrue(result.isFailure)
        }
    }

    @Test fun rejectedEnvelopeMissingSessionAndRepeatedUnauthorizedAreNotFreeSuccesses() = runBlocking {
        assertTrue(runCatching {
            readBillingForAccount("a", { "a" }, { "token" }, { "new" }, { BillingEntitlementsResponse(false, "a") })
        }.isFailure)
        var reads = 0
        assertTrue(runCatching {
            readBillingForAccount("a", { "a" }, { "" }, { error("no retry") }, { reads++; error("no read") })
        }.isFailure)
        assertEquals(0, reads)
        assertTrue(runCatching {
            readBillingForAccount("a", { "a" }, { "token" }, { "new" }, { reads++; throw ApiUnauthorizedException() })
        }.exceptionOrNull() is ApiUnauthorizedException)
        assertEquals(2, reads)
    }

    @Test fun onlyRecognizedActiveUnexpiredEntitlementsProvidePlus() {
        val now = Instant.parse("2026-10-01T12:00:00Z")
        assertTrue(BillingEntitlement("plus", true).providesPlus(now))
        assertTrue(BillingEntitlement("pro", true, "2026-10-02T12:00:00+00:00").providesPlus(now))
        assertFalse(BillingEntitlement("surplus", true).providesPlus(now))
        assertFalse(BillingEntitlement("plus", false).providesPlus(now))
        assertFalse(BillingEntitlement("plus", true, "2026-10-01T12:00:00Z").providesPlus(now))
        assertFalse(BillingEntitlement("plus", true, "bad-date").providesPlus(now))
    }
}
