# Google Play Checklist

Last reviewed: 2026-05-03

## App setup

- Create the Play Console app as Gaia Eyes.
- Package name: `com.gaiaeyes.app`.
- Initial release country: United States.
- Category: Health & Fitness, with Weather/environmental context reflected in the listing copy.
- Privacy policy URL: `https://gaiaeyes.com/privacy-policy/`.
- Terms URL: `https://gaiaeyes.com/terms/`.
- Target SDK: Android 15/API 35 or higher unless Google Play raises the requirement before Android submission.
- Minimum SDK: 28.

## Store listing

- Use app-specific screenshots from the Android build, not iOS screenshots.
- Explain Gaia Eyes as wellness/environmental context, not diagnosis or treatment.
- State Health Connect is optional and the app remains useful with public environmental/space-weather context when skipped.
- Avoid medical claims, prediction guarantees, or wording that implies clinical advice.
- Add a Google Play badge to the website only after the listing URL is live.

## Data Safety

Prepare Data Safety answers for:

- Health and fitness: symptoms and optional Health Connect data.
- Location: coarse/local location or ZIP-derived local context, depending on Android implementation.
- Contact info: email when a user creates an account.
- Identifiers: Supabase user ID, device/app identifiers where applicable.
- Purchases: subscription status via Google Play/RevenueCat.
- Usage data and diagnostics: analytics, crash/performance diagnostics, app interactions.

Review all SDKs before submission. Google requires accurate disclosure for data collected by the app and third-party SDKs.

Source: <https://support.google.com/googleplay/android-developer/answer/10787469>

## Health Connect declaration

Declare only the Android v1 data types:

- Sleep.
- Steps.
- Heart rate.
- Resting heart rate.
- Respiratory rate.
- Oxygen saturation.

For each data type, describe the user-facing benefit: daily body context, sleep/recovery context, and comparison with environmental signals. Do not request HRV, cycle, temperature, BLE, or camera-related permissions in Android v1.

The Android app must show the same privacy policy in the Health Connect permissions rationale activity that is provided in Play Console.

Sources:

- <https://developer.android.com/health-and-fitness/health-connect/declare-access>
- <https://developer.android.com/health-and-fitness/health-connect/data-types>
- <https://developer.android.com/health-and-fitness/health-connect/availability>

## Subscriptions

- Configure Google Play subscription products for Plus monthly and Plus yearly.
- Configure RevenueCat Android app for package `com.gaiaeyes.app`.
- Map Google Play products to the same `plus` entitlement.
- Keep RevenueCat App User ID equal to the Supabase UUID.
- Confirm `/v1/webhooks/revenuecat` receives Android purchase events and updates backend entitlements.
- Include subscription terms, privacy policy, restore behavior, subscription period, and price in-app.

Source: <https://www.revenuecat.com/docs/getting-started/quickstart>

## Testing tracks

- Internal testing: use immediately for engineering and trusted device smoke tests.
- Closed testing: plan for it even if the account may not require it.
- If the Play account is a newly-created personal developer account, Google currently requires a closed test with at least 12 opted-in testers for 14 continuous days before applying for production access.
- Use staged rollout for production after approval.

Source: <https://support.google.com/googleplay/android-developer/answer/14151465>

## Pre-submit QA

- Fresh install and onboarding with Health Connect skipped.
- Fresh install and onboarding with Health Connect granted.
- Existing account login.
- Anonymous-to-account upgrade.
- Subscription purchase and restore in Google Play sandbox.
- Dashboard and Body surfaces with no Health Connect data.
- Dashboard and Body surfaces after Health Connect import.
- Offline launch from cached snapshots.
- Token expiry/refresh path with queued symptom and health uploads.
- Redis ingest queue depth remains healthy during import tests.
- Tablet/foldable responsive smoke.

## Launch gate

Do not submit to production until:

- Auth does not lose users across app restart, account switch, token expiry, and Health Connect permission changes.
- No protected endpoint is called without a usable bearer token.
- Health Connect import writes accepted Android sample payloads.
- RevenueCat Android entitlements match backend entitlements.
- Cached dashboard/features/drivers remain visible during transient backend failures.
- Google Play Data Safety, Health Apps declaration, subscriptions, screenshots, privacy policy, and terms are complete.
