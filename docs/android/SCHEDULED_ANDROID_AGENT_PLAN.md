# Scheduled Android Agent Plan

Last updated: 2026-07-08

## Goal

Start a scheduled Codex/agent track that converts Gaia Eyes into an Android MVP while protecting the iOS release path, production stability, and the health-pattern positioning.

Yes: Gaia Eyes is ready to start Android work now. The right first move is not a full port of every iOS surface. The Android v1 should prove the core promise quickly:

- wearable and symptom context
- personal patterns
- outlook / forecast
- symptom and exposure logging
- subscription access
- Health Connect import where available

Space, Schumann, local, and forecast data should power the pattern read, but Android v1 does not need the full Explore library, earthquake dashboard, Schumann dashboard, hazard pages, or deep scientific displays on day one.

## Existing Decisions To Preserve

- Build native Android with Kotlin and Jetpack Compose.
- Use package name `com.gaiaeyes.app`.
- Create the Android app under `gaiaeyes-android/`.
- Reuse the existing Gaia Eyes backend, Supabase auth model, and RevenueCat subscription model.
- Do not create parallel data sources or Android-only schemas unless backend contract tests prove a gap.
- Keep Android v1 US-first.
- Keep Android copy health-pattern first, plain-English, and non-diagnostic.
- Keep Gaia Eyes positioned as pattern discovery, not diagnosis, detox, treatment, or certainty.

## Day-One Android Scope

Android v1 should include:

- Supabase email/password auth.
- Authenticated backend API client with bearer token support.
- Cached snapshots for key screens so stale data is visible rather than blank.
- Home read focused on gauges, possible symptoms, signals to watch, and daily tip.
- Body page with health stats, symptom logging, exposure logging, and daily check-in entry points.
- Patterns page showing existing pattern cards and confidence buckets.
- Outlook page with 7-day health-pattern forecast context.
- Explore / All Drivers as a compact driver list only, not full scientific dashboards.
- Settings for profile, location, sensitivities, subscription, restore purchase, diagnostics, and sign out.
- Health Connect onboarding and import for the minimum useful data set, including HRV when available.
- Notification permission, notification channels, settings UI, and device-token registration scaffolding.
- RevenueCat subscription and restore flow.

Android v1 should defer:

- Full space weather dashboard.
- Full Schumann dashboard.
- Earthquake pages.
- Hazard pages.
- Camera/photo features.
- BLE / Polar integration.
- Wrist temperature.
- Tablet-specific polish beyond functional responsiveness.

Android v1.1 / optional module candidates:

- Condition-based push alert delivery after alert rules, stale-data guards, user preferences, and throttling are tested.
- Cycle tracking after consent copy, privacy language, onboarding choices, and Google Play data safety declarations are ready.

## Health Connect V1 Data Set

Start with the data types already expected by the backend ingestion contract:

- sleep duration and sleep stages
- steps
- heart rate
- resting heart rate
- HRV / RMSSD where Health Connect provides it
- respiratory rate
- SpO2

Each upload should use:

- `device_os: "android"`
- `source: "health_connect"`
- Supabase user UUID as the user identity, with backend user override behavior preserved

HRV is part of Android v1 because it is central to Gaia Eyes pattern detection. The app should handle it as availability-dependent: import it when the user's device/app ecosystem provides it, and show clear "not available from this source" copy when it does not.

Cycle data should not be treated as unimportant. It should be planned as the next optional health module unless Jennifer explicitly pulls it into v1. It needs extra consent, inclusive onboarding language, and accurate Google Play data safety declarations before launch.

Do not add Health Connect categories outside this v1 set until the backend, privacy copy, and Google Play Health Connect declaration are updated.

## User Setup Checklist

Jennifer should start these in parallel while the scheduled agent begins code planning.

### Local Tools

Install Android Studio:

- Official download: https://developer.android.com/studio
- Homebrew option:

```bash
brew install --cask android-studio
```

In Android Studio, install:

- latest stable Android SDK platform required by Google Play
- Android SDK Build Tools
- Android SDK Platform Tools
- Android Emulator
- Google Play system image for emulator testing

Create at least one emulator:

- Pixel 8 or newer
- current stable Android release image
- Google Play services enabled

Recommended but not required:

- one physical Android device with Google Play services
- Health Connect available or installable

### Google Play

Create or confirm:

- Google Play Console developer account
- app listing for Gaia Eyes
- package name `com.gaiaeyes.app`
- internal testing track

Before submission, verify current Google Play target SDK rules:

- https://developer.android.com/google/play/requirements/target-sdk

If the account is a new personal developer account, plan for the current closed testing requirement before production:

- https://support.google.com/googleplay/android-developer/answer/14151465

### RevenueCat

Create a RevenueCat Android app for:

- `com.gaiaeyes.app`

Add Google Play products equivalent to the iOS Plus products and map them to the existing Plus entitlement.

RevenueCat docs:

- https://www.revenuecat.com/docs/getting-started/quickstart

### Push Notification Foundation

Android v1 should include notification permission handling, notification channels, user-facing notification settings, and a placeholder device-token registration path. Real condition-based alert delivery can wait until v1.1.

For remote push delivery, prepare a Firebase project / Firebase Cloud Messaging setup for the Android app, but do not commit Firebase config or server credentials until the implementation task explicitly needs them.

### Local Secrets

Do not commit these. Put them in local Android config or environment files only:

- `GAIA_API_BASE`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `REVENUECAT_ANDROID_API_KEY`
- `REVENUECAT_PLUS_MONTHLY_PRODUCT_ID`
- `REVENUECAT_PLUS_YEARLY_PRODUCT_ID`
- Firebase / FCM Android config and server-side credentials when push delivery work begins

## Scheduled Agent Operating Contract

Every Android scheduled run should:

1. Start with:

```bash
git status --short
```

2. Read the required docs before editing:

- `AGENTS.md`
- `docs/android/SCHEDULED_ANDROID_AGENT_PLAN.md`
- `docs/android/ANDROID_LAUNCH_PLAN.md`
- `docs/android/ANDROID_PARITY_MATRIX.md`
- `docs/android/CODEX_ANDROID_TASK.md`
- `docs/android/GOOGLE_PLAY_CHECKLIST.md`
- `docs/ENVIRONMENT_VARIABLES.md`

3. Inspect current backend contracts before building UI assumptions:

- `app/routers`
- auth/security helpers
- symptom endpoints
- exposure endpoints
- dashboard/gauge endpoints
- pattern/outlook endpoints
- sample ingest endpoint
- billing entitlement endpoints

4. Work in small branches or worktrees named like:

```text
codex/android-v1-<short-task>
```

5. Deliver one focused change per run.

6. Do not:

- add secrets
- publish or submit to Google Play
- add new backend schema without explicit approval
- add new dependencies without approval
- broaden Android v1 beyond the MVP scope
- implement Health Connect data types outside the v1 list

7. Run checks after every meaningful change.

8. Add a short note to `docs/android/ANDROID_AGENT_LOG.md` after meaningful Android implementation work.

## Dependency Approval Gate

Before adding Android dependencies, the scheduled agent should propose a short dependency list and wait for approval.

Expected categories to evaluate:

- AndroidX / Jetpack Compose
- Kotlin coroutines
- network client, likely OkHttp/Retrofit or Ktor
- JSON parsing, likely Kotlin Serialization or Moshi
- encrypted token storage
- local cache storage
- WorkManager
- Health Connect client
- notification channels and Android 13+ notification permission handling
- Firebase Cloud Messaging only when remote push delivery is approved
- RevenueCat Android SDK
- Supabase auth approach, either official SDK or small direct auth client

The agent should explain why each dependency is needed and whether it can be avoided.

## Phase Plan

### Phase 0: Contract Inventory

Output:

- endpoint contract notes
- screen-to-endpoint map
- missing backend gaps, if any
- dependency proposal

No scaffolding unless dependencies are already approved.

### Phase 1: Android Scaffold

Output:

- `gaiaeyes-android/` project
- package `com.gaiaeyes.app`
- Compose app shell
- local config placeholders
- debug build that opens on emulator

Checks:

- Gradle sync
- debug build
- emulator launch smoke test

### Phase 2: Auth, API Client, And Cache

Output:

- Supabase login/logout
- bearer token storage
- authenticated API client
- refresh behavior
- cached dashboard/outlook/pattern snapshots

Acceptance:

- protected calls are never sent without bearer token
- expired token path does not blank the app
- stale cached data shows with a clear freshness label

### Phase 3: Read-Only Health Pattern MVP

Output:

- Home
- Body read-only health stats
- Patterns
- Outlook
- compact Explore / All Drivers
- Settings shell

Acceptance:

- app is useful without Health Connect permission
- core screens do not show internal notes
- stale data is labeled rather than hidden
- copy is health-pattern first

### Phase 4: Symptom And Exposure Logging

Output:

- symptom log sheet
- exposure diary sheet
- daily check-in entry point
- offline queue / retry behavior

Acceptance:

- user can log a symptom in under 10 seconds
- user can log an exposure in under 10 seconds
- failed submissions retry without duplicate visible logs

### Phase 5: Health Connect

Output:

- permission flow
- 30-day backfill where feasible
- daily/background sync using WorkManager
- `/v1/samples/batch` uploads
- HRV/RMSSD import when available from Health Connect

Acceptance:

- works with permissions skipped
- works with permissions granted
- uploads use `device_os: "android"` and `source: "health_connect"`
- backend accepts samples
- user can see upload/freshness status
- HRV shows as available, unavailable, or waiting for enough samples instead of disappearing silently

### Phase 6: Notification Foundation

Output:

- Android notification permission flow
- notification channels
- notification settings screen
- local notification smoke path
- device-token registration placeholder or contract notes

Acceptance:

- app does not ask for notification permission before there is a user-facing reason
- permission denied does not break the app
- settings clearly explain what alert types will exist
- no condition-based alert delivery ships until stale-data guards and throttling are tested

### Phase 7: RevenueCat And Subscriptions

Output:

- paywall
- purchase
- restore
- entitlement sync
- settings subscription state

Acceptance:

- RevenueCat app user ID matches Supabase UUID
- Plus entitlement unlocks the same Android surfaces expected from iOS
- restore works after reinstall

### Phase 8: Internal Testing Readiness

Output:

- internal APK/AAB
- Google Play internal testing checklist
- screenshots
- privacy/data safety draft notes
- QA issue list

Acceptance:

- app installs from internal test track
- login works
- Health Connect flow works or skips cleanly
- symptom/exposure logging works
- no critical stale/blank screen bugs

## Automation Cadence

Suggested schedule:

- Daily Android build agent: 60-120 minutes.
- Weekly Android review bundle: summarize changed files, screenshots, build status, blockers, and what Jennifer needs to approve.

The Android track should not block iOS release updates. Keep iOS V2 shipping, screenshots, and App Store positioning moving while Android scaffolding begins.

## First Scheduled Run Prompt

Use this prompt for the first Android automation:

```text
You are starting the Gaia Eyes Android v1 conversion track.

Read AGENTS.md and docs/android/SCHEDULED_ANDROID_AGENT_PLAN.md first, then review docs/android/ANDROID_LAUNCH_PLAN.md, docs/android/ANDROID_PARITY_MATRIX.md, docs/android/CODEX_ANDROID_TASK.md, docs/android/GOOGLE_PLAY_CHECKLIST.md, and docs/ENVIRONMENT_VARIABLES.md.

Do not create a full Android scaffold yet unless the dependency plan is already approved. First deliver:
1. a concise endpoint/screen contract inventory,
2. a proposed Android dependency list with reasons,
3. any backend gaps or risks,
4. the smallest next implementation step.

Do not add secrets, do not publish anything, do not change backend schema, and do not broaden Android v1 beyond auth, health/pattern home, body, patterns, outlook, symptoms, exposures, Health Connect v1 including HRV where available, notification foundation, subscriptions, and compact drivers.
```

## Website Parity Note

No website change is required until the Google Play listing exists. Once the internal Android build is stable and the Play listing is created, update the website/app landing page and member hub with:

- Google Play badge
- Android availability language
- any Android-specific privacy/support notes
