package com.gaiaeyes.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DeviceLocationRepositoryTest {
    @Test
    fun normalizesFiveDigitAndZipPlusFourValues() {
        assertEquals("78754", normalizedUsZip("78754"))
        assertEquals("78754", normalizedUsZip("78754-1234"))
    }

    @Test
    fun rejectsMissingOrInvalidPostalCodes() {
        assertNull(normalizedUsZip(null))
        assertNull(normalizedUsZip("7875"))
        assertNull(normalizedUsZip("Austin"))
    }
}
