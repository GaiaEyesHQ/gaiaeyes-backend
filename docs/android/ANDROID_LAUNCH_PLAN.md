# Android Launch Plan

Last reviewed: 2026-07-28

## Decision

Build Gaia Eyes for Android as a native Kotlin + Jetpack Compose app. The Android package name is `com.gaiaeyes.app`.

The first Android release should reuse the existing backend and launch US-first. It should not introduce a new backend schema, new billing source of truth, or a broader health-data scope than the app can justify in Google Play review.

## Launch scope

### Included in Android v1

- Native Kotlin + Jetpack Compose app in a future `gaiaeyes-android/` directory.
- Package name: `com.gaiaeyes.app`.
- Minimum SDK: 28, because Health Connect supports Android 9/API 28+ devices with Google Play services.
- Target SDK: Android 16/API 36 or higher. Google Play requires this for new apps and updates beginning August 31, 2026.
- Supabase account sessions using the same identity and backend authorization model as iOS. The Android sign-in UX must be settled before scaffolding; do not introduce a parallel account model.
- Backend authenticated reads and writes using Supabase access tokens.
- RevenueCat Android SDK with Google Play Billing products mapped to the same Plus entitlement model.
- Optional Health Connect read flow for the minimum useful body-data set.
- Local stale-cache behavior that keeps the app useful when the backend or Health Connect is unavailable.
- US-first Google Play release.

### Deferred from Android v1

- HRV import, because Android Health Connect HRV semantics differ from the current backend `hrv_sdnn` contract.
- Cycle tracking, wrist temperature, BLE/Polar, camera, and push alerts.
- Android-specific backend schema changes unless contract tests prove an existing endpoint cannot support Android.
- Tablet-optimized layouts beyond functional responsive support.
- Website/app landing page Google Play badge until a Play listing URL exists.

## Architecture

The Android app should mirror the iOS separation of responsibilities:

- UI: Jetpack Compose screens for onboarding, Home, Body, Patterns, Outlook, Explore, Guide, Settings, Diagnostics, Subscribe, Restore, and share previews.
- State: a single app-level state holder with scoped caches for the active account.
- Networking: one authenticated API client that attaches `Authorization: Bearer <Supabase access token>`, refreshes tokens before protected requests, and never sends protected requests without a usable token.
- Persistence: encrypted token storage plus local app data stores for cached snapshots, queued symptoms, queued Health Connect uploads, diagnostics, and user preferences.
- Background work: WorkManager jobs for upload drain, Health Connect incremental reads, stale snapshot refresh, and safe retry after network/backend failures.

## Backend contract

Android should use the same backend endpoints already used by iOS:

- `GET /health`
- `GET /v1/features/today`
- `GET /v1/dashboard`
- `GET /v1/dashboard/gauges`
- `GET /v1/users/me/drivers`
- `GET /v1/users/me/outlook`
- `GET /v1/symptoms/today`
- `GET /v1/symptoms/daily`
- `GET /v1/symptoms/diag`
- `GET /v1/symptoms/current`
- `POST /v1/symptoms`
- `GET /v1/profile/preferences`
- `PUT /v1/profile/preferences`
- `GET /v1/profile/location`
- `PUT /v1/profile/location`
- `GET /v1/profile/tags/catalog`
- `GET /v1/profile/tags`
- `PUT /v1/profile/tags`
- `POST /v1/samples/batch`
- `GET /v1/billing/entitlements`
- Existing public space and earth endpoints under `/v1/space/*` and `/v1/earth/*`.

Android Health Connect uploads must use:

- `device_os: "android"`
- `source: "health_connect"`
- `user_id`: the Supabase user UUID, with the backend still enforcing authenticated user override.

## Health Connect v1 mapping

Only request data types that support user-facing Android v1 features.

| Health Connect signal | Backend type | Unit | Notes |
| --- | --- | --- | --- |
| Sleep sessions/stages | `sleep_stage` | none | Use `value_text` values aligned with iOS: `inBed`, `awake`, `rem`, `core`, `deep`, `asleep`. |
| Steps | `step_count` | `count` | Upload interval counts. |
| Heart rate | `heart_rate` | `bpm` | Upload sampled or summarized heart-rate values. |
| Resting heart rate | `resting_heart_rate` | `bpm` | Upload when available from Health Connect provider. |
| Respiratory rate | `respiratory_rate` | `br/min` | Upload sleep/recovery readings when available. |
| Oxygen saturation | `spo2` | `%` | Upload percentage values as `0..100`, matching current backend validation. |

Onboarding should clearly state Health Connect is optional. If skipped or denied, Android should still show public environmental and space-weather context. Body-specific cards should display cached data or a limited-state message rather than blanking unexpectedly.

## Billing and identity

- Configure a RevenueCat Android app for package `com.gaiaeyes.app`.
- Use Google Play subscription products that map to the same `plus` entitlement used by iOS and web.
- RevenueCat App User ID must be the Supabase user UUID.
- RevenueCat webhooks should continue posting to `/v1/webhooks/revenuecat`.
- Backend entitlement reads remain the source for gated API behavior; RevenueCat is the purchase and receipt-management layer.

## Rollout phases

1. Complete the Android contract/dependency readiness pass now.
2. Install Android Studio, the API 36 SDK, and a Google Play-enabled emulator.
3. Scaffold `gaiaeyes-android/` with Kotlin + Compose after dependency approval, with no secrets committed.
4. Implement auth, API client, cache/store layer, and core read-only surfaces.
5. Add symptom, exposure, and daily check-in writes. **Completed locally:
   authenticated writes, stable retry payloads, and account-scoped persistent
   foreground/session-refresh draining are implemented.**
6. Add Health Connect import and WorkManager upload drain after the HRV contract decision.
7. Create the Google Play organization account and listing after the LLC/D-U-N-S prerequisites are complete.
8. Add RevenueCat/Google Play Billing purchase and restore flow after Play products exist.
9. Run internal QA, then Play internal testing.
10. Complete any account-specific testing requirement before production access.
11. Release US-first with staged rollout.

## External requirements checked

- Google Play target API requirement: <https://developer.android.com/google/play/requirements/target-sdk>
- Health Connect publishing declaration: <https://developer.android.com/health-and-fitness/health-connect/declare-access>
- Health Connect availability/API 28 support: <https://developer.android.com/health-and-fitness/health-connect/availability>
- Health Connect data types and additional background/history permissions: <https://developer.android.com/health-and-fitness/health-connect/data-types>
- Google Play Data Safety: <https://support.google.com/googleplay/android-developer/answer/10787469>
- Google Play testing requirements for new personal accounts: <https://support.google.com/googleplay/android-developer/answer/14151465>
- RevenueCat Android quickstart: <https://www.revenuecat.com/docs/getting-started/quickstart>
