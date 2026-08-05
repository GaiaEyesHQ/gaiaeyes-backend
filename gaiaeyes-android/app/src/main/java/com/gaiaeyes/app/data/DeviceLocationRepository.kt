package com.gaiaeyes.app.data

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Looper
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.util.Locale
import kotlin.coroutines.resume

data class DevicePostalLocation(
    val zip: String,
    val latitude: Double,
    val longitude: Double,
)

class DeviceLocationRepository(
    private val context: Context,
) {
    private val locationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    fun hasPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.ACCESS_COARSE_LOCATION,
    ) == PackageManager.PERMISSION_GRANTED

    suspend fun currentPostalLocation(): DevicePostalLocation {
        check(hasPermission()) { "Location access is not available." }

        val location = currentLocation()
            ?: throw IllegalStateException("Your current location could not be found. Try again shortly or enter a ZIP code.")
        val zip = reverseGeocodeZip(location)
            ?: throw IllegalStateException("A ZIP code could not be found for your current location. You can enter one manually.")

        return DevicePostalLocation(
            zip = zip,
            latitude = location.latitude,
            longitude = location.longitude,
        )
    }

    @SuppressLint("MissingPermission")
    private suspend fun currentLocation(): Location? {
        val lastKnown = enabledProviders()
            .mapNotNull { provider -> runCatching { locationManager.getLastKnownLocation(provider) }.getOrNull() }
            .maxByOrNull { it.time }
        val freshEnough = lastKnown?.takeIf {
            System.currentTimeMillis() - it.time <= LAST_KNOWN_MAX_AGE_MS
        }
        if (freshEnough != null) return freshEnough

        val provider = preferredProvider() ?: return lastKnown
        return withTimeoutOrNull(LOCATION_TIMEOUT_MS) {
            suspendCancellableCoroutine { continuation ->
                val listener = object : LocationListener {
                    override fun onLocationChanged(location: Location) {
                        locationManager.removeUpdates(this)
                        if (continuation.isActive) continuation.resume(location)
                    }

                    @Deprecated("Deprecated in Android")
                    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit

                    override fun onProviderEnabled(provider: String) = Unit

                    override fun onProviderDisabled(provider: String) = Unit
                }

                continuation.invokeOnCancellation { locationManager.removeUpdates(listener) }
                runCatching {
                    locationManager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
                }.onFailure {
                    locationManager.removeUpdates(listener)
                    if (continuation.isActive) continuation.resume(null)
                }
            }
        } ?: lastKnown
    }

    private fun enabledProviders(): List<String> = listOf(
        LocationManager.NETWORK_PROVIDER,
        LocationManager.GPS_PROVIDER,
        LocationManager.PASSIVE_PROVIDER,
    ).filter { provider ->
        runCatching { locationManager.isProviderEnabled(provider) }.getOrDefault(false)
    }

    private fun preferredProvider(): String? = enabledProviders().firstOrNull()

    @Suppress("DEPRECATION")
    private suspend fun reverseGeocodeZip(location: Location): String? = withContext(Dispatchers.IO) {
        if (!Geocoder.isPresent()) return@withContext null
        val geocoder = Geocoder(context, Locale.US)
        runCatching {
            geocoder.getFromLocation(location.latitude, location.longitude, 5)
                ?.asSequence()
                ?.mapNotNull { normalizedUsZip(it.postalCode) }
                ?.firstOrNull()
        }.getOrNull()
    }

    private companion object {
        const val LOCATION_TIMEOUT_MS = 10_000L
        const val LAST_KNOWN_MAX_AGE_MS = 10 * 60 * 1_000L
    }
}

internal fun normalizedUsZip(value: String?): String? {
    val match = Regex("\\b(\\d{5})(?:-\\d{4})?\\b").find(value.orEmpty())
    return match?.groupValues?.getOrNull(1)
}
