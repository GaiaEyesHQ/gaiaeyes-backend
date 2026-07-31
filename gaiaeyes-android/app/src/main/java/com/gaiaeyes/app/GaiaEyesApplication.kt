package com.gaiaeyes.app

import android.app.Application
import com.gaiaeyes.app.core.di.AppContainer
import com.gaiaeyes.app.core.work.JournalDrainScheduler

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
        JournalDrainScheduler.schedulePeriodic(this)
    }
}
