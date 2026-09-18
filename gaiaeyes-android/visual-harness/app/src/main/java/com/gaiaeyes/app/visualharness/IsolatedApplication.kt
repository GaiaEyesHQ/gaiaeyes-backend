package com.gaiaeyes.app.visualharness

import android.Manifest
import android.app.Application
import android.content.pm.PackageManager
import android.os.StrictMode
import com.gaiaeyes.app.BuildConfig
import java.util.TimeZone

/** Test-only startup: never delegates to GaiaEyesApplication or constructs real services. */
class IsolatedApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        check(packageName == "com.gaiaeyes.g026.synthetic")
        check(checkSelfPermission(Manifest.permission.INTERNET) == PackageManager.PERMISSION_DENIED)
        check(BuildConfig.GAIA_API_BASE == "https://example.invalid")
        check(listOf(BuildConfig.SUPABASE_URL, BuildConfig.SUPABASE_ANON_KEY,
            BuildConfig.FIREBASE_PROJECT_ID, BuildConfig.FIREBASE_APPLICATION_ID,
            BuildConfig.FIREBASE_API_KEY, BuildConfig.FIREBASE_GCM_SENDER_ID,
            BuildConfig.REVENUECAT_ANDROID_API_KEY).all { it.isEmpty() })
        StrictMode.setThreadPolicy(StrictMode.ThreadPolicy.Builder().detectNetwork().penaltyDeath().build())
        TimeZone.setDefault(TimeZone.getTimeZone("America/Chicago"))
    }
}
