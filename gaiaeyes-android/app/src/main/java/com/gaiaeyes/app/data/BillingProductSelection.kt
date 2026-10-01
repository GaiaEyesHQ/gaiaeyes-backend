package com.gaiaeyes.app.data

internal data class BillingCatalogItem(val id: String, val subscriptionId: String, val period: String)

/** Accept an exact Play subscription:base-plan identifier, or an unambiguous
 * subscription with the configured plan's duration. Never pick the first base plan.
 */
internal fun selectBillingProducts(config: BillingConfig, catalog: List<BillingCatalogItem>): Map<PlusPlan, String> =
    config.configuredProducts.mapNotNull { (plan, configuredId) ->
        catalog.filter { item ->
            item.period == plan.period && if (':' in configuredId) item.id == configuredId
            else item.subscriptionId == configuredId
        }.singleOrNull()?.let { plan to it.id }
    }.toMap()
