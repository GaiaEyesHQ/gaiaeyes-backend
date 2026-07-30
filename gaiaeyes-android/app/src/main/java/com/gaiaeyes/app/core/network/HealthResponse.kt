package com.gaiaeyes.app.core.network

import kotlinx.serialization.Serializable

@Serializable
data class HealthResponse(
    val ok: Boolean = false,
    val service: String = "",
    val time: String = "",
    val db: Boolean = false,
)

