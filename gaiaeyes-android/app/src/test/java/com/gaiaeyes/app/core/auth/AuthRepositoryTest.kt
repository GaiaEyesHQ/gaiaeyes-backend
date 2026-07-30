package com.gaiaeyes.app.core.auth

import org.junit.Assert.assertEquals
import org.junit.Test

class AuthRepositoryTest {
    @Test
    fun preservesSupabaseProjectUrl() {
        assertEquals(
            "https://example.supabase.co",
            normalizeSupabaseProjectUrl("https://example.supabase.co/"),
        )
    }

    @Test
    fun convertsSupabaseRestEndpointToProjectUrl() {
        assertEquals(
            "https://example.supabase.co",
            normalizeSupabaseProjectUrl(" https://example.supabase.co/rest/v1/ "),
        )
    }
}
