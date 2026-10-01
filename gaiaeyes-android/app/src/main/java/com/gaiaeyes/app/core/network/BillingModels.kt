package com.gaiaeyes.app.core.network

import java.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BillingEntitlementsResponse(
    val ok: Boolean = false,
    @SerialName("user_id") val userId: String? = null,
    val entitlements: List<BillingEntitlement> = emptyList(),
)

@Serializable
data class BillingEntitlement(
    val key: String,
    @SerialName("is_active") val isActive: Boolean = false,
    @SerialName("expires_at") val expiresAt: String? = null,
) {
    fun providesPlus(now: Instant): Boolean =
        key in setOf("plus", "pro") && isActive &&
            (expiresAt == null || runCatching { Instant.parse(expiresAt).isAfter(now) }.getOrDefault(false))
}
