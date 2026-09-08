package com.gaiaeyes.app.data

import com.gaiaeyes.app.core.network.ProfilePreferences
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileRepositoryTest {
    @Test
    fun completedOnboardingSkipsOptionalDetailLoad() = runBlocking {
        var detailsLoaded = false
        val preferences = ProfilePreferences(onboardingCompleted = true)

        val bundle = profileBundleFor(preferences) {
            detailsLoaded = true
            error("Completed onboarding should not load optional details")
        }

        assertFalse(detailsLoaded)
        assertEquals(preferences, bundle.preferences)
        assertEquals(null, bundle.location)
        assertTrue(bundle.tagCatalog.isEmpty())
        assertTrue(bundle.selectedTags.isEmpty())
    }

    @Test
    fun incompleteOnboardingStillLoadsOptionalDetails() = runBlocking {
        var detailsLoaded = false
        val preferences = ProfilePreferences(onboardingCompleted = false)
        val expected = ProfileBundle(
            preferences = preferences,
            location = null,
            tagCatalog = emptyList(),
            selectedTags = setOf("migraine"),
        )

        val bundle = profileBundleFor(preferences) {
            detailsLoaded = true
            expected
        }

        assertTrue(detailsLoaded)
        assertEquals(expected, bundle)
    }
}
