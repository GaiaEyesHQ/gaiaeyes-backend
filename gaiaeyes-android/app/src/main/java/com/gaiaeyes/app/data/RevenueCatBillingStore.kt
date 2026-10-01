package com.gaiaeyes.app.data

import android.app.Activity
import android.content.Context
import com.revenuecat.purchases.CacheFetchPolicy
import com.revenuecat.purchases.CustomerInfo
import com.revenuecat.purchases.LogLevel
import com.revenuecat.purchases.ProductType
import com.revenuecat.purchases.PurchaseParams
import com.revenuecat.purchases.Purchases
import com.revenuecat.purchases.PurchasesConfiguration
import com.revenuecat.purchases.PurchasesError
import com.revenuecat.purchases.PurchasesErrorCode
import com.revenuecat.purchases.getCustomerInfoWith
import com.revenuecat.purchases.getProductsWith
import com.revenuecat.purchases.logInWith
import com.revenuecat.purchases.logOutWith
import com.revenuecat.purchases.purchaseWith
import com.revenuecat.purchases.restorePurchasesWith
import com.revenuecat.purchases.models.GoogleStoreProduct
import com.revenuecat.purchases.models.StoreProduct
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

/** Only invoked by BillingController's serialized operations, on the main thread. */
class RevenueCatBillingStore(context: Context, private val config: BillingConfig) : BillingStore {
    private val applicationContext = context.applicationContext
    private var productsById = emptyMap<String, StoreProduct>()

    override suspend fun identify(accountId: String) {
        check(config.storeAvailable && accountId.isNotBlank())
        if (!Purchases.isConfigured) {
            Purchases.logLevel = LogLevel.ERROR
            Purchases.configure(PurchasesConfiguration.Builder(applicationContext, config.apiKey.trim())
                .appUserID(accountId).build())
        }
        if (Purchases.sharedInstance.appUserID != accountId) {
            productsById = emptyMap()
            suspendCoroutine<Unit> { continuation ->
                Purchases.sharedInstance.logInWith(accountId,
                    onError = { continuation.resumeWithException(it.safeFailure()) },
                    onSuccess = { _, _ -> continuation.resume(Unit) })
            }
        }
        check(Purchases.sharedInstance.appUserID == accountId)
    }

    override suspend fun signOut() {
        productsById = emptyMap()
        if (!Purchases.isConfigured || Purchases.sharedInstance.isAnonymous) return
        suspendCoroutine<Unit> { continuation ->
            Purchases.sharedInstance.logOutWith(
                onError = { continuation.resumeWithException(it.safeFailure()) },
                onSuccess = { continuation.resume(Unit) })
        }
    }

    override suspend fun products(): List<BillingProduct> {
        productsById = emptyMap()
        val ids = config.configuredProducts.values.map { it.substringBefore(':') }.distinct()
        if (ids.isEmpty()) return emptyList()
        val products = suspendCoroutine<List<StoreProduct>> { continuation ->
            Purchases.sharedInstance.getProductsWith(ids, ProductType.SUBS,
                onError = { continuation.resumeWithException(it.safeFailure()) },
                onGetStoreProducts = { continuation.resume(it) })
        }
        val googleProducts = products.filterIsInstance<GoogleStoreProduct>()
            .filter { it.defaultOption != null }
        val selected = selectBillingProducts(config, googleProducts.map {
            BillingCatalogItem(it.id, it.productId, it.period?.iso8601.orEmpty())
        })
        productsById = googleProducts.filter { it.id in selected.values }.associateBy { it.id }
        return selected.map { (plan, id) -> BillingProduct(id, plan, productsById.getValue(id).price.formatted) }
    }

    override suspend fun hasPlus(): Boolean = suspendCoroutine { continuation ->
        Purchases.sharedInstance.getCustomerInfoWith(CacheFetchPolicy.FETCH_CURRENT,
            onError = { continuation.resumeWithException(it.safeFailure()) },
            onSuccess = { continuation.resume(it.providesPlus()) })
    }

    override suspend fun restore(): Boolean = suspendCoroutine { continuation ->
        Purchases.sharedInstance.restorePurchasesWith(
            onError = { continuation.resumeWithException(it.safeFailure()) },
            onSuccess = { continuation.resume(it.providesPlus()) })
    }

    suspend fun purchase(activity: Activity, productId: String): Boolean {
        val product = productsById[productId]
            ?: throw BillingStoreException(BillingFailure.UNAVAILABLE)
        if (activity.isFinishing || activity.isDestroyed) throw BillingStoreException(BillingFailure.UNAVAILABLE)
        return suspendCoroutine { continuation ->
            Purchases.sharedInstance.purchaseWith(PurchaseParams.Builder(activity, product).build(),
                onError = { error, cancelled ->
                    continuation.resumeWithException(if (cancelled) BillingStoreException(BillingFailure.CANCELLED)
                        else error.safeFailure())
                },
                onSuccess = { _, info -> continuation.resume(info.providesPlus()) })
        }
    }

    // Same shared entitlement keys as iOS and the billing backend; no client-created grants.
    private fun CustomerInfo.providesPlus() = entitlements["plus"]?.isActive == true ||
        entitlements["pro"]?.isActive == true

    private fun PurchasesError.safeFailure() = BillingStoreException(when (code) {
        PurchasesErrorCode.PurchaseCancelledError -> BillingFailure.CANCELLED
        PurchasesErrorCode.PaymentPendingError -> BillingFailure.PENDING
        PurchasesErrorCode.ProductNotAvailableForPurchaseError -> BillingFailure.UNAVAILABLE
        else -> BillingFailure.FAILED
    })
}
