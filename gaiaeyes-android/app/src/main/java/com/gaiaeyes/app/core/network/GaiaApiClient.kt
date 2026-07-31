package com.gaiaeyes.app.core.network

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.timeout
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.URLProtocol
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

class GaiaApiClient(
    apiBase: String,
    private val httpClient: HttpClient = defaultHttpClient(apiBase),
) : HealthService {
    override suspend fun health(): HealthResponse {
        val response = httpClient.get("/health")
        check(response.status.isSuccess()) {
            "Backend returned ${response.status.value}"
        }
        return response.body()
    }

    suspend fun dashboardGauges(accessToken: String): DashboardGaugesResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for dashboard data"
        }
        val response = httpClient.get("/v1/dashboard/gauges") {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Dashboard returned ${response.status.value}"
        }
        return response.body()
    }

    suspend fun currentSymptoms(accessToken: String): CurrentSymptomsResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for symptom data"
        }
        val response = httpClient.get("/v1/symptoms/current?window_hours=12") {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Current symptoms returned ${response.status.value}"
        }
        val envelope = response.body<CurrentSymptomsEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "Current symptoms were unavailable"
        }
        return requireNotNull(envelope.data)
    }

    suspend fun allDrivers(accessToken: String): AllDriversResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for driver data"
        }
        val response = httpClient.get("/v1/users/me/drivers") {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
            timeout {
                requestTimeoutMillis = DRIVERS_TIMEOUT_MILLIS
                socketTimeoutMillis = DRIVERS_TIMEOUT_MILLIS
            }
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Drivers returned ${response.status.value}"
        }
        val drivers = response.body<AllDriversResponse>()
        check(drivers.ok) {
            "Drivers were unavailable"
        }
        return drivers
    }

    suspend fun featuresToday(accessToken: String): FeaturesTodayResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for Body data"
        }
        val response = httpClient.get("/v1/features/today") {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Body data returned ${response.status.value}"
        }
        val envelope = response.body<FeaturesTodayEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "Body data was unavailable"
        }
        return requireNotNull(envelope.data)
    }

    suspend fun patternsSummary(accessToken: String): PatternsResponse {
        return authenticatedPatternsRequest(
            path = "/v1/patterns/summary",
            accessToken = accessToken,
            timeoutMillis = DEFAULT_TIMEOUT_MILLIS,
        )
    }

    suspend fun patterns(accessToken: String): PatternsResponse {
        return authenticatedPatternsRequest(
            path = "/v1/patterns",
            accessToken = accessToken,
            timeoutMillis = PATTERNS_TIMEOUT_MILLIS,
        )
    }

    suspend fun userOutlook(accessToken: String): OutlookResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for Outlook data"
        }
        val response = httpClient.get("/v1/users/me/outlook") {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
            timeout {
                requestTimeoutMillis = OUTLOOK_TIMEOUT_MILLIS
                socketTimeoutMillis = OUTLOOK_TIMEOUT_MILLIS
            }
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Outlook returned ${response.status.value}"
        }
        val outlook = response.body<OutlookResponse>()
        check(outlook.ok) {
            "Outlook was unavailable"
        }
        return outlook
    }

    suspend fun symptomCodes(accessToken: String): List<SymptomCodeOption> {
        val response = authenticatedGet("/v1/symptoms/codes", accessToken)
        val envelope = response.body<SymptomCodeEnvelope>()
        check(envelope.ok) {
            envelope.friendlyError ?: envelope.error ?: "Symptom choices were unavailable"
        }
        return envelope.data.filter(SymptomCodeOption::isActive)
    }

    suspend fun createSymptom(
        accessToken: String,
        request: SymptomEventRequest,
    ): SymptomEventData {
        val response = authenticatedPost("/v1/symptoms", accessToken, request)
        val envelope = response.body<SymptomEventEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "The symptom could not be saved"
        }
        return requireNotNull(envelope.data)
    }

    suspend fun exposureCatalog(accessToken: String): List<ExposureCatalogOption> {
        val response = authenticatedGet("/v1/exposures/catalog", accessToken)
        val envelope = response.body<ExposureCatalogEnvelope>()
        check(envelope.ok) {
            envelope.friendlyError ?: envelope.error ?: "Exposure choices were unavailable"
        }
        return envelope.data
    }

    suspend fun createExposure(
        accessToken: String,
        request: ExposureEventRequest,
    ): ExposureEventData {
        val response = authenticatedPost("/v1/exposures", accessToken, request)
        val envelope = response.body<ExposureEventEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "The exposure could not be saved"
        }
        return requireNotNull(envelope.data)
    }

    suspend fun dailyCheckInStatus(accessToken: String): DailyCheckInStatus {
        val response = authenticatedGet("/v1/feedback/daily-checkin", accessToken)
        val envelope = response.body<DailyCheckInStatusEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "The daily check-in was unavailable"
        }
        return requireNotNull(envelope.data)
    }

    suspend fun submitDailyCheckIn(
        accessToken: String,
        request: DailyCheckInRequest,
    ): DailyCheckInEntry {
        val response = authenticatedPost("/v1/feedback/daily-checkin", accessToken, request)
        val envelope = response.body<DailyCheckInEntryEnvelope>()
        check(envelope.ok && envelope.data != null) {
            envelope.friendlyError ?: envelope.error ?: "The daily check-in could not be saved"
        }
        return requireNotNull(envelope.data)
    }

    private suspend fun authenticatedGet(path: String, accessToken: String) =
        httpClient.get(path) {
            header(HttpHeaders.Authorization, "Bearer ${requiredToken(accessToken)}")
        }.also(::throwIfUnauthorizedOrFailed)

    private suspend inline fun <reified T> authenticatedPost(
        path: String,
        accessToken: String,
        request: T,
    ) = httpClient.post(path) {
        header(HttpHeaders.Authorization, "Bearer ${requiredToken(accessToken)}")
        contentType(ContentType.Application.Json)
        setBody(request)
    }.also(::throwIfUnauthorizedOrFailed)

    private fun requiredToken(accessToken: String): String {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required"
        }
        return accessToken
    }

    private fun throwIfUnauthorizedOrFailed(response: io.ktor.client.statement.HttpResponse) {
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Gaia Eyes returned ${response.status.value}"
        }
    }

    private suspend fun authenticatedPatternsRequest(
        path: String,
        accessToken: String,
        timeoutMillis: Long,
    ): PatternsResponse {
        require(accessToken.isNotBlank()) {
            "An authenticated session is required for pattern data"
        }
        val response = httpClient.get(path) {
            header(HttpHeaders.Authorization, "Bearer $accessToken")
            timeout {
                requestTimeoutMillis = timeoutMillis
                socketTimeoutMillis = timeoutMillis
            }
        }
        if (response.status == HttpStatusCode.Unauthorized) {
            throw ApiUnauthorizedException()
        }
        check(response.status.isSuccess()) {
            "Patterns returned ${response.status.value}"
        }
        val patterns = response.body<PatternsResponse>()
        check(patterns.ok) {
            "Patterns were unavailable"
        }
        return patterns
    }

    companion object {
        private fun defaultHttpClient(apiBase: String): HttpClient {
            val normalizedBase = apiBase.trim().trimEnd('/')
            require(normalizedBase.isNotBlank()) { "GAIA_API_BASE is required" }

            return HttpClient(OkHttp) {
                expectSuccess = false
                install(HttpTimeout) {
                    requestTimeoutMillis = DEFAULT_TIMEOUT_MILLIS
                    connectTimeoutMillis = DEFAULT_TIMEOUT_MILLIS
                    socketTimeoutMillis = DEFAULT_TIMEOUT_MILLIS
                }
                install(ContentNegotiation) {
                    json(
                        Json {
                            ignoreUnknownKeys = true
                            isLenient = true
                        },
                    )
                }
                defaultRequest {
                    url(normalizedBase)
                    if (url.protocol == URLProtocol.HTTP) {
                        url.protocol = URLProtocol.HTTPS
                    }
                }
            }
        }

        private const val DEFAULT_TIMEOUT_MILLIS = 15_000L
        private const val DRIVERS_TIMEOUT_MILLIS = 60_000L
        private const val PATTERNS_TIMEOUT_MILLIS = 30_000L
        private const val OUTLOOK_TIMEOUT_MILLIS = 30_000L
    }
}

interface HealthService {
    suspend fun health(): HealthResponse
}

class ApiUnauthorizedException : IllegalStateException("Your Gaia Eyes session has expired")
