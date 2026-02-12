# iOS App (GaiaExporter)

## Location
- Source lives in `gaiaeyes-ios/ios/GaiaExporter`.

## Build/run
- See `gaiaeyes-ios/ios/README_iOS.md` for step-by-step setup, HealthKit entitlements, and local run instructions.

## Architecture
- SwiftUI app with an `AppState` ObservableObject shared across views.
- Background tasks are registered on app launch for HealthKit sync and processing.

## Networking layer
- `APIClient` handles GET/POST requests with retries, tolerance for JSON decoding, and optional CDN fallback.
- Uses `Authorization: Bearer <token>` plus `X-Dev-UserId` when available to align with backend auth.

## Auth + user identity
- Dev defaults (base URL, bearer token, user UUID) are stored in `AppState` and persisted to `UserDefaults`.
- Tokens are attached to requests as standard bearer auth.
- The Subscribe view expects the bearer token to be a **Supabase JWT** when calling `/v1/billing/checkout`.

## Supabase auth (billing)
- The billing flow uses Supabase email magic links and stores the Supabase session (access/refresh) in Keychain.
- `AuthManager` reads config from Info.plist:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `GAIA_API_BASE` (backend base for billing calls)
  - `GAIA_BILLING_PORTAL_URL` (optional)
  - `GAIA_MAGICLINK_REDIRECT` (optional redirect URL for magic links, e.g. `gaiaeyes://login`)

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
- `/v1/billing/checkout` for Stripe Checkout (requires Supabase JWT).
- `/v1/billing/entitlements` to show current subscription status (requires Supabase JWT).
