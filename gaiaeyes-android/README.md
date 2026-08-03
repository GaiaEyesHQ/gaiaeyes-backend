# Gaia Eyes Android

Native Android foundation for Gaia Eyes.

## Current milestone

- Jetpack Compose + Material 3 app shell
- Responsive phone and tablet layout
- Supabase email magic-link and shared anonymous-account authentication with
  Android Keystore-backed session storage and in-place email attachment
- Authenticated `GET /v1/dashboard/gauges` Home dashboard with all eight shared
  Gaia Eyes gauges in a compact, expandable layout
- Account-scoped saved dashboard with live refresh and sign-out isolation
- Cache-first current/possible symptoms and Signals to Watch on Home
- Cache-first read-only Body page with sleep stages, efficiency, health stats,
  personal deltas, steps, and heart range
- Cache-first read-only Patterns page with summary-first loading, expanded
  evidence, and responsive phone/tablet cards
- Cache-first read-only Outlook page with the shared seven-day signal cards,
  likely symptom domains, and responsive phone/tablet layouts
- Cache-first read-only Explore / All Drivers page with shared relevance order,
  current signal strength, personal pattern context, active symptoms, and
  responsive phone/tablet cards
- Authenticated symptom, exposure, and daily check-in writes from Home
- Account-scoped persistent write queue with stable retry payloads and
  serialized foreground/session-refresh draining
- Network-constrained WorkManager retry after failed foreground delivery plus
  a 15-minute safety drain for pending journal writes
- Optional Health Connect connection on Body with a 30-day import for sleep,
  steps, heart rate, resting heart rate, respiratory rate, and oxygen
  saturation
- Account-scoped durable Health Connect upload batches with immediate and
  15-minute network-constrained retry
- Real unauthenticated `GET /health` check against the Gaia Eyes backend
- Manual dependency wiring for Supabase auth, Room, DataStore, WorkManager,
  and Health Connect

HRV remains deferred: Health Connect RMSSD must not be written as Gaia Eyes'
existing SDNN sample type. The Health Connect import is opt-in and the rest of
the app remains usable when access is skipped or unavailable.

## Open and run

1. Open the `gaiaeyes-android` directory in Android Studio.
2. Let Android Studio use its bundled JDK.
3. Select the `app` run configuration.
4. Start `GaiaEyes_Pixel8_API36` or another API 36 Google Play emulator.
5. Run the app.

Command-line verification:

```sh
cd /Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-android
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  ./gradlew :app:lintDebug :app:testDebugUnitTest :app:assembleDebug
```

The debug APK is written to:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## Emulator Health Connect seed QA

Use Google's [Health Connect Toolbox](https://developer.android.com/health-and-fitness/health-connect/test/health-connect-toolbox)
to exercise the real Android read and upload path before testing on a physical
device. Keep these records synthetic and confined to the emulator.

1. Download the Toolbox APK linked from the Android documentation and install
   it with `adb install HealthConnectToolbox-*.apk`.
2. In the Toolbox, request all Health Connect permissions and insert recent
   records for sleep, steps, heart rate, resting heart rate, respiratory rate,
   and oxygen saturation. Representative QA values are 4,321 steps, 72 bpm,
   64 resting bpm, 14.2 breaths/min, and 98% SpO2.
3. Open Gaia Eyes, sign in, and use **Body > Health Connect > Import recent
   health data**.
4. Confirm the import reports readings, the pending-sync count clears, and the
   backend receives `device_os=android`, `source=health_connect` rows for all
   six supported sample families.

The number Gaia Eyes reads can be slightly higher than the number inserted in
the database because the backend idempotently skips duplicate sample keys.

## Local configuration

`local.properties` is ignored by Git. Android Studio writes `sdk.dir`; local
runtime values may also be supplied there or as process environment variables:

```properties
GAIA_API_BASE=https://gaiaeyes-backend.onrender.com
SUPABASE_URL=
# SUPABASE_REST_URL= may be used instead of SUPABASE_URL
SUPABASE_ANON_KEY=
REVENUECAT_ANDROID_API_KEY=
REVENUECAT_PLUS_MONTHLY_PRODUCT_ID=
REVENUECAT_PLUS_YEARLY_PRODUCT_ID=
```

Do not commit production keys, signing files, or a populated
`local.properties`. The RevenueCat values are reserved placeholders until the
Google Play products and Android RevenueCat app exist.

Release builds fail before compilation when the Supabase URL or public anon
key is missing. This prevents publishing a build that cannot start secure
account access.

For magic-link testing, add `gaiaeyes://auth/callback` to the Supabase Auth
redirect allowlist. The Android app handles that callback without retaining the
link tokens in the Activity intent.

For guest-account QA:

1. Start from a fresh app install and choose **Continue without email**.
2. Confirm Home loads under the new account and Settings labels it as a guest.
3. In Settings, add an email and open the confirmation link on the same device.
4. Confirm the account keeps its dashboard and journal history after the email
   is attached. Do not clear app data or uninstall before attaching an email;
   an unlinked anonymous account cannot be recovered afterward.
