# Android Phase 0 Readiness

Last reviewed: 2026-07-28

## Outcome

Android engineering can begin before Gaia Eyes LLC, the D-U-N-S number, or the Google Play organization account is ready.

The business-account sequence only gates Play Console ownership, store configuration, Google Play Billing products, Play testing tracks, and release. It does not gate Android Studio setup, app scaffolding, emulator/device testing, backend integration, Health Connect development, or local build artifacts.

## Work that can start now

1. Complete Android Studio's setup wizard and install the Android 16/API 36 SDK.
2. Create a Google Play-enabled Pixel emulator and verify one physical Android device when available.
3. Scaffold `gaiaeyes-android/` with package `com.gaiaeyes.app` after dependency approval.
4. Implement the shared Gaia Eyes visual system, navigation, diagnostics, and cached app state.
5. Implement Supabase authentication and the authenticated backend client.
6. Build read-only Home, Body, Patterns, Outlook, and compact Explore surfaces from existing endpoints.
7. Add symptom logging and follow-ups, exposure logging, daily check-ins, profile preferences, and location. Exposure editing remains a separate backend/product task.
8. Add local cache/outbox behavior and WorkManager retry paths.
9. Implement Health Connect onboarding and supported data reads after the HRV mapping decision.
10. Run unit, Compose UI, emulator, offline, process-death, and tablet/foldable smoke tests.
11. Produce debug APKs and local release AABs. A Play Console account is only needed to upload and distribute them through Google Play.

## Work gated by the organization account

- Creating the Gaia Eyes Play Console organization and app listing.
- Enabling Play App Signing and internal/closed/production tracks.
- Creating Google Play subscription products.
- Linking those products to the RevenueCat Android app and testing real Play purchases/restores.
- Completing Play Data Safety, Health Apps, content-rating, store-listing, and identity declarations in the console.
- Uploading the signed app bundle and releasing it.

## Existing backend contract

No Android-only schema is required for the first implementation pass. Android should use the same authenticated API and Supabase user UUID as iOS.

| Android surface | Existing contract |
| --- | --- |
| Bootstrap / feature flags | `GET /health`, `GET /v1/features/today` |
| Home | `GET /v1/dashboard`, `GET /v1/dashboard/gauges`, `GET /v1/symptoms/today`, `GET /v1/users/me/drivers` |
| Body / active symptoms | `GET /v1/symptoms/current`, `GET /v1/symptoms/daily`, `POST /v1/symptoms` |
| Daily check-in | `POST /v1/feedback/daily-checkin` |
| Exposures | `GET /v1/exposures`, `POST /v1/exposures` |
| Patterns | `GET /v1/patterns`, `GET /v1/patterns/summary` |
| Outlook | `GET /v1/users/me/outlook` |
| Profile / onboarding | Existing `/v1/profile/*` location, preference, and tag routes |
| Health Connect upload | `POST /v1/samples/batch` with `device_os: "android"` and `source: "health_connect"` |
| Subscription state | `GET /v1/billing/entitlements` |
| Local context | `GET /v1/local/check` |

Contract tests should be added as each Android client model is introduced rather than duplicating backend models in advance.

## Foundation decisions

### 1. Authentication

Recommendation: mirror the current iOS Supabase magic-link/session behavior,
including its shared anonymous-account option, and preserve the Supabase UUID
as the single account identity. Users may later attach an email to that same
identity. Do not launch a separate Android-only identity or email/password
model.

### 2. HRV

Health Connect exposes RMSSD-oriented HRV while the current backend contract is named for SDNN. Do not silently write RMSSD values as `hrv_sdnn`.

Recommendation: keep HRV in Android v1, but first add an explicit backend sample type/metadata contract for RMSSD and keep UI wording source-neutral. Other Health Connect types can proceed independently.

### 3. Notifications

Recommendation: include local notification channels, permission handling, and settings scaffolding in v1. Defer Firebase Cloud Messaging and remote condition alerts until delivery rules, throttling, and credentials are approved.

## Approved dependency set

| Dependency | Purpose | Keep / avoid |
| --- | --- | --- |
| Jetpack Compose + Material 3 + Navigation Compose | Native UI and navigation | Keep |
| AndroidX Lifecycle / ViewModel | Screen and app state | Keep |
| Kotlin coroutines | Async work and state flows | Keep |
| Ktor Client + Kotlin Serialization | Authenticated API and JSON contracts | Keep; one networking stack |
| Supabase Kotlin `auth-kt` | Supabase sessions and magic links | Keep only for auth; backend remains the data API |
| Room | Scoped snapshot cache and durable upload outbox | Keep |
| DataStore | Non-sensitive settings and onboarding state | Keep |
| WorkManager | Health/symptom upload drain and safe retries | Keep |
| Health Connect client | Optional wearable/health import | Keep |
| RevenueCat Android | Plus purchase/restore | Add after Play products are available |
| Firebase Cloud Messaging | Remote alerts | Defer |
| Hilt or another DI framework | Dependency injection | Avoid initially; use explicit constructors/manual wiring |

Use Android Keystore-backed storage for session material. Do not commit API keys, service configuration, signing files, or environment files.

## Local environment status

The local Android toolchain is ready:

- Android Studio 2026.1 in `/Applications`
- Android Studio bundled JDK 21
- Android 16 / API 36.1 platform and build tools 36.0.0
- Gradle wrapper 9.4.1
- Google Play-enabled `GaiaEyes_Pixel8_API36` emulator

The emulator has been verified as Android 16, API 36, ARM64, boot-complete, and
Google Play Services-capable.

## Completed implementation milestones

The initial foundation and authenticated Home vertical slice are complete in
`gaiaeyes-android/`:

1. Native Compose/Material 3 project with package `com.gaiaeyes.app`.
2. Placeholder-safe environment injection from process variables or ignored
   `local.properties`.
3. Ktor API client and a real public `GET /health` vertical slice.
4. Supabase email magic-link and anonymous-account authentication with Android
   Keystore-backed encrypted session persistence and in-place email attachment.
5. Authenticated `GET /v1/dashboard/gauges` Home dashboard using the existing
   Supabase bearer contract.
6. Account-scoped saved dashboard, cache-first launch behavior, live refresh,
   and sign-out isolation.
7. Honest loading, reauthentication, stale-cache, and missing-configuration
   states that do not simulate user health data.
8. Unit contract tests plus clean compile, lint, unit-test, and debug-assembly
   checks.
9. Successful phone and tablet-layout emulator smoke checks.

The next milestone is Home symptom/driver enrichment followed by the read-only
Body surface. Health Connect, purchases, and publishing remain intentionally
out of this foundation slice.
