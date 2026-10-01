# Gaia Eyes Android

Native Android foundation for Gaia Eyes.

## Current milestone

- Jetpack Compose + Material 3 app shell
- Responsive phone and tablet layout
- Supabase email magic-link and shared anonymous-account authentication with
  Android Keystore-backed session storage and in-place email attachment
- Resumable account-scoped onboarding backed by the shared profile APIs for
  display style, health context, optional approximate foreground location with
  a saved ZIP fallback/local insights, and optional Health Connect permission
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
- Optional Health Connect connection during onboarding or on Body with a
  30-day import for sleep,
  steps, heart rate, resting heart rate, respiratory rate, and oxygen
  saturation
- Account-scoped durable Health Connect upload batches with immediate and
  15-minute network-constrained retry
- Real unauthenticated `GET /health` check against the Gaia Eyes backend
- Manual dependency wiring for Supabase auth, Room, DataStore, WorkManager,
  and Health Connect
- Settings > Gaia Eyes Plus: RevenueCat Android purchase/restore, Play-localized
  monthly/yearly prices, account-isolated membership refresh and explicit pending/error states

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
`local.properties`. Billing uses these existing RevenueCat configuration names;
no product identifiers or prices are supplied by the source. Configure the existing
Android app and Play products, with the shared `plus` entitlement, before store QA.

## Android Plus billing

The native adapter uses RevenueCat `purchases:10.15.1` and the Supabase account UUID
as its App User ID, including for a guest account. Settings recommends attaching a
recovery email; it does not add a new purchase/account gate. Store operations and
identity transitions are serialized. Signing out clears visible membership state
immediately; an in-flight store callback cannot grant access to a replacement account.
Transient auth errors preserve identity only while the same account is still present.

Use the existing `REVENUECAT_PLUS_MONTHLY_PRODUCT_ID` and
`REVENUECAT_PLUS_YEARLY_PRODUCT_ID` values. A value may identify a Play subscription
or its exact `subscription:base-plan` pair. A subscription-only value must resolve
to exactly one matching monthly/yearly base plan; ambiguous, unavailable or wrong-duration
products are not offered. The UI displays the store's localized regular price.
RevenueCat selects its eligible default offer, whose final price and renewal terms
Google Play presents before confirmation. No offerings, prices or product IDs are invented.

Missing SDK configuration leaves purchase and restore visibly unavailable. Missing
products leave purchase unavailable but still allow an explicitly requested restore
when the SDK is configured. The app never automatically calls restore. Users should
restore while signed into their original Gaia Eyes account; RevenueCat's existing
restore/transfer policy must be confirmed during platform acceptance.

`GET /v1/billing/entitlements` supplies account membership status; SDK confirmation
and backend membership are separate. A confirmed receipt with an unrefreshed backend
shows syncing, and never writes a client-side entitlement. Refresh runs on account
changes, when Plus settings resumes, after purchase/restore, and on explicit request.
Unknown membership blocks a new purchase until refreshed. Existing membership leads
to management of the existing subscription rather than a second purchase. This adds
Android billing parity without changing free access, paid gating, prices, or the
existing iOS/web checkout surfaces. MainActivity uses `singleTop` to support payment
verification outside the app while retaining its deep-link routing.

Focused offline verification (no SDK configuration, store or production requests):

```sh
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  ./gradlew :app:testDebugUnitTest \
  --tests 'com.gaiaeyes.app.data.Billing*Test' \
  --tests 'com.gaiaeyes.app.core.network.BillingApiClientTest'
ANDROID_HOME="/Users/gennwu/Library/Android/sdk" \
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  ./gradlew -p visual-harness :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.gaiaeyes.app.visualharness.BillingSettingsScreenTest
```

Before release, verify the existing Android SDK key/app/package, Play product/base-plan
mapping and shared entitlement, webhook delivery, intended restore/transfer behavior,
and signed internal-track tester access. Device/store checks still include purchase,
cancellation, pending payment, approval/decline, restore, account switching, guest
email attachment, cross-platform membership, renewal/expiry/refund and returning from
external payment verification or auth/quick-log links. Synthetic tests establish source
behavior, not purchase, physical-device or store acceptance. No release package is
produced by the focused unit/UI checks above; the UI harness package is isolated.

SDK references: [installation](https://www.revenuecat.com/docs/getting-started/installation/android),
[identity](https://www.revenuecat.com/docs/customers/identifying-customers),
[restore](https://www.revenuecat.com/docs/getting-started/restoring-purchases).

## Release configuration

Release builds fail before compilation when required account/Firebase client
configuration is missing. The signing/version check below runs independently;
unsigned candidates retain the account/Firebase check.

## Release signing and version inputs

Use the **existing** upload key for the Play app `com.gaiaeyes.app`. No task
creates or resets a key, changes Play settings, or chooses a release version.
Provide these names through environment variables or ignored `local.properties`
(environment variables take precedence, including an explicitly empty value):

| Input | Required value |
| --- | --- |
| `ANDROID_VERSION_CODE` | Intended Play build code, an integer from 1 to 2100000000; confirm it is unused and greater than prior uploaded codes. |
| `ANDROID_VERSION_NAME` | Intended nonempty user-visible release version. |
| `ANDROID_UPLOAD_KEYSTORE_FILE` | Path to the existing upload keystore. |
| `ANDROID_UPLOAD_KEY_ALIAS` | Existing key alias in that keystore. |
| `ANDROID_UPLOAD_STORE_PASSWORD_FILE` | Path to a private UTF-8 file containing the keystore password. |
| `ANDROID_UPLOAD_KEY_PASSWORD_FILE` | Path to a private UTF-8 file containing the key password. |

Keep the keystore and password files outside Git. File references can be absolute
or relative to `gaiaeyes-android/`. Passwords are read as one nonempty line; a
trailing CR/LF is removed and spaces are preserved. Do not paste passwords into
commands, tracked files, reports, or logs. The validation task records only
configuration problem descriptions, not password values. Gradle/Android still
need the password values internally when signing. Private-file loading requires
the explicit command-line flag `-PgaiaReleaseSigning=true` and is restricted to
`bundleRelease`, `assembleRelease`, or `validateReleaseSigning` (optionally
qualified with `:app:`). Run other tasks separately. Configuration caching must
be disabled: the build checks Gradle's effective cache state and fails **before
reading private files** if caching is requested or active. Saved signing flags
cannot opt in. Ordinary Debug/test/help invocations never load these files or
create the upload signing configuration, even when references are configured.

Check the supplied inputs without compiling or signing:

```sh
./gradlew -PgaiaReleaseSigning=true --no-configuration-cache :app:validateReleaseSigning
```

Build with those same inputs after the selected version and upload identity have
been confirmed:

```sh
./gradlew -PgaiaReleaseSigning=true --no-configuration-cache :app:bundleRelease :app:assembleRelease
```

The release variant uses the supplied version and `playUpload` signing config;
Debug keeps its existing development version and debug signing. Missing inputs,
unreadable files, empty password files, and invalid build codes fail the release
check. This configuration check does **not** authenticate a keystore, verify its
alias/password, compare its certificate with Play, or query prior Play versions;
the actual signing and Play acceptance steps remain required. The explicit
preflight above reads the password files to check their shape and configure
signing, but does not compile, sign, or open the keystore contents. A release
invocation without either explicit signing mode or unsigned mode fails its guard.

For deliberately **unsigned local candidates**, opt in on that invocation:

```sh
./gradlew -PgaiaUnsignedCandidate=true :app:bundleRelease :app:assembleRelease
```

This bypasses upload-key loading/signing only. With no version inputs, it retains
the existing `0.1.0-dev`/code 1; explicitly supplied build codes must still be valid.
Only command-line `-PgaiaUnsignedCandidate=true` enables this mode; saved Gradle
properties, environment-backed project properties, and system properties cannot.
It never loads password files, even when signing references are saved locally.
Combining it with `-PgaiaReleaseSigning=true` is rejected before private-file access.
Outputs use the usual `app/build/outputs/bundle/release/` and
`app/build/outputs/apk/release/` directories, so retain any accepted package before
another build. Label the AAB as unsigned when copying it for review; the APK is
named `app-release-unsigned.apk`. Neither is a signed distribution candidate.

See Android's [app signing](https://developer.android.com/studio/publish/app-signing)
and [versioning](https://developer.android.com/studio/publish/versioning) guidance.

## Account and location QA

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

## Local conditions QA

Gaia Eyes requests approximate location only while the Android app is in use.
It does not request precise or background location. The resolved ZIP and
coordinates are saved to the shared profile so local conditions can load before
the next device-location refresh.

1. Start onboarding with a new account and choose **Use current location**.
2. Grant approximate location access and confirm the detected ZIP appears.
3. Finish onboarding, open **Explore > Local Weather**, and confirm local
   conditions load for that ZIP.
4. Change the saved location from either **Settings > Local conditions** or
   **Explore > Local Weather**, then confirm both surfaces show the new ZIP.
5. Disable current-location updates and save a manual ZIP. Reopen the app and
   confirm local conditions continue to load from that saved fallback.
