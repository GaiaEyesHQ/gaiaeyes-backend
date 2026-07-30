package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.HealthService

class HealthRepository(
    private val healthService: HealthService,
) {
    suspend fun check(): BackendHealth {
        return runCatching {
            val response = healthService.health()
            BackendHealth(
                isAvailable = response.ok && response.db,
                checkedAt = response.time,
                detail = if (response.ok && response.db) {
                    "Live data service is ready"
                } else {
                    "The service is responding, but data is limited"
                },
            )
        }.getOrElse { error ->
            BackendHealth(
                isAvailable = false,
                checkedAt = "",
                detail = error.message ?: "Gaia Eyes could not reach the data service",
            )
        }
    }
}

data class BackendHealth(
    val isAvailable: Boolean,
    val checkedAt: String,
    val detail: String,
)
