package com.gaiaeyes.app

import android.app.Application
import com.gaiaeyes.app.core.di.AppContainer

class GaiaEyesApplication : Application() {
    val container: AppContainer by lazy {
        AppContainer(
            context = this,
            apiBase = BuildConfig.GAIA_API_BASE,
            supabaseUrl = BuildConfig.SUPABASE_URL,
            supabaseAnonKey = BuildConfig.SUPABASE_ANON_KEY,
        )
    }
}
