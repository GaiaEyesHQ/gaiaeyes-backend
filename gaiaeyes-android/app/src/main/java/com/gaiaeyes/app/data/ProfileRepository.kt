package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.auth.AuthRepository
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import com.gaiaeyes.app.core.network.GaiaApiClient
import com.gaiaeyes.app.core.network.ProfileLocation
import com.gaiaeyes.app.core.network.ProfileLocationUpdate
import com.gaiaeyes.app.core.network.ProfilePreferences
import com.gaiaeyes.app.core.network.ProfilePreferencesUpdate
import com.gaiaeyes.app.core.network.ProfileTagOption
import com.gaiaeyes.app.core.network.ProfileTagsUpdate

class ProfileRepository(
    private val authRepository: AuthRepository,
    private val apiClient: GaiaApiClient,
) {
    suspend fun load(): ProfileBundle = authenticatedRequest {
        val token = authRepository.accessToken()
        ProfileBundle(
            preferences = apiClient.profilePreferences(token),
            location = apiClient.profileLocation(token),
            tagCatalog = apiClient.profileTagCatalog(token)
                .filter { it.isActive && it.section == "health_context" },
            selectedTags = apiClient.profileTags(token).toSet(),
        )
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
}

data class ProfileBundle(
    val preferences: ProfilePreferences,
    val location: ProfileLocation?,
    val tagCatalog: List<ProfileTagOption>,
    val selectedTags: Set<String>,
)
