# Gaia Eyes Android

Native Android foundation for Gaia Eyes.

## Current milestone

- Jetpack Compose + Material 3 app shell
- Responsive phone and tablet layout
- Supabase email magic-link authentication with Android Keystore-backed session
  storage
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
- Real unauthenticated `GET /health` check against the Gaia Eyes backend
- Manual dependency wiring for Supabase auth, Room, DataStore, WorkManager,
  and the pending Health Connect slice

The next vertical slice adds Health Connect import for the approved v1 signals.
HRV remains deferred: RMSSD must not be written as the existing SDNN sample
type.

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

## Local configuration

`local.properties` is ignored by Git. Android Studio writes `sdk.dir`; local
runtime values may also be supplied there or as process environment variables:

```properties
GAIA_API_BASE=https://gaiaeyes-backend.onrender.com
SUPABASE_URL=
SUPABASE_ANON_KEY=
REVENUECAT_ANDROID_API_KEY=
REVENUECAT_PLUS_MONTHLY_PRODUCT_ID=
REVENUECAT_PLUS_YEARLY_PRODUCT_ID=
```

Do not commit production keys, signing files, or a populated
`local.properties`. The RevenueCat values are reserved placeholders until the
Google Play products and Android RevenueCat app exist.

For magic-link testing, add `gaiaeyes://auth/callback` to the Supabase Auth
redirect allowlist. The Android app handles that callback without retaining the
link tokens in the Activity intent.
