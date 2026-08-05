package com.gaiaeyes.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingPresentationTest {
    @Test
    fun mapsPersistedBackendStepsToAndroidScreens() {
        assertEquals(OnboardingStep.WELCOME, onboardingStepFor("welcome"))
        assertEquals(OnboardingStep.PREFERENCES, onboardingStepFor("mode"))
        assertEquals(OnboardingStep.PREFERENCES, onboardingStepFor("guide"))
        assertEquals(OnboardingStep.PREFERENCES, onboardingStepFor("tone"))
        assertEquals(OnboardingStep.PREFERENCES, onboardingStepFor("temperature_unit"))
        assertEquals(OnboardingStep.PREFERENCES, onboardingStepFor("sensitivities"))
        assertEquals(OnboardingStep.HEALTH_CONTEXT, onboardingStepFor("health_context"))
        assertEquals(OnboardingStep.LOCATION, onboardingStepFor("location"))
        assertEquals(OnboardingStep.HEALTH_CONNECT, onboardingStepFor("healthkit"))
        assertEquals(OnboardingStep.HEALTH_CONNECT, onboardingStepFor("backfill"))
        assertEquals(OnboardingStep.HEALTH_CONNECT, onboardingStepFor("notifications"))
        assertEquals(OnboardingStep.READY, onboardingStepFor("activation"))
        assertEquals(OnboardingStep.WELCOME, onboardingStepFor("unexpected_step"))
    }

    @Test
    fun acceptsOnlyFiveDigitZipCodes() {
        assertTrue(isValidOnboardingZip("78754"))
        assertFalse(isValidOnboardingZip("7875"))
        assertFalse(isValidOnboardingZip("78A54"))
        assertFalse(isValidOnboardingZip("787541"))
    }
}
