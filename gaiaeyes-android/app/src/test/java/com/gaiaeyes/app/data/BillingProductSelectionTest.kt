package com.gaiaeyes.app.data

import org.junit.Assert.*
import org.junit.Test

class BillingProductSelectionTest {
    private val catalog = listOf(
        BillingCatalogItem("subscription:monthly", "subscription", "P1M"),
        BillingCatalogItem("subscription:yearly", "subscription", "P1Y"),
    )
    @Test fun exactBasePlansKeepExistingConfigurationAndDurations() {
        val selected = selectBillingProducts(BillingConfig("key", mapOf(
            PlusPlan.MONTHLY to "subscription:monthly", PlusPlan.YEARLY to "subscription:yearly")), catalog)
        assertEquals("subscription:monthly", selected[PlusPlan.MONTHLY])
        assertEquals("subscription:yearly", selected[PlusPlan.YEARLY])
    }
    @Test fun highLevelSubscriptionOnlySelectsUnambiguousMatchingDuration() {
        val config = BillingConfig("key", mapOf(PlusPlan.MONTHLY to "subscription", PlusPlan.YEARLY to "subscription"))
        assertEquals(2, selectBillingProducts(config, catalog).size)
        val ambiguous = catalog + BillingCatalogItem("subscription:other-month", "subscription", "P1M")
        assertNull(selectBillingProducts(config, ambiguous)[PlusPlan.MONTHLY])
        assertEquals("subscription:yearly", selectBillingProducts(config, ambiguous)[PlusPlan.YEARLY])
    }
    @Test fun missingMismatchedAndUnresolvedConfigurationCannotCreateAnOption() {
        for (id in listOf("", "  ", "$(MONTHLY_ID)", "invented", "subscription:yearly")) {
            assertTrue(selectBillingProducts(BillingConfig("key", mapOf(PlusPlan.MONTHLY to id)), catalog).isEmpty())
        }
        assertFalse(BillingConfig("$(ANDROID_KEY)", emptyMap()).storeAvailable)
    }
}
