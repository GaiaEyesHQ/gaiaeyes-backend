# Android Parity Matrix

Last reviewed: 2026-05-03

This matrix defines Android v1 parity against the live iOS app. It is intentionally scoped to a practical first Android release, not every iOS-only or future feature.

| Surface | Android v1 | Backend/API dependency | Notes |
| --- | --- | --- | --- |
| Welcome/onboarding | Required | Supabase auth, profile endpoints | Match iOS flow with anonymous start and optional account creation. |
| Health permission step | Required | Health Connect | Optional. No forced permission wall. Continue with limited body surfaces if skipped. |
| 30-day import | Required | `/v1/samples/batch` | Health Connect initial sync for the minimum useful set only. |
| Home | Required | `/v1/dashboard`, `/v1/features/today`, `/v1/users/me/drivers`, profile feed | Must preload last cached snapshot and show stale notices. |
| Body | Required | `/v1/features/today`, `/v1/samples/batch` | Sleep and health stats use Health Connect when available; cached prior data remains visible until newer data arrives. |
| Patterns | Required | `/v1/patterns`, `/v1/patterns/summary` | Read-only v1 parity is acceptable; deeper drilldowns can follow. |
| Outlook | Required | `/v1/users/me/outlook`, `/v1/space/forecast/outlook` | Match iOS card model and avoid summary blocks that were removed from iOS. |
| Explore / All Drivers | Required | `/v1/users/me/drivers`, public space/earth/local endpoints | Use existing driver payloads and signal-bar behavior. |
| Symptoms | Required | `/v1/symptoms/*` | Include queued symptom upload and retry through authenticated API client. |
| Guide | Required | bundled/app API content | Include launch welcome notice and app guidance. |
| Settings | Required | profile, auth, diagnostics | Include account, units, guide/mode/tone, privacy links, and diagnostics export. |
| Subscribe / Restore | Required | RevenueCat Android, `/v1/billing/entitlements` | Plus monthly/yearly only for v1 unless product strategy changes. |
| Share cards | Required | local rendering + current app data | Match current iOS social share direction; no backend dependency required beyond source data. |
| Diagnostics bundle | Required | `/health`, `/v1/diag/features`, cached local state | Must include auth, billing, Health Connect, cache, and queue status. |
| Push alerts | Deferred | FCM, backend notification jobs | Keep out of v1 to reduce Play review and delivery risk. |
| BLE/Polar | Deferred | BLE permissions, ingest | Not user-facing in Android v1. |
| Camera | Deferred | Camera permissions | Not user-facing in Android v1. |
| HRV | Deferred | backend type decision needed | Health Connect HRV is not equivalent to current `hrv_sdnn` assumptions. |
| Cycle tracking | Deferred | Health Connect + policy declaration | Add only after a clear user-facing need and Play declaration plan. |
| Wrist/skin temperature | Deferred | Health Connect + provider quality review | Add after Android data quality is verified. |

## Android v1 navigation

Android should keep the same mental model as iOS:

- Bottom tabs: Home, Body, Patterns, Outlook, Explore.
- Settings entry from top-right gear.
- Guide entry from Home or settings.
- Subscribe/Restore reachable from Settings and gated surfaces.
- Diagnostics reachable from Settings debug/toolkit area.

## Cache parity requirements

Android must not blank core surfaces at day rollover or during transient backend failures. These snapshots should persist by scoped user:

- Features today payload.
- Dashboard payload.
- Dashboard gauges.
- Drivers preview and all drivers.
- User outlook.
- Symptoms current/today/daily/diag.
- Profile preferences/location/tags.
- Health Connect last upload and last sample metadata.

If a new live fetch fails, keep the previous cache and show a small stale/fallback notice rather than replacing content with an empty state.

## Website parity note

No immediate website change is required for Android docs or backend contract tests. Once the Google Play listing exists, add a Google Play badge and Android-specific language to the website app landing page.
