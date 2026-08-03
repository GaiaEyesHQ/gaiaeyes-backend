# Android Parity Matrix

Last reviewed: 2026-08-02

This matrix defines Android v1 parity against the live iOS app. It is intentionally scoped to a practical first Android release, not every iOS-only or future feature.

| Surface | Android v1 | Backend/API dependency | Notes |
| --- | --- | --- | --- |
| Welcome/onboarding | Required | Supabase auth, profile endpoints | Match the current iOS email magic-link/session flow, including **Continue without email** through a shared Supabase anonymous account. Let users attach an email later without changing their Supabase UUID; do not create a parallel Android identity model. |
| Health permission step | Required | Health Connect | Optional. No forced permission wall. Continue with limited body surfaces if skipped. |
| 30-day import | Required | `/v1/samples/batch` | Health Connect initial sync for the minimum useful set only. |
| Home | Required | `/v1/dashboard`, `/v1/features/today`, `/v1/users/me/drivers`, profile feed | Cache-first Home is implemented with all eight shared gauges in a compact expandable layout, tap-to-open gauge explanations, current/possible symptoms, Signals to Watch, and authenticated context-entry actions. |
| Body | Required | `/v1/features/today`, `/v1/samples/batch` | Cache-first sleep stages, efficiency, health stats, personal deltas, steps, and heart range are implemented from shared account data. Optional 30-day Health Connect import is implemented for sleep, steps, heart rate, resting heart rate, respiratory rate, and oxygen saturation, with account-scoped durable retry. HRV remains deferred under the explicit RMSSD/SDNN boundary. |
| Patterns | Required | `/v1/patterns`, `/v1/patterns/summary` | Read-only cache-first parity is implemented with a fast summary, expanded background refresh, shared confidence/evidence language, varied category accents, three-card previews, and explicit Show all/Show fewer controls. Deeper drilldowns and subscription presentation can follow. |
| Outlook | Required | `/v1/users/me/outlook`, `/v1/space/forecast/outlook` | Read-only cache-first parity is implemented with the shared daily signal cards, likely symptom domains, corrected signal labels, and responsive phone/tablet layouts. Narrative summary blocks removed from iOS remain omitted. |
| Explore / All Drivers | Required | `/v1/users/me/drivers`, profile location, `/v1/local/check` | Read-only cache-first parity is implemented from the shared ranked driver payload, including current role/state, signal strength, personal pattern context, active symptoms, and summary counts. Explore also includes a location-aware Local Weather card and detail page using the existing shared local-current payload. |
| Symptoms | Required | `/v1/symptoms/codes`, `/v1/symptoms`, `/v1/symptoms/current` | Implemented with server-driven choices, authenticated writes, and an account-scoped persistent queue with WorkManager background retry. Body and Home link to an active-symptom review page where users can mark an item ongoing, improving, worse, or resolved; edit severity/notes; or delete an accidental entry. |
| Hands-free migraine log | Required | `/v1/symptoms` | Android V1 accepts an Assistant/App Action or `gaiaeyes://log/migraine`, records the invocation time with the shared `MIGRAINE` code and default severity 5, and uses the existing persistent symptom queue. It opens Gaia Eyes for confirmation; Android does not guarantee invisible background fulfillment. |
| Exposures | Required | `/v1/exposures/catalog`, `/v1/exposures` | Implemented with the shared backend allowlist, authenticated writes, and the same persistent queue with WorkManager background retry. The catalog endpoint must be deployed before production end-to-end testing. |
| Daily check-in | Required | `/v1/feedback/daily-checkin` | Implemented with the backend-selected target day, authenticated upsert, and persistent foreground/background retry. |
| Guide | Required | bundled/app API content | Include launch welcome notice and app guidance. |
| Settings | Required | profile, auth, diagnostics | Launch slice implemented with account/sign-out, data-service and Health Connect status, pending journal/health queue counts, refresh, support/privacy/terms links, and privacy-safe diagnostics sharing. Units, guide/mode/tone, and subscription management remain follow-ups. |
| Subscribe / Restore | Required | RevenueCat Android, `/v1/billing/entitlements` | Plus monthly/yearly only for v1 unless product strategy changes. |
| Share cards | Required | local rendering + current app data | Match current iOS social share direction; no backend dependency required beyond source data. |
| Diagnostics bundle | Required | `/health`, cached local state | Initial redacted status share is implemented with app version, backend/Health Connect state, queue counts, and cache-loaded flags. It explicitly excludes email, account ID, access credentials, and raw health readings. Billing and richer support metadata remain follow-ups. |
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
- Patterns summary and expanded result.
- Drivers preview and all drivers.
- Local weather/current-conditions payload.
- User outlook.
- Symptoms current/today/daily/diag.
- Profile preferences/location/tags.
- Health Connect last upload and last sample metadata.

If a new live fetch fails, keep the previous cache and show a small stale/fallback notice rather than replacing content with an empty state.

Journal writes are persisted before the network request and drained while an
authenticated session is active, including account refresh/reconnect. A shared
mutex serializes foreground and background delivery. WorkManager retries a
failed foreground delivery once the network is connected and also runs a
15-minute safety drain; an expired or absent session does not create a retry
storm.

Health Connect access is optional and requested only from the Body page. The
initial import covers 30 days and uses the shared `/v1/samples/batch` contract
with Android/Health Connect provenance. Upload batches are account scoped,
persisted before delivery, and retried when network access returns. HRV is not
requested or uploaded in v1.

## Website parity note

No immediate website change is required for Android docs or backend contract tests. Once the Google Play listing exists, add a Google Play badge and Android-specific language to the website app landing page.
