package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AccountDeletionPreflightEnvelope(val ok: Boolean = false, val data: AccountDeletionPreflight? = null)

@Serializable
data class AccountDeletionPreflight(
    @SerialName("user_id") val userId: String,
    @SerialName("delete_ready") val deleteReady: Boolean = false,
    @SerialName("auth_delete_ready") val authDeleteReady: Boolean = false,
)

@Serializable
data class AccountDeletionEnvelope(val ok: Boolean = false, val data: AccountDeletionResult? = null)

@Serializable
data class AccountDeletionResult(
    @SerialName("deleted_user_id") val deletedUserId: String,
    @SerialName("rows_deleted") val rowsDeleted: Long,
    @SerialName("tables_touched") val tablesTouched: Int,
)
