# Codex Change Log

Document noteworthy backend/front-end changes implemented via Codex tasks. Keep the newest entries at the top.

## 2024-04-08 — Persist fallback errors without tripping the UI

- Added `diagnostics.last_error` and now clear `diagnostics.error` whenever cached/yesterday data is served successfully so existing clients stop treating fallbacks as hard failures.
- Updated the `/v1/features/today` docs and iOS follow-up checklist to consume the new field while keeping banners/debug copy informative.
- Extended the regression suite to lock in the adjusted diagnostics contract.

## 2024-04-07 — Cache fallback diagnostics

- Flag mart query failures as cache fallbacks so mobile clients throttle refreshes while still showing cached tiles.
- Ensure the diagnostics payload carries the triggering error (and pool timeout flag when relevant) when cached data is returned.
- Document the updated behavior for the iOS Codex assignee.

## 2024-04-06 — Cache fallback envelope tweaks

- Updated `/v1/features/today` to always return a populated data block (with defaults when necessary) while surfacing outage causes via `diagnostics.error`, preventing the iOS dashboard from entering a refresh loop during database timeouts.
- Added regression coverage ensuring error paths fall back to the cached snapshot and remain `ok:true`.
- Refreshed the iOS follow-up notes to call out that `ok` stays true during cache usage so the app must read the diagnostics flags.

## 2024-04-05 — Features endpoint cache hardening

- Guarded `/v1/features/today` against pgBouncer pool exhaustion by attempting a manual connection acquisition and falling back to the last-good cache snapshot when the pool is saturated.
- Extended diagnostics with `cache_fallback`, `pool_timeout`, and `error` markers so client teams can detect when cached data was served.
- Added automated tests covering the new cache fallback branch and updated docs describing the behavior.
