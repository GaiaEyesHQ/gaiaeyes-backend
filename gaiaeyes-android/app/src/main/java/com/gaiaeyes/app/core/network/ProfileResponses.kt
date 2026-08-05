package com.gaiaeyes.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ProfilePreferencesEnvelope(
    val ok: Boolean = false,
    val preferences: ProfilePreferences = ProfilePreferences(),
    val error: String? = null,
)

@Serializable
data class ProfilePreferences(
    val mode: String = "scientific",
    val guide: String = "cat",
    val tone: String = "balanced",
    @SerialName("temp_unit")
    val tempUnit: String? = null,
    @SerialName("onboarding_step")
    val onboardingStep: String = "welcome",
    @SerialName("onboarding_completed")
    val onboardingCompleted: Boolean = false,
)

@Serializable
data class ProfilePreferencesUpdate(
    val mode: String? = null,
    val guide: String? = null,
    val tone: String? = null,
    @SerialName("temp_unit")
    val tempUnit: String? = null,
    @SerialName("onboarding_step")
    val onboardingStep: String? = null,
    @SerialName("onboarding_completed")
    val onboardingCompleted: Boolean? = null,
)

@Serializable
data class ProfileLocationUpdate(
    val zip: String? = null,
    @SerialName("use_gps")
    val useGps: Boolean = false,
    @SerialName("local_insights_enabled")
    val localInsightsEnabled: Boolean = true,
)

@Serializable
data class ProfileTagCatalogEnvelope(
    val ok: Boolean = false,
    val items: List<ProfileTagOption> = emptyList(),
    val error: String? = null,
)

@Serializable
data class ProfileTagOption(
    @SerialName("tag_key")
    val tagKey: String = "",
    val label: String = "",
    val description: String? = null,
    val section: String? = null,
    @SerialName("is_active")
    val isActive: Boolean = true,
)

@Serializable
data class ProfileTagsEnvelope(
    val ok: Boolean = false,
    val tags: List<String> = emptyList(),
    val error: String? = null,
)

@Serializable
data class ProfileTagsUpdate(
    val tags: List<String>,
)
