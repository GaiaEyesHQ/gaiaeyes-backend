# iOS App (Gaia Eyes)

## Location
- Source lives in `gaiaeyes-ios/ios/GaiaExporter`.
- The Xcode project path remains `gaiaeyes-ios/ios/GaiaExporter.xcodeproj` for stability, but the app display name is `Gaia Eyes`, the compact product name is `GaiaEyes`, and the bundle identifier remains `com.gaiaeyes.GaiaExporter`.

## Build/run
- See `gaiaeyes-ios/ios/README_iOS.md` for step-by-step setup, HealthKit entitlements, and local run instructions.
- Build with the shared `GaiaEyes` scheme in `gaiaeyes-ios/ios/GaiaExporter.xcodeproj`.

## Architecture
- SwiftUI app with an `AppState` ObservableObject shared across views.
- Background tasks are registered on app launch for HealthKit sync and processing.

## Networking layer
- `APIClient` handles GET/POST requests with retries, tolerance for JSON decoding, and optional CDN fallback.
- Uses `Authorization: Bearer <token>` plus `X-Dev-UserId` when available to align with backend auth.

## Auth + user identity
- Dev defaults (base URL, bearer token, user UUID) are stored in `AppState` and persisted to `UserDefaults`.
- Tokens are attached to requests as standard bearer auth.
- The Subscribe view expects a **Supabase JWT** for backend entitlement confirmation and uses RevenueCat for native iOS purchases.

## Supabase auth + RevenueCat billing
- Account auth uses Supabase email magic links and stores the Supabase session (access/refresh) in Keychain.
- iOS purchases use RevenueCat/App Store products. RevenueCat is configured with the Supabase user UUID as the app user id when the user is signed in.
- RevenueCat webhooks should point to `/v1/webhooks/revenuecat` so App Store subscription events update `public.app_user_entitlements` for backend-gated member content.
- `AuthManager` reads config from Info.plist:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `GAIA_API_BASE` (backend base for entitlement confirmation)
  - `GAIA_MAGICLINK_REDIRECT` (optional redirect URL for magic links, e.g. `gaiaeyes://auth/callback`)
  - `REVENUECAT_IOS_API_KEY`
  - `REVENUECAT_PLUS_MONTHLY_PRODUCT_ID`, `REVENUECAT_PLUS_YEARLY_PRODUCT_ID`
  - `REVENUECAT_PRO_MONTHLY_PRODUCT_ID`, `REVENUECAT_PRO_YEARLY_PRODUCT_ID`
- Supabase Auth redirect allow-list must include `gaiaeyes://auth/callback` for native sign-in completion.

## Environment/config
- API base URL and dev tokens are configured in-app via the connection settings UI.
- `MEDIA_BASE_URL` env var (optional) enables CDN fallback to JSON snapshots when the backend is unavailable.

## Dependencies (SwiftPM)
- Polar BLE SDK (6.10.0)
- RxSwift (6.5.0)
- SwiftProtobuf (1.33.3)
- Zip (2.1.2)

## Backend endpoints used by the app
- `/v1/samples/batch` for HealthKit uploads.
- `/v1/symptoms` and related symptom list endpoints.
- `/v1/features/today`, `/v1/space/forecast/*`, `/v1/space/series`, `/v1/space/visuals` (with CDN fallbacks).
- `/v1/billing/entitlements` to confirm backend subscription status (requires Supabase JWT).
