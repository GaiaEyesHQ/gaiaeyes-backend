# Codex Task: Build Gaia Eyes Android v1

Use this task after the iOS launch has had 7 stable days of monitoring. Do not start the Android app scaffold before that stabilization window unless explicitly directed.

## Goal

Create a native Android app for Gaia Eyes using Kotlin + Jetpack Compose with package `com.gaiaeyes.app`. The Android app must reuse the existing Gaia Eyes backend, Supabase auth, RevenueCat entitlement model, and `/v1/samples/batch` Health Connect upload contract.

## Required reading

- `AGENTS.md`
- `docs/android/ANDROID_LAUNCH_PLAN.md`
- `docs/android/ANDROID_PARITY_MATRIX.md`
- `docs/android/GOOGLE_PLAY_CHECKLIST.md`
- `docs/IOS_APP.md`
- `gaiaeyes-ios/docs/ios/Frontend_Overview.md`
- `docs/ENVIRONMENT_VARIABLES.md`
- `app/routers/ingest.py`
- `app/api/webhooks.py`

## Hard constraints

- No secrets committed.
- No backend schema changes unless contract tests prove they are required.
- No new Android health data types outside the approved v1 Health Connect set.
- No HRV, cycle tracking, wrist temperature, BLE/Polar, camera, or push alerts in Android v1.
- RevenueCat App User ID must equal the Supabase UUID.
- Protected backend calls must never be sent without a valid Supabase bearer.
- Cached snapshots must remain visible during transient backend failures.

## Deliverables

1. Create `gaiaeyes-android/` as a native Kotlin + Jetpack Compose project.
2. Add build config placeholders for:
   - `GAIA_API_BASE`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `REVENUECAT_ANDROID_API_KEY`
   - `REVENUECAT_PLUS_MONTHLY_PRODUCT_ID`
   - `REVENUECAT_PLUS_YEARLY_PRODUCT_ID`
3. Implement Supabase anonymous and email/password auth.
4. Implement encrypted token/session storage.
5. Implement a single authenticated backend API client with token refresh and reauth notice behavior.
6. Implement app-scoped caches for features, dashboard, gauges, drivers, outlook, symptoms, profile, and Health Connect diagnostics.
7. Implement WorkManager-backed upload queues for symptoms and Health Connect samples.
8. Implement Health Connect read flow for sleep, steps, heart rate, resting heart rate, respiratory rate, and SpO2 only.
9. Implement RevenueCat Android purchase and restore flow for Plus monthly/yearly.
10. Implement core screens: onboarding, Home, Body, Patterns, Outlook, Explore, Guide, Settings, Diagnostics, Subscribe/Restore, and share cards.

## Health Connect upload contract

Use `POST /v1/samples/batch` with rows shaped like:

```json
{
  "user_id": "<supabase-user-uuid>",
  "device_os": "android",
  "source": "health_connect",
  "type": "sleep_stage",
  "start_time": "2026-05-01T06:00:00Z",
  "end_time": "2026-05-01T06:30:00Z",
  "value": null,
  "unit": null,
  "value_text": "deep"
}
```

Allowed Android v1 sample types:

- `sleep_stage`
- `step_count`
- `heart_rate`
- `resting_heart_rate`
- `respiratory_rate`
- `spo2`

Allowed `sleep_stage.value_text` values:

- `inBed`
- `awake`
- `rem`
- `core`
- `deep`
- `asleep`

## Acceptance tests

- Fresh install can complete onboarding with Health Connect skipped.
- Fresh install can complete onboarding with Health Connect granted.
- Health Connect initial import uploads accepted Android payloads.
- Health Connect permission denial does not block app use.
- Existing account login restores cached account-scoped state.
- Token expiry triggers refresh before protected requests.
- Lost secure session shows reauth UI and suppresses unauthenticated protected calls.
- Plus purchase and restore update backend entitlements.
- Dashboard/features/drivers keep stale cache on backend timeout.
- Symptom and health upload queues retry without data loss.
- Google Play internal test build installs and passes smoke on phone and tablet.
