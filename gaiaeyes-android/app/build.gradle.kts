import java.util.Properties
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.configuration.BuildFeatures
import org.gradle.api.provider.ListProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

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

val supabaseUrl = runtimeValue(
    "SUPABASE_URL",
    runtimeValue("SUPABASE_REST_URL"),
)
val supabaseAnonKey = runtimeValue("SUPABASE_ANON_KEY")
val firebaseProjectId = runtimeValue("FIREBASE_PROJECT_ID")
val firebaseApplicationId = runtimeValue("FIREBASE_APPLICATION_ID")
val firebaseApiKey = runtimeValue("FIREBASE_API_KEY")
val firebaseGcmSenderId = runtimeValue("FIREBASE_GCM_SENDER_ID")

// Unsigned packaging is an explicit invocation choice, never a saved default.
val unsignedCandidate = gradle.startParameter.projectProperties["gaiaUnsignedCandidate"]?.let {
    it.toBooleanStrictOrNull()
        ?: throw GradleException("gaiaUnsignedCandidate must be true or false.")
} ?: false
val releaseSigningEnabled = gradle.startParameter.projectProperties["gaiaReleaseSigning"]?.let {
    it.toBooleanStrictOrNull()
        ?: throw GradleException("gaiaReleaseSigning must be true or false.")
} ?: false

abstract class ReleaseBuildFeatures {
    @get:Inject
    abstract val buildFeatures: BuildFeatures
}

// Check scope/cache before resolving any private-file references or contents.
if (releaseSigningEnabled) {
    if (unsignedCandidate) {
        throw GradleException("gaiaReleaseSigning and gaiaUnsignedCandidate cannot both be true.")
    }
    val allowedSigningTasks = setOf("bundleRelease", "assembleRelease", "validateReleaseSigning")
    val requestedTasks = gradle.startParameter.taskNames
    if (requestedTasks.isEmpty() || requestedTasks.any {
            val task = it.removePrefix(":")
            task !in allowedSigningTasks && task !in allowedSigningTasks.map { name -> "app:$name" }
        }
    ) {
        throw GradleException(
            "gaiaReleaseSigning is restricted to app bundleRelease, assembleRelease, or " +
                "validateReleaseSigning invocations. Run Debug/test/help and other tasks separately.",
        )
    }
    val configurationCache = objects.newInstance(ReleaseBuildFeatures::class.java)
        .buildFeatures.configurationCache
    if (configurationCache.active.get() || configurationCache.requested.orNull == true) {
        throw GradleException(
            "Release signing requires --no-configuration-cache. No private signing files were read.",
        )
    }
}

val releaseVersionCodeText = runtimeValue("ANDROID_VERSION_CODE")
val releaseVersionName = runtimeValue("ANDROID_VERSION_NAME")
val releaseVersionCode = releaseVersionCodeText.toIntOrNull()
val releaseSigningProblems = mutableListOf<String>()
if (!unsignedCandidate && !releaseSigningEnabled) {
    releaseSigningProblems += "Signed release requires -PgaiaReleaseSigning=true --no-configuration-cache."
}
if (!unsignedCandidate || releaseVersionCodeText.isNotBlank()) {
    if (!releaseVersionCodeText.matches(Regex("[0-9]+")) ||
        releaseVersionCode == null || releaseVersionCode !in 1..2_100_000_000
    ) {
        releaseSigningProblems += "ANDROID_VERSION_CODE must be an explicit integer from 1 to 2100000000."
    }
}
if (!unsignedCandidate && releaseVersionName.isBlank()) {
    releaseSigningProblems += "ANDROID_VERSION_NAME is required."
}

fun releaseFile(setting: String): java.io.File? {
    val path = runtimeValue(setting)
    if (path.isBlank()) {
        releaseSigningProblems += "$setting is required."
        return null
    }
    return rootProject.file(path).takeIf { it.isFile && it.canRead() } ?: run {
        releaseSigningProblems += "$setting must reference a readable existing file."
        null
    }
}

fun releasePassword(setting: String): String? {
    val file = releaseFile(setting) ?: return null
    val password = try {
        providers.fileContents(layout.projectDirectory.file(file.absolutePath))
            .asText.get().trimEnd('\r', '\n')
    } catch (_: Exception) {
        releaseSigningProblems += "$setting could not be read."
        return null
    }
    if (password.isEmpty() || password.contains('\n') || password.contains('\r')) {
        releaseSigningProblems += "$setting must contain one nonempty password line."
        return null
    }
    return password
}

val uploadKeystore = if (releaseSigningEnabled) releaseFile("ANDROID_UPLOAD_KEYSTORE_FILE") else null
val uploadKeyAlias = if (!releaseSigningEnabled) "" else runtimeValue("ANDROID_UPLOAD_KEY_ALIAS").also {
    if (it.isBlank()) releaseSigningProblems += "ANDROID_UPLOAD_KEY_ALIAS is required."
}
val uploadStorePassword = if (releaseSigningEnabled) releasePassword("ANDROID_UPLOAD_STORE_PASSWORD_FILE") else null
val uploadKeyPassword = if (releaseSigningEnabled) releasePassword("ANDROID_UPLOAD_KEY_PASSWORD_FILE") else null

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
            quotedBuildConfigValue(supabaseUrl),
        )
        buildConfigField(
            "String",
            "SUPABASE_ANON_KEY",
            quotedBuildConfigValue(supabaseAnonKey),
        )
        buildConfigField("String", "FIREBASE_PROJECT_ID", quotedBuildConfigValue(firebaseProjectId))
        buildConfigField("String", "FIREBASE_APPLICATION_ID", quotedBuildConfigValue(firebaseApplicationId))
        buildConfigField("String", "FIREBASE_API_KEY", quotedBuildConfigValue(firebaseApiKey))
        buildConfigField("String", "FIREBASE_GCM_SENDER_ID", quotedBuildConfigValue(firebaseGcmSenderId))
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

    signingConfigs {
        if (releaseSigningEnabled && releaseSigningProblems.isEmpty()) {
            create("playUpload") {
                storeFile = uploadKeystore
                storePassword = uploadStorePassword
                keyAlias = uploadKeyAlias
                keyPassword = uploadKeyPassword
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("playUpload")
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

androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        variant.outputs.forEach { output ->
            // Missing/invalid signed-release inputs fail before compilation below.
            output.versionCode.set(releaseVersionCode?.takeIf { it in 1..2_100_000_000 } ?: 1)
            output.versionName.set(releaseVersionName.ifBlank { "0.1.0-dev" })
        }
    }
}

dependencies {
    implementation("com.revenuecat.purchases:purchases:10.15.1")
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
    implementation(platform("com.google.firebase:firebase-bom:34.17.0"))
    implementation("com.google.firebase:firebase-messaging")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

abstract class ValidateReleaseConfiguration : DefaultTask() {
    @get:Input
    abstract val missingConfigurationNames: ListProperty<String>

    @TaskAction
    fun validate() {
        val missing = missingConfigurationNames.get()
        if (missing.isNotEmpty()) {
            throw GradleException(
                "Release account or notification configuration is missing: " +
                    missing.joinToString(", ") +
                    ". Set these Android values outside Git before building.",
            )
        }
    }
}

val validateReleaseConfiguration by tasks.registering(ValidateReleaseConfiguration::class) {
    group = "verification"
    description = "Fails release builds when secure account access is not configured."
    missingConfigurationNames.set(
        mapOf(
            "SUPABASE_URL (or SUPABASE_REST_URL)" to supabaseUrl,
            "SUPABASE_ANON_KEY" to supabaseAnonKey,
            "FIREBASE_PROJECT_ID" to firebaseProjectId,
            "FIREBASE_APPLICATION_ID" to firebaseApplicationId,
            "FIREBASE_API_KEY" to firebaseApiKey,
            "FIREBASE_GCM_SENDER_ID" to firebaseGcmSenderId,
        ).filterValues { it.isBlank() }.keys.toList(),
    )
}

abstract class ValidateReleaseSigning : DefaultTask() {
    @get:Input
    abstract val configurationProblems: ListProperty<String>

    @TaskAction
    fun validate() {
        val problems = configurationProblems.get()
        if (problems.isNotEmpty()) {
            throw GradleException(
                "Release signing/version configuration is incomplete:\n" +
                    problems.joinToString("\n") +
                    "\nUse the existing Play upload key and intended release version. " +
                    "For unsigned local packaging only, explicitly pass -PgaiaUnsignedCandidate=true.",
            )
        }
    }
}

val validateReleaseSigning by tasks.registering(ValidateReleaseSigning::class) {
    group = "verification"
    description = "Checks existing upload-key references and explicit release version inputs."
    configurationProblems.set(releaseSigningProblems)
}

tasks.matching { it.name == "preReleaseBuild" }.configureEach {
    dependsOn(validateReleaseConfiguration, validateReleaseSigning)
}
