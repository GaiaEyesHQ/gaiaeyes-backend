import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val localProperties = Properties().apply {
    val localPropertiesFile = rootProject.file("local.properties")
    if (localPropertiesFile.exists()) {
        localPropertiesFile.inputStream().use(::load)
    }
}

fun runtimeValue(name: String, fallback: String = ""): String {
    return providers.environmentVariable(name).orNull
        ?: localProperties.getProperty(name)
        ?: fallback
}

fun quotedBuildConfigValue(value: String): String {
    val escaped = value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
    return "\"$escaped\""
}

android {
    namespace = "com.gaiaeyes.app"

    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.gaiaeyes.app"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0-dev"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField(
            "String",
            "GAIA_API_BASE",
            quotedBuildConfigValue(
                runtimeValue(
                    "GAIA_API_BASE",
                    "https://gaiaeyes-backend.onrender.com",
                ),
            ),
        )
        buildConfigField(
            "String",
            "SUPABASE_URL",
            quotedBuildConfigValue(runtimeValue("SUPABASE_URL")),
        )
        buildConfigField(
            "String",
            "SUPABASE_ANON_KEY",
            quotedBuildConfigValue(runtimeValue("SUPABASE_ANON_KEY")),
        )
        buildConfigField(
            "String",
            "REVENUECAT_ANDROID_API_KEY",
            quotedBuildConfigValue(runtimeValue("REVENUECAT_ANDROID_API_KEY")),
        )
        buildConfigField(
            "String",
            "REVENUECAT_PLUS_MONTHLY_PRODUCT_ID",
            quotedBuildConfigValue(runtimeValue("REVENUECAT_PLUS_MONTHLY_PRODUCT_ID")),
        )
        buildConfigField(
            "String",
            "REVENUECAT_PLUS_YEARLY_PRODUCT_ID",
            quotedBuildConfigValue(runtimeValue("REVENUECAT_PLUS_YEARLY_PRODUCT_ID")),
        )
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.04.01")

    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.navigation:navigation-compose:2.9.8")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")

    implementation("io.ktor:ktor-client-core:3.3.3")
    implementation("io.ktor:ktor-client-okhttp:3.3.3")
    implementation("io.ktor:ktor-client-content-negotiation:3.3.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.3.3")

    implementation("io.github.jan-tennert.supabase:auth-kt:3.3.0")
    implementation("androidx.room:room-runtime:2.8.4")
    implementation("androidx.room:room-ktx:2.8.4")
    implementation("androidx.datastore:datastore-preferences:1.2.1")
    implementation("androidx.work:work-runtime-ktx:2.11.1")
    implementation("androidx.health.connect:connect-client:1.1.0")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

