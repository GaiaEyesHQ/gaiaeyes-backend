package com.gaiaeyes.app.data

import android.util.Log
import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.ProfileLocation
import com.gaiaeyes.app.core.network.ProfileLocationUpdate
import com.gaiaeyes.app.core.network.ProfilePreferences
import com.gaiaeyes.app.core.network.ProfilePreferencesUpdate
import com.gaiaeyes.app.core.network.ProfileTagOption
import com.gaiaeyes.app.core.network.ProfileTagsUpdate
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay

class ProfileRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
) {
    suspend fun load(): ProfileBundle = authenticatedRequest {
        var token = loadStage("session") { authRepository.accessToken() }
        val preferences = try {
            loadRequiredStage("preferences", attempts = 1) {
                apiClient.profilePreferences(token)
            }
        } catch (error: Exception) {
            if (error is CancellationException || error is ApiUnauthorizedException) {
                throw error
            }
            token = loadStage("session_refresh") { authRepository.refreshAccessToken() }
            loadRequiredStage("preferences", attempts = 2) {
                apiClient.profilePreferences(token)
            }
        }
        coroutineScope {
            val location = async {
                loadOptionalStage("location", null) { apiClient.profileLocation(token) }
            }
            val tagCatalog = async {
                loadOptionalStage("tag_catalog", emptyList()) {
                    apiClient.profileTagCatalog(token)
                }.filter { it.isActive && it.section == "health_context" }
            }
            val selectedTags = async {
                loadOptionalStage("selected_tags", emptyList()) {
                    apiClient.profileTags(token)
                }.toSet()
            }
            ProfileBundle(
                preferences = preferences,
                location = location.await(),
                tagCatalog = tagCatalog.await(),
                selectedTags = selectedTags.await(),
            )
        }
    }

    suspend fun savePreferences(update: ProfilePreferencesUpdate): ProfilePreferences =
        authenticatedRequest {
            apiClient.updateProfilePreferences(authRepository.accessToken(), update)
        }

    suspend fun loadLocation(): ProfileLocation? = authenticatedRequest {
        apiClient.profileLocation(authRepository.accessToken())
    }

    suspend fun saveLocation(update: ProfileLocationUpdate): ProfileLocation? =
        authenticatedRequest {
            apiClient.updateProfileLocation(authRepository.accessToken(), update)
        }

    suspend fun saveTags(tags: Set<String>): Set<String> = authenticatedRequest {
        apiClient.updateProfileTags(
            authRepository.accessToken(),
            ProfileTagsUpdate(tags.toList().sorted()),
        ).toSet()
    }

    private suspend fun <T> authenticatedRequest(block: suspend () -> T): T = try {
        block()
    } catch (unauthorized: ApiUnauthorizedException) {
        authRepository.signOut()
        throw unauthorized
    }

    private suspend fun <T> loadStage(stage: String, block: suspend () -> T): T = try {
        block()
    } catch (error: Exception) {
        Log.e(
            "GaiaSetup",
            "Profile load failed stage=$stage type=${error.javaClass.simpleName} message=${error.message}",
        )
        throw error
    }

    private suspend fun <T> loadRequiredStage(
        stage: String,
        attempts: Int = 3,
        block: suspend () -> T,
    ): T {
        var lastError: Exception? = null
        repeat(attempts) { attempt ->
            try {
                return block()
            } catch (unauthorized: ApiUnauthorizedException) {
                throw unauthorized
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                lastError = error
                Log.w(
                    "GaiaSetup",
                    "Required profile load unavailable stage=$stage " +
                        "attempt=${attempt + 1}/$attempts " +
                        "type=${error.javaClass.simpleName} message=${error.message}",
                )
                if (attempt + 1 < attempts) {
                    delay(750L * (attempt + 1))
                }
            }
        }
        throw checkNotNull(lastError)
    }

    private suspend fun <T> loadOptionalStage(
        stage: String,
        fallback: T,
        block: suspend () -> T,
    ): T = try {
        block()
    } catch (unauthorized: ApiUnauthorizedException) {
        throw unauthorized
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (error: Exception) {
        Log.w(
            "GaiaSetup",
            "Optional profile load unavailable stage=$stage " +
                "type=${error.javaClass.simpleName} message=${error.message}",
        )
        fallback
    }
}

data class ProfileBundle(
    val preferences: ProfilePreferences,
    val location: ProfileLocation?,
    val tagCatalog: List<ProfileTagOption>,
    val selectedTags: Set<String>,
)
