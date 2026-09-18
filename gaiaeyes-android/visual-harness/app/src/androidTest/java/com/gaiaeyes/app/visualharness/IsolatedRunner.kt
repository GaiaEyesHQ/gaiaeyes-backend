package com.gaiaeyes.app.visualharness

import android.app.Application
import android.content.Context
import androidx.test.runner.AndroidJUnitRunner

class IsolatedRunner : AndroidJUnitRunner() {
    override fun newApplication(cl: ClassLoader, className: String, context: Context): Application {
        check(className == IsolatedApplication::class.java.name)
        check(context.packageName == "com.gaiaeyes.g026.synthetic")
        return super.newApplication(cl, className, context)
    }
}
