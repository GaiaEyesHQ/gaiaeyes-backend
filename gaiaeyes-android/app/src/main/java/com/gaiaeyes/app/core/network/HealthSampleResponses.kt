package com.gaiaeyes.app.core.network

import kotlinx.serialization.Serializable

@Serializable
data class HealthSampleUpload(
    val user_id: String,
    val device_os: String,
    val source: String,
    val type: String,
    val start_time: String,
    val end_time: String,
    val value: Double? = null,
    val unit: String? = null,
    val value_text: String? = null,
)

@Serializable
data class HealthSampleBatchResponse(
    val ok: Boolean = false,
    val received: Int = 0,
    val inserted: Int = 0,
    val skipped: Int = 0,
    val buffered: Int = 0,
    val queued: Boolean = false,
    val db: Boolean? = null,
    val error: String? = null,
)
