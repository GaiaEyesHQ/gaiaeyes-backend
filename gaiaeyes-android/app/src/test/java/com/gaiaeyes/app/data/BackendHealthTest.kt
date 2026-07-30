package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.HealthResponse
import com.gaiaeyes.app.core.network.HealthService
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackendHealthTest {
    @Test
    fun availableHealthRequiresServiceAndDatabase() = runBlocking {
        val repository = HealthRepository(
            healthService = FakeHealthService(
                response = HealthResponse(
                    ok = true,
                    db = true,
                    service = "gaiaeyes-backend",
                    time = "2026-07-28T12:00:00Z",
                ),
            ),
        )

        val result = repository.check()

        assertTrue(result.isAvailable)
        assertEquals("Live data service is ready", result.detail)
    }

    @Test
    fun databaseFailureProducesLimitedState() = runBlocking {
        val repository = HealthRepository(
            healthService = FakeHealthService(
                response = HealthResponse(ok = true, db = false),
            ),
        )

        val result = repository.check()

        assertFalse(result.isAvailable)
        assertEquals("The service is responding, but data is limited", result.detail)
    }

    @Test
    fun networkFailureProducesUnavailableState() = runBlocking {
        val repository = HealthRepository(
            healthService = FakeHealthService(error = IllegalStateException("offline")),
        )

        val result = repository.check()

        assertFalse(result.isAvailable)
        assertEquals("offline", result.detail)
    }

    private class FakeHealthService(
        private val response: HealthResponse? = null,
        private val error: Throwable? = null,
    ) : HealthService {
        override suspend fun health(): HealthResponse {
            error?.let { throw it }
            return requireNotNull(response)
        }
    }
}
