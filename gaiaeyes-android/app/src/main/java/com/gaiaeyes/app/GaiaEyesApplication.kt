package com.gaiaeyes.app

import android.app.Application
import com.gaiaeyes.app.core.di.AppContainer
import com.gaiaeyes.app.core.work.JournalDrainScheduler
import com.gaiaeyes.app.core.work.HealthSampleDrainScheduler
import com.gaiaeyes.app.notifications.FirebaseConfiguration

class GaiaEyesApplication : Application() {
    val container: AppContainer by lazy {
        AppContainer(
            context = this,
            apiBase = BuildConfig.GAIA_API_BASE,
            supabaseUrl = BuildConfig.SUPABASE_URL,
            supabaseAnonKey = BuildConfig.SUPABASE_ANON_KEY,
        )
    }

    override fun onCreate() {
        super.onCreate()
        FirebaseConfiguration.initialize(this)
        JournalDrainScheduler.schedulePeriodic(this)
        HealthSampleDrainScheduler.schedulePeriodic(this)
    }
}
